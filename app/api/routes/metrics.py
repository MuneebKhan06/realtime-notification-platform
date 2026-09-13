from fastapi import APIRouter, Response

from app.core.metrics import render_latest

router = APIRouter()


@router.get("/metrics")
async def metrics() -> Response:
    body, content_type = render_latest()
    return Response(content=body, media_type=content_type)
