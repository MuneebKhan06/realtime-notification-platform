from unittest.mock import AsyncMock

from app.websocket.connection_manager import ConnectionManager


def make_fake_websocket() -> AsyncMock:
    return AsyncMock()


def test_add_and_get_connection():
    manager = ConnectionManager()
    websocket = make_fake_websocket()

    manager.add("user-1", websocket)

    assert manager.get("user-1") is websocket
    assert manager.is_connected("user-1") is True
    assert manager.active_connection_count == 1


def test_remove_connection():
    manager = ConnectionManager()
    manager.add("user-1", make_fake_websocket())

    manager.remove("user-1")

    assert manager.get("user-1") is None
    assert manager.is_connected("user-1") is False
    assert manager.active_connection_count == 0


def test_remove_unknown_user_is_a_no_op():
    manager = ConnectionManager()

    manager.remove("does-not-exist")

    assert manager.active_connection_count == 0


def test_connected_user_ids():
    manager = ConnectionManager()
    manager.add("user-1", make_fake_websocket())
    manager.add("user-2", make_fake_websocket())

    assert sorted(manager.connected_user_ids()) == ["user-1", "user-2"]


async def test_send_json_delivers_to_connected_user():
    manager = ConnectionManager()
    websocket = make_fake_websocket()
    manager.add("user-1", websocket)

    delivered = await manager.send_json("user-1", {"type": "notification"})

    assert delivered is True
    websocket.send_json.assert_awaited_once_with({"type": "notification"})


async def test_send_json_returns_false_for_unknown_user():
    manager = ConnectionManager()

    delivered = await manager.send_json("ghost", {"type": "notification"})

    assert delivered is False


async def test_send_json_drops_connection_on_send_failure():
    manager = ConnectionManager()
    websocket = make_fake_websocket()
    websocket.send_json.side_effect = RuntimeError("connection reset")
    manager.add("user-1", websocket)

    delivered = await manager.send_json("user-1", {"type": "notification"})

    assert delivered is False
    assert manager.is_connected("user-1") is False


async def test_close_all_closes_every_connection_with_the_given_code_and_reason():
    manager = ConnectionManager()
    websocket_a = make_fake_websocket()
    websocket_b = make_fake_websocket()
    manager.add("user-1", websocket_a)
    manager.add("user-2", websocket_b)

    closed_user_ids = await manager.close_all(code=1001, reason="Server shutting down")

    assert sorted(closed_user_ids) == ["user-1", "user-2"]
    websocket_a.close.assert_awaited_once_with(code=1001, reason="Server shutting down")
    websocket_b.close.assert_awaited_once_with(code=1001, reason="Server shutting down")
    assert manager.active_connection_count == 0


async def test_close_all_continues_past_a_failed_close():
    manager = ConnectionManager()
    failing_websocket = make_fake_websocket()
    failing_websocket.close.side_effect = RuntimeError("already gone")
    healthy_websocket = make_fake_websocket()
    manager.add("user-1", failing_websocket)
    manager.add("user-2", healthy_websocket)

    closed_user_ids = await manager.close_all(code=1001, reason="Server shutting down")

    assert sorted(closed_user_ids) == ["user-1", "user-2"]
    healthy_websocket.close.assert_awaited_once()
    assert manager.active_connection_count == 0


async def test_close_all_on_an_empty_manager_is_a_no_op():
    manager = ConnectionManager()

    closed_user_ids = await manager.close_all(code=1001, reason="Server shutting down")

    assert closed_user_ids == []
