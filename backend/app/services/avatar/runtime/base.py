from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel


class RuntimeHealth(BaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    message: str = ""


class RenderRequest(BaseModel):
    job_id: str
    avatar_id: str
    audio_path: str       # absolute local path to normalized WAV
    source_path: str      # absolute local path to idle_base.mp4 or source image
    source_type: str = "idle_video"
    fps: int = 25
    bbox_shift: int = 0


class RenderResult(BaseModel):
    job_id: str
    output_path: str       # absolute local path to rendered MP4
    metadata: dict[str, Any]
    render_duration_seconds: float
    audio_duration_seconds: float | None = None


class AvatarRuntime(Protocol):
    async def health_check(self) -> RuntimeHealth: ...
    async def render(self, request: RenderRequest) -> RenderResult: ...
