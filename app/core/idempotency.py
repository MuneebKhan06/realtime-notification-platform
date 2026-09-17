import uuid

from redis.asyncio import Redis


def dedup_key(notification_id: uuid.UUID) -> str:
    return f"notification_dedup:{notification_id}"


class IdempotencyGuard:
    """Fast, non-authoritative duplicate check ahead of the PostgreSQL write.

    The unique constraint on notification_id is the real guarantee, this
    guard only saves a round trip to Postgres for the common case of a
    retried request arriving within a short window of the original.

    has_seen and mark_seen are deliberately separate calls rather than one
    atomic check-and-set: the caller must only mark_seen after Postgres has
    confirmed the notification_id's actual state (either a fresh insert or
    a unique-constraint conflict). Marking it seen any earlier, e.g. before
    attempting the DB write, would mean a failed or slow write leaves a
    false "seen" flag in Redis, silently rejecting legitimate retries for
    a notification that was never actually persisted.
    """

    def __init__(self, redis: Redis, ttl_seconds: int = 300) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def has_seen(self, notification_id: uuid.UUID) -> bool:
        value = await self._redis.get(dedup_key(notification_id))
        return value is not None

    async def mark_seen(self, notification_id: uuid.UUID) -> None:
        await self._redis.set(dedup_key(notification_id), "1", ex=self._ttl_seconds)
