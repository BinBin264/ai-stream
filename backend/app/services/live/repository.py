import json
from uuid import UUID

from app.core.database import db_connection
from app.models.domain import LiveSession
from app.services.media.publisher import DEMO_TENANT_ID


class LiveSessionRepository:
    async def upsert_from_domain(self, live: LiveSession, tenant_id: str = DEMO_TENANT_ID) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO live_sessions (
                    id, tenant_id, external_live_video_id, title, status,
                    media_provider, settings_json, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
                ON CONFLICT (id) DO UPDATE SET
                    external_live_video_id = EXCLUDED.external_live_video_id,
                    title = EXCLUDED.title,
                    status = EXCLUDED.status,
                    media_provider = EXCLUDED.media_provider,
                    settings_json = EXCLUDED.settings_json,
                    updated_at = now()
                RETURNING *
                """,
                UUID(str(live.id)),
                UUID(str(tenant_id)),
                live.external_live_video_id or live.facebook_live_video_id,
                live.title,
                str(live.status),
                live.media_provider,
                json.dumps(live.settings_json) if isinstance(live.settings_json, dict) else live.settings_json,
                live.created_at,
            )
            return dict(row)

    async def get(self, live_id: str, tenant_id: str = DEMO_TENANT_ID) -> dict | None:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM live_sessions WHERE tenant_id = $1 AND id = $2",
                UUID(str(tenant_id)),
                UUID(str(live_id)),
            )
            return dict(row) if row else None

    async def has_active_playout(self, live_id: str, tenant_id: str = DEMO_TENANT_ID) -> bool:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1
                FROM playout_sessions
                WHERE tenant_id = $1
                  AND live_session_id = $2
                  AND status IN ('starting', 'idle', 'playing_talking', 'stopping')
                LIMIT 1
                """,
                UUID(str(tenant_id)),
                str(live_id),
            )
        return row is not None

    async def delete(self, live_id: str, tenant_id: str = DEMO_TENANT_ID) -> bool:
        async with db_connection() as conn:
            live_uuid = UUID(str(live_id))
            tenant_uuid = UUID(str(tenant_id))
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id
                    FROM live_sessions
                    WHERE tenant_id = $1 AND id = $2
                    FOR UPDATE
                    """,
                    tenant_uuid,
                    live_uuid,
                )
                if not row:
                    return False

                await conn.execute(
                    """
                    UPDATE playout_sessions
                    SET active_segment_id = NULL
                    WHERE tenant_id = $1 AND live_session_id = $2
                    """,
                    tenant_uuid,
                    str(live_id),
                )
                await conn.execute(
                    "DELETE FROM playout_sessions WHERE tenant_id = $1 AND live_session_id = $2",
                    tenant_uuid,
                    str(live_id),
                )
                await conn.execute(
                    "DELETE FROM avatar_render_jobs WHERE tenant_id = $1 AND live_session_id = $2",
                    tenant_uuid,
                    live_uuid,
                )
                await conn.execute(
                    "DELETE FROM media_render_jobs WHERE tenant_id = $1 AND live_session_id = $2",
                    tenant_uuid,
                    live_uuid,
                )
                await conn.execute(
                    "DELETE FROM speech_queue_items WHERE tenant_id = $1 AND live_session_id = $2",
                    tenant_uuid,
                    live_uuid,
                )
                await conn.execute(
                    "DELETE FROM ai_response_jobs WHERE tenant_id = $1 AND live_session_id = $2",
                    tenant_uuid,
                    live_uuid,
                )
                await conn.execute(
                    "DELETE FROM live_comments WHERE tenant_id = $1 AND live_session_id = $2",
                    tenant_uuid,
                    live_uuid,
                )
                await conn.execute(
                    "DELETE FROM live_sessions WHERE tenant_id = $1 AND id = $2",
                    tenant_uuid,
                    live_uuid,
                )
        return row is not None


live_session_repository = LiveSessionRepository()
