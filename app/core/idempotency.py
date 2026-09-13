import uuid

from redis.asyncio import Redis


def dedup_key(notification_id: uuid.UUID) -> str:
    return f"notification_dedup:{notification_id}"


class IdempotencyGuard:
    """Fast, non-authoritative duplicate check ahead of the PostgreSQL write.

    The unique constraint on notification_id is the real guarantee, this
    guard only saves a round trip to Postgres for the common case of a
    retried request arriving within a short window of the original.
    """

    def __init__(self, redis: Redis, ttl_seconds: int = 300) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def seen_recently(self, notification_id: uuid.UUID) -> bool:
        was_set = await self._redis.set(
            dedup_key(notification_id), "1", ex=self._ttl_seconds, nx=True
        )
        return not was_set
