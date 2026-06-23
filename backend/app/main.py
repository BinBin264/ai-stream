from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    avatar_renders,
    avatars,
    comments,
    conversations,
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
from app.services.realtime import realtime_hub

app = FastAPI(title="DTP AI Stream API", version="0.1.0")

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


@app.websocket("/ws/live/{live_id}")
async def live_ws(websocket: WebSocket, live_id: str) -> None:
    await realtime_hub.connect(live_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        realtime_hub.disconnect(live_id, websocket)
