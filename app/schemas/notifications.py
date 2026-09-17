import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# Matches the notification.trigger convention used throughout the API
# (message.received, benchmark.ping, ...): lowercase dotted namespaces.
NOTIFICATION_TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"

# JSONB has no practical size limit, but an unbounded payload from an
# arbitrary caller is a storage and fan-out abuse vector, so it is capped
# here rather than left to whatever Postgres or Redis will silently accept.
MAX_PAYLOAD_BYTES = 32 * 1024


class NotificationCreate(BaseModel):
    notification_id: UUID
    user_id: UUID
    type: str = Field(min_length=1, max_length=50, pattern=NOTIFICATION_TYPE_PATTERN)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def payload_within_size_limit(cls, payload: dict[str, Any]) -> dict[str, Any]:
        size = len(json.dumps(payload).encode("utf-8"))
        if size > MAX_PAYLOAD_BYTES:
            raise ValueError(f"payload exceeds the {MAX_PAYLOAD_BYTES} byte limit ({size} bytes)")
        return payload


class NotificationCreateResponse(BaseModel):
    notification_id: UUID
    persisted: bool
    delivered_live: bool


class NotificationRead(BaseModel):
    notification_id: UUID
    user_id: UUID
    type: str
    payload: dict[str, Any]
    created_at: datetime
    delivered_live: bool
    read_at: datetime | None

    model_config = {"from_attributes": True}


class NotificationHistoryPage(BaseModel):
    notifications: list[NotificationRead]
    next_cursor: datetime | None


class ReadReceiptRead(BaseModel):
    notification_id: UUID
    user_id: UUID
    read_at: datetime

    model_config = {"from_attributes": True}


class PresenceRead(BaseModel):
    user_id: str
    status: str
    last_seen: datetime | None


class HealthCheck(BaseModel):
    status: str
    instance_id: str
    redis: str
    database: str
    active_connections: int
