from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.playout.errors import PLAYOUT_FFPROBE_FAILED, PlayoutError
from app.services.playout.schemas import MediaProbe, MediaStream


class FFprobeService:
    def __init__(self, ffprobe_bin: str = "ffprobe") -> None:
        self.ffprobe_bin = ffprobe_bin

    def probe(self, path: Path) -> MediaProbe:
        command = [
            self.ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,pix_fmt,sample_rate,channels,avg_frame_rate,duration",
            "-of",
            "json",
            str(path),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=True)
        except FileNotFoundError as exc:
            raise PlayoutError(PLAYOUT_FFPROBE_FAILED, "ffprobe binary is not available") from exc
        except subprocess.CalledProcessError as exc:
            raise PlayoutError(PLAYOUT_FFPROBE_FAILED, "ffprobe failed for media source") from exc

        payload = json.loads(completed.stdout or "{}")
        streams = [MediaStream(**stream) for stream in payload.get("streams", [])]
        duration = payload.get("format", {}).get("duration")
        return MediaProbe(
            path=path.name,
            duration_seconds=float(duration) if duration is not None else None,
            streams=streams,
        )

