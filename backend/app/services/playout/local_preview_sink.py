from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.playout.dynamic_errors import DynamicPlayoutError
from app.services.playout.playout_output_sink import PlayoutOutputSink


class LocalPreviewSink(PlayoutOutputSink):
    def __init__(self, *, ffmpeg_bin: str | None = None) -> None:
        self.ffmpeg_bin = ffmpeg_bin or settings.FFMPEG_BIN
        self.session_id: str | None = None
        self.output_dir: Path | None = None
        self.playlist_path: Path | None = None
        self.sequence = 0
        self._alive = False
        self._last_output_update_at: datetime | None = None

    async def start(self, session_id: str) -> str:
        self.session_id = session_id
        self.output_dir = self._hls_root() / session_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.playlist_path = self.output_dir / "index.m3u8"
        for child in self.output_dir.glob("*.ts"):
            child.unlink(missing_ok=True)
        self.playlist_path.write_text(
            "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:"
            f"{max(1, settings.PLAYOUT_HLS_TIME_SECONDS)}\n#EXT-X-MEDIA-SEQUENCE:0\n",
            encoding="utf-8",
        )
        self.sequence = 0
        self._alive = True
        self._last_output_update_at = datetime.now(timezone.utc)
        return self._relative_output_path(self.playlist_path)

    async def append_idle(self, *, source_path: Path, duration_seconds: int) -> None:
        await self._append_clip(source_path=source_path, duration_seconds=duration_seconds, idle=True)

    async def append_talking(self, *, source_path: Path) -> None:
        await self._append_clip(source_path=source_path, duration_seconds=None, idle=False)

    async def stop(self) -> None:
        if self.playlist_path and self.playlist_path.exists():
            with self.playlist_path.open("a", encoding="utf-8") as handle:
                handle.write("#EXT-X-ENDLIST\n")
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive

    def last_output_update_at(self):
        return self._last_output_update_at

    async def _append_clip(self, *, source_path: Path, duration_seconds: int | None, idle: bool) -> None:
        if not self.output_dir or not self.playlist_path:
            raise DynamicPlayoutError("playout_runtime_not_available", "local preview sink is not started")
        if not source_path.exists():
            raise DynamicPlayoutError("playout_segment_missing", "source media does not exist")

        filename = f"seg_{self.sequence:08d}.ts"
        output_path = self.output_dir / filename
        args = [self.ffmpeg_bin, "-y"]
        if idle:
            args.extend(["-stream_loop", "-1", "-i", str(source_path)])
        else:
            args.extend(["-i", str(source_path)])
        if idle:
            # Add silent audio to idle chunks when the source has no usable audio.
            args.extend(
                [
                    "-f",
                    "lavfi",
                    "-t",
                    str(duration_seconds or settings.PLAYOUT_HLS_TIME_SECONDS),
                    "-i",
                    f"anullsrc=channel_layout=stereo:sample_rate={settings.PLAYOUT_AUDIO_SAMPLE_RATE}",
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                ]
            )
        if duration_seconds is not None:
            args.extend(["-t", str(duration_seconds)])
        args.extend(
            [
                "-vf",
                (
                    f"fps={settings.PLAYOUT_TARGET_FPS},"
                    f"scale={settings.PLAYOUT_TARGET_WIDTH}:{settings.PLAYOUT_TARGET_HEIGHT}:force_original_aspect_ratio=decrease,"
                    f"pad={settings.PLAYOUT_TARGET_WIDTH}:{settings.PLAYOUT_TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
                    f"format={settings.PLAYOUT_PIXEL_FORMAT}"
                ),
            ]
        )
        args.extend(
            [
                "-c:v",
                settings.PLAYOUT_VIDEO_CODEC,
                "-pix_fmt",
                settings.PLAYOUT_PIXEL_FORMAT,
                "-c:a",
                settings.PLAYOUT_AUDIO_CODEC,
                "-ar",
                str(settings.PLAYOUT_AUDIO_SAMPLE_RATE),
                "-ac",
                str(settings.PLAYOUT_AUDIO_CHANNELS),
                "-f",
                "mpegts",
                str(output_path),
            ]
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise DynamicPlayoutError("playout_ffmpeg_missing", "ffmpeg binary is not available") from exc
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise DynamicPlayoutError(
                "playout_hls_output_failed",
                f"failed to append {'idle' if idle else 'talking'} media to local preview",
            )

        segment_duration = float(duration_seconds or settings.PLAYOUT_HLS_TIME_SECONDS)
        if not idle:
            segment_duration = await self._probe_duration(source_path)
        with self.playlist_path.open("a", encoding="utf-8") as handle:
            handle.write(f"#EXTINF:{segment_duration:.3f},\n{filename}\n")
        self.sequence += 1
        self._last_output_update_at = datetime.now(timezone.utc)

    async def _probe_duration(self, source_path: Path) -> float:
        args = [
            settings.FFPROBE_BIN,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source_path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return float(settings.PLAYOUT_HLS_TIME_SECONDS)
        stdout, _stderr = await proc.communicate()
        if proc.returncode != 0:
            return float(settings.PLAYOUT_HLS_TIME_SECONDS)
        try:
            return max(0.1, float(stdout.decode().strip()))
        except ValueError:
            return float(settings.PLAYOUT_HLS_TIME_SECONDS)

    def _hls_root(self) -> Path:
        configured = Path(settings.PLAYOUT_HLS_DIRECTORY)
        if configured.is_absolute():
            return configured
        return Path(settings.MEDIA_OUTPUT_DIR) / configured

    def _relative_output_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(Path(settings.MEDIA_OUTPUT_DIR).resolve()))
        except ValueError:
            return path.name
