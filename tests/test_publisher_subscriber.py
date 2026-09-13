import asyncio

from app.pubsub.publisher import Publisher
from app.pubsub.subscriber import Subscriber


async def test_subscriber_receives_message_published_to_its_channel(redis):
    received = []

    async def handler(message: dict) -> None:
        received.append(message)

    subscriber = Subscriber(redis, instance_id="instance-1", handler=handler)
    await subscriber.start()
    try:
        publisher = Publisher(redis)
        await publisher.publish_to_instance(
            "instance-1", {"user_id": "user-1", "notification": {"a": 1}}
        )

        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.02)
    finally:
        await subscriber.stop()

    assert received == [{"user_id": "user-1", "notification": {"a": 1}}]


async def test_subscriber_only_receives_messages_on_its_own_channel(redis):
    received = []

    async def handler(message: dict) -> None:
        received.append(message)

    subscriber = Subscriber(redis, instance_id="instance-1", handler=handler)
    await subscriber.start()
    try:
        publisher = Publisher(redis)
        await publisher.publish_to_instance("instance-2", {"user_id": "user-2", "notification": {}})

        await asyncio.sleep(0.1)
    finally:
        await subscriber.stop()

    assert received == []


async def test_malformed_message_is_discarded_without_crashing_the_loop(redis, caplog):
    received = []

    async def handler(message: dict) -> None:
        received.append(message)

    subscriber = Subscriber(redis, instance_id="instance-1", handler=handler)
    await subscriber.start()
    try:
        await redis.publish("channel:instance-instance-1", "not-json")
        publisher = Publisher(redis)
        await publisher.publish_to_instance("instance-1", {"user_id": "user-1", "notification": {}})

        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.02)
    finally:
        await subscriber.stop()

    assert received == [{"user_id": "user-1", "notification": {}}]
