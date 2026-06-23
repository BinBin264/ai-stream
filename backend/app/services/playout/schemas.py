from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.playout.errors import PLAYOUT_PATH_INVALID, PlayoutError
from app.services.playout.paths import ensure_relative_safe

Priority = Literal["P0", "P1", "P2", "P3", "P4"]
TransitionMode = Literal["cut", "fade"]
TimelineKind = Literal["idle", "talking"]
FormatStatus = Literal["pass", "warning", "fail"]


class TalkingSegmentInput(BaseModel):
    segment_id: str
    source_path: str
    priority: Priority = "P2"
    duration_seconds: float | None = Field(default=None, gt=0)

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, value: str) -> str:
        ensure_relative_safe(value, field="source_path")
        return value


class PlayoutManifest(BaseModel):
    program_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")
    avatar_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")
    target_duration_seconds: float = Field(default=90, gt=0)
    idle_lead_seconds: float = Field(default=8, ge=0)
    idle_between_seconds: float = Field(default=10, ge=0)
    idle_tail_minimum_seconds: float = Field(default=10, ge=0)
    transition: TransitionMode = "cut"
    output_name: str = Field(default="program_output.mp4", min_length=1)
    talking_segments: list[TalkingSegmentInput] = Field(default_factory=list, min_length=1)

    @field_validator("output_name")
    @classmethod
    def validate_output_name(cls, value: str) -> str:
        if value != ensure_relative_safe(value, field="output_name").name:
            raise PlayoutError(PLAYOUT_PATH_INVALID, "output_name must be a filename")
        if not value.endswith(".mp4"):
            raise PlayoutError(PLAYOUT_PATH_INVALID, "output_name must end with .mp4")
        return value


class MediaStream(BaseModel):
    codec_type: str
    codec_name: str | None = None
    width: int | None = None
    height: int | None = None
    pix_fmt: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    avg_frame_rate: str | None = None
    duration: float | None = None


class MediaProbe(BaseModel):
    path: str
    duration_seconds: float | None = None
    streams: list[MediaStream] = Field(default_factory=list)

    @property
    def video_stream(self) -> MediaStream | None:
        return next((stream for stream in self.streams if stream.codec_type == "video"), None)

    @property
    def audio_stream(self) -> MediaStream | None:
        return next((stream for stream in self.streams if stream.codec_type == "audio"), None)


class FormatCheck(BaseModel):
    status: FormatStatus
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    normalizable: bool = False


class SegmentValidation(BaseModel):
    segment_id: str
    source_path: str
    absolute_path: str
    duration_seconds: float
    format_check: FormatCheck


class TimelineItem(BaseModel):
    sequence: int
    kind: TimelineKind
    segment_id: str
    source_path: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    priority: Priority | None = None
    normalized_path: str | None = None


class TimelinePlan(BaseModel):
    program_id: str
    avatar_id: str
    target_duration_seconds: float
    planned_duration_seconds: float
    transition: TransitionMode
    items: list[TimelineItem]
    warnings: list[str] = Field(default_factory=list)


class AutomatedChecks(BaseModel):
    output_exists: bool = False
    has_video: bool = False
    has_audio: bool = False
    duration_seconds: float | None = None
    duration_within_expected_range: bool = False
    codec_compatible: bool = False
    no_black_frame_check: str = "manual_required"
    errors: list[str] = Field(default_factory=list)


class ManualReview(BaseModel):
    required: bool = True
    ready_for_phase_4b: bool = False
    checklist: list[str] = Field(
        default_factory=lambda: [
            "idle video loops naturally",
            "no black frames occur at transitions",
            "talking segment starts cleanly",
            "talking segment ends cleanly",
            "no speech audio is cut off",
            "idle segments have no unwanted audio",
            "video remains vertical and centered",
            "face remains large and clear",
            "final output plays continuously for the planned duration",
            "output is suitable for RTMP testing in Phase 4B",
        ]
    )


class ValidationReport(BaseModel):
    program_id: str
    status: Literal["dry_run", "completed", "failed"]
    automated_checks: AutomatedChecks
    manual_review: ManualReview = Field(default_factory=ManualReview)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ProgramMetadata(BaseModel):
    program_id: str
    avatar_id: str
    status: Literal["dry_run", "completed", "failed"]
    target_duration_seconds: float
    actual_duration_seconds: float | None = None
    output_path: str | None = None
    timeline_path: str | None = None
    manifest_path: str | None = None
    validation_report_path: str | None = None
    transition: TransitionMode
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    resolution: str = "1080x1920"
    fps: int = 25
    pixel_format: str = "yuv420p"
    warnings: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ProgramBuildResult(BaseModel):
    program_id: str
    status: Literal["dry_run", "completed", "failed"]
    output_path: str | None = None
    metadata_path: str | None = None
    timeline_path: str | None = None
    validation_report_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
