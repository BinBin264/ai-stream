from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.avatar.runtime.base import AvatarRuntime, RenderRequest, RenderResult, RuntimeHealth

logger = logging.getLogger(__name__)


class ModalAvatarRuntime:
    """Calls the Modal-hosted MuseTalk endpoint for GPU-accelerated avatar render."""

    async def health_check(self) -> RuntimeHealth:
        if not settings.MODAL_ENABLED:
            return RuntimeHealth(status="unavailable", message="Modal runtime disabled")
        if not settings.MODAL_AVATAR_URL:
            return RuntimeHealth(status="unavailable", message="MODAL_AVATAR_URL not set")
        try:
            health_url = settings.MODAL_AVATAR_URL.replace("/avatar-render", "/avatar-health")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(health_url)
                resp.raise_for_status()
            return RuntimeHealth(status="ok", message="Modal MuseTalk reachable")
        except Exception as exc:
            return RuntimeHealth(status="degraded", message=str(exc))

    async def render(self, request: RenderRequest) -> RenderResult:
        if not settings.MODAL_ENABLED:
            raise RuntimeError("Modal avatar runtime is disabled")
        headers: dict[str, str] = {}
        if settings.MODAL_API_TOKEN:
            headers["x-api-token"] = settings.MODAL_API_TOKEN

        audio_path = Path(request.audio_path)
        source_path = Path(request.source_path)

        mime = "video/mp4" if source_path.suffix == ".mp4" else "image/png"

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
            resp = await client.post(
                settings.MODAL_AVATAR_URL,
                files={
                    "audio": ("input.wav", audio_path.read_bytes(), "audio/wav"),
                    "source": (source_path.name, source_path.read_bytes(), mime),
                },
                headers=headers,
            )
            if not resp.is_success:
                logger.error("Modal avatar render HTTP %s: %s", resp.status_code, resp.text[:1000])
            resp.raise_for_status()
        render_duration = time.perf_counter() - t0

        # Derive output path from job_id in same dir as audio
        output_path = audio_path.parent / f"{request.job_id}.mp4"
        output_path.write_bytes(resp.content)

        logger.info(
            "Modal avatar render done in %.1fs → %s (%d bytes)",
            render_duration, output_path, len(resp.content),
        )
        return RenderResult(
            job_id=request.job_id,
            output_path=str(output_path),
            metadata={"provider": "modal-musetalk", "gpu": "A10G"},
            render_duration_seconds=render_duration,
        )
