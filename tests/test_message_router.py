from unittest.mock import AsyncMock

from app.core.rate_limiter import RateLimiter
from app.websocket.message_router import MessageRouter


def make_router(redis, on_read_receipt=None) -> tuple[MessageRouter, AsyncMock, AsyncMock]:
    heartbeat_handler = AsyncMock()
    presence_manager = AsyncMock()
    rate_limiter = RateLimiter(redis, limit=50, window_seconds=10)
    router = MessageRouter(
        heartbeat_handler,
        presence_manager,
        rate_limiter,
        on_read_receipt or AsyncMock(),
    )
    return router, heartbeat_handler, presence_manager


async def test_heartbeat_message_is_routed_to_the_heartbeat_handler(redis):
    router, heartbeat_handler, _ = make_router(redis)

    response = await router.route("user-1", "conn-1", {"type": "heartbeat"})

    assert response is None
    heartbeat_handler.handle.assert_awaited_once_with("user-1")


async def test_presence_update_online_marks_user_online(redis):
    router, _, presence_manager = make_router(redis)

    response = await router.route(
        "user-1", "conn-1", {"type": "presence_update", "status": "online"}
    )

    assert response is None
    presence_manager.mark_online.assert_awaited_once_with("user-1")
    presence_manager.mark_away.assert_not_awaited()


async def test_presence_update_away_marks_user_away(redis):
    router, _, presence_manager = make_router(redis)

    response = await router.route("user-1", "conn-1", {"type": "presence_update", "status": "away"})

    assert response is None
    presence_manager.mark_away.assert_awaited_once_with("user-1")
    presence_manager.mark_online.assert_not_awaited()


async def test_read_receipt_invokes_the_callback_with_notification_id_and_user(redis):
    on_read_receipt = AsyncMock()
    router, _, _ = make_router(redis, on_read_receipt=on_read_receipt)
    notification_id = "550e8400-e29b-41d4-a716-446655440000"

    response = await router.route(
        "user-1", "conn-1", {"type": "read_receipt", "notification_id": notification_id}
    )

    assert response is None
    on_read_receipt.assert_awaited_once()
    called_notification_id, called_user_id, _read_at = on_read_receipt.call_args.args
    assert str(called_notification_id) == notification_id
    assert called_user_id == "user-1"


async def test_unknown_message_type_returns_an_error_frame(redis):
    router, _, _ = make_router(redis)

    response = await router.route("user-1", "conn-1", {"type": "not_a_real_type"})

    assert response == {"type": "error", "detail": "Unknown message type: not_a_real_type"}


async def test_malformed_payload_returns_an_error_frame_without_crashing(redis):
    router, _, _ = make_router(redis)

    response = await router.route(
        "user-1", "conn-1", {"type": "presence_update", "status": "asleep"}
    )

    assert response == {"type": "error", "detail": "Malformed message payload"}


async def test_messages_beyond_the_rate_limit_are_dropped(redis):
    heartbeat_handler = AsyncMock()
    presence_manager = AsyncMock()
    rate_limiter = RateLimiter(redis, limit=1, window_seconds=10)
    router = MessageRouter(heartbeat_handler, presence_manager, rate_limiter, AsyncMock())

    first = await router.route("user-1", "conn-1", {"type": "heartbeat"})
    second = await router.route("user-1", "conn-1", {"type": "heartbeat"})

    assert first is None
    assert second == {
        "type": "rate_limited",
        "detail": "Message rate limit exceeded, message dropped",
    }
    heartbeat_handler.handle.assert_awaited_once()
