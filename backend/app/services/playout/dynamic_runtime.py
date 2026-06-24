from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.config import settings
from app.services.playout.dynamic_errors import DynamicPlayoutError
from app.services.playout.ffmpeg_runtime_process import make_output_sink
from app.services.playout.paths import backend_root, safe_join
from app.services.playout.playout_segment_queue import playout_segment_queue
from app.services.playout.playout_segment_service import playout_segment_service
from app.services.playout.playout_session_service import playout_session_service

logger = logging.getLogger(__name__)


class DynamicPlayoutRuntime:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._force_stop = False
        self._sink = None

    def request_force_stop(self) -> None:
        self._force_stop = True

    async def run(self) -> None:
        if not settings.PLAYOUT_RUNTIME_ENABLED:
            await playout_session_service.transition(
                self.session_id,
                "failed",
                force=True,
                error_code="playout_runtime_not_available",
                error_message="playout runtime is disabled",
            )
            return

        session = await playout_session_service.get(self.session_id)
        idle_path = safe_join(backend_root(), session["idle_video_path"], field="idle_video_path")
        self._sink = make_output_sink(str(session["output_mode"]))

        try:
            output_path = await self._sink.start(self.session_id)
            if session["status"] == "starting":
                await playout_session_service.transition(self.session_id, "idle", output_path=output_path)
            await playout_segment_queue.publish_event(
                {"event_type": "playout.session.idle", "session_id": self.session_id}
            )

            while True:
                session = await playout_session_service.get(self.session_id)
                if self._force_stop or session["status"] == "stopping":
                    break
                if session["status"] == "failed":
                    return

                segment = await playout_segment_service.next_ready(self.session_id)
                if segment is None:
                    await self._append_idle_chunk(idle_path)
                    continue

                await self._play_segment(segment)
                session = await playout_session_service.get(self.session_id)
                if session["status"] == "stopping" or self._force_stop:
                    break
                await playout_session_service.transition(self.session_id, "idle")
                await playout_segment_queue.publish_event(
                    {"event_type": "playout.session.idle", "session_id": self.session_id}
                )

            await self._sink.stop()
            await playout_session_service.transition(self.session_id, "stopped", force=True)
            await playout_segment_queue.publish_event(
                {"event_type": "playout.session.stopped", "session_id": self.session_id}
            )
        except Exception as exc:
            logger.exception("Dynamic playout runtime failed", extra={"session_id": self.session_id})
            try:
                if self._sink:
                    await self._sink.stop()
            except Exception:
                logger.exception("Failed to stop playout sink", extra={"session_id": self.session_id})
            await playout_session_service.transition(
                self.session_id,
                "failed",
                force=True,
                error_code=self._error_code(exc),
                error_message=str(exc),
            )
            await playout_segment_queue.publish_event(
                {
                    "event_type": "playout.session.failed",
                    "session_id": self.session_id,
                    "error_code": self._error_code(exc),
                }
            )

    async def _append_idle_chunk(self, idle_path: Path) -> None:
        assert self._sink is not None
        await self._sink.append_idle(
            source_path=idle_path,
            duration_seconds=max(1, settings.PLAYOUT_HLS_TIME_SECONDS),
        )
        await playout_session_service.touch_heartbeat(self.session_id)
        await asyncio.sleep(0)

    async def _play_segment(self, segment: dict) -> None:
        assert self._sink is not None
        segment_id = str(segment["id"])
        try:
            segment = await playout_segment_service.mark_playing(segment_id)
            await playout_session_service.transition(
                self.session_id,
                "playing_talking",
                active_segment_id=segment_id,
            )
            await playout_segment_queue.publish_event(
                {
                    "event_type": "playout.segment.playing",
                    "session_id": self.session_id,
                    "segment_id": segment_id,
                }
            )
            source = Path(settings.MEDIA_OUTPUT_DIR) / str(segment["source_video_path"])
            await self._sink.append_talking(source_path=source)
            await playout_segment_service.mark_completed(segment_id)
            await playout_segment_queue.publish_event(
                {
                    "event_type": "playout.segment.completed",
                    "session_id": self.session_id,
                    "segment_id": segment_id,
                }
            )
        except Exception as exc:
            await playout_segment_service.mark_failed(segment_id, self._error_code(exc), str(exc))
            await playout_segment_queue.publish_event(
                {
                    "event_type": "playout.segment.failed",
                    "session_id": self.session_id,
                    "segment_id": segment_id,
                    "error_code": self._error_code(exc),
                }
            )

    def is_alive(self) -> bool:
        return bool(self._sink and self._sink.is_alive())

    def last_output_update_at(self):
        return self._sink.last_output_update_at() if self._sink else None

    def _error_code(self, exc: Exception) -> str:
        if isinstance(exc, DynamicPlayoutError):
            return exc.code
        return "playout_runtime_crashed"
