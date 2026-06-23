from pathlib import Path
from typing import Literal

from pydantic import BaseModel


AudioFormat = Literal["wav", "mp3"]


class TTSResult(BaseModel):
    audio_path: Path
    duration_seconds: float | None = None
    sample_rate: int | None = None
    format: AudioFormat = "wav"
    provider: str = "unknown"


class TTSRequest(BaseModel):
    text: str
    output_path: Path
    voice_id: str | None = None
    language: str = "vi"
    sample_rate: int = 24_000
