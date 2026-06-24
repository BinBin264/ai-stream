from __future__ import annotations

from uuid import UUID

from app.core.config import settings
from app.core.database import db_connection
from app.services.avatar.avatar_render_service import avatar_render_service
from app.services.avatar.render_job_repository import DEMO_TENANT_ID, render_job_repository
from app.services.playout.dynamic_errors import DynamicPlayoutError
from app.services.playout.playout_segment_queue import playout_segment_queue
from app.services.playout.playout_session_service import playout_session_service
from app.services.playout.segment_preflight_validator import segment_preflight_validator


class PlayoutSegmentService:
    def _uuid(self, value: str) -> UUID:
        return UUID(str(value))

    async def list(self, session_id: str) -> list[dict]:
        async with db_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM playout_segments
                WHERE playout_session_id = $1
                ORDER BY queue_position ASC, created_at ASC
                """,
                self._uuid(session_id),
            )
        return [dict(row) for row in rows]

    async def get(self, segment_id: str) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow("SELECT * FROM playout_segments WHERE id = $1", self._uuid(segment_id))
        if not row:
            raise DynamicPlayoutError("playout_segment_not_found", "playout segment not found", status_code=404)
        return dict(row)

    async def count_queue(self, session_id: str) -> int:
        async with db_connection() as conn:
            value = await conn.fetchval(
                """
                SELECT COUNT(*) FROM playout_segments
                WHERE playout_session_id = $1 AND status IN ('queued', 'ready')
                """,
                self._uuid(session_id),
            )
        return int(value or 0)

    async def find_by_idempotency(self, session_id: str, idempotency_key: str | None) -> dict | None:
        if not idempotency_key:
            return None
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM playout_segments
                WHERE playout_session_id = $1 AND idempotency_key = $2
                """,
                self._uuid(session_id),
                idempotency_key,
            )
        return dict(row) if row else None

    async def enqueue_existing_video(
        self,
        *,
        session_id: str,
        source_video_path: str,
        priority: str,
        idempotency_key: str | None,
    ) -> dict:
        await self._assert_session_active_or_startable(session_id)
        if await self.count_queue(session_id) >= settings.PLAYOUT_MAX_QUEUE_SIZE:
            raise DynamicPlayoutError("playout_queue_full", "playout segment queue is full", status_code=409)

        safe_source = segment_preflight_validator.validate_relative_path(source_video_path)
        segment = await self._create_segment(
            session_id=session_id,
            avatar_render_job_id=None,
            source_video_path=safe_source,
            priority=priority,
            status="ready",
            idempotency_key=idempotency_key,
        )
        await playout_segment_queue.publish_ready(
            session_id=session_id,
            segment_id=str(segment["id"]),
            priority=segment["priority"],
        )
        return segment

    async def submit_script(
        self,
        *,
        session_id: str,
        text: str,
        priority: str,
        voice_id: str | None,
        idempotency_key: str | None,
    ) -> tuple[dict, dict]:
        session = await self._assert_session_active_or_startable(session_id)
        existing = await self.find_by_idempotency(session_id, idempotency_key)
        if existing and existing.get("avatar_render_job_id"):
            job = await render_job_repository.get(str(existing["avatar_render_job_id"]))
            return job, existing
        if existing:
            raise DynamicPlayoutError(
                "playout_segment_invalid",
                "idempotency key is already used by a non-script segment",
                status_code=409,
            )
        live_session_id = self._uuid_or_none(session.get("live_session_id"))
        job = await avatar_render_service.submit(
            tenant_id=str(session["tenant_id"]),
            avatar_id=session["avatar_id"],
            input_text=text,
            voice_id=voice_id,
            language="vi",
            live_session_id=live_session_id,
        )
        segment = await self._create_segment(
            session_id=session_id,
            avatar_render_job_id=str(job["id"]),
            source_video_path=None,
            priority=priority,
            status="queued",
            idempotency_key=idempotency_key,
        )
        return job, segment

    async def mark_render_job_ready(self, *, render_job_id: str, source_video_path: str) -> dict | None:
        safe_source = segment_preflight_validator.validate_absolute_runtime_output(source_video_path)
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE playout_segments
                SET source_video_path = $2,
                    status = 'ready',
                    queued_at = COALESCE(queued_at, now()),
                    updated_at = now(),
                    error_code = NULL,
                    error_message = NULL
                WHERE avatar_render_job_id = $1
                  AND status IN ('queued', 'failed')
                RETURNING *
                """,
                self._uuid(render_job_id),
                safe_source,
            )
        if not row:
            return None
        segment = dict(row)
        await playout_segment_queue.publish_ready(
            session_id=str(segment["playout_session_id"]),
            segment_id=str(segment["id"]),
            priority=segment["priority"],
        )
        return segment

    async def mark_render_job_failed(self, *, render_job_id: str, error_code: str, error_message: str) -> dict | None:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE playout_segments
                SET status = 'failed',
                    error_code = $2,
                    error_message = $3,
                    updated_at = now()
                WHERE avatar_render_job_id = $1
                  AND status IN ('queued', 'ready')
                RETURNING *
                """,
                self._uuid(render_job_id),
                error_code,
                error_message[:500],
            )
        return dict(row) if row else None

    async def next_ready(self, session_id: str) -> dict | None:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM playout_segments
                WHERE playout_session_id = $1
                  AND status = 'ready'
                ORDER BY
                  CASE priority
                    WHEN 'P0' THEN 100
                    WHEN 'P1' THEN 90
                    WHEN 'P2' THEN 80
                    WHEN 'P3' THEN 60
                    ELSE 40
                  END DESC,
                  queue_position ASC,
                  created_at ASC
                LIMIT 1
                """,
                self._uuid(session_id),
            )
        return dict(row) if row else None

    async def mark_playing(self, segment_id: str) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE playout_segments
                SET status = 'playing', started_at = COALESCE(started_at, now()), updated_at = now()
                WHERE id = $1 AND status = 'ready'
                RETURNING *
                """,
                self._uuid(segment_id),
            )
        if not row:
            raise DynamicPlayoutError("playout_segment_not_ready", "segment is not ready")
        return dict(row)

    async def mark_completed(self, segment_id: str) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE playout_segments
                SET status = 'completed', completed_at = now(), updated_at = now()
                WHERE id = $1 AND status = 'playing'
                RETURNING *
                """,
                self._uuid(segment_id),
            )
        if not row:
            raise DynamicPlayoutError("playout_segment_not_found", "playing segment not found", status_code=404)
        return dict(row)

    async def mark_failed(self, segment_id: str, error_code: str, error_message: str) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE playout_segments
                SET status = 'failed',
                    error_code = $2,
                    error_message = $3,
                    updated_at = now()
                WHERE id = $1
                RETURNING *
                """,
                self._uuid(segment_id),
                error_code,
                error_message[:500],
            )
        if not row:
            raise DynamicPlayoutError("playout_segment_not_found", "segment not found", status_code=404)
        return dict(row)

    async def cancel(self, session_id: str, segment_id: str) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE playout_segments
                SET status = 'cancelled',
                    cancelled_at = now(),
                    updated_at = now()
                WHERE id = $1
                  AND playout_session_id = $2
                  AND status IN ('queued', 'ready')
                RETURNING *
                """,
                self._uuid(segment_id),
                self._uuid(session_id),
            )
        if not row:
            raise DynamicPlayoutError(
                "playout_segment_cancel_not_allowed",
                "segment cannot be cancelled from its current status",
                status_code=409,
            )
        return dict(row)

    async def _create_segment(
        self,
        *,
        session_id: str,
        avatar_render_job_id: str | None,
        source_video_path: str | None,
        priority: str,
        status: str,
        idempotency_key: str | None,
    ) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                WITH next_pos AS (
                    SELECT COALESCE(MAX(queue_position), 0) + 1 AS value
                    FROM playout_segments
                    WHERE playout_session_id = $1
                )
                INSERT INTO playout_segments (
                    playout_session_id, avatar_render_job_id, source_video_path,
                    segment_type, priority, status, queue_position, queued_at,
                    idempotency_key
                )
                SELECT $1, $2, $3, 'talking', $4, $5, next_pos.value,
                       CASE WHEN $5 IN ('queued', 'ready') THEN now() ELSE NULL END,
                       $6
                FROM next_pos
                ON CONFLICT (playout_session_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL
                DO UPDATE SET updated_at = playout_segments.updated_at
                RETURNING *
                """,
                self._uuid(session_id),
                self._uuid(avatar_render_job_id) if avatar_render_job_id else None,
                source_video_path,
                priority,
                status,
                idempotency_key,
            )
        return dict(row)

    async def _assert_session_active_or_startable(self, session_id: str) -> dict:
        session = await playout_session_service.get(session_id)
        if session["status"] in {"stopping", "failed", "stopped"}:
            raise DynamicPlayoutError("playout_session_not_active", "playout session is not active", status_code=409)
        return session

    def _uuid_or_none(self, value) -> str | None:
        if not value:
            return None
        try:
            return str(UUID(str(value)))
        except ValueError:
            return None


playout_segment_service = PlayoutSegmentService()
