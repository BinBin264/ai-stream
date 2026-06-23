from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.avatar_render import (
    AvatarRenderJobResponse,
    CancelAvatarRenderJobResponse,
    CreateAvatarRenderRequest,
    ListAvatarRenderJobsResponse,
)
from app.services.avatar.avatar_render_service import avatar_render_service
from app.services.avatar.render_job_repository import RenderJobNotFoundError

router = APIRouter(prefix="/api/avatar-renders", tags=["avatar-renders"])


def _to_response(job: dict) -> AvatarRenderJobResponse:
    return AvatarRenderJobResponse(
        job_id=str(job["id"]),
        status=job["status"],
        avatar_id=job["avatar_id"],
        input_text=job["input_text"],
        voice_id=job.get("voice_id"),
        language=job.get("language", "vi"),
        audio_path=job.get("audio_path"),
        video_path=job.get("video_path"),
        audio_duration_seconds=job.get("audio_duration_seconds"),
        render_duration_seconds=job.get("render_duration_seconds"),
        error_code=job.get("error_code"),
        error_message=job.get("error_message"),
        retry_count=job.get("retry_count", 0),
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        completed_at=job.get("completed_at"),
    )


@router.post("", response_model=AvatarRenderJobResponse, status_code=202)
async def create_avatar_render(body: CreateAvatarRenderRequest):
    """Submit a new avatar render job. Returns 202 Accepted with the queued job."""
    try:
        job = await avatar_render_service.submit(
            avatar_id=body.avatar_id,
            input_text=body.input_text,
            voice_id=body.voice_id,
            language=body.language,
            live_session_id=body.live_session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(job)


@router.get("", response_model=ListAvatarRenderJobsResponse)
async def list_avatar_renders(
    status: str | None = Query(default=None, description="Filter by job status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List avatar render jobs for the default tenant."""
    jobs, total = await avatar_render_service.list(
        limit=limit, offset=offset, status=status
    )
    return ListAvatarRenderJobsResponse(
        jobs=[_to_response(j) for j in jobs],
        total=total,
    )


@router.get("/{job_id}", response_model=AvatarRenderJobResponse)
async def get_avatar_render(job_id: str):
    """Get a single avatar render job by ID."""
    try:
        job = await avatar_render_service.get(job_id)
    except RenderJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(job)


@router.delete("/{job_id}", response_model=CancelAvatarRenderJobResponse)
async def cancel_avatar_render(job_id: str):
    """Cancel a queued or in-progress avatar render job."""
    try:
        job = await avatar_render_service.cancel(job_id)
    except RenderJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CancelAvatarRenderJobResponse(
        job_id=str(job["id"]),
        status=job["status"],
        message="Job cancelled",
    )
