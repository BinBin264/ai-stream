from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.media.render_orchestrator import DEMO_TENANT_ID, media_render_orchestrator

router = APIRouter(prefix="/api/media", tags=["media"])


class CreateRenderJobRequest(BaseModel):
    tenant_id: str = DEMO_TENANT_ID
    input_text: str
    render_profile_id: str | None = None
    live_session_id: str | None = None
    live_comment_id: str | None = None
    priority: str = "P3"


@router.get("/ai-profiles")
async def list_ai_profiles(tenant_id: str = DEMO_TENANT_ID) -> dict:
    return {"items": await media_render_orchestrator.list_ai_profiles(tenant_id)}


@router.get("/avatar-models")
async def list_avatar_models(tenant_id: str = DEMO_TENANT_ID) -> dict:
    return {"items": await media_render_orchestrator.list_avatar_models(tenant_id)}


@router.get("/render-profiles")
async def list_render_profiles(tenant_id: str = DEMO_TENANT_ID) -> dict:
    return {"items": await media_render_orchestrator.list_render_profiles(tenant_id)}


@router.get("/render-jobs")
async def list_render_jobs(tenant_id: str = DEMO_TENANT_ID, limit: int = 100) -> dict:
    return {"items": await media_render_orchestrator.list_render_jobs(tenant_id, limit)}


@router.get("/render-jobs/{job_id}")
async def get_render_job(job_id: str, tenant_id: str = DEMO_TENANT_ID) -> dict:
    try:
        job = await media_render_orchestrator.get_render_job(tenant_id, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"job": job}


@router.post("/render-jobs")
async def create_render_job(payload: CreateRenderJobRequest) -> dict:
    if not payload.input_text.strip():
        raise HTTPException(status_code=400, detail="input_text is required")
    try:
        job = await media_render_orchestrator.create_render_job(
            tenant_id=payload.tenant_id,
            input_text=payload.input_text,
            render_profile_id=payload.render_profile_id,
            live_session_id=payload.live_session_id,
            live_comment_id=payload.live_comment_id,
            priority=payload.priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"job": job}
