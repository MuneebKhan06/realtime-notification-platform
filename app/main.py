import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.routes import auth, health, history, metrics, notifications, presence
from app.config import get_settings
from app.core.idempotency import IdempotencyGuard
from app.core.logging_config import configure_logging
from app.core.metrics import delivery_latency_seconds, read_receipts_recorded_total
from app.core.rate_limiter import RateLimiter
from app.db.connection import dispose_engine, get_session
from app.db.repository import NotificationRepository
from app.presence.presence_manager import PresenceManager
from app.presence.presence_store import PresenceStore
from app.pubsub.instance_registry import InstanceRegistry
from app.pubsub.publisher import Publisher
from app.pubsub.subscriber import MessageHandler, Subscriber
from app.websocket.auth_handshake import WSTicketAuth
from app.websocket.connection_manager import ConnectionManager
from app.websocket.gateway import router as gateway_router
from app.websocket.heartbeat import HeartbeatHandler, InstanceLivenessLoop, ReconciliationLoop
from app.websocket.message_router import MessageRouter

configure_logging(get_settings().log_level, get_settings().instance_id)
logger = logging.getLogger(__name__)


async def _mark_read(notification_id: UUID, user_id: str, read_at: datetime) -> None:
    async with get_session() as session:
        repository = NotificationRepository(session)
        await repository.mark_read(notification_id, UUID(user_id), read_at)
    read_receipts_recorded_total.inc()


def _make_local_delivery_handler(connection_manager: ConnectionManager) -> MessageHandler:
    async def deliver(payload: dict) -> None:
        user_id = payload["user_id"]
        delivered = await connection_manager.send_json(
            user_id, {"type": "notification", "notification": payload["notification"]}
        )

        published_at = payload.get("published_at")
        if delivered and published_at is not None:
            delivery_latency_seconds.observe(time.time() - published_at)

    return deliver


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)

    connection_manager = ConnectionManager()
    instance_registry = InstanceRegistry(redis)
    presence_manager = PresenceManager(PresenceStore(redis), settings.presence_ttl_seconds)
    ticket_auth = WSTicketAuth(redis, settings.ws_ticket_ttl_seconds)
    rate_limiter = RateLimiter(
        redis, settings.rate_limit_messages, settings.rate_limit_window_seconds
    )
    api_rate_limiter = RateLimiter(
        redis, settings.api_rate_limit_requests, settings.api_rate_limit_window_seconds
    )
    publisher = Publisher(redis)
    idempotency_guard = IdempotencyGuard(redis)
    heartbeat_handler = HeartbeatHandler(
        presence_manager, instance_registry, settings.presence_ttl_seconds
    )
    message_router = MessageRouter(heartbeat_handler, presence_manager, rate_limiter, _mark_read)

    subscriber = Subscriber(
        redis, settings.instance_id, _make_local_delivery_handler(connection_manager)
    )
    reconciliation_loop = ReconciliationLoop(
        connection_manager,
        instance_registry,
        settings.instance_id,
        settings.heartbeat_interval_seconds * 2,
    )
    liveness_loop = InstanceLivenessLoop(
        instance_registry, settings.instance_id, settings.instance_liveness_ttl_seconds
    )

    app.state.settings = settings
    app.state.redis = redis
    app.state.connection_manager = connection_manager
    app.state.instance_registry = instance_registry
    app.state.presence_manager = presence_manager
    app.state.ticket_auth = ticket_auth
    app.state.rate_limiter = rate_limiter
    app.state.api_rate_limiter = api_rate_limiter
    app.state.publisher = publisher
    app.state.idempotency_guard = idempotency_guard
    app.state.message_router = message_router

    await subscriber.start()
    reconciliation_loop.start()
    await liveness_loop.start()
    logger.info("Gateway instance %s ready", settings.instance_id)

    try:
        yield
    finally:
        disconnected_user_ids = await connection_manager.close_all(
            code=1001, reason="Server shutting down"
        )
        for user_id in disconnected_user_ids:
            await instance_registry.unregister(user_id)
            await presence_manager.mark_offline(user_id)

        await liveness_loop.stop()
        await reconciliation_loop.stop()
        await subscriber.stop()
        await redis.aclose()
        await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(title="Real-Time Notification & Presence Platform", lifespan=lifespan)

    app.include_router(gateway_router)
    app.include_router(auth.router)
    app.include_router(notifications.router)
    app.include_router(presence.router)
    app.include_router(history.router)
    app.include_router(health.router)
    app.include_router(metrics.router)

    return app


app = create_app()
