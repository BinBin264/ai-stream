from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.playout.dynamic_errors import DynamicPlayoutError
from app.services.playout.playout_output_sink import PlaybackReceipt, PlayoutOutputSink


@dataclass(frozen=True)
class HlsSegment:
    sequence: int
    filename: str
    duration_seconds: float


class LocalPreviewSink(PlayoutOutputSink):
    def __init__(self, *, ffmpeg_bin: str | None = None) -> None:
        self.ffmpeg_bin = ffmpeg_bin or "ffmpeg"
        self.session_id: str | None = None
        self.output_dir: Path | None = None
        self.playlist_path: Path | None = None
        self.sequence = 0
        self._alive = False
        self._last_output_update_at: datetime | None = None
        self._segments: list[HlsSegment] = []
        self._output_offset: float = 0.0

    async def start(self, session_id: str) -> str:
        self.session_id = session_id
        self.output_dir = self._hls_root() / session_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.playlist_path = self.output_dir / "index.m3u8"
        for child in self.output_dir.glob("*.ts"):
            child.unlink(missing_ok=True)
        self.sequence = 0
        self._segments = []
        self._output_offset = 0.0
        self._write_playlist(endlist=False)
        self._alive = True
        self._last_output_update_at = datetime.now(timezone.utc)
        return self._relative_output_path(self.playlist_path)

    async def append_idle(self, *, source_path: Path, duration_seconds: int, start_offset: float = 0.0) -> PlaybackReceipt:
        return await self._append_clip(source_path=source_path, duration_seconds=duration_seconds, idle=True, start_offset=start_offset)

    async def append_talking(self, *, source_path: Path) -> PlaybackReceipt:
        return await self._append_clip(source_path=source_path, duration_seconds=None, idle=False)

    async def stop(self) -> None:
        if self.playlist_path and self.playlist_path.exists():
            self._write_playlist(endlist=True)
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive

    def last_output_update_at(self):
        return self._last_output_update_at

    async def _append_clip(self, *, source_path: Path, duration_seconds: int | None, idle: bool, start_offset: float = 0.0) -> PlaybackReceipt:
        if not self.output_dir or not self.playlist_path:
            raise DynamicPlayoutError("playout_runtime_not_available", "local preview sink is not started")
        if not source_path.exists():
            raise DynamicPlayoutError("playout_segment_missing", "source media does not exist")

        started_at = datetime.now(timezone.utc)
        ts_offset = self._output_offset
        filename = f"seg_{self.sequence:08d}.ts"
        output_path = self.output_dir / filename
        args = [self.ffmpeg_bin, "-y"]
        if idle:
            args.extend(["-stream_loop", "-1"])
            if start_offset > 0.0:
                args.extend(["-ss", str(start_offset)])
            args.extend(["-i", str(source_path)])
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
                "-preset",
                "ultrafast",
                "-pix_fmt",
                settings.PLAYOUT_PIXEL_FORMAT,
                "-c:a",
                settings.PLAYOUT_AUDIO_CODEC,
                "-ar",
                str(settings.PLAYOUT_AUDIO_SAMPLE_RATE),
                "-ac",
                str(settings.PLAYOUT_AUDIO_CHANNELS),
                "-output_ts_offset",
                f"{ts_offset:.6f}",
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
        _stdout, _stderr = await proc.communicate()
        if proc.returncode != 0:
            raise DynamicPlayoutError(
                "playout_hls_output_failed",
                f"failed to append {'idle' if idle else 'talking'} media to local preview",
            )
        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise DynamicPlayoutError("playout_hls_output_failed", "HLS segment output was not written")

        segment_duration = float(duration_seconds or settings.PLAYOUT_HLS_TIME_SECONDS)
        if not idle:
            segment_duration = await self._probe_duration(source_path)
        self._output_offset += segment_duration
        current_sequence = self.sequence
        self._segments.append(HlsSegment(current_sequence, filename, segment_duration))
        self.sequence += 1
        self._trim_window()
        self._write_playlist(endlist=False)
        self._last_output_update_at = datetime.now(timezone.utc)
        return PlaybackReceipt(
            output_path=self._relative_output_path(output_path),
            duration_seconds=segment_duration,
            started_at=started_at,
            appended_at=self._last_output_update_at,
            sequence_number=current_sequence,
        )

    async def _probe_duration(self, source_path: Path) -> float:
        args = [
            "ffprobe",
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
        except FileNotFoundError as exc:
            raise DynamicPlayoutError("playout_ffprobe_failed", "ffprobe binary is not available") from exc
        stdout, _stderr = await proc.communicate()
        if proc.returncode != 0:
            raise DynamicPlayoutError("playout_ffprobe_failed", "ffprobe failed to read talking segment duration")
        try:
            duration = max(0.1, float(stdout.decode().strip()))
        except ValueError as exc:
            raise DynamicPlayoutError("playout_segment_invalid", "talking segment duration is invalid") from exc
        return duration

    def _trim_window(self) -> None:
        if not self.output_dir:
            return
        max_segments = max(1, settings.PLAYOUT_HLS_LIST_SIZE)
        removed: list[HlsSegment] = []
        if len(self._segments) > max_segments:
            removed = self._segments[: len(self._segments) - max_segments]
            self._segments = self._segments[-max_segments:]
        for segment in removed:
            (self.output_dir / segment.filename).unlink(missing_ok=True)

    def _write_playlist(self, *, endlist: bool) -> None:
        if not self.output_dir or not self.playlist_path:
            return
        media_sequence = self._segments[0].sequence if self._segments else self.sequence
        target_duration = max(
            max(1, settings.PLAYOUT_HLS_TIME_SECONDS),
            int(max((segment.duration_seconds for segment in self._segments), default=settings.PLAYOUT_HLS_TIME_SECONDS) + 0.999),
        )
        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            "#EXT-X-INDEPENDENT-SEGMENTS",
            f"#EXT-X-TARGETDURATION:{target_duration}",
            f"#EXT-X-MEDIA-SEQUENCE:{media_sequence}",
        ]
        for segment in self._segments:
            lines.append(f"#EXTINF:{segment.duration_seconds:.3f},")
            lines.append(segment.filename)
        if endlist:
            lines.append("#EXT-X-ENDLIST")
        content = "\n".join(lines) + "\n"
        tmp_path = self.output_dir / f".{self.playlist_path.name}.tmp"
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(self.playlist_path)

    def _hls_root(self) -> Path:
        media_root = Path(settings.MEDIA_OUTPUT_DIR).resolve()
        configured = Path(settings.PLAYOUT_HLS_DIRECTORY)
        if ".." in configured.parts:
            raise DynamicPlayoutError("playout_segment_invalid", "HLS directory must not contain traversal")
        root = configured.resolve() if configured.is_absolute() else (media_root / configured).resolve()
        if root != media_root and media_root not in root.parents:
            raise DynamicPlayoutError("playout_segment_invalid", "HLS directory must stay under media output root")
        return root

    def _relative_output_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(Path(settings.MEDIA_OUTPUT_DIR).resolve()))
        except ValueError:
            return path.name
