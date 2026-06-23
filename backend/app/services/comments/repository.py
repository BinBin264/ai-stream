from datetime import datetime
from uuid import UUID

from app.core.database import db_connection
from app.models.domain import CommentStatus, LiveComment
from app.services.media.publisher import DEMO_TENANT_ID


class LiveCommentRepository:
    def _uuid_or_none(self, value: str | None) -> UUID | None:
        if not value:
            return None
        try:
            return UUID(str(value))
        except ValueError:
            return None

    def _status_to_domain(self, value: str) -> CommentStatus:
        try:
            return CommentStatus(value)
        except ValueError:
            return CommentStatus.QUEUED

    def _row_to_comment(self, row) -> LiveComment:
        live_id = str(row["live_session_id"]) if row["live_session_id"] else "unknown-live"
        return LiveComment(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            facebook_page_id=row["facebook_page_id"],
            live_id=live_id,
            live_session_id=live_id if row["live_session_id"] else None,
            facebook_comment_id=row["external_comment_id"],
            external_comment_id=row["external_comment_id"],
            external_parent_comment_id=row["external_parent_comment_id"],
            viewer_profile_id=row["external_viewer_id_hash"],
            user_name=row["viewer_name"] or "Facebook User",
            text=row["message"],
            normalized_text=row["normalized_message"],
            status=self._status_to_domain(row["processing_status"]),
            priority=row["priority"] or 0,
            raw_payload_reference=row["raw_payload_reference"],
            created_at=row["created_at"],
            processed_at=row["processed_at"],
        )

    async def resolve_live_session_id(
        self,
        *,
        external_live_id: str | None,
        page_id: str | None = None,
        tenant_id: str = DEMO_TENANT_ID,
    ) -> str | None:
        if not external_live_id:
            return None
        async with db_connection() as conn:
            candidate = self._uuid_or_none(external_live_id)
            if candidate:
                row = await conn.fetchrow(
                    "SELECT id FROM live_sessions WHERE tenant_id = $1 AND id = $2",
                    UUID(str(tenant_id)),
                    candidate,
                )
                if row:
                    return str(row["id"])
            row = await conn.fetchrow(
                """
                SELECT ls.id
                FROM live_sessions ls
                LEFT JOIN facebook_pages fp ON fp.id = ls.facebook_page_id
                WHERE ls.tenant_id = $1
                  AND ls.external_live_video_id = $2
                  AND ($3::text IS NULL OR fp.page_id = $3 OR ls.facebook_page_id IS NULL)
                ORDER BY ls.created_at DESC
                LIMIT 1
                """,
                UUID(str(tenant_id)),
                external_live_id,
                page_id,
            )
            return str(row["id"]) if row else None

    async def get(self, comment_id: str, tenant_id: str = DEMO_TENANT_ID) -> LiveComment | None:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM live_comments WHERE tenant_id = $1 AND id = $2",
                UUID(str(tenant_id)),
                UUID(str(comment_id)),
            )
            return self._row_to_comment(row) if row else None

    async def find_by_external_id(
        self,
        *,
        live_session_id: str | None,
        external_comment_id: str | None,
        tenant_id: str = DEMO_TENANT_ID,
    ) -> LiveComment | None:
        if not live_session_id or not external_comment_id:
            return None
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM live_comments
                WHERE tenant_id = $1
                  AND live_session_id = $2
                  AND external_comment_id = $3
                """,
                UUID(str(tenant_id)),
                UUID(str(live_session_id)),
                external_comment_id,
            )
            return self._row_to_comment(row) if row else None

    async def save(
        self,
        comment: LiveComment,
        *,
        tenant_id: str = DEMO_TENANT_ID,
        live_session_id: str | None = None,
    ) -> LiveComment:
        resolved_live_id = live_session_id or comment.live_session_id or comment.live_id
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO live_comments (
                    id, tenant_id, live_session_id, facebook_page_id,
                    external_comment_id, external_parent_comment_id,
                    external_viewer_id_hash, viewer_name, message,
                    normalized_message, intent, processing_status, priority,
                    raw_payload_reference, received_at, processed_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                ON CONFLICT (live_session_id, external_comment_id) DO UPDATE SET
                    viewer_name = EXCLUDED.viewer_name,
                    message = EXCLUDED.message,
                    normalized_message = COALESCE(EXCLUDED.normalized_message, live_comments.normalized_message),
                    intent = COALESCE(EXCLUDED.intent, live_comments.intent),
                    processing_status = EXCLUDED.processing_status,
                    priority = EXCLUDED.priority,
                    raw_payload_reference = COALESCE(EXCLUDED.raw_payload_reference, live_comments.raw_payload_reference),
                    processed_at = COALESCE(EXCLUDED.processed_at, live_comments.processed_at)
                RETURNING *
                """,
                UUID(str(comment.id)),
                UUID(str(tenant_id)),
                self._uuid_or_none(resolved_live_id),
                comment.facebook_page_id,
                comment.external_comment_id or comment.facebook_comment_id,
                comment.external_parent_comment_id,
                comment.viewer_profile_id,
                comment.user_name,
                comment.text,
                comment.normalized_text,
                None,
                str(comment.status),
                comment.priority,
                comment.raw_payload_reference,
                comment.created_at,
                comment.processed_at,
            )
            return self._row_to_comment(row)

    async def update_from_domain(self, comment: LiveComment, tenant_id: str = DEMO_TENANT_ID) -> LiveComment:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE live_comments
                SET normalized_message = $3,
                    processing_status = $4,
                    processed_at = $5
                WHERE tenant_id = $1 AND id = $2
                RETURNING *
                """,
                UUID(str(tenant_id)),
                UUID(str(comment.id)),
                comment.normalized_text,
                str(comment.status),
                comment.processed_at,
            )
            if not row:
                raise ValueError("Live comment not found")
            return self._row_to_comment(row)

    async def mark_answered(
        self,
        comment_id: str,
        *,
        ai_reply: str,
        status: str = "answered",
        tenant_id: str = DEMO_TENANT_ID,
    ) -> LiveComment:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE live_comments
                SET processing_status = $3,
                    ai_reply = $4,
                    processed_at = $5
                WHERE tenant_id = $1 AND id = $2
                RETURNING *
                """,
                UUID(str(tenant_id)),
                UUID(str(comment_id)),
                status,
                ai_reply,
                datetime.utcnow(),
            )
            if not row:
                raise ValueError("Live comment not found")
            return self._row_to_comment(row)


live_comment_repository = LiveCommentRepository()
