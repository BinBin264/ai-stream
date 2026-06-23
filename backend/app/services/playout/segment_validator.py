from __future__ import annotations

from pathlib import Path

from app.services.playout.errors import (
    PLAYOUT_AVATAR_NOT_FOUND,
    PLAYOUT_IDLE_ASSET_MISSING,
    PLAYOUT_TALKING_SEGMENT_INVALID,
    PLAYOUT_TALKING_SEGMENT_MISSING,
    PLAYOUT_UNSUPPORTED_MEDIA,
    PlayoutError,
)
from app.services.playout.media_format_policy import MediaFormatPolicy
from app.services.playout.paths import safe_join
from app.services.playout.schemas import PlayoutManifest, SegmentValidation


class SegmentValidator:
    def __init__(
        self,
        *,
        backend_root: Path,
        media_root: Path,
        probe_service,
        policy: MediaFormatPolicy,
    ) -> None:
        self.backend_root = backend_root
        self.media_root = media_root
        self.probe_service = probe_service
        self.policy = policy

    def idle_path_for(self, avatar_id: str) -> Path:
        avatar_dir = self.backend_root / "avatars" / avatar_id
        if not avatar_dir.exists():
            raise PlayoutError(PLAYOUT_AVATAR_NOT_FOUND, "avatar directory does not exist", status_code=404)
        idle_path = avatar_dir / "idle_base.mp4"
        if not idle_path.exists():
            raise PlayoutError(PLAYOUT_IDLE_ASSET_MISSING, "avatar idle_base.mp4 is missing", status_code=404)
        return idle_path

    def validate_idle(self, manifest: PlayoutManifest) -> SegmentValidation:
        idle_path = self.idle_path_for(manifest.avatar_id)
        try:
            probe = self.probe_service.probe(idle_path)
        except PlayoutError as exc:
            raise PlayoutError(PLAYOUT_UNSUPPORTED_MEDIA, "idle video could not be probed") from exc
        check = self.policy.classify(probe)
        if check.status == "fail":
            raise PlayoutError(PLAYOUT_TALKING_SEGMENT_INVALID, "idle video is unsupported")
        return SegmentValidation(
            segment_id="idle",
            source_path=f"avatars/{manifest.avatar_id}/idle_base.mp4",
            absolute_path=str(idle_path),
            duration_seconds=probe.duration_seconds or 0,
            format_check=check,
        )

    def validate_talking(self, manifest: PlayoutManifest) -> list[SegmentValidation]:
        results: list[SegmentValidation] = []
        for segment in manifest.talking_segments:
            source = safe_join(self.media_root, segment.source_path, field="source_path")
            if not source.exists():
                raise PlayoutError(
                    PLAYOUT_TALKING_SEGMENT_MISSING,
                    f"talking segment is missing: {segment.segment_id}",
                    status_code=404,
                )
            try:
                probe = self.probe_service.probe(source)
            except PlayoutError as exc:
                raise PlayoutError(
                    PLAYOUT_TALKING_SEGMENT_INVALID,
                    f"talking segment could not be probed: {segment.segment_id}",
                ) from exc
            check = self.policy.classify(probe)
            if check.status == "fail":
                raise PlayoutError(
                    PLAYOUT_TALKING_SEGMENT_INVALID,
                    f"talking segment is unsupported: {segment.segment_id}",
                )
            duration = segment.duration_seconds or probe.duration_seconds or 0
            if duration <= 0:
                raise PlayoutError(
                    PLAYOUT_TALKING_SEGMENT_INVALID,
                    f"talking segment has no duration: {segment.segment_id}",
                )
            results.append(
                SegmentValidation(
                    segment_id=segment.segment_id,
                    source_path=segment.source_path,
                    absolute_path=str(source),
                    duration_seconds=duration,
                    format_check=check,
                )
            )
        return results
