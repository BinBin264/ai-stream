import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.api import (
    avatar_renders,
    avatars,
    comments,
    conversations,
    dynamic_playout,
    facebook,
    health,
    inventory,
    live,
    live_session_products,
    live_sessions,
    media,
    ops,
    orders,
    playout_programs,
    products,
)
from app.core.config import settings
from app.services.realtime import realtime_hub

logger = logging.getLogger(__name__)


class LocalMediaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        if path.endswith(".m3u8"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _restore_live_sessions()
    yield


async def _restore_live_sessions() -> None:
    try:
        from app.core.database import db_connection
        from app.models.domain import LiveSession, LiveStatus
        from app.services.store import store

        async with db_connection() as conn:
            rows = await conn.fetch(
                "SELECT id, tenant_id, external_live_video_id, title, status, "
                "media_provider, settings_json, created_at, updated_at "
                "FROM live_sessions ORDER BY created_at ASC"
            )
        for row in rows:
            row = dict(row)
            live = LiveSession(
                id=str(row["id"]),
                tenant_id=str(row["tenant_id"]),
                title=row["title"],
                status=LiveStatus(row["status"]) if row["status"] else LiveStatus.DRAFT,
                external_live_video_id=row.get("external_live_video_id"),
                media_provider=row.get("media_provider") or "ffmpeg",
                settings_json=json.loads(row["settings_json"]) if isinstance(row["settings_json"], str) else (row["settings_json"] or {}),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            store.live_sessions[live.id] = live
        logger.info("Restored %d live session(s) from DB", len(rows))
    except Exception as exc:
        logger.warning("Could not restore live sessions from DB: %s", exc)


app = FastAPI(title="DTP AI Stream API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(avatars.router)
app.include_router(avatar_renders.router)
app.include_router(dynamic_playout.router)
app.include_router(live.router)
app.include_router(live_sessions.router)
app.include_router(live_session_products.router)
app.include_router(facebook.router)
app.include_router(comments.router)
app.include_router(products.router)
app.include_router(media.router)
app.include_router(inventory.router)
app.include_router(orders.router)
app.include_router(conversations.router)
app.include_router(ops.router)
app.include_router(playout_programs.router)

if settings.SERVE_LOCAL_MEDIA:
    media_root = Path(settings.MEDIA_OUTPUT_DIR).resolve()
    try:
        media_root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    app.mount("/media", LocalMediaStaticFiles(directory=str(media_root), check_dir=False), name="local-media")


@app.websocket("/ws/live/{live_id}")
async def live_ws(websocket: WebSocket, live_id: str) -> None:
    await realtime_hub.connect(live_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        realtime_hub.disconnect(live_id, websocket)
