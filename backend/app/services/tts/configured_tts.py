from __future__ import annotations

import subprocess
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.tts.schemas import TTSRequest, TTSResult


class ConfiguredTTSProvider:
    """Selects the TTS provider from settings and delegates synthesis."""

    def _provider(self):
        if settings.TTS_PROVIDER == "fake":
            from app.services.tts.fake_tts import FakeTTSProvider  # noqa: PLC0415
            return FakeTTSProvider()
        if settings.TTS_PROVIDER in ("vietnamese", "edge"):
            from app.services.tts.vietnamese_tts import VietnameseTTSProvider  # noqa: PLC0415
            return VietnameseTTSProvider()
        raise RuntimeError(f"Unsupported TTS_PROVIDER: {settings.TTS_PROVIDER!r}")

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        if settings.TTS_PROVIDER == "elevenlabs":
            return await self._synthesize_elevenlabs(request)
        return await self._provider().synthesize(request)

    async def _synthesize_elevenlabs(self, request: TTSRequest) -> TTSResult:
        if not settings.ELEVENLABS_API_KEY:
            raise RuntimeError("ELEVENLABS_API_KEY is required")
        voice_id = request.voice_id or settings.ELEVENLABS_VOICE_ID
        if not voice_id:
            raise RuntimeError("ELEVENLABS_VOICE_ID is required")

        output_path = request.output_path
        if output_path.suffix.lower() != ".mp3":
            output_path = output_path.with_suffix(".mp3")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        payload = {
            "text": request.text,
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
        output_path.write_bytes(response.content)

        return TTSResult(
            audio_path=output_path,
            duration_seconds=_probe_duration(output_path),
            format="mp3",
            provider="elevenlabs",
        )


def _probe_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


configured_tts = ConfiguredTTSProvider()
