"""Tests for SegmentPreflightValidator: missing file, empty file, path traversal, no video stream."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.playout.dynamic_errors import DynamicPlayoutError
from app.services.playout.errors import PlayoutError
from app.services.playout.segment_preflight_validator import SegmentPreflightValidator


class FakeFFprobe:
    def __init__(self, *, has_video: bool = True, duration: float = 5.0, raises: bool = False) -> None:
        self._has_video = has_video
        self._duration = duration
        self._raises = raises

    def probe(self, path: Path):
        if self._raises:
            raise RuntimeError("ffprobe unavailable")
        result = MagicMock()
        result.video_stream = MagicMock() if self._has_video else None
        result.duration_seconds = self._duration
        return result


def _validator(tmp_path: Path, monkeypatch, **ffprobe_kwargs) -> SegmentPreflightValidator:
    monkeypatch.setattr("app.core.config.settings.MEDIA_OUTPUT_DIR", str(tmp_path))
    return SegmentPreflightValidator(ffprobe=FakeFFprobe(**ffprobe_kwargs))


class TestValidateRelativePath:
    def test_valid_file_passes(self, tmp_path: Path, monkeypatch):
        (tmp_path / "test.mp4").write_bytes(b"fake-video-data")
        v = _validator(tmp_path, monkeypatch)
        assert v.validate_relative_path("test.mp4") == "test.mp4"

    def test_missing_file_raises_segment_missing(self, tmp_path: Path, monkeypatch):
        v = _validator(tmp_path, monkeypatch)
        with pytest.raises(DynamicPlayoutError) as exc_info:
            v.validate_relative_path("nonexistent.mp4")
        assert exc_info.value.code == "playout_segment_missing"

    def test_empty_file_raises_segment_invalid(self, tmp_path: Path, monkeypatch):
        (tmp_path / "empty.mp4").write_bytes(b"")
        v = _validator(tmp_path, monkeypatch)
        with pytest.raises(DynamicPlayoutError) as exc_info:
            v.validate_relative_path("empty.mp4")
        assert exc_info.value.code == "playout_segment_invalid"

    def test_path_traversal_raises(self, tmp_path: Path, monkeypatch):
        # ensure_relative_safe raises PlayoutError (not DynamicPlayoutError) for traversal
        v = _validator(tmp_path, monkeypatch)
        with pytest.raises((PlayoutError, DynamicPlayoutError)):
            v.validate_relative_path("../escape.mp4")

    def test_absolute_path_raises(self, tmp_path: Path, monkeypatch):
        v = _validator(tmp_path, monkeypatch)
        with pytest.raises((PlayoutError, DynamicPlayoutError)):
            v.validate_relative_path("/etc/passwd")

    def test_no_video_stream_raises_invalid(self, tmp_path: Path, monkeypatch):
        (tmp_path / "audio_only.mp4").write_bytes(b"audio-data")
        v = _validator(tmp_path, monkeypatch, has_video=False)
        with pytest.raises(DynamicPlayoutError) as exc_info:
            v.validate_relative_path("audio_only.mp4")
        assert exc_info.value.code == "playout_segment_invalid"

    def test_zero_duration_raises_invalid(self, tmp_path: Path, monkeypatch):
        (tmp_path / "zero.mp4").write_bytes(b"content")
        v = _validator(tmp_path, monkeypatch, duration=0.0)
        with pytest.raises(DynamicPlayoutError) as exc_info:
            v.validate_relative_path("zero.mp4")
        assert exc_info.value.code == "playout_segment_invalid"

    def test_ffprobe_failure_raises_ffprobe_failed(self, tmp_path: Path, monkeypatch):
        (tmp_path / "bad.mp4").write_bytes(b"content")
        v = _validator(tmp_path, monkeypatch, raises=True)
        with pytest.raises(DynamicPlayoutError) as exc_info:
            v.validate_relative_path("bad.mp4")
        assert exc_info.value.code == "playout_ffprobe_failed"

    def test_nested_valid_path(self, tmp_path: Path, monkeypatch):
        subdir = tmp_path / "renders" / "session_01"
        subdir.mkdir(parents=True)
        (subdir / "output.mp4").write_bytes(b"data")
        v = _validator(tmp_path, monkeypatch)
        assert v.validate_relative_path("renders/session_01/output.mp4") == "renders/session_01/output.mp4"
