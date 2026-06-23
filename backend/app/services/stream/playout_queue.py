from uuid import UUID

from app.core.database import db_connection
from app.services.media.publisher import DEMO_TENANT_ID
from app.services.queue.redis_streams import redis_streams
from app.core.config import settings

PRIORITY_NUMERIC = {
    "P0": 100,
    "P1": 90,
    "P2": 80,
    "P3": 60,
    "P4": 40,
}


class PlayoutQueueService:
    async def enqueue_render_job(self, job: dict, tenant_id: str = DEMO_TENANT_ID) -> dict | None:
        live_session_id = job.get("live_session_id")
        video_url = job.get("video_url")
        if not live_session_id or not video_url:
            return None

        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO playout_queue_items (
                    tenant_id, live_session_id, source_type, source_id,
                    speech_text, audio_url, video_url, motion_code,
                    overlay_json, priority, status
                )
                VALUES ($1, $2, 'media_render_job', $3, $4, $5, $6, $7, $8, $9, 'queued')
                RETURNING *
                """,
                UUID(str(tenant_id)),
                UUID(str(live_session_id)),
                UUID(str(job["id"])),
                job.get("input_text"),
                job.get("audio_url"),
                video_url,
                job.get("motion_code"),
                job.get("overlay_json") or {},
                PRIORITY_NUMERIC.get(str(job.get("priority") or "P4"), 40),
            )
            item = dict(row)

        await redis_streams.publish(
            settings.STREAM_PLAYOUT,
            {
                "playout_item_id": item["id"],
                "tenant_id": tenant_id,
                "live_session_id": item["live_session_id"],
                "priority": item["priority"],
            },
        )
        return item


playout_queue_service = PlayoutQueueService()
