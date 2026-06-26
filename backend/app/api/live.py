from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.models.domain import LiveStatus
from app.services.live.repository import live_session_repository
from app.services.meta.client import meta_client
from app.services.realtime import realtime_hub
from app.services.store import store
from app.services.stream.broadcaster import stream_broadcaster

router = APIRouter(prefix="/api/live", tags=["live"])


class CreateLiveRequest(BaseModel):
    title: str = "DTP AI Live"


@router.get("")
async def list_live_sessions() -> dict:
    return {"items": store.list_lives()}


@router.post("")
async def create_live_session(payload: CreateLiveRequest) -> dict:
    live = await meta_client.create_live_video(payload.title)
    store.create_live(live)
    await live_session_repository.upsert_from_domain(live)
    await realtime_hub.broadcast(live.id, {"type": "live_created", "live": live.model_dump()})
    return {"live": live}


@router.get("/{live_id}")
async def get_live_session(live_id: str) -> dict:
    live = store.get_live(live_id)
    if not live:
        raise HTTPException(status_code=404, detail="Live session not found")
    return {
        "live": live,
        "broadcaster_running": stream_broadcaster.is_running(live_id),
        "comments": store.list_comments(live_id),
        "jobs": store.list_jobs(live_id),
    }


@router.post("/{live_id}/start")
async def start_live(live_id: str) -> dict:
    live = store.get_live(live_id)
    if not live:
        raise HTTPException(status_code=404, detail="Live session not found")
    try:
        await stream_broadcaster.start(live)
        live.status = LiveStatus.PREVIEW
    except Exception as exc:
        live.status = LiveStatus.ERROR
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await realtime_hub.broadcast(live.id, {"type": "live_status", "live": live.model_dump()})
    return {"live": live}


@router.post("/{live_id}/go-live")
async def go_live(live_id: str) -> dict:
    live = store.get_live(live_id)
    if not live:
        raise HTTPException(status_code=404, detail="Live session not found")
    await meta_client.go_live(live)
    live.status = LiveStatus.LIVE
    await realtime_hub.broadcast(live.id, {"type": "live_status", "live": live.model_dump()})
    return {"live": live}


@router.post("/{live_id}/stop")
async def stop_live(live_id: str) -> dict:
    live = store.get_live(live_id)
    if not live:
        raise HTTPException(status_code=404, detail="Live session not found")
    await stream_broadcaster.stop(live)
    await meta_client.stop_live(live)
    await realtime_hub.broadcast(live.id, {"type": "live_status", "live": live.model_dump()})
    return {"live": live}


@router.delete("/{live_id}", status_code=204)
async def delete_live_session(live_id: str) -> Response:
    live = store.get_live(live_id)
    if live and live.status in {LiveStatus.PREVIEW, LiveStatus.LIVE, LiveStatus.DRAINING}:
        raise HTTPException(status_code=409, detail="Stop the live session before deleting it")
    if stream_broadcaster.is_running(live_id):
        raise HTTPException(status_code=409, detail="Stop the broadcaster before deleting this session")
    if await live_session_repository.has_active_playout(live_id):
        raise HTTPException(status_code=409, detail="Stop the playout session before deleting this live session")

    deleted = await live_session_repository.delete(live_id)
    store.delete_live(live_id)
    if not deleted and live is None:
        raise HTTPException(status_code=404, detail="Live session not found")
    await realtime_hub.broadcast(live_id, {"type": "live_deleted", "live_id": live_id})
    return Response(status_code=204)
