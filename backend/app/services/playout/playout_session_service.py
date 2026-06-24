from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.core.database import db_connection
from app.services.avatar.render_job_repository import DEMO_TENANT_ID
from app.services.playout.dynamic_errors import DynamicPlayoutError
from app.services.playout.paths import backend_root
from app.services.playout.playout_state_machine import playout_state_machine


class PlayoutSessionService:
    def _uuid(self, value: str) -> UUID:
        return UUID(str(value))

    def _relative_backend_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(backend_root().resolve()))
        except ValueError:
            return path.name

    def idle_path_for(self, avatar_id: str) -> tuple[Path, str]:
        idle = backend_root() / "avatars" / avatar_id / "idle_base.mp4"
        if not idle.exists():
            raise DynamicPlayoutError(
                "playout_idle_asset_missing",
                f"idle_base.mp4 is missing for avatar {avatar_id}",
                status_code=404,
            )
        return idle, self._relative_backend_path(idle)

    async def create(
        self,
        *,
        avatar_id: str,
        live_session_id: str | None,
        output_mode: str,
        tenant_id: str = DEMO_TENANT_ID,
    ) -> dict:
        if output_mode not in {"local_preview", "file_output"}:
            raise DynamicPlayoutError("playout_runtime_not_available", "unsupported playout output mode")
        _idle_abs, idle_rel = self.idle_path_for(avatar_id)
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO playout_sessions (
                    tenant_id, live_session_id, avatar_id, idle_video_path, status, output_mode
                )
                VALUES ($1, $2, $3, $4, 'stopped', $5)
                RETURNING *
                """,
                self._uuid(tenant_id),
                live_session_id,
                avatar_id,
                idle_rel,
                output_mode,
            )
        return dict(row)

    async def get(self, session_id: str) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow("SELECT * FROM playout_sessions WHERE id = $1", self._uuid(session_id))
        if not row:
            raise DynamicPlayoutError("playout_session_not_found", "playout session not found", status_code=404)
        return dict(row)

    async def list(self, tenant_id: str = DEMO_TENANT_ID, limit: int = 100) -> list[dict]:
        async with db_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM playout_sessions
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                self._uuid(tenant_id),
                max(1, min(limit, 500)),
            )
        return [dict(row) for row in rows]

    async def transition(
        self,
        session_id: str,
        target_status: str,
        *,
        force: bool = False,
        active_segment_id: str | None = None,
        output_path: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> dict:
        session = await self.get(session_id)
        playout_state_machine.assert_transition(str(session["status"]), target_status, force=force)

        fields = ["status = $2", "updated_at = now()"]
        values: list = [self._uuid(session_id), target_status]
        index = 3
        if active_segment_id is not None or target_status in {"idle", "stopped", "failed"}:
            fields.append(f"active_segment_id = ${index}")
            values.append(self._uuid(active_segment_id) if active_segment_id else None)
            index += 1
        if output_path is not None:
            fields.append(f"output_path = ${index}")
            values.append(output_path)
            index += 1
        if target_status == "starting":
            fields.append("started_at = COALESCE(started_at, now())")
            fields.append("stopped_at = NULL")
            fields.append("error_code = NULL")
            fields.append("error_message = NULL")
        if target_status == "stopped":
            fields.append("stopped_at = now()")
        if target_status == "failed":
            fields.append(f"error_code = ${index}")
            values.append(error_code or "playout_runtime_crashed")
            index += 1
            fields.append(f"error_message = ${index}")
            values.append((error_message or "playout runtime failed")[:500])
            index += 1

        async with db_connection() as conn:
            row = await conn.fetchrow(
                f"UPDATE playout_sessions SET {', '.join(fields)} WHERE id = $1 RETURNING *",
                *values,
            )
        if not row:
            raise DynamicPlayoutError("playout_session_not_found", "playout session not found", status_code=404)
        return dict(row)

    async def touch_heartbeat(self, session_id: str) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE playout_sessions
                SET last_heartbeat_at = now(), updated_at = now()
                WHERE id = $1
                RETURNING *
                """,
                self._uuid(session_id),
            )
        if not row:
            raise DynamicPlayoutError("playout_session_not_found", "playout session not found", status_code=404)
        return dict(row)

    async def request_stop(self, session_id: str, *, force: bool = False) -> dict:
        session = await self.get(session_id)
        if session["status"] in {"stopped", "failed"}:
            return session
        return await self.transition(session_id, "stopping", force=force)


playout_session_service = PlayoutSessionService()

