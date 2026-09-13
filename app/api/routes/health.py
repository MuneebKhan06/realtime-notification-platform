from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db.connection import get_session
from app.schemas.notifications import HealthCheck

router = APIRouter()


@router.get("/health", response_model=HealthCheck)
async def health_check(request: Request) -> HealthCheck:
    state = request.app.state

    redis_status = "connected"
    try:
        await state.redis.ping()
    except Exception:
        redis_status = "unavailable"

    database_status = "connected"
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"

    return HealthCheck(
        status="healthy"
        if redis_status == "connected" and database_status == "connected"
        else "degraded",
        instance_id=state.settings.instance_id,
        redis=redis_status,
        database=database_status,
        active_connections=state.connection_manager.active_connection_count,
    )
