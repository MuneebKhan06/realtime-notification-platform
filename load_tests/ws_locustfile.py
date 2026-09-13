"""Concurrent WebSocket connection load test.

Usage:
    locust -f load_tests/ws_locustfile.py --host=ws://localhost:8000

Each simulated user requests a ticket over the paired HTTP host, opens a
WebSocket connection, and sends a heartbeat every 15 seconds for the
duration of the run, mirroring real client behavior described in the
presence design (Decision 5 in the README).
"""

import json
import time
import uuid

import httpx
import jwt
import websockets
from locust import User, between, events, task

HTTP_HOST = "http://localhost:8000"


class WebSocketUser(User):
    wait_time = between(10, 20)

    async def on_start(self) -> None:
        self.user_id = f"load-{uuid.uuid4()}"
        self.connection = None
        await self._connect()

    async def on_stop(self) -> None:
        if self.connection is not None:
            await self.connection.close()

    async def _connect(self) -> None:
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(base_url=HTTP_HOST) as client:
                token = _fake_bearer_token(self.user_id)
                response = await client.post(
                    "/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"}
                )
                response.raise_for_status()
                ticket = response.json()["ticket"]

            self.connection = await websockets.connect(f"{self.host}/ws?ticket={ticket}")
            await self.connection.recv()  # backlog message
            events.request.fire(
                request_type="WS",
                name="connect",
                response_time=(time.perf_counter() - start) * 1000,
                response_length=0,
                exception=None,
            )
        except Exception as exc:
            events.request.fire(
                request_type="WS",
                name="connect",
                response_time=(time.perf_counter() - start) * 1000,
                response_length=0,
                exception=exc,
            )

    @task
    async def heartbeat(self) -> None:
        if self.connection is None:
            return
        start = time.perf_counter()
        try:
            await self.connection.send(json.dumps({"type": "heartbeat"}))
            events.request.fire(
                request_type="WS",
                name="heartbeat",
                response_time=(time.perf_counter() - start) * 1000,
                response_length=0,
                exception=None,
            )
        except Exception as exc:
            events.request.fire(
                request_type="WS",
                name="heartbeat",
                response_time=(time.perf_counter() - start) * 1000,
                response_length=0,
                exception=exc,
            )


def _fake_bearer_token(user_id: str) -> str:
    # Replace with a real JWT issuer call in an environment with auth enabled.
    return jwt.encode({"sub": user_id}, "change-me-in-production", algorithm="HS256")
