from unittest.mock import AsyncMock

from app.presence.presence_manager import PresenceManager, PresenceStatus
from app.presence.presence_store import PresenceStore
from app.pubsub.instance_registry import InstanceRegistry
from app.websocket.connection_manager import ConnectionManager
from app.websocket.heartbeat import HeartbeatHandler, InstanceLivenessLoop, ReconciliationLoop


async def test_heartbeat_refreshes_presence_and_registry_together(redis):
    presence = PresenceManager(PresenceStore(redis), ttl_seconds=30)
    registry = InstanceRegistry(redis)
    await presence.mark_online("user-1")
    await registry.register("user-1", "instance-1", ttl_seconds=30)

    handler = HeartbeatHandler(presence, registry, ttl_seconds=30)
    await handler.handle("user-1")

    info = await presence.get("user-1")
    assert info.status == PresenceStatus.ONLINE
    assert await registry.lookup("user-1") == "instance-1"


async def test_reconciliation_detects_drift(redis, caplog):
    registry = InstanceRegistry(redis)
    connections = ConnectionManager()
    connections.add("user-1", AsyncMock())
    await registry.register("user-1", "instance-2", ttl_seconds=30)

    loop = ReconciliationLoop(connections, registry, instance_id="instance-1", interval_seconds=60)

    with caplog.at_level("WARNING"):
        await loop._reconcile()

    assert "Registry drift detected" in caplog.text


async def test_reconciliation_is_quiet_when_registry_matches(redis, caplog):
    registry = InstanceRegistry(redis)
    connections = ConnectionManager()
    connections.add("user-1", AsyncMock())
    await registry.register("user-1", "instance-1", ttl_seconds=30)

    loop = ReconciliationLoop(connections, registry, instance_id="instance-1", interval_seconds=60)

    with caplog.at_level("WARNING"):
        await loop._reconcile()

    assert "Registry drift detected" not in caplog.text


async def test_liveness_loop_marks_the_instance_alive_on_start(redis):
    registry = InstanceRegistry(redis)
    loop = InstanceLivenessLoop(registry, instance_id="instance-1", ttl_seconds=15)

    await loop.start()
    try:
        assert await registry.is_alive("instance-1") is True
    finally:
        await loop.stop()


async def test_liveness_loop_stop_cancels_the_background_task(redis):
    registry = InstanceRegistry(redis)
    loop = InstanceLivenessLoop(registry, instance_id="instance-1", ttl_seconds=15)
    await loop.start()

    await loop.stop()

    assert loop._task.cancelled() or loop._task.done()
