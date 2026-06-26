from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.tts.schemas import TTSRequest, TTSResult

logger = logging.getLogger(__name__)


class ModalTTSProvider:
    """Calls the Modal-hosted viXTTS endpoint for GPU-accelerated TTS."""

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        if not settings.MODAL_ENABLED:
            raise RuntimeError("Modal TTS is disabled")
        headers: dict[str, str] = {}
        if settings.MODAL_API_TOKEN:
            headers["x-api-token"] = settings.MODAL_API_TOKEN

        async with httpx.AsyncClient(timeout=settings.MODAL_TTS_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                settings.MODAL_TTS_URL,
                json={"text": request.text, "voice_id": request.voice_id},
                headers=headers,
            )
            resp.raise_for_status()

        output_path = Path(str(request.output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(resp.content)

        logger.info("Modal TTS wrote %d bytes → %s", len(resp.content), output_path)
        return TTSResult(
            audio_path=output_path,
            format="wav",
            sample_rate=24_000,
            provider="modal-vixtts",
        )
