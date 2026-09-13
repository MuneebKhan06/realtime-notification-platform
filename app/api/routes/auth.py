import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

router = APIRouter()

_bearer_scheme = HTTPBearer()


class WSTicketResponse(BaseModel):
    ticket: str
    expires_in: int


def decode_user_id(request: Request, credentials: HTTPAuthorizationCredentials) -> str:
    settings = request.app.state.settings
    try:
        claims = jwt.decode(
            credentials.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject claim"
        )
    return user_id


@router.post("/auth/ws-ticket", response_model=WSTicketResponse)
async def issue_ws_ticket(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> WSTicketResponse:
    user_id = decode_user_id(request, credentials)
    settings = request.app.state.settings
    ticket = await request.app.state.ticket_auth.issue_ticket(user_id)
    return WSTicketResponse(ticket=ticket, expires_in=settings.ws_ticket_ttl_seconds)
