import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis

from app.pubsub.publisher import instance_channel

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class Subscriber:
    """Subscribes a single gateway instance to its own targeted Pub/Sub channel.

    Each instance only listens on channel:instance-{id}, so a notification for
    a locally connected user is the only traffic this instance ever receives.
    """

    def __init__(self, redis: Redis, instance_id: str, handler: MessageHandler) -> None:
        self._redis = redis
        self._instance_id = instance_id
        self._handler = handler
        self._task: asyncio.Task | None = None
        self._pubsub = None

    async def start(self) -> None:
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(instance_channel(self._instance_id))
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._pubsub is not None:
            await self._pubsub.aclose()

    async def _listen(self) -> None:
        assert self._pubsub is not None
        async for message in self._pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                payload = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "Discarding malformed pubsub message on instance %s", self._instance_id
                )
                continue
            try:
                await self._handler(payload)
            except Exception:
                logger.exception(
                    "Handler failed for pubsub message on instance %s", self._instance_id
                )
