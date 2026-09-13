from app.pubsub.instance_registry import InstanceRegistry


async def test_register_and_lookup(redis):
    registry = InstanceRegistry(redis)

    await registry.register("user-1", "instance-2", ttl_seconds=30)

    assert await registry.lookup("user-1") == "instance-2"


async def test_lookup_returns_none_for_unregistered_user(redis):
    registry = InstanceRegistry(redis)

    assert await registry.lookup("user-unknown") is None


async def test_unregister_removes_the_mapping(redis):
    registry = InstanceRegistry(redis)
    await registry.register("user-1", "instance-1", ttl_seconds=30)

    await registry.unregister("user-1")

    assert await registry.lookup("user-1") is None


async def test_reconnect_to_a_different_instance_updates_the_mapping(redis):
    registry = InstanceRegistry(redis)
    await registry.register("user-1", "instance-1", ttl_seconds=30)

    await registry.register("user-1", "instance-2", ttl_seconds=30)

    assert await registry.lookup("user-1") == "instance-2"


async def test_refresh_extends_the_ttl_without_changing_the_owner(redis):
    registry = InstanceRegistry(redis)
    await registry.register("user-1", "instance-1", ttl_seconds=30)

    await registry.refresh("user-1", ttl_seconds=60)

    assert await registry.lookup("user-1") == "instance-1"
    ttl = await redis.ttl("user:user-1")
    assert ttl > 30
