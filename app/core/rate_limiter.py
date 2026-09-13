from redis.asyncio import Redis

# Token bucket, evaluated atomically in Lua so concurrent messages on the same
# connection cannot race past the limit between a read and a write.
_TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local count = redis.call("INCR", key)
if count == 1 then
    redis.call("EXPIRE", key, window)
end

if count > limit then
    return 0
end
return 1
"""


def rate_limit_key(connection_id: str) -> str:
    return f"rate_limit:{connection_id}"


class RateLimiter:
    """Per-connection token bucket, applied to inbound WebSocket messages.

    A connection exceeding the limit has individual messages dropped with a
    rate_limited frame, the connection itself is never closed for this.
    """

    def __init__(self, redis: Redis, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self._limit = limit
        self._window_seconds = window_seconds
        self._script = redis.register_script(_TOKEN_BUCKET_SCRIPT)

    async def allow(self, connection_id: str) -> bool:
        result = await self._script(
            keys=[rate_limit_key(connection_id)],
            args=[self._limit, self._window_seconds],
        )
        return bool(result)
