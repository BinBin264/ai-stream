"""
MuseTalkClient — clean adapter for the MuseTalk lip-sync engine.

Supports two execution modes (controlled by AVATAR_RUNTIME_MODE env var):
  cli  — invoke a local MuseTalk installation via subprocess
  http — forward to a running MuseTalk HTTP service

Only CLI mode is fully implemented here. HTTP mode is stubbed cleanly.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MuseTalkHealth:
    available: bool
    mode: str  # "cli" | "http" | "unavailable"
    musetalk_home: Path | None = None
    version: str | None = None
    message: str = ""


@dataclass
class PreparedAvatar:
    avatar_id: str
    source_path: Path
    source_type: str  # "idle_video" | "source_image"
    cache_dir: Path
    prepared: bool = False
    message: str = ""


@dataclass
class RenderOptions:
    fps: int = 25
    resolution: str = "1080x1920"
    motion_profile: str = "minimal"
    keep_temp: bool = False
    extra_args: list[str] = field(default_factory=list)


@dataclass
class RenderResult:
    success: bool
    output_path: Path | None = None
    duration_seconds: float | None = None
    fps: int | None = None
    resolution: str | None = None
    engine_version: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class MuseTalkClient:
    """
    Adapter that translates render requests into MuseTalk CLI commands.

    Constructor reads from environment variables so no secrets are
    hardcoded.
    """

    def __init__(
        self,
        mode: str | None = None,
        musetalk_home: str | None = None,
        python_bin: str | None = None,
        command_template: str | None = None,
        http_base_url: str | None = None,
        ffprobe_bin: str = "ffprobe",
    ) -> None:
        self.mode = (mode or os.environ.get("AVATAR_RUNTIME_MODE", "cli")).lower()
        self.musetalk_home = Path(
            musetalk_home or os.environ.get("MUSETALK_HOME", "/opt/musetalk")
        )
        self.python_bin = python_bin or os.environ.get("MUSETALK_PYTHON", "python")
        self.command_template = command_template or os.environ.get(
            "MUSETALK_COMMAND_TEMPLATE", ""
        )
        self.http_base_url = http_base_url or os.environ.get("AVATAR_RUNTIME_BASE_URL", "")
        self.ffprobe_bin = ffprobe_bin

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def health_check(self) -> MuseTalkHealth:
        if self.mode == "http":
            return self._health_http()
        return self._health_cli()

    def prepare_avatar(
        self,
        avatar_id: str,
        input_path: Path,
        cache_dir: Path,
    ) -> PreparedAvatar:
        """
        Ensure MuseTalk has cached preprocessing artefacts for the avatar.
        In CLI mode this is a no-op today (MuseTalk re-processes on every
        render call), but the hook is here for future optimisation.
        """
        if not input_path.exists():
            return PreparedAvatar(
                avatar_id=avatar_id,
                source_path=input_path,
                source_type=_source_type(input_path),
                cache_dir=cache_dir,
                prepared=False,
                message=f"Source not found: {input_path}",
            )
        cache_dir.mkdir(parents=True, exist_ok=True)
        return PreparedAvatar(
            avatar_id=avatar_id,
            source_path=input_path,
            source_type=_source_type(input_path),
            cache_dir=cache_dir,
            prepared=True,
        )

    def render(
        self,
        prepared_avatar: PreparedAvatar,
        audio_path: Path,
        output_path: Path,
        options: RenderOptions | None = None,
    ) -> RenderResult:
        options = options or RenderOptions()

        if not prepared_avatar.prepared:
            return RenderResult(
                success=False,
                error=f"Avatar not prepared: {prepared_avatar.message}",
            )
        if not audio_path.exists():
            return RenderResult(success=False, error=f"Audio not found: {audio_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self.mode == "http":
            return self._render_http(prepared_avatar, audio_path, output_path, options)
        return self._render_cli(prepared_avatar, audio_path, output_path, options)

    # ------------------------------------------------------------------
    # CLI mode
    # ------------------------------------------------------------------

    def _health_cli(self) -> MuseTalkHealth:
        if not self.musetalk_home.exists():
            return MuseTalkHealth(
                available=False,
                mode="cli",
                musetalk_home=self.musetalk_home,
                message=f"MUSETALK_HOME not found: {self.musetalk_home}",
            )
        entrypoint = self.musetalk_home / "inference.py"
        if not entrypoint.exists():
            return MuseTalkHealth(
                available=False,
                mode="cli",
                musetalk_home=self.musetalk_home,
                message=f"MuseTalk entrypoint not found: {entrypoint}",
            )
        return MuseTalkHealth(
            available=True,
            mode="cli",
            musetalk_home=self.musetalk_home,
            message="MuseTalk CLI available",
        )

    def build_cli_command(
        self,
        prepared_avatar: PreparedAvatar,
        audio_path: Path,
        output_path: Path,
        options: RenderOptions,
    ) -> list[str]:
        """
        Build the subprocess command list for MuseTalk.
        Exposed as a public method so tests can verify the command without
        actually running it.
        """
        if self.command_template:
            # Allow full override via MUSETALK_COMMAND_TEMPLATE
            rendered = self.command_template.format(
                python=self.python_bin,
                musetalk_home=self.musetalk_home,
                source=prepared_avatar.source_path,
                audio=audio_path,
                output=output_path,
                fps=options.fps,
                resolution=options.resolution,
            )
            import shlex
            return shlex.split(rendered)

        cmd = [
            self.python_bin,
            str(self.musetalk_home / "inference.py"),
            "--source_video" if prepared_avatar.source_type == "idle_video" else "--source_image",
            str(prepared_avatar.source_path),
            "--driven_audio", str(audio_path),
            "--result_dir", str(output_path.parent),
            "--fps", str(options.fps),
            "--crop_size", "256",
        ]
        cmd += options.extra_args
        return cmd

    def _render_cli(
        self,
        prepared_avatar: PreparedAvatar,
        audio_path: Path,
        output_path: Path,
        options: RenderOptions,
    ) -> RenderResult:
        health = self._health_cli()
        if not health.available:
            return RenderResult(success=False, error=health.message)

        cmd = self.build_cli_command(prepared_avatar, audio_path, output_path, options)
        logger.info("MuseTalk CLI: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(self.musetalk_home),
            )
        except subprocess.TimeoutExpired:
            return RenderResult(success=False, error="MuseTalk render timed out (600s)")
        except FileNotFoundError as exc:
            return RenderResult(success=False, error=f"Python binary not found: {exc}")

        if result.returncode != 0:
            return RenderResult(
                success=False,
                error=f"MuseTalk exited {result.returncode}:\n{result.stderr[-2000:]}",
            )

        if not output_path.exists():
            # MuseTalk may write to a different filename; try to locate it
            candidates = list(output_path.parent.glob("*.mp4"))
            if candidates:
                shutil.move(str(candidates[0]), str(output_path))
            else:
                return RenderResult(
                    success=False,
                    error=f"MuseTalk finished but output not found: {output_path}",
                )

        duration = _ffprobe_duration(output_path, self.ffprobe_bin)
        return RenderResult(
            success=True,
            output_path=output_path,
            duration_seconds=duration,
            fps=options.fps,
            resolution=options.resolution,
        )

    # ------------------------------------------------------------------
    # HTTP mode
    # ------------------------------------------------------------------

    def _health_http(self) -> MuseTalkHealth:
        if not self.http_base_url:
            return MuseTalkHealth(
                available=False,
                mode="http",
                message="AVATAR_RUNTIME_BASE_URL is not set",
            )
        return MuseTalkHealth(
            available=True,
            mode="http",
            message=f"HTTP runtime at {self.http_base_url} (not yet verified)",
        )

    def _render_http(
        self,
        prepared_avatar: PreparedAvatar,
        audio_path: Path,
        output_path: Path,
        options: RenderOptions,
    ) -> RenderResult:
        return RenderResult(
            success=False,
            error="HTTP render mode is not implemented.",
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _source_type(path: Path) -> str:
    return "idle_video" if path.suffix.lower() == ".mp4" else "source_image"



def _ffprobe_duration(path: Path, ffprobe_bin: str = "ffprobe") -> float | None:
    try:
        result = subprocess.run(
            [
                ffprobe_bin, "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return None
