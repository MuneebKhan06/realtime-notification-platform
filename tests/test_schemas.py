import uuid

import pytest
from pydantic import ValidationError

from app.schemas.notifications import MAX_PAYLOAD_BYTES, NotificationCreate


def _base_payload(**overrides) -> dict:
    payload = {
        "notification_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "type": "message.received",
        "payload": {},
    }
    payload.update(overrides)
    return payload


def test_accepts_a_well_formed_dotted_type():
    notification = NotificationCreate.model_validate(_base_payload(type="message.received"))

    assert notification.type == "message.received"


@pytest.mark.parametrize(
    "bad_type",
    [
        "no_dot",
        "Message.Received",
        "message..received",
        ".leading",
        "trailing.",
        "message received",
    ],
)
def test_rejects_types_that_are_not_a_lowercase_dotted_namespace(bad_type):
    with pytest.raises(ValidationError):
        NotificationCreate.model_validate(_base_payload(type=bad_type))


def test_accepts_a_payload_at_the_size_limit():
    # Leaves room for the surrounding JSON structure so the serialized size
    # lands under the limit, not just the raw string length.
    value = "a" * (MAX_PAYLOAD_BYTES - 100)

    notification = NotificationCreate.model_validate(_base_payload(payload={"data": value}))

    assert len(notification.payload["data"]) == len(value)


def test_rejects_a_payload_over_the_size_limit():
    value = "a" * MAX_PAYLOAD_BYTES

    with pytest.raises(ValidationError, match="exceeds the"):
        NotificationCreate.model_validate(_base_payload(payload={"data": value}))
