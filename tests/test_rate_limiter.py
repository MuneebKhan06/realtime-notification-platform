from app.core.rate_limiter import RateLimiter


async def test_requests_within_the_limit_are_allowed(redis):
    limiter = RateLimiter(redis, limit=5, window_seconds=10)

    for _ in range(5):
        assert await limiter.allow("connection-1") is True


async def test_requests_beyond_the_limit_are_rejected(redis):
    limiter = RateLimiter(redis, limit=3, window_seconds=10)

    for _ in range(3):
        assert await limiter.allow("connection-1") is True

    assert await limiter.allow("connection-1") is False


async def test_limits_are_tracked_independently_per_connection(redis):
    limiter = RateLimiter(redis, limit=1, window_seconds=10)

    assert await limiter.allow("connection-1") is True
    assert await limiter.allow("connection-2") is True
    assert await limiter.allow("connection-1") is False


async def test_window_reset_allows_further_requests(redis):
    limiter = RateLimiter(redis, limit=1, window_seconds=10)
    await limiter.allow("connection-1")

    await redis.delete("rate_limit:connection-1")

    assert await limiter.allow("connection-1") is True
