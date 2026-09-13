import asyncio
import logging

from app.presence.presence_manager import PresenceManager
from app.pubsub.instance_registry import InstanceRegistry
from app.websocket.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


class HeartbeatHandler:
    """Refreshes presence and the instance registry entry on each client heartbeat.

    Both TTLs are refreshed together because a stale registry entry with a
    live presence key (or vice versa) is exactly the inconsistency the
    reconciliation loop below exists to catch.
    """

    def __init__(self, presence: PresenceManager, registry: InstanceRegistry, ttl_seconds: int) -> None:
        self._presence = presence
        self._registry = registry
        self._ttl_seconds = ttl_seconds

    async def handle(self, user_id: str) -> None:
        await self._presence.heartbeat(user_id)
        await self._registry.refresh(user_id, self._ttl_seconds)


class ReconciliationLoop:
    """Periodic safety net against missed Redis keyspace expiry notifications.

    Redis keyspace notifications are documented as at-most-once under a
    Redis restart, so a periodic sweep re-derives truth from this instance's
    actual open connections rather than trusting notifications alone.
    """

    def __init__(
        self,
        connections: ConnectionManager,
        registry: InstanceRegistry,
        instance_id: str,
        interval_seconds: int,
    ) -> None:
        self._connections = connections
        self._registry = registry
        self._instance_id = instance_id
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            try:
                await self._reconcile()
            except Exception:
                logger.exception("Reconciliation pass failed on instance %s", self._instance_id)

    async def _reconcile(self) -> None:
        for user_id in self._connections.connected_user_ids():
            owner = await self._registry.lookup(user_id)
            if owner != self._instance_id:
                logger.warning(
                    "Registry drift detected for user %s, expected %s, found %s",
                    user_id,
                    self._instance_id,
                    owner,
                )
