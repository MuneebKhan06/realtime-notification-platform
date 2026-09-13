from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationCreate(BaseModel):
    notification_id: UUID
    user_id: UUID
    type: str = Field(min_length=1, max_length=50)
    payload: dict[str, Any] = Field(default_factory=dict)


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
