from pathlib import Path

import httpx

from app.core.config import settings
from app.services.tts.base import TTSResult


class ElevenLabsTTSProvider:
    async def synthesize(self, *, text: str, voice_id: str, output_path: str) -> TTSResult:
        if not settings.ELEVENLABS_API_KEY:
            raise RuntimeError("ELEVENLABS_API_KEY is required")
        if not voice_id:
            raise RuntimeError("ELEVENLABS_VOICE_ID is required")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        payload = {
            "text": text,
            "model_id": settings.ELEVENLABS_MODEL_ID,
            "output_format": settings.ELEVENLABS_OUTPUT_FORMAT,
        }
        headers = {
            "xi-api-key": settings.ELEVENLABS_API_KEY,
            "content-type": "application/json",
            "accept": "audio/mpeg",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return TTSResult(audio_url=str(path), duration_ms=None, content_type="audio/mpeg")
