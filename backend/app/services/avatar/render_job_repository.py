from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.database import db_connection

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


class RenderJobNotFoundError(ValueError):
    pass


class AvatarRenderJobRepository:
    """Raw asyncpg repository for avatar_render_jobs."""

    async def create(
        self,
        *,
        job_id: str,
        tenant_id: str,
        avatar_id: str,
        input_text: str,
        voice_id: str | None,
        language: str,
        live_session_id: str | None,
        runtime_provider: str,
    ) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO avatar_render_jobs (
                    id, tenant_id, avatar_id, input_text,
                    voice_id, language, live_session_id, runtime_provider, status
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'queued')
                RETURNING *
                """,
                UUID(job_id),
                UUID(tenant_id),
                avatar_id,
                input_text,
                voice_id,
                language,
                UUID(live_session_id) if live_session_id else None,
                runtime_provider,
            )
        return dict(row)

    async def get(self, job_id: str) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM avatar_render_jobs WHERE id = $1",
                UUID(job_id),
            )
        if not row:
            raise RenderJobNotFoundError(f"Avatar render job not found: {job_id}")
        return dict(row)

    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> tuple[list[dict], int]:
        async with db_connection() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT * FROM avatar_render_jobs
                    WHERE tenant_id = $1 AND status = $2
                    ORDER BY created_at DESC LIMIT $3 OFFSET $4
                    """,
                    UUID(tenant_id), status, limit, offset,
                )
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM avatar_render_jobs WHERE tenant_id = $1 AND status = $2",
                    UUID(tenant_id), status,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM avatar_render_jobs
                    WHERE tenant_id = $1
                    ORDER BY created_at DESC LIMIT $2 OFFSET $3
                    """,
                    UUID(tenant_id), limit, offset,
                )
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM avatar_render_jobs WHERE tenant_id = $1",
                    UUID(tenant_id),
                )
        return [dict(r) for r in rows], int(total or 0)

    async def _update(self, job_id: str, status: str, **kwargs) -> dict:
        now = datetime.now(timezone.utc)
        set_clauses = ["status = $2", "updated_at = $3"]
        values: list = [UUID(job_id), status, now]
        idx = 4
        for k, v in kwargs.items():
            set_clauses.append(f"{k} = ${idx}")
            values.append(v)
            idx += 1
        sql = f"UPDATE avatar_render_jobs SET {', '.join(set_clauses)} WHERE id = $1 RETURNING *"
        async with db_connection() as conn:
            row = await conn.fetchrow(sql, *values)
        if not row:
            raise RenderJobNotFoundError(f"Avatar render job not found: {job_id}")
        return dict(row)

    async def mark_generating_audio(self, job_id: str) -> dict:
        return await self._update(
            job_id, "generating_audio",
            started_at=datetime.now(timezone.utc),
        )

    async def mark_rendering(
        self, job_id: str, audio_path: str, audio_duration_seconds: float
    ) -> dict:
        return await self._update(
            job_id, "rendering",
            audio_path=audio_path,
            audio_duration_seconds=audio_duration_seconds,
        )

    async def mark_downloading(self, job_id: str) -> dict:
        return await self._update(job_id, "downloading")

    async def mark_completed(
        self,
        job_id: str,
        *,
        video_path: str,
        metadata_path: str | None,
        quality_report_path: str | None,
        render_duration_seconds: float | None,
    ) -> dict:
        return await self._update(
            job_id, "completed",
            video_path=video_path,
            metadata_path=metadata_path,
            quality_report_path=quality_report_path,
            render_duration_seconds=render_duration_seconds,
            completed_at=datetime.now(timezone.utc),
        )

    async def mark_failed(self, job_id: str, error_code: str, error_message: str) -> dict:
        return await self._update(
            job_id, "failed",
            error_code=error_code,
            error_message=error_message,
            failed_at=datetime.now(timezone.utc),
        )

    async def mark_cancelled(self, job_id: str) -> dict:
        return await self._update(
            job_id, "cancelled",
            completed_at=datetime.now(timezone.utc),
        )

    async def increment_retry(self, job_id: str) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE avatar_render_jobs
                SET retry_count = retry_count + 1,
                    status = 'queued',
                    updated_at = now()
                WHERE id = $1
                RETURNING *
                """,
                UUID(job_id),
            )
        if not row:
            raise RenderJobNotFoundError(job_id)
        return dict(row)


render_job_repository = AvatarRenderJobRepository()
