import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes import auth, health, history, metrics, notifications, presence
from app.config import Settings
from app.core.idempotency import IdempotencyGuard
from app.core.rate_limiter import RateLimiter
from app.presence.presence_manager import PresenceManager
from app.presence.presence_store import PresenceStore
from app.pubsub.instance_registry import InstanceRegistry
from app.pubsub.publisher import Publisher
from app.websocket.auth_handshake import WSTicketAuth
from app.websocket.connection_manager import ConnectionManager


@pytest.fixture
def settings() -> Settings:
    return Settings(instance_id="instance-1", jwt_secret_key="test-secret", jwt_algorithm="HS256")


@pytest.fixture
def app(redis, settings) -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.include_router(auth.router)
    fastapi_app.include_router(notifications.router)
    fastapi_app.include_router(presence.router)
    fastapi_app.include_router(history.router)
    fastapi_app.include_router(health.router)
    fastapi_app.include_router(metrics.router)

    fastapi_app.state.settings = settings
    fastapi_app.state.redis = redis
    fastapi_app.state.connection_manager = ConnectionManager()
    fastapi_app.state.instance_registry = InstanceRegistry(redis)
    fastapi_app.state.presence_manager = PresenceManager(
        PresenceStore(redis), settings.presence_ttl_seconds
    )
    fastapi_app.state.ticket_auth = WSTicketAuth(redis, settings.ws_ticket_ttl_seconds)
    fastapi_app.state.publisher = Publisher(redis)
    fastapi_app.state.idempotency_guard = IdempotencyGuard(redis)
    fastapi_app.state.api_rate_limiter = RateLimiter(
        redis, settings.api_rate_limit_requests, settings.api_rate_limit_window_seconds
    )

    return fastapi_app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


def _fake_session_scope():
    @asynccontextmanager
    async def _scope():
        yield AsyncMock()

    return _scope


async def test_health_check_reports_redis_and_instance_id(client, monkeypatch):
    monkeypatch.setattr(health, "get_session", _fake_session_scope())

    response = await client.get("/health")

    body = response.json()
    assert response.status_code == 200
    assert body["instance_id"] == "instance-1"
    assert body["redis"] == "connected"
    assert body["active_connections"] == 0


async def test_health_check_reports_unavailable_when_redis_is_slow(client, app, monkeypatch):
    monkeypatch.setattr(health, "get_session", _fake_session_scope())
    app.state.settings.health_check_timeout_seconds = 0.01

    async def slow_ping():
        await asyncio.sleep(1)

    monkeypatch.setattr(app.state.redis, "ping", slow_ping)

    response = await client.get("/health")

    body = response.json()
    assert response.status_code == 200
    assert body["redis"] == "unavailable"
    assert body["status"] == "degraded"


async def test_metrics_endpoint_returns_prometheus_text(client):
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "notification_gateway_active_connections" in response.text


async def test_get_presence_defaults_to_offline(client):
    response = await client.get("/presence/user-42")

    body = response.json()
    assert response.status_code == 200
    assert body == {"user_id": "user-42", "status": "offline", "last_seen": None}


async def test_ws_ticket_issued_for_a_valid_bearer_token(client, settings):
    token = jwt.encode(
        {"sub": str(uuid.uuid4())}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )

    response = await client.post("/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"})

    body = response.json()
    assert response.status_code == 200
    assert body["expires_in"] == settings.ws_ticket_ttl_seconds
    assert len(body["ticket"]) > 0


async def test_ws_ticket_rejects_invalid_token(client):
    response = await client.post(
        "/auth/ws-ticket", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401


async def test_ws_ticket_rejects_a_non_uuid_subject_claim(client, settings):
    token = jwt.encode(
        {"sub": "not-a-uuid"}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )

    response = await client.post("/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_ws_ticket_requires_authorization_header(client):
    response = await client.post("/auth/ws-ticket")

    assert response.status_code in (401, 403)


async def test_create_notification_persists_and_reports_no_live_recipient(client, monkeypatch):
    row = AsyncMock()
    row.notification_id = uuid.uuid4()
    row.user_id = uuid.uuid4()
    row.type = "message.received"
    row.payload = {"from": "Ayesha"}
    row.created_at = datetime.now(timezone.utc)

    fake_repository = AsyncMock()
    fake_repository.create.return_value = row

    monkeypatch.setattr(notifications, "get_session", _fake_session_scope())
    monkeypatch.setattr(notifications, "NotificationRepository", lambda session: fake_repository)

    response = await client.post(
        "/notifications",
        json={
            "notification_id": str(row.notification_id),
            "user_id": str(row.user_id),
            "type": "message.received",
            "payload": {"from": "Ayesha"},
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["persisted"] is True
    assert body["delivered_live"] is False
    fake_repository.mark_delivered_live.assert_not_awaited()


async def test_create_notification_delivers_live_to_a_registered_and_alive_instance(
    client, app, monkeypatch
):
    row = AsyncMock()
    row.notification_id = uuid.uuid4()
    row.user_id = uuid.uuid4()
    row.type = "message.received"
    row.payload = {}
    row.created_at = datetime.now(timezone.utc)

    fake_repository = AsyncMock()
    fake_repository.create.return_value = row

    monkeypatch.setattr(notifications, "get_session", _fake_session_scope())
    monkeypatch.setattr(notifications, "NotificationRepository", lambda session: fake_repository)

    await app.state.instance_registry.register(str(row.user_id), "instance-2", ttl_seconds=30)
    await app.state.instance_registry.mark_alive("instance-2", ttl_seconds=15)

    response = await client.post(
        "/notifications",
        json={
            "notification_id": str(row.notification_id),
            "user_id": str(row.user_id),
            "type": "message.received",
            "payload": {},
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["delivered_live"] is True
    fake_repository.mark_delivered_live.assert_awaited_once_with(row.notification_id)


async def test_create_notification_skips_delivery_to_a_registered_but_dead_instance(
    client, app, monkeypatch
):
    row = AsyncMock()
    row.notification_id = uuid.uuid4()
    row.user_id = uuid.uuid4()
    row.type = "message.received"
    row.payload = {}
    row.created_at = datetime.now(timezone.utc)

    fake_repository = AsyncMock()
    fake_repository.create.return_value = row

    monkeypatch.setattr(notifications, "get_session", _fake_session_scope())
    monkeypatch.setattr(notifications, "NotificationRepository", lambda session: fake_repository)

    # Registered but never marked alive, simulating a crashed instance whose
    # registry entries have not yet expired.
    await app.state.instance_registry.register(str(row.user_id), "instance-2", ttl_seconds=30)

    response = await client.post(
        "/notifications",
        json={
            "notification_id": str(row.notification_id),
            "user_id": str(row.user_id),
            "type": "message.received",
            "payload": {},
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["delivered_live"] is False
    fake_repository.mark_delivered_live.assert_not_awaited()


async def test_create_notification_is_idempotent_for_duplicate_ids(client, app):
    notification_id = str(uuid.uuid4())
    await app.state.idempotency_guard.seen_recently(uuid.UUID(notification_id))

    response = await client.post(
        "/notifications",
        json={
            "notification_id": notification_id,
            "user_id": str(uuid.uuid4()),
            "type": "message.received",
            "payload": {},
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["persisted"] is False
    assert body["delivered_live"] is False


async def test_create_notification_is_rate_limited_per_caller(client, app, monkeypatch):
    app.state.api_rate_limiter = RateLimiter(app.state.redis, limit=1, window_seconds=10)

    fake_repository = AsyncMock()
    fake_repository.create.return_value = None
    monkeypatch.setattr(notifications, "get_session", _fake_session_scope())
    monkeypatch.setattr(notifications, "NotificationRepository", lambda session: fake_repository)

    payload = {
        "notification_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "type": "message.received",
        "payload": {},
    }

    first = await client.post("/notifications", json=payload)
    second = await client.post(
        "/notifications", json={**payload, "notification_id": str(uuid.uuid4())}
    )

    assert first.status_code == 200
    assert second.status_code == 429


async def test_get_history_returns_notifications_for_user(client, monkeypatch):
    row = AsyncMock()
    row.notification_id = uuid.uuid4()
    row.user_id = uuid.uuid4()
    row.type = "message.received"
    row.payload = {}
    row.created_at = datetime.now(timezone.utc)
    row.delivered_live = True
    row.read_at = None

    fake_repository = AsyncMock()
    fake_repository.get_history.return_value = [row]

    monkeypatch.setattr(history, "get_session", _fake_session_scope())
    monkeypatch.setattr(history, "NotificationRepository", lambda session: fake_repository)

    response = await client.get(
        "/notifications/history", params={"user_id": str(row.user_id), "limit": 50}
    )

    body = response.json()
    assert response.status_code == 200
    assert len(body["notifications"]) == 1
    assert body["notifications"][0]["notification_id"] == str(row.notification_id)
    assert body["next_cursor"] is None


async def test_get_history_sets_next_cursor_when_a_full_page_is_returned(client, monkeypatch):
    rows = []
    for _ in range(2):
        row = AsyncMock()
        row.notification_id = uuid.uuid4()
        row.user_id = uuid.uuid4()
        row.type = "message.received"
        row.payload = {}
        row.created_at = datetime.now(timezone.utc)
        row.delivered_live = True
        row.read_at = None
        rows.append(row)

    fake_repository = AsyncMock()
    fake_repository.get_history.return_value = rows

    monkeypatch.setattr(history, "get_session", _fake_session_scope())
    monkeypatch.setattr(history, "NotificationRepository", lambda session: fake_repository)

    response = await client.get(
        "/notifications/history", params={"user_id": str(uuid.uuid4()), "limit": 2}
    )

    body = response.json()
    assert response.status_code == 200
    assert len(body["notifications"]) == 2
    next_cursor = datetime.fromisoformat(body["next_cursor"].replace("Z", "+00:00"))
    assert next_cursor == rows[-1].created_at


async def test_get_history_forwards_the_before_cursor_and_limit(client, monkeypatch):
    user_id = uuid.uuid4()
    before = datetime(2026, 1, 1, tzinfo=timezone.utc)

    fake_repository = AsyncMock()
    fake_repository.get_history.return_value = []

    monkeypatch.setattr(history, "get_session", _fake_session_scope())
    monkeypatch.setattr(history, "NotificationRepository", lambda session: fake_repository)

    response = await client.get(
        "/notifications/history",
        params={"user_id": str(user_id), "limit": 10, "before": before.isoformat()},
    )

    assert response.status_code == 200
    fake_repository.get_history.assert_awaited_once_with(user_id, 10, before)


async def test_get_history_rejects_a_limit_above_the_maximum(client):
    response = await client.get(
        "/notifications/history", params={"user_id": str(uuid.uuid4()), "limit": 500}
    )

    assert response.status_code == 422


async def test_get_read_receipts_returns_the_audit_trail(client, monkeypatch):
    notification_id = uuid.uuid4()
    receipt = AsyncMock()
    receipt.notification_id = notification_id
    receipt.user_id = uuid.uuid4()
    receipt.read_at = datetime.now(timezone.utc)

    fake_repository = AsyncMock()
    fake_repository.get_read_receipts.return_value = [receipt]

    monkeypatch.setattr(history, "get_session", _fake_session_scope())
    monkeypatch.setattr(history, "NotificationRepository", lambda session: fake_repository)

    response = await client.get(f"/notifications/{notification_id}/read-receipts")

    body = response.json()
    assert response.status_code == 200
    assert len(body) == 1
    assert body[0]["notification_id"] == str(notification_id)
    assert body[0]["user_id"] == str(receipt.user_id)
    fake_repository.get_read_receipts.assert_awaited_once_with(notification_id)


async def test_get_read_receipts_returns_an_empty_list_when_unread(client, monkeypatch):
    fake_repository = AsyncMock()
    fake_repository.get_read_receipts.return_value = []

    monkeypatch.setattr(history, "get_session", _fake_session_scope())
    monkeypatch.setattr(history, "NotificationRepository", lambda session: fake_repository)

    response = await client.get(f"/notifications/{uuid.uuid4()}/read-receipts")

    assert response.status_code == 200
    assert response.json() == []
