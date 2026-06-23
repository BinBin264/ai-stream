from typing import Protocol

from pydantic import BaseModel


class AvatarRenderResult(BaseModel):
    status: str
    video_url: str | None = None
    duration_ms: int | None = None


class AvatarRuntime(Protocol):
    async def render(self, payload: dict) -> AvatarRenderResult:
        ...
