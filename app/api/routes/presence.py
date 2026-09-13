from fastapi import APIRouter, Request

from app.schemas.notifications import PresenceRead

router = APIRouter()


@router.get("/presence/{user_id}", response_model=PresenceRead)
async def get_presence(user_id: str, request: Request) -> PresenceRead:
    presence_manager = request.app.state.presence_manager
    info = await presence_manager.get(user_id)
    return PresenceRead(user_id=info.user_id, status=info.status.value, last_seen=info.last_seen)
