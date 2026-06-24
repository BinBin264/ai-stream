from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.services.playout.dynamic_errors import DynamicPlayoutError
from app.services.playout.ffprobe_service import FFprobeService
from app.services.playout.paths import ensure_relative_safe, safe_join


class SegmentPreflightValidator:
    def __init__(self, ffprobe: FFprobeService | None = None) -> None:
        self.ffprobe = ffprobe or FFprobeService(settings.FFPROBE_BIN)

    def media_root(self) -> Path:
        return Path(settings.MEDIA_OUTPUT_DIR)

    def resolve_source(self, source_video_path: str) -> Path:
        try:
            return safe_join(self.media_root(), source_video_path, field="source_video_path")
        except Exception as exc:
            raise DynamicPlayoutError("playout_segment_invalid", "source video path is invalid") from exc

    def relative_to_media_root(self, path: Path) -> str:
        root = self.media_root().resolve()
        resolved = path.resolve()
        try:
            return str(resolved.relative_to(root))
        except ValueError as exc:
            raise DynamicPlayoutError("playout_segment_invalid", "source video must be under media output root") from exc

    def validate_relative_path(self, source_video_path: str) -> str:
        ensure_relative_safe(source_video_path, field="source_video_path")
        source = self.resolve_source(source_video_path)
        if not source.exists():
            raise DynamicPlayoutError("playout_segment_missing", "source video does not exist", status_code=404)
        if source.stat().st_size <= 0:
            raise DynamicPlayoutError("playout_segment_invalid", "source video is empty")
        self._probe(source)
        return source_video_path

    def validate_absolute_runtime_output(self, source_video_path: str) -> str:
        path = Path(source_video_path)
        if not path.is_absolute():
            return self.validate_relative_path(source_video_path)
        if not path.exists() or path.stat().st_size <= 0:
            raise DynamicPlayoutError("playout_segment_missing", "render output video does not exist", status_code=404)
        self._probe(path)
        return self.relative_to_media_root(path)

    def _probe(self, path: Path) -> None:
        try:
            probe = self.ffprobe.probe(path)
        except Exception as exc:
            raise DynamicPlayoutError("playout_ffprobe_failed", "ffprobe could not read source video") from exc
        if not probe.video_stream:
            raise DynamicPlayoutError("playout_segment_invalid", "source video has no video stream")
        duration = probe.duration_seconds or 0
        if duration <= 0:
            raise DynamicPlayoutError("playout_segment_invalid", "source video has no valid duration")
        if duration > settings.PLAYOUT_SEGMENT_MAX_DURATION_SECONDS:
            raise DynamicPlayoutError("playout_segment_invalid", "source video exceeds max segment duration")


segment_preflight_validator = SegmentPreflightValidator()

