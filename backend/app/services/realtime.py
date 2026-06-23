import json
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class RealtimeHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, live_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[live_id].add(websocket)

    def disconnect(self, live_id: str, websocket: WebSocket) -> None:
        self._connections[live_id].discard(websocket)

    async def broadcast(self, live_id: str, event: dict) -> None:
        dead: list[WebSocket] = []
        message = json.dumps(event, default=str)
        for websocket in self._connections.get(live_id, set()):
            try:
                await websocket.send_text(message)
            except Exception:
                logger.warning("Dropping dead websocket connection", exc_info=True, extra={"live_id": live_id})
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(live_id, websocket)


realtime_hub = RealtimeHub()
