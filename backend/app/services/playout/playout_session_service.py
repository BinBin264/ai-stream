from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.core.database import db_connection
from app.services.avatar.render_job_repository import DEMO_TENANT_ID
from app.services.playout.dynamic_errors import DynamicPlayoutError
from app.services.playout.ffprobe_service import FFprobeService
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
        avatar_dir = backend_root() / "avatars" / avatar_id
        if not avatar_dir.is_dir():
            raise DynamicPlayoutError(
                "playout_idle_asset_missing",
                f"avatar directory is missing for {avatar_id}",
                status_code=404,
            )
        metadata = avatar_dir / "avatar.json"
        if not metadata.exists():
            raise DynamicPlayoutError(
                "playout_idle_asset_missing",
                f"avatar metadata is missing for {avatar_id}",
                status_code=404,
            )
        idle = avatar_dir / "idle_base.mp4"
        if not idle.exists():
            raise DynamicPlayoutError(
                "playout_idle_asset_missing",
                f"idle_base.mp4 is missing for avatar {avatar_id}",
                status_code=404,
            )
        return idle, self._relative_backend_path(idle)

    def preflight_idle_asset(self, avatar_id: str) -> tuple[Path, str]:
        idle, idle_rel = self.idle_path_for(avatar_id)
        if not idle.is_file() or idle.stat().st_size <= 0:
            raise DynamicPlayoutError("playout_idle_asset_missing", "idle_base.mp4 is not readable", status_code=404)
        try:
            probe = FFprobeService("ffprobe").probe(idle)
        except Exception as exc:
            raise DynamicPlayoutError("playout_ffprobe_failed", "ffprobe could not read idle_base.mp4") from exc
        if not probe.video_stream or not probe.duration_seconds or probe.duration_seconds <= 0:
            raise DynamicPlayoutError("playout_idle_asset_missing", "idle_base.mp4 has no valid video stream")
        return idle, idle_rel

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

    async def touch_heartbeat(self, session_id: str, *, output_updated_at=None) -> dict:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE playout_sessions
                SET last_heartbeat_at = now(),
                    last_output_update_at = COALESCE($2, last_output_update_at),
                    lease_expires_at = CASE
                        WHEN runtime_owner_id IS NOT NULL THEN now() + ($3::text || ' seconds')::interval
                        ELSE lease_expires_at
                    END,
                    updated_at = now()
                WHERE id = $1
                RETURNING *
                """,
                self._uuid(session_id),
                output_updated_at,
                str(settings.PLAYOUT_RUNTIME_HEARTBEAT_SECONDS * 3),
            )
        if not row:
            raise DynamicPlayoutError("playout_session_not_found", "playout session not found", status_code=404)
        return dict(row)

    async def acquire_lease(self, session_id: str, owner_id: str) -> bool:
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE playout_sessions
                SET runtime_owner_id = $2,
                    lease_expires_at = now() + ($3::text || ' seconds')::interval,
                    restart_count = restart_count + 1,
                    updated_at = now()
                WHERE id = $1
                  AND (
                    runtime_owner_id IS NULL
                    OR lease_expires_at IS NULL
                    OR lease_expires_at < now()
                    OR runtime_owner_id = $2
                  )
                  AND restart_count < $4
                RETURNING *
                """,
                self._uuid(session_id),
                owner_id,
                str(settings.PLAYOUT_RUNTIME_HEARTBEAT_SECONDS * 3),
                settings.PLAYOUT_MAX_RUNTIME_RESTARTS + 1,
            )
        return row is not None

    async def release_lease(self, session_id: str, owner_id: str) -> None:
        async with db_connection() as conn:
            await conn.execute(
                """
                UPDATE playout_sessions
                SET runtime_owner_id = NULL,
                    lease_expires_at = NULL,
                    updated_at = now()
                WHERE id = $1 AND runtime_owner_id = $2
                """,
                self._uuid(session_id),
                owner_id,
            )

    async def recoverable_sessions(self) -> list[dict]:
        async with db_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM playout_sessions
                WHERE status IN ('starting', 'idle', 'playing_talking', 'stopping')
                  AND restart_count < $1
                ORDER BY updated_at ASC
                """,
                settings.PLAYOUT_MAX_RUNTIME_RESTARTS + 1,
            )
        return [dict(row) for row in rows]

    async def prepare_recovery(self, session_id: str) -> dict:
        session = await self.get(session_id)
        target_status = "stopped" if session["status"] == "stopping" else "starting"
        async with db_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE playout_sessions
                SET status = $2,
                    active_segment_id = NULL,
                    runtime_owner_id = NULL,
                    lease_expires_at = NULL,
                    error_code = NULL,
                    error_message = NULL,
                    updated_at = now()
                WHERE id = $1
                RETURNING *
                """,
                self._uuid(session_id),
                target_status,
            )
        if not row:
            raise DynamicPlayoutError("playout_session_not_found", "playout session not found", status_code=404)
        return dict(row)

    async def delete(self, session_id: str) -> None:
        session = await self.get(session_id)
        if session["status"] not in {"stopped", "failed"}:
            raise DynamicPlayoutError(
                "playout_session_not_stopped",
                "can only delete a stopped or failed session",
                status_code=409,
            )
        async with db_connection() as conn:
            await conn.execute("DELETE FROM playout_segments WHERE playout_session_id = $1", self._uuid(session_id))
            await conn.execute("DELETE FROM playout_sessions WHERE id = $1", self._uuid(session_id))

    async def request_stop(self, session_id: str, *, force: bool = False) -> dict:
        session = await self.get(session_id)
        if session["status"] in {"stopped", "failed"}:
            return session
        return await self.transition(session_id, "stopping", force=force)


playout_session_service = PlayoutSessionService()
