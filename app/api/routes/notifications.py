from fastapi import APIRouter, Request

from app.core.metrics import notifications_delivered_live_total, notifications_persisted_total
from app.db.connection import get_session
from app.db.repository import NotificationRepository
from app.schemas.notifications import NotificationCreate, NotificationCreateResponse

router = APIRouter()


@router.post("/notifications", response_model=NotificationCreateResponse)
async def create_notification(
    body: NotificationCreate, request: Request
) -> NotificationCreateResponse:
    state = request.app.state

    if await state.idempotency_guard.seen_recently(body.notification_id):
        return NotificationCreateResponse(
            notification_id=body.notification_id, persisted=False, delivered_live=False
        )

    async with get_session() as session:
        repository = NotificationRepository(session)
        row = await repository.create(body.notification_id, body.user_id, body.type, body.payload)

        if row is None:
            return NotificationCreateResponse(
                notification_id=body.notification_id, persisted=False, delivered_live=False
            )

        notifications_persisted_total.inc()

        delivered_live = False
        owning_instance = await state.instance_registry.lookup(str(body.user_id))
        if owning_instance is not None:
            await state.publisher.publish_to_instance(
                owning_instance,
                {
                    "user_id": str(body.user_id),
                    "notification": {
                        "notification_id": str(row.notification_id),
                        "user_id": str(row.user_id),
                        "type": row.type,
                        "payload": row.payload,
                        "created_at": row.created_at.isoformat(),
                    },
                },
            )
            await repository.mark_delivered_live(row.notification_id)
            notifications_delivered_live_total.inc()
            delivered_live = True

    return NotificationCreateResponse(
        notification_id=body.notification_id, persisted=True, delivered_live=delivered_live
    )
