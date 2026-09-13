import secrets

from redis.asyncio import Redis


def ticket_key(ticket: str) -> str:
    return f"ws_ticket:{ticket}"


class WSTicketAuth:
    """Single-use WebSocket connection ticket exchange.

    A client authenticates over regular HTTPS with its Bearer JWT and
    receives a short-lived random ticket. The WebSocket upgrade then carries
    only that opaque ticket, never the JWT itself, so a leaked access log or
    proxy log never exposes a reusable credential.
    """

    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def issue_ticket(self, user_id: str) -> str:
        ticket = secrets.token_urlsafe(32)
        await self._redis.set(ticket_key(ticket), user_id, ex=self._ttl_seconds)
        return ticket

    async def redeem_ticket(self, ticket: str) -> str | None:
        """Atomically fetch and delete the ticket so it cannot be replayed."""
        user_id = await self._redis.getdel(ticket_key(ticket))
        if user_id is None:
            return None
        return user_id.decode() if isinstance(user_id, bytes) else user_id
