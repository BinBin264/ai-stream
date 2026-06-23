import httpx

from app.core.config import settings
from app.services.avatar.base import AvatarRenderResult


class MuseTalkRuntimeClient:
    async def render(self, payload: dict) -> AvatarRenderResult:
        if not settings.AVATAR_RUNTIME_BASE_URL:
            raise RuntimeError("AVATAR_RUNTIME_BASE_URL is required")
        headers = {}
        if settings.AVATAR_RUNTIME_API_TOKEN:
            headers["authorization"] = f"Bearer {settings.AVATAR_RUNTIME_API_TOKEN}"
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{settings.AVATAR_RUNTIME_BASE_URL.rstrip('/')}/render",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            body = response.json()
        return AvatarRenderResult(
            status=body.get("status") or "submitted",
            video_url=body.get("video_url"),
            duration_ms=body.get("duration_ms"),
        )
