import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app import main


def _fake_session_scope():
    @asynccontextmanager
    async def _scope():
        yield AsyncMock()

    return _scope


async def test_mark_read_forwards_notification_user_and_timestamp_to_the_repository(monkeypatch):
    fake_repository = AsyncMock()
    monkeypatch.setattr(main, "get_session", _fake_session_scope())
    monkeypatch.setattr(main, "NotificationRepository", lambda session: fake_repository)

    notification_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    read_at = datetime.now(timezone.utc)

    await main._mark_read(notification_id, user_id, read_at)

    fake_repository.mark_read.assert_awaited_once_with(notification_id, uuid.UUID(user_id), read_at)


async def test_local_delivery_handler_pushes_to_the_matching_local_connection():
    connection_manager = AsyncMock()
    deliver = main._make_local_delivery_handler(connection_manager)
    notification = {"notification_id": "n1", "type": "message.received", "payload": {}}

    await deliver({"user_id": "user-1", "notification": notification})

    connection_manager.send_json.assert_awaited_once_with(
        "user-1", {"type": "notification", "notification": notification}
    )
