from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.models.domain import LiveSession


class MetaClient:
    """Meta Graph API boundary.

    Local development can run with FACEBOOK_ENABLED=false and manual RTMPS_URL /
    RTMPS_STREAM_KEY. When FACEBOOK_ENABLED=true this adapter creates and ends a
    Page Live Video through Graph API, while keeping provider-specific fields
    contained here.
    """

    def verify_webhook(self, mode: str | None, token: str | None, challenge: str | None) -> str | None:
        if mode == "subscribe" and token == settings.META_VERIFY_TOKEN and challenge:
            return challenge
        return None

    async def create_live_video(self, title: str) -> LiveSession:
        if settings.FACEBOOK_ENABLED:
            if not settings.META_PAGE_ID or not settings.META_PAGE_ACCESS_TOKEN:
                raise RuntimeError("FACEBOOK_ENABLED requires META_PAGE_ID and META_PAGE_ACCESS_TOKEN")
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{settings.META_PAGE_ID}/live_videos",
                    data={
                        "access_token": settings.META_PAGE_ACCESS_TOKEN,
                        "title": title,
                        "description": title,
                        "status": "UNPUBLISHED",
                    },
                )
                response.raise_for_status()
                data = response.json()
            stream_url = data.get("secure_stream_url") or data.get("stream_url") or ""
            rtmps_url, stream_key = self._split_stream_url(stream_url)
            return LiveSession(
                title=title,
                facebook_live_video_id=data.get("id"),
                external_live_video_id=data.get("id"),
                rtmps_url=rtmps_url,
                stream_key=stream_key,
                settings_json={
                    "meta_live_video_id": data.get("id"),
                    "meta_stream_url_returned": bool(stream_url),
                },
            )

        return LiveSession(
            title=title,
            facebook_live_video_id=None,
            rtmps_url=settings.RTMPS_URL or None,
            stream_key=settings.RTMPS_STREAM_KEY or None,
        )

    async def go_live(self, live: LiveSession) -> LiveSession:
        if settings.FACEBOOK_ENABLED and live.facebook_live_video_id:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{live.facebook_live_video_id}",
                    data={
                        "access_token": settings.META_PAGE_ACCESS_TOKEN,
                        "status": "LIVE_NOW",
                    },
                )
                response.raise_for_status()
        return live

    async def stop_live(self, live: LiveSession) -> LiveSession:
        if settings.FACEBOOK_ENABLED and live.facebook_live_video_id:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{live.facebook_live_video_id}",
                    data={
                        "access_token": settings.META_PAGE_ACCESS_TOKEN,
                        "end_live_video": "true",
                    },
                )
                response.raise_for_status()
        return live

    def _split_stream_url(self, stream_url: str) -> tuple[str | None, str | None]:
        if not stream_url:
            return None, None
        parsed = urlparse(stream_url)
        path = parsed.path.strip("/")
        if "/" not in path:
            return stream_url.rstrip("/"), None
        prefix, stream_key = path.rsplit("/", 1)
        base_url = f"{parsed.scheme}://{parsed.netloc}/{prefix}"
        return base_url, stream_key


meta_client = MetaClient()
