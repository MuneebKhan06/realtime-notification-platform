import uuid

from app.core.idempotency import IdempotencyGuard


async def test_unseen_notification_is_not_a_duplicate(redis):
    guard = IdempotencyGuard(redis)
    notification_id = uuid.uuid4()

    assert await guard.has_seen(notification_id) is False


async def test_marking_seen_makes_it_a_duplicate(redis):
    guard = IdempotencyGuard(redis)
    notification_id = uuid.uuid4()

    await guard.mark_seen(notification_id)

    assert await guard.has_seen(notification_id) is True


async def test_different_notification_ids_are_tracked_independently(redis):
    guard = IdempotencyGuard(redis)

    await guard.mark_seen(uuid.uuid4())

    assert await guard.has_seen(uuid.uuid4()) is False


async def test_has_seen_does_not_itself_mark_the_notification(redis):
    """A read-only check must not have the side effect of reserving the id.

    This is the fix for a data-loss window: if marking happened on the
    check itself, a DB write that failed after the check would leave the
    notification permanently unable to be retried within the TTL, even
    though nothing was ever persisted.
    """
    guard = IdempotencyGuard(redis)
    notification_id = uuid.uuid4()

    await guard.has_seen(notification_id)

    assert await guard.has_seen(notification_id) is False
