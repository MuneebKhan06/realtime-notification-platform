from redis.asyncio import Redis


def registry_key(user_id: str) -> str:
    return f"user:{user_id}"


class InstanceRegistry:
    """Maps a connected user to the gateway instance holding their live socket.

    Entries carry a TTL matching the presence window and are refreshed on
    every heartbeat, so an ungracefully dropped connection self-expires
    instead of leaving a permanently stale mapping.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def register(self, user_id: str, instance_id: str, ttl_seconds: int) -> None:
        await self._redis.set(registry_key(user_id), instance_id, ex=ttl_seconds)

    async def refresh(self, user_id: str, ttl_seconds: int) -> None:
        await self._redis.expire(registry_key(user_id), ttl_seconds)

    async def unregister(self, user_id: str) -> None:
        await self._redis.delete(registry_key(user_id))

    async def lookup(self, user_id: str) -> str | None:
        instance_id = await self._redis.get(registry_key(user_id))
        if instance_id is None:
            return None
        return instance_id.decode() if isinstance(instance_id, bytes) else instance_id
