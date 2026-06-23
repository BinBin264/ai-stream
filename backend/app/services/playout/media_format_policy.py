from __future__ import annotations

from dataclasses import dataclass

from app.services.playout.schemas import FormatCheck, MediaProbe


@dataclass(frozen=True)
class MediaFormatPolicy:
    target_width: int = 1080
    target_height: int = 1920
    target_fps: int = 25
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    pixel_format: str = "yuv420p"
    audio_rate: int = 48000
    audio_channels: int = 2

    @property
    def resolution(self) -> str:
        return f"{self.target_width}x{self.target_height}"

    def classify(self, probe: MediaProbe) -> FormatCheck:
        video = probe.video_stream
        if video is None:
            return FormatCheck(status="fail", errors=["missing video stream"], normalizable=False)
        if not probe.duration_seconds or probe.duration_seconds <= 0:
            return FormatCheck(status="fail", errors=["missing or zero duration"], normalizable=False)

        warnings: list[str] = []
        if (video.width, video.height) == (720, 1280):
            warnings.append("720x1280 source will be scaled and padded to 1080x1920")
        elif (video.width, video.height) != (self.target_width, self.target_height):
            warnings.append("source resolution will be scaled and padded to target 9:16 output")

        if probe.audio_stream is None:
            warnings.append("source has no audio stream; silent AAC will be added for idle clips")

        status = "warning" if warnings else "pass"
        return FormatCheck(status=status, warnings=warnings, normalizable=True)

