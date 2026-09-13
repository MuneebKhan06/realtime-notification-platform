import json
from typing import Any

from redis.asyncio import Redis


def instance_channel(instance_id: str) -> str:
    return f"channel:instance-{instance_id}"


class Publisher:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish_to_instance(self, instance_id: str, message: dict[str, Any]) -> None:
        channel = instance_channel(instance_id)
        await self._redis.publish(channel, json.dumps(message))
