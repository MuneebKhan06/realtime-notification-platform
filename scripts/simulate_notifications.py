#!/usr/bin/env python3
"""Bulk notification generator for manual load exploration.

Usage:
    python scripts/simulate_notifications.py --user-id user-123 --count 100
"""

import argparse
import asyncio
import uuid

import httpx


async def send_notifications(host: str, user_id: str, count: int, notification_type: str) -> None:
    async with httpx.AsyncClient(base_url=host) as client:
        for i in range(count):
            payload = {
                "notification_id": str(uuid.uuid4()),
                "user_id": user_id,
                "type": notification_type,
                "payload": {"index": i},
            }
            response = await client.post("/notifications", json=payload)
            response.raise_for_status()
            print(f"[{i + 1}/{count}] {response.json()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trigger a batch of notifications for a single user"
    )
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--type", default="message.received", dest="notification_type")
    parser.add_argument("--host", default="http://localhost:8000")
    args = parser.parse_args()

    asyncio.run(send_notifications(args.host, args.user_id, args.count, args.notification_type))


if __name__ == "__main__":
    main()
