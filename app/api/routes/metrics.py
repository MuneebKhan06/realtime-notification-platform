from fastapi import APIRouter, Response

from app.core.metrics import render_latest

router = APIRouter()


@router.get("/metrics", summary="Prometheus metrics in exposition format")
async def metrics() -> Response:
    body, content_type = render_latest()
    return Response(content=body, media_type=content_type)
