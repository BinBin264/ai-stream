from __future__ import annotations

from uuid import UUID

from app.core.config import settings
from app.core.database import db_connection
from app.models.domain import SpeechQueueItem
from app.services.queue.redis_streams import redis_streams

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


class MediaPublisher:
    def _uuid_or_none(self, value: str | None) -> UUID | None:
        if not value:
            return None
        try:
            return UUID(str(value))
        except ValueError:
            return None

    def _to_model(self, row) -> SpeechQueueItem:
        return SpeechQueueItem(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            live_session_id=str(row["live_session_id"]) if row["live_session_id"] else None,
            source_comment_id=str(row["live_comment_id"]) if row["live_comment_id"] else None,
            text=row["text"],
            voice=row["voice"],
            priority=row["priority"],
            status=row["status"],
            audio_url=row["audio_url"],
            error_message=row["error_message"],
            attempt_count=row["attempt_count"],
            scheduled_at=row["scheduled_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def queue_speech(
        self,
        *,
        tenant_id: str,
        live_session_id: str | None,
        source_comment_id: str | None,
        text: str,
        priority: str,
        voice: str = "default",
    ) -> SpeechQueueItem | None:
        if not settings.MEDIA_ENABLED or not settings.AI_SPEECH_ENABLED:
            return None
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO speech_queue_items (
                    tenant_id, live_session_id, live_comment_id, text, voice, priority, status
                )
                VALUES ($1, $2, $3, $4, $5, $6, 'queued')
                RETURNING *
                """,
                UUID(str(tenant_id)),
                self._uuid_or_none(live_session_id),
                self._uuid_or_none(source_comment_id),
                text,
                voice,
                priority,
            )
        item = self._to_model(row)
        await redis_streams.publish(
            settings.STREAM_SPEECH,
            {
                "speech_item_id": item.id,
                "tenant_id": item.tenant_id,
                "live_session_id": item.live_session_id,
                "priority": item.priority,
            },
        )
        return item

    async def list_items(self, tenant_id: str = DEMO_TENANT_ID, limit: int = 100) -> list[dict]:
        async with db_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM speech_queue_items
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                UUID(str(tenant_id)),
                limit,
            )
        return [dict(row) for row in rows]

    async def mark_processing(self, speech_item_id: str, tenant_id: str = DEMO_TENANT_ID) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE speech_queue_items
                SET status = 'processing',
                    attempt_count = attempt_count + 1,
                    started_at = COALESCE(started_at, now()),
                    updated_at = now()
                WHERE tenant_id = $1 AND id = $2 AND status IN ('queued', 'failed')
                RETURNING *
                """,
                UUID(str(tenant_id)),
                UUID(str(speech_item_id)),
            )
        if not row:
            raise ValueError("Speech queue item not found or already processing")
        return dict(row)

    async def mark_completed(self, speech_item_id: str, *, audio_url: str, tenant_id: str = DEMO_TENANT_ID) -> dict:
        return await self.update_status(speech_item_id, "completed", audio_url=audio_url, tenant_id=tenant_id)

    async def mark_failed(self, speech_item_id: str, error_message: str, tenant_id: str = DEMO_TENANT_ID) -> dict:
        return await self.update_status(speech_item_id, "failed", error_message=error_message, tenant_id=tenant_id)

    async def update_status(
        self,
        speech_item_id: str,
        status: str,
        *,
        audio_url: str | None = None,
        error_message: str | None = None,
        tenant_id: str = DEMO_TENANT_ID,
    ) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE speech_queue_items
                SET status = $3,
                    audio_url = COALESCE($4, audio_url),
                    error_message = $5,
                    updated_at = now(),
                    completed_at = CASE WHEN $3 IN ('completed', 'failed') THEN now() ELSE completed_at END
                WHERE tenant_id = $1 AND id = $2
                RETURNING *
                """,
                UUID(str(tenant_id)),
                UUID(str(speech_item_id)),
                status,
                audio_url,
                error_message,
            )
        if not row:
            raise ValueError("Speech queue item not found")
        return dict(row)


media_publisher = MediaPublisher()

