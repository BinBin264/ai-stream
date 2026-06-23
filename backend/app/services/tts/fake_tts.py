import math
import wave
from pathlib import Path

from app.services.tts.schemas import TTSRequest, TTSResult


class FakeTTSProvider:
    """Silent-tone WAV generator for unit tests. No external calls."""

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        path = request.output_path
        path.parent.mkdir(parents=True, exist_ok=True)

        sample_rate = request.sample_rate
        # ~0.1 seconds per character, capped 1–10 seconds
        duration_seconds = max(1.0, min(10.0, len(request.text) * 0.1))
        n_samples = int(duration_seconds * sample_rate)

        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            for i in range(n_samples):
                value = int(800 * math.sin(2 * math.pi * 220 * i / sample_rate))
                wav.writeframesraw(value.to_bytes(2, byteorder="little", signed=True))

        return TTSResult(
            audio_path=path,
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
            format="wav",
            provider="fake",
        )
