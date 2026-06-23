from __future__ import annotations

from app.services.avatar.runtime.base import RenderRequest, RenderResult, RuntimeHealth


class LocalMuseTalkRuntime:
    """Local MuseTalk runtime adapter placeholder."""

    async def health_check(self) -> RuntimeHealth:
        return RuntimeHealth(
            status="unavailable",
            message="LocalMuseTalkRuntime is not implemented",
        )

    async def render(self, request: RenderRequest) -> RenderResult:
        raise NotImplementedError("LocalMuseTalkRuntime is not implemented")
