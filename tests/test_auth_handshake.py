from app.websocket.auth_handshake import WSTicketAuth


async def test_issued_ticket_redeems_to_the_correct_user(redis):
    auth = WSTicketAuth(redis, ttl_seconds=10)

    ticket = await auth.issue_ticket("user-123")
    user_id = await auth.redeem_ticket(ticket)

    assert user_id == "user-123"


async def test_ticket_is_single_use(redis):
    auth = WSTicketAuth(redis, ttl_seconds=10)
    ticket = await auth.issue_ticket("user-123")

    first = await auth.redeem_ticket(ticket)
    second = await auth.redeem_ticket(ticket)

    assert first == "user-123"
    assert second is None


async def test_unknown_ticket_is_rejected(redis):
    auth = WSTicketAuth(redis, ttl_seconds=10)

    user_id = await auth.redeem_ticket("never-issued")

    assert user_id is None


async def test_expired_ticket_is_rejected(redis):
    auth = WSTicketAuth(redis, ttl_seconds=1)
    ticket = await auth.issue_ticket("user-123")

    await redis.delete(f"ws_ticket:{ticket}")
    user_id = await auth.redeem_ticket(ticket)

    assert user_id is None
