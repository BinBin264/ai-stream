from __future__ import annotations


class PlayoutError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


PLAYOUT_MANIFEST_MISSING = "playout_manifest_missing"
PLAYOUT_MANIFEST_INVALID = "playout_manifest_invalid"
PLAYOUT_PROGRAM_EXISTS = "playout_program_exists"
PLAYOUT_AVATAR_NOT_FOUND = "playout_avatar_not_found"
PLAYOUT_IDLE_ASSET_MISSING = "playout_idle_asset_missing"
PLAYOUT_TALKING_SEGMENT_MISSING = "playout_talking_segment_missing"
PLAYOUT_TALKING_SEGMENT_INVALID = "playout_talking_segment_invalid"
PLAYOUT_UNSUPPORTED_MEDIA = "playout_unsupported_media"
PLAYOUT_FFPROBE_FAILED = "playout_ffprobe_failed"
PLAYOUT_FFMPEG_MISSING = "playout_ffmpeg_missing"
PLAYOUT_NORMALIZATION_FAILED = "playout_normalization_failed"
PLAYOUT_CONCAT_FAILED = "playout_concat_failed"
PLAYOUT_OUTPUT_MISSING = "playout_output_missing"
PLAYOUT_OUTPUT_INVALID = "playout_output_invalid"
PLAYOUT_DURATION_OVERFLOW = "playout_duration_overflow"
PLAYOUT_PATH_INVALID = "playout_path_invalid"

