import logging

from fastapi import WebSocket

from app.core.metrics import active_connections

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks the WebSocket connections held by this gateway instance.

    Only local state, this is deliberately not shared across instances. The
    Redis instance registry is what makes a connection reachable from other
    instances, this class is just where the live socket objects live.
    """

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    def add(self, user_id: str, websocket: WebSocket) -> None:
        self._connections[user_id] = websocket
        active_connections.set(len(self._connections))

    def remove(self, user_id: str) -> None:
        self._connections.pop(user_id, None)
        active_connections.set(len(self._connections))

    def get(self, user_id: str) -> WebSocket | None:
        return self._connections.get(user_id)

    def is_connected(self, user_id: str) -> bool:
        return user_id in self._connections

    def connected_user_ids(self) -> list[str]:
        return list(self._connections.keys())

    @property
    def active_connection_count(self) -> int:
        return len(self._connections)

    async def send_json(self, user_id: str, message: dict) -> bool:
        """Send a message to a locally connected user. Returns False if not connected here."""
        websocket = self._connections.get(user_id)
        if websocket is None:
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            logger.exception("Failed to deliver message to user %s, dropping connection", user_id)
            self.remove(user_id)
            return False
