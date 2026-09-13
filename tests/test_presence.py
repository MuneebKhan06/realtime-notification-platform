from app.presence.presence_manager import PresenceManager, PresenceStatus
from app.presence.presence_store import PresenceStore


async def test_new_user_is_offline_by_default(redis):
    manager = PresenceManager(PresenceStore(redis), ttl_seconds=30)

    info = await manager.get("user-1")

    assert info.status == PresenceStatus.OFFLINE
    assert info.last_seen is None


async def test_mark_online_sets_status_and_last_seen(redis):
    manager = PresenceManager(PresenceStore(redis), ttl_seconds=30)

    await manager.mark_online("user-1")
    info = await manager.get("user-1")

    assert info.status == PresenceStatus.ONLINE
    assert info.last_seen is not None


async def test_mark_away_requires_still_connected_semantics(redis):
    manager = PresenceManager(PresenceStore(redis), ttl_seconds=30)

    await manager.mark_online("user-1")
    await manager.mark_away("user-1")
    info = await manager.get("user-1")

    assert info.status == PresenceStatus.AWAY


async def test_heartbeat_refreshes_ttl_without_changing_status(redis):
    manager = PresenceManager(PresenceStore(redis), ttl_seconds=30)
    await manager.mark_online("user-1")

    await manager.heartbeat("user-1")
    info = await manager.get("user-1")

    assert info.status == PresenceStatus.ONLINE
    ttl = await redis.ttl("presence:user-1")
    assert ttl > 0


async def test_mark_offline_clears_status_but_keeps_last_seen(redis):
    manager = PresenceManager(PresenceStore(redis), ttl_seconds=30)
    await manager.mark_online("user-1")

    await manager.mark_offline("user-1")
    info = await manager.get("user-1")

    assert info.status == PresenceStatus.OFFLINE
    assert info.last_seen is not None


async def test_ttl_expiry_is_treated_as_offline(redis):
    manager = PresenceManager(PresenceStore(redis), ttl_seconds=30)
    await manager.mark_online("user-1")

    await redis.delete("presence:user-1")
    info = await manager.get("user-1")

    assert info.status == PresenceStatus.OFFLINE
