"""Tests for LocalPreviewSink bookkeeping: trim window, atomic playlist write, sequence tracking.

All tests bypass FFmpeg by exercising the private bookkeeping methods directly.
The sink's output_dir is set to a tmp_path fixture directory.
"""

from pathlib import Path

import pytest

from app.services.playout.local_preview_sink import HlsSegment, LocalPreviewSink


def _make_sink(tmp_path: Path) -> LocalPreviewSink:
    sink = LocalPreviewSink()
    sink.output_dir = tmp_path
    sink.playlist_path = tmp_path / "index.m3u8"
    sink.sequence = 0
    sink._alive = True
    return sink


def _add_fake_segments(sink: LocalPreviewSink, count: int, duration: float = 2.0) -> None:
    """Populate sink._segments with fake TS files on disk."""
    for _ in range(count):
        filename = f"seg_{sink.sequence:08d}.ts"
        (sink.output_dir / filename).write_bytes(b"fake-ts")
        sink._segments.append(HlsSegment(sequence=sink.sequence, filename=filename, duration_seconds=duration))
        sink.sequence += 1


class TestTrimWindow:
    def test_removes_oldest_when_over_limit(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_LIST_SIZE", 3)
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 4)  # 4 segments, max 3

        sink._trim_window()

        assert len(sink._segments) == 3
        assert not (tmp_path / "seg_00000000.ts").exists(), "oldest segment should be deleted"
        assert (tmp_path / "seg_00000001.ts").exists()
        assert (tmp_path / "seg_00000002.ts").exists()
        assert (tmp_path / "seg_00000003.ts").exists()

    def test_no_removal_within_limit(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_LIST_SIZE", 5)
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 3)

        sink._trim_window()

        assert len(sink._segments) == 3
        for i in range(3):
            assert (tmp_path / f"seg_{i:08d}.ts").exists()

    def test_removes_multiple_excess(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_LIST_SIZE", 2)
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 5)

        sink._trim_window()

        assert len(sink._segments) == 2
        for i in range(3):
            assert not (tmp_path / f"seg_{i:08d}.ts").exists(), f"seg_{i} should be deleted"
        assert (tmp_path / "seg_00000003.ts").exists()
        assert (tmp_path / "seg_00000004.ts").exists()

    def test_sequence_numbers_of_retained_segments_are_correct(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_LIST_SIZE", 2)
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 4)

        sink._trim_window()

        retained_seqs = [s.sequence for s in sink._segments]
        assert retained_seqs == [2, 3]


class TestWritePlaylist:
    def test_atomic_write_leaves_no_tmp_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_TIME_SECONDS", 2)
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 1)

        sink._write_playlist(endlist=False)

        assert not (tmp_path / ".index.m3u8.tmp").exists()
        assert (tmp_path / "index.m3u8").exists()

    def test_playlist_contains_all_segments(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_TIME_SECONDS", 2)
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 3)

        sink._write_playlist(endlist=False)

        content = (tmp_path / "index.m3u8").read_text()
        assert "#EXTM3U" in content
        assert "#EXT-X-VERSION:3" in content
        for i in range(3):
            assert f"seg_{i:08d}.ts" in content

    def test_no_endlist_when_live(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_TIME_SECONDS", 2)
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 1)

        sink._write_playlist(endlist=False)

        content = (tmp_path / "index.m3u8").read_text()
        assert "#EXT-X-ENDLIST" not in content

    def test_endlist_appended_on_stop(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_TIME_SECONDS", 2)
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 1)

        sink._write_playlist(endlist=True)

        content = (tmp_path / "index.m3u8").read_text()
        assert "#EXT-X-ENDLIST" in content

    def test_media_sequence_tracks_oldest_segment(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_LIST_SIZE", 2)
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_TIME_SECONDS", 2)
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 4)
        sink._trim_window()  # retains seqs 2,3

        sink._write_playlist(endlist=False)

        content = (tmp_path / "index.m3u8").read_text()
        assert "#EXT-X-MEDIA-SEQUENCE:2" in content

    def test_extinf_lines_match_duration(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_TIME_SECONDS", 2)
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 2, duration=3.5)

        sink._write_playlist(endlist=False)

        content = (tmp_path / "index.m3u8").read_text()
        assert "#EXTINF:3.500," in content

    def test_idempotent_overwrite(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PLAYOUT_HLS_TIME_SECONDS", 2)
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 1)

        sink._write_playlist(endlist=False)
        first = (tmp_path / "index.m3u8").read_text()

        sink._write_playlist(endlist=False)
        second = (tmp_path / "index.m3u8").read_text()

        assert first == second


class TestSequenceTracking:
    def test_sequence_starts_at_zero(self, tmp_path: Path):
        sink = _make_sink(tmp_path)
        assert sink.sequence == 0

    def test_each_append_increments_sequence(self, tmp_path: Path):
        sink = _make_sink(tmp_path)
        _add_fake_segments(sink, 3)
        assert sink.sequence == 3
        seqs = [s.sequence for s in sink._segments]
        assert seqs == [0, 1, 2]
