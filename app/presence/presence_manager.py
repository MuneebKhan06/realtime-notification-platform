from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.presence.presence_store import PresenceStore


class PresenceStatus(StrEnum):
    ONLINE = "online"
    AWAY = "away"
    OFFLINE = "offline"


@dataclass
class PresenceInfo:
    user_id: str
    status: PresenceStatus
    last_seen: datetime | None


class PresenceManager:
    """Presence state machine.

    online: heartbeat received within the TTL window.
    away: client explicitly reported backgrounded while still connected.
    offline: presence key expired or the connection was closed.

    away is layered on top of the same TTL mechanism as online, it is not a
    separate liveness signal, a connection must still be heartbeating to stay
    away rather than falling through to offline.
    """

    def __init__(self, store: PresenceStore, ttl_seconds: int) -> None:
        self._store = store
        self._ttl_seconds = ttl_seconds

    async def mark_online(self, user_id: str) -> None:
        await self._store.set_online(user_id, self._ttl_seconds)

    async def mark_away(self, user_id: str) -> None:
        await self._store.set_away(user_id, self._ttl_seconds)

    async def heartbeat(self, user_id: str) -> None:
        await self._store.refresh(user_id, self._ttl_seconds)

    async def mark_offline(self, user_id: str) -> None:
        await self._store.clear(user_id)

    async def get(self, user_id: str) -> PresenceInfo:
        status = await self._store.get_status(user_id)
        last_seen = await self._store.get_last_seen(user_id)
        return PresenceInfo(user_id=user_id, status=PresenceStatus(status), last_seen=last_seen)
