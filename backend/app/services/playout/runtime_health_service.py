from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import settings
from app.services.playout.playout_segment_service import playout_segment_service
from app.services.playout.playout_session_service import playout_session_service


class RuntimeHealthService:
    async def health(self, session_id: str, *, runtime_alive: bool = False, last_output_update_at=None) -> dict:
        session = await playout_session_service.get(session_id)
        queued = await playout_segment_service.count_queue(session_id)
        heartbeat_alive = False
        last_heartbeat = session.get("last_heartbeat_at")
        if last_heartbeat is not None and session["status"] in {"starting", "idle", "playing_talking", "stopping"}:
            now = datetime.now(timezone.utc)
            heartbeat_alive = (now - last_heartbeat).total_seconds() <= settings.PLAYOUT_RUNTIME_HEARTBEAT_SECONDS * 3
        return {
            "session_id": session_id,
            "status": session["status"],
            "runtime_alive": runtime_alive or heartbeat_alive,
            "active_segment_id": str(session["active_segment_id"]) if session.get("active_segment_id") else None,
            "queued_segments": queued,
            "last_heartbeat_at": session.get("last_heartbeat_at"),
            "last_output_update_at": last_output_update_at or session.get("last_output_update_at"),
            "output_path": session.get("output_path"),
            "last_error_code": session.get("error_code"),
        }


runtime_health_service = RuntimeHealthService()
