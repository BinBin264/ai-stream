from __future__ import annotations

import logging
from uuid import uuid4

from app.core.config import settings
from app.services.avatar.render_job_repository import (
    DEMO_TENANT_ID,
    RenderJobNotFoundError,
    render_job_repository,
)
from app.services.avatar.render_status_service import render_status_service
from app.services.queue.redis_streams import redis_streams

logger = logging.getLogger(__name__)


class AvatarRenderService:
    """Creates render jobs, persists them to DB, and publishes to Redis stream."""

    async def submit(
        self,
        *,
        tenant_id: str | None = None,
        avatar_id: str,
        input_text: str,
        voice_id: str | None = None,
        language: str = "vi",
        live_session_id: str | None = None,
    ) -> dict:
        resolved_tenant = tenant_id or DEMO_TENANT_ID

        input_text = input_text.strip()
        if not input_text:
            raise ValueError("input_text must not be empty")
        if len(input_text) > settings.AVATAR_MAX_TEXT_LENGTH:
            raise ValueError(
                f"input_text length {len(input_text)} exceeds max {settings.AVATAR_MAX_TEXT_LENGTH}"
            )

        job_id = str(uuid4())

        job = await render_job_repository.create(
            job_id=job_id,
            tenant_id=resolved_tenant,
            avatar_id=avatar_id,
            input_text=input_text,
            voice_id=voice_id,
            language=language,
            live_session_id=live_session_id,
            runtime_provider=settings.AVATAR_RENDER_PROVIDER,
        )

        await redis_streams.publish(
            settings.AVATAR_RENDER_STREAM,
            {
                "job_id": job_id,
                "tenant_id": resolved_tenant,
                "avatar_id": avatar_id,
            },
        )

        logger.info("Avatar render job submitted", extra={"job_id": job_id, "avatar_id": avatar_id})
        return job

    async def get(self, job_id: str) -> dict:
        return await render_job_repository.get(job_id)

    async def list(
        self,
        tenant_id: str | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> tuple[list[dict], int]:
        resolved_tenant = tenant_id or DEMO_TENANT_ID
        return await render_job_repository.list_by_tenant(
            resolved_tenant, limit=limit, offset=offset, status=status
        )

    async def cancel(self, job_id: str) -> dict:
        job = await render_job_repository.get(job_id)
        if not render_status_service.can_cancel(job["status"]):
            raise ValueError(
                f"Job {job_id!r} cannot be cancelled from status {job['status']!r}"
            )
        return await render_job_repository.mark_cancelled(job_id)


avatar_render_service = AvatarRenderService()
