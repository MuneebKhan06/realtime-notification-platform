import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError

from app.core.rate_limiter import RateLimiter
from app.presence.presence_manager import PresenceManager
from app.schemas.ws_messages import (
    ErrorMessage,
    HeartbeatMessage,
    PresenceUpdateMessage,
    RateLimitedMessage,
    ReadReceiptMessage,
)
from app.websocket.heartbeat import HeartbeatHandler

logger = logging.getLogger(__name__)

ReadReceiptCallback = Callable[[UUID, str, datetime], Awaitable[None]]


class MessageRouter:
    """Dispatches parsed client WebSocket messages by their `type` field."""

    def __init__(
        self,
        heartbeat_handler: HeartbeatHandler,
        presence_manager: PresenceManager,
        rate_limiter: RateLimiter,
        on_read_receipt: ReadReceiptCallback,
    ) -> None:
        self._heartbeat_handler = heartbeat_handler
        self._presence_manager = presence_manager
        self._rate_limiter = rate_limiter
        self._on_read_receipt = on_read_receipt

    async def route(self, user_id: str, connection_id: str, raw_message: dict) -> dict | None:
        if not await self._rate_limiter.allow(connection_id):
            return RateLimitedMessage().model_dump()

        message_type = raw_message.get("type")
        try:
            if message_type == "heartbeat":
                HeartbeatMessage.model_validate(raw_message)
                await self._heartbeat_handler.handle(user_id)
                return None

            if message_type == "presence_update":
                update = PresenceUpdateMessage.model_validate(raw_message)
                if update.status == "online":
                    await self._presence_manager.mark_online(user_id)
                else:
                    await self._presence_manager.mark_away(user_id)
                return None

            if message_type == "read_receipt":
                receipt = ReadReceiptMessage.model_validate(raw_message)
                await self._on_read_receipt(receipt.notification_id, user_id, datetime.now(UTC))
                return None

            return ErrorMessage(detail=f"Unknown message type: {message_type}").model_dump()

        except ValidationError as exc:
            logger.info("Rejected malformed message from user %s: %s", user_id, exc)
            return ErrorMessage(detail="Malformed message payload").model_dump()
