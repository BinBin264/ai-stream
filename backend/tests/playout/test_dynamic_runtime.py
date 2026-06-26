"""Tests for DynamicPlayoutRuntime: pacing, segment state transitions, stop behaviour.

Services (playout_segment_service, playout_session_service, playout_segment_queue) and
safe_join are monkeypatched so no Redis, DB, or FFmpeg is needed.
"""

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import app.services.playout.dynamic_runtime as dr_module
from app.services.playout.dynamic_errors import DynamicPlayoutError
from app.services.playout.dynamic_runtime import DynamicPlayoutRuntime
from app.services.playout.playout_output_sink import PlaybackReceipt


# ── helpers ───────────────────────────────────────────────────────────────────

def _receipt(duration: float = 0.0) -> PlaybackReceipt:
    now = datetime.now(timezone.utc)
    return PlaybackReceipt(
        output_path="playout/live/test/seg_00000000.ts",
        duration_seconds=duration,
        started_at=now,
        appended_at=now,
        sequence_number=0,
    )


class FakeSink:
    """Sink that records call order without invoking FFmpeg."""

    def __init__(self, *, append_duration: float = 0.0, fail_append: bool = False) -> None:
        self.calls: list[str] = []
        self._duration = append_duration
        self._fail = fail_append
        self._alive = True

    async def start(self, session_id: str) -> str:
        self.calls.append("start")
        return f"playout/live/{session_id}/index.m3u8"

    async def append_idle(self, *, source_path: Path, duration_seconds: int) -> PlaybackReceipt:
        self.calls.append("append_idle")
        return _receipt(float(duration_seconds))

    async def append_talking(self, *, source_path: Path) -> PlaybackReceipt:
        if self._fail:
            raise DynamicPlayoutError("playout_hls_output_failed", "ffmpeg failed")
        self.calls.append("append_talking")
        return _receipt(self._duration)

    async def stop(self) -> None:
        self.calls.append("stop")
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive

    def last_output_update_at(self):
        return None


def _patch_services(monkeypatch, *, mark_playing_return=None):
    """Install no-op async mocks for all module-level service singletons."""
    monkeypatch.setattr(dr_module.playout_segment_service, "mark_playing",
                        AsyncMock(return_value=mark_playing_return or {}))
    monkeypatch.setattr(dr_module.playout_segment_service, "mark_completed", AsyncMock())
    monkeypatch.setattr(dr_module.playout_segment_service, "mark_failed", AsyncMock())
    monkeypatch.setattr(dr_module.playout_session_service, "transition", AsyncMock())
    monkeypatch.setattr(dr_module.playout_session_service, "touch_heartbeat", AsyncMock())
    monkeypatch.setattr(dr_module.playout_segment_queue, "publish_event", AsyncMock())
    monkeypatch.setattr(dr_module, "safe_join",
                        lambda root, rel, field="path": Path("/tmp/fake.mp4"))


# ── _wait_for_playback ────────────────────────────────────────────────────────

class TestWaitForPlayback:
    async def test_zero_duration_returns_true_immediately(self):
        rt = DynamicPlayoutRuntime("s1")
        start = time.monotonic()
        assert await rt._wait_for_playback(0.0, interrupt_on_graceful_stop=False) is True
        assert time.monotonic() - start < 0.2

    async def test_duration_actually_elapses(self):
        rt = DynamicPlayoutRuntime("s1")
        start = time.monotonic()
        assert await rt._wait_for_playback(0.12, interrupt_on_graceful_stop=False) is True
        assert time.monotonic() - start >= 0.10

    async def test_force_stop_already_set_returns_false_fast(self):
        rt = DynamicPlayoutRuntime("s1")
        rt._force_stop_event.set()
        start = time.monotonic()
        assert await rt._wait_for_playback(60.0, interrupt_on_graceful_stop=False) is False
        assert time.monotonic() - start < 1.0

    async def test_force_stop_set_async_during_wait(self):
        rt = DynamicPlayoutRuntime("s1")

        async def arm():
            await asyncio.sleep(0.05)
            rt._force_stop_event.set()

        start = time.monotonic()
        _, result = await asyncio.gather(
            arm(),
            rt._wait_for_playback(60.0, interrupt_on_graceful_stop=False),
        )
        assert result is False
        assert time.monotonic() - start < 2.0

    async def test_graceful_stop_interrupts_idle_wait(self):
        rt = DynamicPlayoutRuntime("s1")
        rt._stop_event.set()
        start = time.monotonic()
        result = await rt._wait_for_playback(60.0, interrupt_on_graceful_stop=True)
        assert result is True   # graceful → completes (not crashed)
        assert time.monotonic() - start < 1.0

    async def test_graceful_stop_does_not_cut_segment_wait(self):
        """interrupt_on_graceful_stop=False means stop_event is ignored for talking segments."""
        rt = DynamicPlayoutRuntime("s1")
        rt._stop_event.set()
        start = time.monotonic()
        result = await rt._wait_for_playback(0.08, interrupt_on_graceful_stop=False)
        assert result is True
        assert time.monotonic() - start >= 0.06

    async def test_negative_duration_treated_as_zero(self):
        rt = DynamicPlayoutRuntime("s1")
        start = time.monotonic()
        assert await rt._wait_for_playback(-5.0, interrupt_on_graceful_stop=False) is True
        assert time.monotonic() - start < 0.5


# ── _play_segment: call ordering ─────────────────────────────────────────────

class TestPlaySegmentOrdering:
    async def test_append_talking_before_mark_playing(self, monkeypatch):
        """Core invariant for the Part B fix: append must precede state update."""
        call_log: list[str] = []
        sink = FakeSink(append_duration=0.0)
        original_append = sink.append_talking

        async def traced_append(**kwargs):
            result = await original_append(**kwargs)
            call_log.append("append_talking")
            return result

        sink.append_talking = traced_append  # type: ignore[method-assign]

        async def traced_mark_playing(segment_id):
            call_log.append("mark_playing")
            return {}

        monkeypatch.setattr(dr_module.playout_segment_service, "mark_playing", traced_mark_playing)
        monkeypatch.setattr(dr_module.playout_segment_service, "mark_completed", AsyncMock())
        monkeypatch.setattr(dr_module.playout_session_service, "transition", AsyncMock())
        monkeypatch.setattr(dr_module.playout_session_service, "touch_heartbeat", AsyncMock())
        monkeypatch.setattr(dr_module.playout_segment_queue, "publish_event", AsyncMock())
        monkeypatch.setattr(dr_module, "safe_join",
                            lambda root, rel, field="path": Path("/tmp/fake.mp4"))

        rt = DynamicPlayoutRuntime("s1")
        rt._sink = sink

        await rt._play_segment({"id": "seg-001", "source_video_path": "test/test.mp4"})

        assert "append_talking" in call_log, f"append_talking not called: {call_log}"
        assert "mark_playing" in call_log, f"mark_playing not called: {call_log}"
        assert call_log.index("append_talking") < call_log.index("mark_playing"), \
            f"Wrong order: {call_log}"

    async def test_append_failure_skips_mark_playing(self, monkeypatch):
        """If append_talking raises, mark_playing must NOT be called."""
        sink = FakeSink(fail_append=True)

        mark_playing_calls: list[str] = []

        async def fake_mark_playing(seg_id):
            mark_playing_calls.append(seg_id)
            return {}

        mark_failed_calls: list[tuple] = []

        async def fake_mark_failed(seg_id, code, message):
            mark_failed_calls.append((seg_id, code))

        monkeypatch.setattr(dr_module.playout_segment_service, "mark_playing", fake_mark_playing)
        monkeypatch.setattr(dr_module.playout_segment_service, "mark_failed", fake_mark_failed)
        monkeypatch.setattr(dr_module.playout_segment_queue, "publish_event", AsyncMock())
        monkeypatch.setattr(dr_module, "safe_join",
                            lambda root, rel, field="path": Path("/tmp/fake.mp4"))

        rt = DynamicPlayoutRuntime("s1")
        rt._sink = sink

        await rt._play_segment({"id": "seg-002", "source_video_path": "test.mp4"})

        assert mark_playing_calls == [], "mark_playing must NOT be called when append fails"
        assert len(mark_failed_calls) == 1
        assert mark_failed_calls[0][0] == "seg-002"

    async def test_mark_completed_after_full_wait(self, monkeypatch):
        """mark_completed is called only after the playback duration has elapsed."""
        sink = FakeSink(append_duration=0.06)
        _patch_services(monkeypatch)

        mark_completed_calls: list[str] = []

        async def fake_mark_completed(seg_id):
            mark_completed_calls.append(seg_id)

        monkeypatch.setattr(dr_module.playout_segment_service, "mark_completed", fake_mark_completed)

        rt = DynamicPlayoutRuntime("s1")
        rt._sink = sink

        start = time.monotonic()
        await rt._play_segment({"id": "seg-003", "source_video_path": "test.mp4"})
        elapsed = time.monotonic() - start

        assert mark_completed_calls == ["seg-003"]
        assert elapsed >= 0.05, "should have waited for the segment duration"

    async def test_force_stop_during_wait_marks_failed_not_completed(self, monkeypatch):
        """Segment interrupted by force stop → failed, not completed."""
        sink = FakeSink(append_duration=60.0)
        _patch_services(monkeypatch)

        completed: list[str] = []
        failed: list[tuple] = []

        async def fake_completed(seg_id):
            completed.append(seg_id)

        async def fake_failed(seg_id, code, msg):
            failed.append((seg_id, code))

        monkeypatch.setattr(dr_module.playout_segment_service, "mark_completed", fake_completed)
        monkeypatch.setattr(dr_module.playout_segment_service, "mark_failed", fake_failed)

        rt = DynamicPlayoutRuntime("s1")
        rt._sink = sink

        async def force_stop():
            await asyncio.sleep(0.05)
            rt.request_force_stop()

        start = time.monotonic()
        await asyncio.gather(
            force_stop(),
            rt._play_segment({"id": "seg-004", "source_video_path": "test.mp4"}),
        )

        assert time.monotonic() - start < 5.0, "force stop should interrupt quickly"
        assert completed == [], "mark_completed must NOT be called after force stop"
        assert len(failed) == 1
        assert failed[0] == ("seg-004", "playout_runtime_crashed")


# ── stop / force_stop ─────────────────────────────────────────────────────────

class TestStopEvents:
    def test_request_stop_sets_stop_event(self):
        rt = DynamicPlayoutRuntime("s1")
        rt.request_stop()
        assert rt._stop_event.is_set()
        assert not rt._force_stop_event.is_set()

    def test_request_force_stop_sets_both_events(self):
        rt = DynamicPlayoutRuntime("s1")
        rt.request_force_stop()
        assert rt._stop_event.is_set()
        assert rt._force_stop_event.is_set()
