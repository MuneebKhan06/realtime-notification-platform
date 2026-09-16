"""Two-instance end-to-end delivery test.

Requires the stack from docker-compose.test.yml to be running:

    docker-compose -f docker-compose.test.yml up -d --build
    pytest tests/test_integration.py -m integration
    docker-compose -f docker-compose.test.yml down -v

This is the test that actually proves the architecture: user A connects to
instance-1, user B connects to instance-2, a notification triggered for B
through instance-1's REST API arrives on B's socket, which instance-1 never
holds a direct connection to.
"""

import json
import uuid

import httpx
import jwt
import pytest
import websockets

pytestmark = pytest.mark.integration

INSTANCE_1_HTTP = "http://localhost:8001"
INSTANCE_2_HTTP = "http://localhost:8002"
INSTANCE_1_WS = "ws://localhost:8001"
INSTANCE_2_WS = "ws://localhost:8002"
JWT_SECRET = "integration-test-secret"


def _bearer_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id}, JWT_SECRET, algorithm="HS256")


async def _get_ticket(http_base_url: str, user_id: str) -> str:
    async with httpx.AsyncClient(base_url=http_base_url) as client:
        response = await client.post(
            "/auth/ws-ticket", headers={"Authorization": f"Bearer {_bearer_token(user_id)}"}
        )
        response.raise_for_status()
        return response.json()["ticket"]


async def test_notification_reaches_recipient_connected_to_a_different_instance():
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())

    ticket_a = await _get_ticket(INSTANCE_1_HTTP, user_a)
    ticket_b = await _get_ticket(INSTANCE_2_HTTP, user_b)

    async with websockets.connect(f"{INSTANCE_1_WS}/ws?ticket={ticket_a}") as ws_a:
        await ws_a.recv()  # initial backlog message

        async with websockets.connect(f"{INSTANCE_2_WS}/ws?ticket={ticket_b}") as ws_b:
            await ws_b.recv()  # initial backlog message

            notification_id = str(uuid.uuid4())
            async with httpx.AsyncClient(base_url=INSTANCE_1_HTTP) as client:
                response = await client.post(
                    "/notifications",
                    json={
                        "notification_id": notification_id,
                        "user_id": user_b,
                        "type": "message.received",
                        "payload": {"from": "Ayesha"},
                    },
                )
                response.raise_for_status()
                assert response.json()["delivered_live"] is True

            delivered = json.loads(await ws_b.recv())
            assert delivered["type"] == "notification"
            assert delivered["notification"]["notification_id"] == notification_id
            assert delivered["notification"]["payload"]["from"] == "Ayesha"


async def test_offline_recipient_gets_backlog_on_reconnect():
    user_id = str(uuid.uuid4())
    notification_id = str(uuid.uuid4())

    async with httpx.AsyncClient(base_url=INSTANCE_1_HTTP) as client:
        response = await client.post(
            "/notifications",
            json={
                "notification_id": notification_id,
                "user_id": user_id,
                "type": "message.received",
                "payload": {"from": "Bilal"},
            },
        )
        response.raise_for_status()
        assert response.json()["delivered_live"] is False

    ticket = await _get_ticket(INSTANCE_2_HTTP, user_id)
    async with websockets.connect(f"{INSTANCE_2_WS}/ws?ticket={ticket}") as ws:
        backlog = json.loads(await ws.recv())
        assert backlog["type"] == "backlog"
        notification_ids = [n["notification_id"] for n in backlog["notifications"]]
        assert notification_id in notification_ids
