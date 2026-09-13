import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db.connection import get_session
from app.db.repository import NotificationRepository
from app.schemas.ws_messages import BacklogMessage, NotificationEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, ticket: str) -> None:
    state = websocket.app.state

    user_id = await state.ticket_auth.redeem_ticket(ticket)
    if user_id is None:
        await websocket.close(code=1008, reason="Invalid or expired ticket")
        return

    await websocket.accept()
    connection_id = str(uuid.uuid4())

    state.connection_manager.add(user_id, websocket)
    await state.instance_registry.register(user_id, state.settings.instance_id, state.settings.presence_ttl_seconds)
    await state.presence_manager.mark_online(user_id)

    try:
        await _send_backlog(websocket, user_id, state.settings.backlog_limit)

        while True:
            raw_message = await websocket.receive_json()
            response = await state.message_router.route(user_id, connection_id, raw_message)
            if response is not None:
                await websocket.send_json(response)

    except WebSocketDisconnect:
        logger.info("User %s disconnected from instance %s", user_id, state.settings.instance_id)
    finally:
        state.connection_manager.remove(user_id)
        await state.instance_registry.unregister(user_id)
        await state.presence_manager.mark_offline(user_id)


async def _send_backlog(websocket: WebSocket, user_id: str, limit: int) -> None:
    async with get_session() as session:
        repository = NotificationRepository(session)
        backlog = await repository.get_unread_backlog(uuid.UUID(user_id), limit)

    message = BacklogMessage(
        notifications=[
            NotificationEnvelope(
                notification_id=row.notification_id,
                user_id=row.user_id,
                type=row.type,
                payload=row.payload,
                created_at=row.created_at,
            )
            for row in backlog
        ]
    )
    await websocket.send_json(message.model_dump(mode="json"))
