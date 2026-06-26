from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.playout.errors import (
    PLAYOUT_CONCAT_FAILED,
    PLAYOUT_FFMPEG_MISSING,
    PLAYOUT_NORMALIZATION_FAILED,
    PLAYOUT_OUTPUT_INVALID,
    PLAYOUT_OUTPUT_MISSING,
    PlayoutError,
)
from app.services.playout.ffmpeg_runner import FFmpegRunner
from app.services.playout.ffprobe_service import FFprobeService
from app.services.playout.media_format_policy import MediaFormatPolicy
from app.services.playout.paths import backend_root as default_backend_root
from app.services.playout.paths import relative_to_backend, safe_join
from app.services.playout.schemas import (
    AutomatedChecks,
    PlayoutManifest,
    ProgramBuildResult,
    ProgramMetadata,
    TimelinePlan,
    ValidationReport,
)
from app.services.playout.segment_normalizer import SegmentNormalizer
from app.services.playout.segment_validator import SegmentValidator
from app.services.playout.timeline_planner import TimelinePlanner


class ProgramBuilder:
    def __init__(
        self,
        *,
        backend_root: Path | None = None,
        media_root: Path | None = None,
        probe_service=None,
        runner=None,
        policy: MediaFormatPolicy | None = None,
    ) -> None:
        self.backend_root = backend_root or default_backend_root()
        self.media_root = media_root or self.backend_root / "media"
        self.playout_root = self.backend_root / settings.PLAYOUT_MEDIA_ROOT
        self.manifest_dir = self.backend_root / settings.PLAYOUT_MANIFEST_DIR
        self.normalized_dir = self.backend_root / settings.PLAYOUT_NORMALIZED_DIR
        self.program_dir = self.backend_root / settings.PLAYOUT_PROGRAM_DIR
        self.policy = policy or MediaFormatPolicy(
            target_width=settings.PLAYOUT_TARGET_WIDTH,
            target_height=settings.PLAYOUT_TARGET_HEIGHT,
            target_fps=settings.PLAYOUT_TARGET_FPS,
            video_codec=settings.PLAYOUT_TARGET_VIDEO_CODEC,
            audio_codec=settings.PLAYOUT_TARGET_AUDIO_CODEC,
            pixel_format=settings.PLAYOUT_TARGET_PIXEL_FORMAT,
            audio_rate=settings.PLAYOUT_TARGET_AUDIO_RATE,
            audio_channels=settings.PLAYOUT_TARGET_AUDIO_CHANNELS,
        )
        self.probe_service = probe_service or FFprobeService("ffprobe")
        self.runner = runner or FFmpegRunner("ffmpeg")
        self.validator = SegmentValidator(
            backend_root=self.backend_root,
            media_root=self.media_root,
            probe_service=self.probe_service,
            policy=self.policy,
        )
        self.planner = TimelinePlanner()
        self.normalizer = SegmentNormalizer(self.runner, self.policy)

    def build(
        self,
        manifest: PlayoutManifest,
        *,
        dry_run: bool = False,
        overwrite: bool = False,
        skip_validation: bool = False,
        keep_normalized_segments: bool = True,
    ) -> ProgramBuildResult:
        if manifest.target_duration_seconds > settings.PLAYOUT_MAX_TARGET_DURATION_SECONDS:
            raise PlayoutError(
                "playout_duration_overflow",
                f"target duration exceeds {settings.PLAYOUT_MAX_TARGET_DURATION_SECONDS} seconds",
            )
        program_dir = self.program_dir / manifest.program_id
        if program_dir.exists() and not overwrite and not dry_run:
            raise PlayoutError("playout_program_exists", "program output already exists", status_code=409)
        program_dir.mkdir(parents=True, exist_ok=True)
        normalized_dir = self.normalized_dir / manifest.program_id
        normalized_dir.mkdir(parents=True, exist_ok=True)

        idle = self.validator.validate_idle(manifest)
        talking = self.validator.validate_talking(manifest)
        timeline = self.planner.plan(manifest, idle_source_path=idle.source_path, talking_segments=talking)
        if manifest.transition == "fade":
            timeline.warnings.append("fade transition is not implemented safely yet; using cut")

        manifest_path = program_dir / "manifest.json"
        timeline_path = program_dir / "timeline.json"
        validation_path = program_dir / "validation_report.json"
        metadata_path = program_dir / "output_metadata.json"
        output_path = program_dir / manifest.output_name

        self._write_json(manifest_path, manifest.model_dump(mode="json"))
        self._write_json(timeline_path, timeline.model_dump(mode="json"))

        if dry_run:
            report = ValidationReport(
                program_id=manifest.program_id,
                status="dry_run",
                automated_checks=AutomatedChecks(),
                warnings=timeline.warnings,
            )
            metadata = self._metadata(manifest, "dry_run", timeline, None, manifest_path, timeline_path, validation_path)
            self._write_json(validation_path, report.model_dump(mode="json"))
            self._write_json(metadata_path, metadata.model_dump(mode="json"))
            return ProgramBuildResult(
                program_id=manifest.program_id,
                status="dry_run",
                metadata_path=relative_to_backend(metadata_path, self.backend_root),
                timeline_path=relative_to_backend(timeline_path, self.backend_root),
                validation_report_path=relative_to_backend(validation_path, self.backend_root),
                warnings=timeline.warnings,
            )

        updated_timeline = self._normalize_timeline(timeline, normalized_dir)
        self._write_json(timeline_path, updated_timeline.model_dump(mode="json"))
        concat_list = program_dir / "concat_list.txt"
        self._write_concat_list(concat_list, updated_timeline)
        self._concat(concat_list, output_path)

        if not output_path.exists():
            raise PlayoutError(PLAYOUT_OUTPUT_MISSING, "program output was not created")

        final_probe = None if skip_validation else self.probe_service.probe(output_path)
        checks = self._automated_checks(output_path, final_probe, updated_timeline)
        report_status = "completed" if not checks.errors else "failed"
        report = ValidationReport(
            program_id=manifest.program_id,
            status=report_status,
            automated_checks=checks,
            warnings=updated_timeline.warnings,
            errors=checks.errors,
        )
        metadata = self._metadata(
            manifest,
            report_status,
            updated_timeline,
            output_path,
            manifest_path,
            timeline_path,
            validation_path,
            actual_duration=checks.duration_seconds,
        )
        self._write_json(validation_path, report.model_dump(mode="json"))
        self._write_json(metadata_path, metadata.model_dump(mode="json"))
        self.runner.write_log(program_dir / "ffmpeg_commands.log")
        if not keep_normalized_segments:
            shutil.rmtree(normalized_dir, ignore_errors=True)
        if report_status == "failed":
            raise PlayoutError(PLAYOUT_OUTPUT_INVALID, "program output failed validation")

        return ProgramBuildResult(
            program_id=manifest.program_id,
            status="completed",
            output_path=relative_to_backend(output_path, self.backend_root),
            metadata_path=relative_to_backend(metadata_path, self.backend_root),
            timeline_path=relative_to_backend(timeline_path, self.backend_root),
            validation_report_path=relative_to_backend(validation_path, self.backend_root),
            warnings=updated_timeline.warnings,
        )

    def _normalize_timeline(self, timeline: TimelinePlan, normalized_dir: Path) -> TimelinePlan:
        updated = timeline.model_copy(deep=True)
        for item in updated.items:
            output = normalized_dir / f"{item.sequence:03d}_{item.kind}_{item.segment_id}.mp4"
            if item.kind == "idle":
                source = safe_join(self.backend_root, item.source_path, field="source_path")
                try:
                    self.normalizer.normalize_idle(source, output, duration_seconds=item.duration_seconds)
                except PlayoutError as exc:
                    if exc.code == PLAYOUT_FFMPEG_MISSING:
                        raise
                    raise PlayoutError(PLAYOUT_NORMALIZATION_FAILED, "failed to normalize idle segment") from exc
            else:
                source = safe_join(self.media_root, item.source_path, field="source_path")
                try:
                    self.normalizer.normalize_talking(source, output)
                except PlayoutError as exc:
                    if exc.code == PLAYOUT_FFMPEG_MISSING:
                        raise
                    raise PlayoutError(PLAYOUT_NORMALIZATION_FAILED, f"failed to normalize talking segment: {item.segment_id}") from exc
            item.normalized_path = relative_to_backend(output, self.backend_root)
        return updated

    def _write_concat_list(self, concat_list: Path, timeline: TimelinePlan) -> None:
        lines = []
        for item in timeline.items:
            if not item.normalized_path:
                raise PlayoutError(PLAYOUT_CONCAT_FAILED, "timeline item is missing normalized path")
            source = safe_join(self.backend_root, item.normalized_path, field="normalized_path")
            lines.append(f"file '{source.as_posix()}'")
        concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _concat(self, concat_list: Path, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.runner.run(["-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output_path)])
        except PlayoutError as exc:
            raise PlayoutError(PLAYOUT_CONCAT_FAILED, "failed to concatenate normalized clips") from exc

    def _automated_checks(self, output_path: Path, probe, timeline: TimelinePlan) -> AutomatedChecks:
        errors: list[str] = []
        if probe is None:
            return AutomatedChecks(output_exists=output_path.exists(), errors=errors)
        has_video = probe.video_stream is not None
        has_audio = probe.audio_stream is not None
        if not has_video:
            errors.append("missing video stream")
        if not has_audio:
            errors.append("missing audio stream")
        duration = probe.duration_seconds
        duration_ok = duration is not None and abs(duration - timeline.planned_duration_seconds) <= 2.0
        if not duration_ok:
            errors.append("duration outside expected tolerance")
        video = probe.video_stream
        audio = probe.audio_stream
        codec_ok = bool(
            video
            and audio
            and video.width == self.policy.target_width
            and video.height == self.policy.target_height
            and audio.channels == self.policy.audio_channels
        )
        if not codec_ok:
            errors.append("output format is not compatible with policy")
        return AutomatedChecks(
            output_exists=output_path.exists(),
            has_video=has_video,
            has_audio=has_audio,
            duration_seconds=duration,
            duration_within_expected_range=duration_ok,
            codec_compatible=codec_ok,
            errors=errors,
        )

    def _metadata(
        self,
        manifest: PlayoutManifest,
        status: str,
        timeline: TimelinePlan,
        output_path: Path | None,
        manifest_path: Path,
        timeline_path: Path,
        validation_path: Path,
        *,
        actual_duration: float | None = None,
    ) -> ProgramMetadata:
        now = datetime.now(timezone.utc).isoformat()
        return ProgramMetadata(
            program_id=manifest.program_id,
            avatar_id=manifest.avatar_id,
            status=status,  # type: ignore[arg-type]
            target_duration_seconds=manifest.target_duration_seconds,
            actual_duration_seconds=actual_duration or timeline.planned_duration_seconds,
            output_path=relative_to_backend(output_path, self.backend_root) if output_path else None,
            timeline_path=relative_to_backend(timeline_path, self.backend_root),
            manifest_path=relative_to_backend(manifest_path, self.backend_root),
            validation_report_path=relative_to_backend(validation_path, self.backend_root),
            transition="cut" if manifest.transition == "fade" else manifest.transition,
            video_codec=self.policy.video_codec,
            audio_codec=self.policy.audio_codec,
            resolution=self.policy.resolution,
            fps=self.policy.target_fps,
            pixel_format=self.policy.pixel_format,
            warnings=timeline.warnings,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
