"""Tests for path-safety utilities: safe_join and ensure_relative_safe."""

import pytest
from pathlib import Path

from app.services.playout.paths import ensure_relative_safe, safe_join
from app.services.playout.errors import PlayoutError


class TestEnsureRelativeSafe:
    def test_simple_filename_passes(self):
        result = ensure_relative_safe("segment.mp4")
        assert result == Path("segment.mp4")

    def test_nested_relative_path_passes(self):
        result = ensure_relative_safe("avatars/model_01/idle_base.mp4")
        assert result == Path("avatars/model_01/idle_base.mp4")

    def test_dotdot_at_start_rejected(self):
        with pytest.raises(PlayoutError) as exc_info:
            ensure_relative_safe("../etc/passwd")
        assert "safe relative path" in str(exc_info.value)

    def test_absolute_path_rejected(self):
        with pytest.raises(PlayoutError):
            ensure_relative_safe("/etc/passwd")

    def test_dotdot_in_middle_rejected(self):
        with pytest.raises(PlayoutError):
            ensure_relative_safe("foo/../bar/file.mp4")

    def test_dotdot_nested_rejected(self):
        with pytest.raises(PlayoutError):
            ensure_relative_safe("foo/../../etc/passwd")


class TestSafeJoin:
    def test_valid_relative_resolves(self, tmp_path: Path):
        result = safe_join(tmp_path, "subdir/file.mp4")
        assert result == tmp_path / "subdir" / "file.mp4"

    def test_simple_filename_resolves(self, tmp_path: Path):
        result = safe_join(tmp_path, "file.mp4")
        assert result == tmp_path / "file.mp4"

    def test_traversal_outside_root_rejected(self, tmp_path: Path):
        with pytest.raises(PlayoutError):
            safe_join(tmp_path, "../outside.mp4")

    def test_absolute_path_rejected(self, tmp_path: Path):
        with pytest.raises(PlayoutError):
            safe_join(tmp_path, "/etc/passwd")

    def test_multi_level_traversal_rejected(self, tmp_path: Path):
        with pytest.raises(PlayoutError):
            safe_join(tmp_path, "a/../../b/file.mp4")

    def test_deeply_nested_valid_path(self, tmp_path: Path):
        result = safe_join(tmp_path, "a/b/c/d.mp4")
        assert result == tmp_path / "a" / "b" / "c" / "d.mp4"
