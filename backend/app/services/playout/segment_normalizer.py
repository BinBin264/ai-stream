from __future__ import annotations

from pathlib import Path

from app.services.playout.media_format_policy import MediaFormatPolicy


class SegmentNormalizer:
    def __init__(self, runner, policy: MediaFormatPolicy) -> None:
        self.runner = runner
        self.policy = policy

    def _video_filter(self) -> str:
        return (
            f"fps={self.policy.target_fps},"
            f"scale={self.policy.target_width}:{self.policy.target_height}:force_original_aspect_ratio=decrease,"
            f"pad={self.policy.target_width}:{self.policy.target_height}:(ow-iw)/2:(oh-ih)/2,"
            f"format={self.policy.pixel_format}"
        )

    def normalize_idle(self, source: Path, output: Path, *, duration_seconds: float) -> list[str]:
        output.parent.mkdir(parents=True, exist_ok=True)
        args = [
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(source),
            "-f",
            "lavfi",
            "-t",
            f"{duration_seconds:.3f}",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate={self.policy.audio_rate}",
            "-t",
            f"{duration_seconds:.3f}",
            "-vf",
            self._video_filter(),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            self.policy.video_codec,
            "-pix_fmt",
            self.policy.pixel_format,
            "-c:a",
            self.policy.audio_codec,
            "-ar",
            str(self.policy.audio_rate),
            "-ac",
            str(self.policy.audio_channels),
            "-shortest",
            str(output),
        ]
        self.runner.run(args)
        return args

    def normalize_talking(self, source: Path, output: Path) -> list[str]:
        output.parent.mkdir(parents=True, exist_ok=True)
        args = [
            "-y",
            "-i",
            str(source),
            "-vf",
            self._video_filter(),
            "-c:v",
            self.policy.video_codec,
            "-pix_fmt",
            self.policy.pixel_format,
            "-c:a",
            self.policy.audio_codec,
            "-ar",
            str(self.policy.audio_rate),
            "-ac",
            str(self.policy.audio_channels),
            "-movflags",
            "+faststart",
            str(output),
        ]
        self.runner.run(args)
        return args

