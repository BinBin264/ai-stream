from __future__ import annotations

import asyncio
import logging
import time
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
    def __init__(self, session_id: str, *, owner_id: str | None = None) -> None:
        self.session_id = session_id
        self.owner_id = owner_id
        self._stop_event = asyncio.Event()
        self._force_stop_event = asyncio.Event()
        self._sink = None
        self._idle_offset: float = 0.0
        self._idle_duration: float | None = None

    def request_stop(self) -> None:
        self._stop_event.set()

    def request_force_stop(self) -> None:
        self._stop_event.set()
        self._force_stop_event.set()

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
                if self._force_stop_event.is_set() or session["status"] == "stopping":
                    break
                if session["status"] == "failed":
                    return

                segment = await playout_segment_service.next_ready(self.session_id)
                if segment is None:
                    await self._append_idle_chunk(idle_path)
                    continue

                await self._play_segment(segment)
                session = await playout_session_service.get(self.session_id)
                if session["status"] == "stopping" or self._stop_event.is_set():
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
        finally:
            if self.owner_id:
                await playout_session_service.release_lease(self.session_id, self.owner_id)

    async def _probe_idle_duration(self, idle_path: Path) -> float:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(idle_path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return max(1.0, float(stdout.decode().strip()))
        except Exception:
            return float(max(1, settings.PLAYOUT_HLS_TIME_SECONDS))

    async def _append_idle_chunk(self, idle_path: Path) -> None:
        assert self._sink is not None
        if self._idle_duration is None:
            self._idle_duration = await self._probe_idle_duration(idle_path)

        chunk_duration = max(1, settings.PLAYOUT_HLS_TIME_SECONDS)
        started = time.monotonic()
        receipt = await self._sink.append_idle(
            source_path=idle_path,
            duration_seconds=chunk_duration,
            start_offset=self._idle_offset,
        )
        # Advance position through the idle video, wrapping at the end.
        self._idle_offset = (self._idle_offset + chunk_duration) % self._idle_duration

        # Pace to ~2× real-time: sleep half the remaining time so the HLS
        # live edge stays 1-2 segments ahead of the player without racing
        # so far ahead that hls.js loses track.
        remaining = receipt.duration_seconds - (time.monotonic() - started)
        if remaining > 0.05:
            await self._wait_for_playback(remaining * 0.5, interrupt_on_graceful_stop=True)
        await playout_session_service.touch_heartbeat(
            self.session_id,
            output_updated_at=receipt.appended_at,
        )

    async def _play_segment(self, segment: dict) -> None:
        assert self._sink is not None
        segment_id = str(segment["id"])
        try:
            source = safe_join(Path(settings.MEDIA_OUTPUT_DIR), str(segment["source_video_path"]), field="source_video_path")
            receipt = await self._sink.append_talking(source_path=source)
            # HLS write succeeded — only now update DB state
            await playout_segment_service.mark_playing(segment_id)
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
            completed = await self._wait_for_playback(receipt.duration_seconds, interrupt_on_graceful_stop=False)
            if not completed:
                await playout_segment_service.mark_failed(
                    segment_id,
                    "playout_runtime_crashed",
                    "playback interrupted by force stop",
                )
                return
            await playout_segment_service.mark_completed(segment_id)
            await playout_session_service.touch_heartbeat(
                self.session_id,
                output_updated_at=receipt.appended_at,
            )
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

    async def _wait_for_playback(self, duration_seconds: float, *, interrupt_on_graceful_stop: bool) -> bool:
        duration = max(0.0, duration_seconds)
        deadline = time.monotonic() + duration
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            if self._force_stop_event.is_set():
                return False
            wait_task = asyncio.create_task(self._force_stop_event.wait())
            stop_task = None
            tasks = {wait_task}
            if interrupt_on_graceful_stop:
                stop_task = asyncio.create_task(self._stop_event.wait())
                tasks.add(stop_task)
            done, pending = await asyncio.wait(tasks, timeout=min(remaining, 0.5), return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            if stop_task and stop_task in done and self._stop_event.is_set():
                return True
            if wait_task in done and self._force_stop_event.is_set():
                return False

    def _error_code(self, exc: Exception) -> str:
        if isinstance(exc, DynamicPlayoutError):
            return exc.code
        return "playout_runtime_crashed"
