from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query

from app.db.connection import get_session
from app.db.repository import NotificationRepository
from app.schemas.notifications import NotificationHistoryPage, NotificationRead, ReadReceiptRead

router = APIRouter()


@router.get(
    "/notifications/history",
    response_model=NotificationHistoryPage,
    summary="Paginated notification history for a user",
)
async def get_history(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    before: datetime | None = None,
) -> NotificationHistoryPage:
    async with get_session() as session:
        repository = NotificationRepository(session)
        rows = await repository.get_history(user_id, limit, before)

    notifications = [NotificationRead.model_validate(row) for row in rows]
    next_cursor = notifications[-1].created_at if len(notifications) == limit else None

    return NotificationHistoryPage(notifications=notifications, next_cursor=next_cursor)


@router.get(
    "/notifications/{notification_id}/read-receipts",
    response_model=list[ReadReceiptRead],
    summary="Read receipt audit trail for a notification",
)
async def get_read_receipts(notification_id: UUID) -> list[ReadReceiptRead]:
    async with get_session() as session:
        repository = NotificationRepository(session)
        rows = await repository.get_read_receipts(notification_id)

    return [ReadReceiptRead.model_validate(row) for row in rows]
