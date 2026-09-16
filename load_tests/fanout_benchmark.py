#!/usr/bin/env python3
"""Measures cross-instance delivery latency.

Connects a receiving client to one gateway instance, triggers notifications
through another instance's REST API, and times how long delivery takes over
the Redis Pub/Sub fan-out path end to end.

Usage:
    python load_tests/fanout_benchmark.py --iterations 200 \
        --trigger-host http://localhost:8000 --recv-host ws://localhost:8000
"""

import argparse
import asyncio
import json
import statistics
import time
import uuid

import httpx
import jwt
import websockets


async def get_ticket(http_host: str, user_id: str) -> str:
    token = jwt.encode({"sub": user_id}, "change-me-in-production", algorithm="HS256")
    async with httpx.AsyncClient(base_url=http_host) as client:
        response = await client.post(
            "/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        return response.json()["ticket"]


async def run_benchmark(trigger_host: str, recv_host: str, iterations: int) -> list[float]:
    user_id = str(uuid.uuid4())
    ticket = await get_ticket(
        recv_host.replace("ws://", "http://").replace("wss://", "https://"), user_id
    )

    latencies: list[float] = []
    async with websockets.connect(f"{recv_host}/ws?ticket={ticket}") as ws:
        await ws.recv()  # initial backlog message

        async with httpx.AsyncClient(base_url=trigger_host) as client:
            for _ in range(iterations):
                notification_id = str(uuid.uuid4())
                sent_at = time.perf_counter()
                response = await client.post(
                    "/notifications",
                    json={
                        "notification_id": notification_id,
                        "user_id": user_id,
                        "type": "benchmark.ping",
                        "payload": {},
                    },
                )
                response.raise_for_status()

                message = json.loads(await ws.recv())
                received_at = time.perf_counter()
                assert message["notification"]["notification_id"] == notification_id

                latencies.append((received_at - sent_at) * 1000)

    return latencies


def print_summary(latencies: list[float]) -> None:
    sorted_latencies = sorted(latencies)
    print(f"Samples: {len(sorted_latencies)}")
    print(f"P50: {statistics.median(sorted_latencies):.2f} ms")
    print(f"P95: {sorted_latencies[int(len(sorted_latencies) * 0.95)]:.2f} ms")
    print(f"P99: {sorted_latencies[int(len(sorted_latencies) * 0.99)]:.2f} ms")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark cross-instance notification delivery latency"
    )
    parser.add_argument("--trigger-host", default="http://localhost:8000")
    parser.add_argument("--recv-host", default="ws://localhost:8000")
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()

    latencies = asyncio.run(run_benchmark(args.trigger_host, args.recv_host, args.iterations))
    print_summary(latencies)


if __name__ == "__main__":
    main()
