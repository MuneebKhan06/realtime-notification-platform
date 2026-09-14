from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, create_autospec

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.presence.presence_manager import PresenceManager
from app.pubsub.instance_registry import InstanceRegistry
from app.websocket import gateway
from app.websocket.auth_handshake import WSTicketAuth
from app.websocket.connection_manager import ConnectionManager
from app.websocket.message_router import MessageRouter

TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"


def _fake_session_scope():
    @asynccontextmanager
    async def _scope():
        yield AsyncMock()

    return _scope


@pytest.fixture
def app(monkeypatch):
    fastapi_app = FastAPI()
    fastapi_app.include_router(gateway.router)

    fastapi_app.state.settings = Settings(
        instance_id="instance-1", presence_ttl_seconds=30, backlog_limit=100
    )
    fastapi_app.state.ticket_auth = create_autospec(WSTicketAuth, instance=True)
    fastapi_app.state.connection_manager = create_autospec(ConnectionManager, instance=True)
    fastapi_app.state.instance_registry = create_autospec(InstanceRegistry, instance=True)
    fastapi_app.state.presence_manager = create_autospec(PresenceManager, instance=True)
    fastapi_app.state.message_router = create_autospec(MessageRouter, instance=True)

    monkeypatch.setattr(gateway, "get_session", _fake_session_scope())

    fake_repository = AsyncMock()
    fake_repository.get_unread_backlog.return_value = []
    monkeypatch.setattr(gateway, "NotificationRepository", lambda session: fake_repository)

    return fastapi_app


def test_invalid_ticket_is_rejected_before_accept(app):
    app.state.ticket_auth.redeem_ticket.return_value = None
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?ticket=bad-ticket"):
            pass

    app.state.connection_manager.add.assert_not_called()


def test_valid_ticket_registers_the_connection_and_sends_backlog(app):
    app.state.ticket_auth.redeem_ticket.return_value = TEST_USER_ID
    client = TestClient(app)

    with client.websocket_connect("/ws?ticket=good-ticket") as websocket:
        backlog = websocket.receive_json()
        assert backlog == {"type": "backlog", "notifications": []}

    app.state.connection_manager.add.assert_called_once()
    assert app.state.connection_manager.add.call_args.args[0] == TEST_USER_ID
    app.state.instance_registry.register.assert_awaited_once_with(TEST_USER_ID, "instance-1", 30)
    app.state.presence_manager.mark_online.assert_awaited_once_with(TEST_USER_ID)


def test_client_message_is_routed_and_response_sent_back(app):
    app.state.ticket_auth.redeem_ticket.return_value = TEST_USER_ID
    app.state.message_router.route.return_value = {
        "type": "error",
        "detail": "Unknown message type: bogus",
    }
    client = TestClient(app)

    with client.websocket_connect("/ws?ticket=good-ticket") as websocket:
        websocket.receive_json()  # backlog
        websocket.send_json({"type": "bogus"})
        response = websocket.receive_json()

    assert response == {"type": "error", "detail": "Unknown message type: bogus"}


def test_disconnect_cleans_up_registry_and_presence(app):
    app.state.ticket_auth.redeem_ticket.return_value = TEST_USER_ID
    client = TestClient(app)

    with client.websocket_connect("/ws?ticket=good-ticket") as websocket:
        websocket.receive_json()  # backlog

    app.state.connection_manager.remove.assert_called_once_with(TEST_USER_ID)
    app.state.instance_registry.unregister.assert_awaited_once_with(TEST_USER_ID)
    app.state.presence_manager.mark_offline.assert_awaited_once_with(TEST_USER_ID)
