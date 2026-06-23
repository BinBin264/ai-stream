from typing import Protocol

from pydantic import BaseModel


class TTSResult(BaseModel):
    audio_url: str
    duration_ms: int | None = None
    content_type: str


class TTSProvider(Protocol):
    async def synthesize(self, *, text: str, voice_id: str, output_path: str) -> TTSResult:
        ...
