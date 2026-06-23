from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RenderJobStatus = Literal[
    "queued",
    "generating_audio",
    "rendering",
    "downloading",
    "completed",
    "failed",
    "cancelled",
]


class CreateAvatarRenderRequest(BaseModel):
    avatar_id: str
    input_text: str = Field(..., max_length=350)
    voice_id: str | None = None
    language: str = "vi"
    live_session_id: str | None = None


class AvatarRenderJobResponse(BaseModel):
    job_id: str
    status: RenderJobStatus
    avatar_id: str
    input_text: str
    voice_id: str | None = None
    language: str
    audio_path: str | None = None
    video_path: str | None = None
    audio_duration_seconds: float | None = None
    render_duration_seconds: float | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class ListAvatarRenderJobsResponse(BaseModel):
    jobs: list[AvatarRenderJobResponse]
    total: int


class CancelAvatarRenderJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
