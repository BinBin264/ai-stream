import math
import wave
from pathlib import Path

from app.services.tts.base import TTSResult


class FakeTTSProvider:
    async def synthesize(self, *, text: str, voice_id: str, output_path: str) -> TTSResult:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 16_000
        duration_seconds = max(1, min(8, len(text) // 20 + 1))
        samples = duration_seconds * sample_rate

        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            for index in range(samples):
                value = int(1200 * math.sin(2 * math.pi * 220 * index / sample_rate))
                wav.writeframesraw(value.to_bytes(2, byteorder="little", signed=True))

        return TTSResult(
            audio_url=str(path),
            duration_ms=duration_seconds * 1000,
            content_type="audio/wav",
        )
