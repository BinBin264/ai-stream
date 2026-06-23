from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.playout.errors import PLAYOUT_FFMPEG_MISSING, PlayoutError


class FFmpegRunner:
    def __init__(self, ffmpeg_bin: str = "ffmpeg") -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.commands: list[list[str]] = []

    def run(self, args: list[str]) -> None:
        command = [self.ffmpeg_bin, *args]
        self.commands.append(command)
        try:
            subprocess.run(command, capture_output=True, text=True, check=True)
        except FileNotFoundError as exc:
            raise PlayoutError(PLAYOUT_FFMPEG_MISSING, "ffmpeg binary is not available") from exc
        except subprocess.CalledProcessError as exc:
            raise PlayoutError("playout_ffmpeg_failed", "ffmpeg command failed") from exc

    def write_log(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [" ".join(command) for command in self.commands]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

