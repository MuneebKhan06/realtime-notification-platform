import uuid

from app.core.idempotency import IdempotencyGuard


async def test_first_sighting_is_not_a_duplicate(redis):
    guard = IdempotencyGuard(redis)
    notification_id = uuid.uuid4()

    assert await guard.seen_recently(notification_id) is False


async def test_repeated_sighting_is_flagged_as_duplicate(redis):
    guard = IdempotencyGuard(redis)
    notification_id = uuid.uuid4()

    await guard.seen_recently(notification_id)

    assert await guard.seen_recently(notification_id) is True


async def test_different_notification_ids_are_tracked_independently(redis):
    guard = IdempotencyGuard(redis)

    await guard.seen_recently(uuid.uuid4())

    assert await guard.seen_recently(uuid.uuid4()) is False
