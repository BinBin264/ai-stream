from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.core.database import asyncpg_dsn
from app.services.queue.redis_streams import redis_streams

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"
VALID_PRIORITIES = {"P0", "P1", "P2", "P3", "P4"}


class MediaRenderOrchestrator:
    def _uuid(self, value: str, field: str) -> UUID:
        try:
            return UUID(str(value))
        except ValueError as exc:
            raise ValueError(f"Invalid {field}") from exc

    async def _connect(self):
        return await asyncpg.connect(asyncpg_dsn())

    async def list_ai_profiles(self, tenant_id: str) -> list[dict[str, Any]]:
        return await self._list_table("ai_model_profiles", tenant_id)

    async def list_avatar_models(self, tenant_id: str) -> list[dict[str, Any]]:
        return await self._list_table("avatar_models", tenant_id)

    async def list_render_profiles(self, tenant_id: str) -> list[dict[str, Any]]:
        return await self._list_table("render_profiles", tenant_id)

    async def _list_table(self, table_name: str, tenant_id: str) -> list[dict[str, Any]]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                f"SELECT * FROM {table_name} WHERE tenant_id = $1 ORDER BY created_at DESC",
                self._uuid(tenant_id, "tenant_id"),
            )
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    async def get_render_job(self, tenant_id: str, job_id: str) -> dict[str, Any]:
        conn = await self._connect()
        try:
            row = await conn.fetchrow(
                "SELECT * FROM media_render_jobs WHERE tenant_id = $1 AND id = $2",
                self._uuid(tenant_id, "tenant_id"),
                self._uuid(job_id, "job_id"),
            )
        finally:
            await conn.close()
        if not row:
            raise ValueError("Render job not found")
        return dict(row)

    async def list_render_jobs(self, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                """
                SELECT * FROM media_render_jobs
                WHERE tenant_id = $1
                ORDER BY requested_at DESC
                LIMIT $2
                """,
                self._uuid(tenant_id, "tenant_id"),
                max(1, min(limit, 500)),
            )
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    async def create_render_job(
        self,
        *,
        tenant_id: str,
        input_text: str,
        render_profile_id: str | None = None,
        live_session_id: str | None = None,
        live_comment_id: str | None = None,
        speech_queue_item_id: str | None = None,
        audio_url: str | None = None,
        motion_code: str = "talk_calm",
        overlay_json: dict | None = None,
        priority: str = "P3",
    ) -> dict[str, Any]:
        clean_text = input_text.strip()
        if not clean_text:
            raise ValueError("input_text is required")
        normalized_priority = priority.strip().upper()
        if normalized_priority not in VALID_PRIORITIES:
            raise ValueError(f"Invalid render priority: {priority}")

        conn = await self._connect()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO media_render_jobs (
                    tenant_id, live_session_id, live_comment_id, render_profile_id,
                    speech_queue_item_id, input_text, status, priority, audio_url,
                    motion_code, overlay_json
                )
                VALUES ($1, $2, $3, $4, $5, $6, 'queued', $7, $8, $9, $10)
                RETURNING *
                """,
                self._uuid(tenant_id, "tenant_id"),
                self._uuid_or_none(live_session_id),
                self._uuid_or_none(live_comment_id),
                self._uuid_or_none(render_profile_id or settings.DEFAULT_RENDER_PROFILE_ID),
                self._uuid_or_none(speech_queue_item_id),
                clean_text,
                normalized_priority,
                audio_url,
                motion_code or "talk_calm",
                overlay_json or {},
            )
            job = dict(row)
        finally:
            await conn.close()

        await redis_streams.publish(
            settings.AVATAR_RENDER_STREAM,
            {
                "job_id": job["id"],
                "tenant_id": job["tenant_id"],
                "live_session_id": job.get("live_session_id"),
                "priority": job["priority"],
            },
        )
        return job

    async def submit_to_render_provider(self, *, tenant_id: str, job_id: str) -> dict[str, Any]:
        job = await self.get_render_job(tenant_id, job_id)
        return await self.mark_completed(job_id, tenant_id=tenant_id, video_url=job.get("video_url") or "", audio_url=job.get("audio_url"))

    async def mark_completed(self, job_id: str, *, video_url: str, audio_url: str | None = None, tenant_id: str = DEMO_TENANT_ID) -> dict[str, Any]:
        conn = await self._connect()
        try:
            row = await conn.fetchrow(
                """
                UPDATE media_render_jobs
                SET status = 'completed',
                    video_url = $3,
                    audio_url = COALESCE($4, audio_url),
                    completed_at = now(),
                    updated_at = now()
                WHERE tenant_id = $1 AND id = $2
                RETURNING *
                """,
                self._uuid(tenant_id, "tenant_id"),
                self._uuid(job_id, "job_id"),
                video_url,
                audio_url,
            )
        finally:
            await conn.close()
        if not row:
            raise ValueError("Render job not found")
        return dict(row)

    async def mark_failed(self, job_id: str, error_message: str, *, tenant_id: str = DEMO_TENANT_ID) -> dict[str, Any]:
        conn = await self._connect()
        try:
            row = await conn.fetchrow(
                """
                UPDATE media_render_jobs
                SET status = 'failed',
                    error_message = $3,
                    updated_at = now()
                WHERE tenant_id = $1 AND id = $2
                RETURNING *
                """,
                self._uuid(tenant_id, "tenant_id"),
                self._uuid(job_id, "job_id"),
                error_message[:500],
            )
        finally:
            await conn.close()
        if not row:
            raise ValueError("Render job not found")
        return dict(row)

    def _uuid_or_none(self, value: str | None) -> UUID | None:
        if not value:
            return None
        try:
            return UUID(str(value))
        except ValueError:
            return None


media_render_orchestrator = MediaRenderOrchestrator()

