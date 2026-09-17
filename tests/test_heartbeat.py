import asyncio
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


async def test_reconciliation_loop_stop_before_start_is_a_no_op(redis):
    registry = InstanceRegistry(redis)
    connections = ConnectionManager()
    loop = ReconciliationLoop(connections, registry, instance_id="instance-1", interval_seconds=60)

    await loop.stop()  # never started, must not raise


async def test_reconciliation_loop_runs_periodically_until_stopped(redis):
    registry = InstanceRegistry(redis)
    connections = ConnectionManager()
    loop = ReconciliationLoop(
        connections, registry, instance_id="instance-1", interval_seconds=0.01
    )
    loop._reconcile = AsyncMock()

    loop.start()
    await asyncio.sleep(0.05)
    await loop.stop()

    assert loop._reconcile.await_count >= 2
    assert loop._task.cancelled() or loop._task.done()


async def test_reconciliation_loop_survives_a_failed_pass(redis, caplog):
    registry = InstanceRegistry(redis)
    connections = ConnectionManager()
    loop = ReconciliationLoop(
        connections, registry, instance_id="instance-1", interval_seconds=0.01
    )
    loop._reconcile = AsyncMock(side_effect=[RuntimeError("boom"), None, None])

    with caplog.at_level("ERROR"):
        loop.start()
        await asyncio.sleep(0.05)
        await loop.stop()

    assert loop._reconcile.await_count >= 2
    assert "Reconciliation pass failed" in caplog.text


async def test_liveness_loop_marks_the_instance_alive_on_start(redis):
    registry = InstanceRegistry(redis)
    loop = InstanceLivenessLoop(registry, instance_id="instance-1", ttl_seconds=15)

    await loop.start()
    try:
        assert await registry.is_alive("instance-1") is True
    finally:
        await loop.stop()


async def test_liveness_loop_refreshes_periodically_until_stopped(redis):
    registry = InstanceRegistry(redis)
    loop = InstanceLivenessLoop(registry, instance_id="instance-1", ttl_seconds=15)
    loop._interval_seconds = 0.01
    loop._registry.mark_alive = AsyncMock()

    await loop.start()
    await asyncio.sleep(0.05)
    await loop.stop()

    # once from start() plus at least two periodic refreshes
    assert loop._registry.mark_alive.await_count >= 3
    assert loop._task.cancelled() or loop._task.done()


async def test_liveness_loop_survives_a_failed_refresh(redis, caplog):
    registry = InstanceRegistry(redis)
    loop = InstanceLivenessLoop(registry, instance_id="instance-1", ttl_seconds=15)
    loop._interval_seconds = 0.01
    loop._registry.mark_alive = AsyncMock(side_effect=[None, RuntimeError("boom"), None, None])

    with caplog.at_level("ERROR"):
        await loop.start()
        await asyncio.sleep(0.05)
        await loop.stop()

    assert loop._registry.mark_alive.await_count >= 3
    assert "Failed to refresh liveness key" in caplog.text


async def test_liveness_loop_stop_cancels_the_background_task(redis):
    registry = InstanceRegistry(redis)
    loop = InstanceLivenessLoop(registry, instance_id="instance-1", ttl_seconds=15)
    await loop.start()

    await loop.stop()

    assert loop._task.cancelled() or loop._task.done()
