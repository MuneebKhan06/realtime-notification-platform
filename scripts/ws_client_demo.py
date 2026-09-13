#!/usr/bin/env python3
"""Minimal CLI WebSocket client for manually exercising the gateway.

Usage:
    curl -X POST http://localhost:8000/auth/ws-ticket -H "Authorization: Bearer $JWT"
    python scripts/ws_client_demo.py --ticket TICKET --host ws://localhost:8000
"""

import argparse
import asyncio
import json

import websockets


async def run(host: str, ticket: str) -> None:
    url = f"{host}/ws?ticket={ticket}"
    async with websockets.connect(url) as ws:
        print(f"Connected to {url}")

        async def receive_loop() -> None:
            async for raw in ws:
                message = json.loads(raw)
                print(f"<- {message}")

        async def heartbeat_loop() -> None:
            while True:
                await asyncio.sleep(15)
                await ws.send(json.dumps({"type": "heartbeat"}))

        await asyncio.gather(receive_loop(), heartbeat_loop())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Connect to the notification gateway over WebSocket"
    )
    parser.add_argument(
        "--ticket", required=True, help="Single-use ticket from POST /auth/ws-ticket"
    )
    parser.add_argument("--host", default="ws://localhost:8000", help="Gateway WebSocket base URL")
    args = parser.parse_args()

    try:
        asyncio.run(run(args.host, args.ticket))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
