from __future__ import annotations

import asyncio
from pathlib import Path

from app.services.avatar.runtime.base import RenderRequest, RenderResult, RuntimeHealth


class FakeAvatarRuntime:
    """Deterministic stub that writes an empty MP4 placeholder. No GPU or network."""

    async def health_check(self) -> RuntimeHealth:
        return RuntimeHealth(status="ok", message="fake runtime always ok")

    async def render(self, request: RenderRequest) -> RenderResult:
        await asyncio.sleep(0.01)
        output_path = Path(request.audio_path).parent / f"{request.job_id}_output.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"")
        return RenderResult(
            job_id=request.job_id,
            output_path=str(output_path),
            metadata={
                "engine": "fake",
                "engine_version": "0",
                "gpu_type": "none",
                "source_type": request.source_type,
            },
            render_duration_seconds=0.01,
            audio_duration_seconds=1.0,
        )
