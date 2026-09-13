from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class HeartbeatMessage(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"


class PresenceUpdateMessage(BaseModel):
    type: Literal["presence_update"] = "presence_update"
    status: Literal["online", "away"]


class ReadReceiptMessage(BaseModel):
    type: Literal["read_receipt"] = "read_receipt"
    notification_id: UUID


class NotificationEnvelope(BaseModel):
    notification_id: UUID
    user_id: UUID
    type: str
    payload: dict[str, Any]
    created_at: datetime


class NotificationMessage(BaseModel):
    type: Literal["notification"] = "notification"
    notification: NotificationEnvelope


class BacklogMessage(BaseModel):
    type: Literal["backlog"] = "backlog"
    notifications: list[NotificationEnvelope]


class RateLimitedMessage(BaseModel):
    type: Literal["rate_limited"] = "rate_limited"
    detail: str = "Message rate limit exceeded, message dropped"


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    detail: str
