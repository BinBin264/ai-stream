from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.playout_segment import PlayoutPriority, PlayoutSegmentStatus
from app.models.playout_session import PlayoutOutputMode, PlayoutSessionStatus


class CreatePlayoutSessionRequest(BaseModel):
    avatar_id: str = "model_01"
    live_session_id: str | None = None
    output_mode: PlayoutOutputMode = "local_preview"


class PlayoutSessionResponse(BaseModel):
    session_id: str
    avatar_id: str
    live_session_id: str | None = None
    status: PlayoutSessionStatus
    output_mode: PlayoutOutputMode
    idle_video_path: str
    output_path: str | None = None
    active_segment_id: str | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class PlayoutSessionListResponse(BaseModel):
    items: list[PlayoutSessionResponse]


class StopPlayoutSessionRequest(BaseModel):
    force: bool = False


class PlayoutStatusResponse(BaseModel):
    session_id: str
    status: PlayoutSessionStatus


class SubmitPlayoutScriptRequest(BaseModel):
    text: str = Field(min_length=1)
    priority: PlayoutPriority = "P2"
    voice_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class SubmitPlayoutScriptResponse(BaseModel):
    render_job_id: str
    playout_segment_id: str | None
    status: str
    message: str


class EnqueueTalkingSegmentRequest(BaseModel):
    source_video_path: str
    priority: PlayoutPriority = "P2"
    idempotency_key: str | None = Field(default=None, max_length=128)


class PlayoutSegmentResponse(BaseModel):
    segment_id: str
    playout_session_id: str
    avatar_render_job_id: str | None = None
    source_video_path: str | None = None
    segment_type: Literal["talking"]
    priority: PlayoutPriority
    status: PlayoutSegmentStatus
    queue_position: int
    requested_at: datetime
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class PlayoutSegmentListResponse(BaseModel):
    items: list[PlayoutSegmentResponse]


class PlayoutHealthResponse(BaseModel):
    session_id: str
    status: PlayoutSessionStatus
    runtime_alive: bool
    active_segment_id: str | None = None
    queued_segments: int = 0
    last_heartbeat_at: datetime | None = None
    last_output_update_at: datetime | None = None
    last_error_code: str | None = None

