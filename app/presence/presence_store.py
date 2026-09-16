from datetime import datetime, timezone

from redis.asyncio import Redis


def presence_key(user_id: str) -> str:
    return f"presence:{user_id}"


def last_seen_key(user_id: str) -> str:
    return f"presence:last_seen:{user_id}"


class PresenceStore:
    """TTL-based presence storage in Redis.

    A present key means online (or away); expiry is the offline signal, so
    there is no server-side polling loop needed to detect a dead connection.
    last_seen is tracked separately without a TTL so it survives past offline.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def set_online(self, user_id: str, ttl_seconds: int) -> None:
        await self._redis.set(presence_key(user_id), "online", ex=ttl_seconds)
        await self._touch_last_seen(user_id)

    async def set_away(self, user_id: str, ttl_seconds: int) -> None:
        await self._redis.set(presence_key(user_id), "away", ex=ttl_seconds)
        await self._touch_last_seen(user_id)

    async def refresh(self, user_id: str, ttl_seconds: int) -> None:
        await self._redis.expire(presence_key(user_id), ttl_seconds)
        await self._touch_last_seen(user_id)

    async def clear(self, user_id: str) -> None:
        await self._redis.delete(presence_key(user_id))

    async def get_status(self, user_id: str) -> str:
        value = await self._redis.get(presence_key(user_id))
        if value is None:
            return "offline"
        return value.decode() if isinstance(value, bytes) else str(value)

    async def get_last_seen(self, user_id: str) -> datetime | None:
        value = await self._redis.get(last_seen_key(user_id))
        if value is None:
            return None
        raw = value.decode() if isinstance(value, bytes) else value
        return datetime.fromisoformat(raw)

    async def _touch_last_seen(self, user_id: str) -> None:
        await self._redis.set(last_seen_key(user_id), datetime.now(timezone.utc).isoformat())
