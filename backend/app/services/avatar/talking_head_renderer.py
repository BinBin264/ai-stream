"""
TalkingHeadRenderer — orchestrates the full offline pipeline:

    TTS audio  →  (FFmpeg WAV normalize)  →  MuseTalk render  →  output MP4 + metadata JSON
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.services.avatar.avatar_registry import AvatarRegistry, AvatarNotFoundError
from app.services.avatar.musetalk_client import (
    MuseTalkClient,
    PreparedAvatar,
    RenderOptions,
    RenderResult,
)
from app.services.tts.schemas import TTSRequest, TTSResult

logger = logging.getLogger(__name__)

SourceMode = Literal["auto", "idle_video", "source_image"]


class RenderMetadata(BaseModel):
    render_id: str
    avatar_id: str
    source_type: str
    source_path: str
    input_text: str | None = None
    audio_path: str
    output_path: str
    duration_seconds: float | None = None
    fps: int
    resolution: str
    motion_profile: str
    engine: str = "musetalk"
    engine_version: str | None = None
    started_at: str
    completed_at: str
    render_duration_seconds: float
    status: Literal["completed", "failed"]
    warnings: list[str]
    error: str | None = None


class TalkingHeadRenderer:
    def __init__(
        self,
        registry: AvatarRegistry | None = None,
        musetalk_client: MuseTalkClient | None = None,
        ffmpeg_bin: str | None = None,
        audio_dir: Path | None = None,
    ) -> None:
        self.registry = registry or AvatarRegistry()
        self.musetalk = musetalk_client or MuseTalkClient()
        self.ffmpeg_bin = ffmpeg_bin or "ffmpeg"
        backend_root = Path(__file__).resolve().parents[3]
        self.audio_dir = audio_dir or (backend_root / "media" / "audio")

    # ------------------------------------------------------------------
    # Main render entry points
    # ------------------------------------------------------------------

    async def render_from_text(
        self,
        *,
        avatar_id: str,
        text: str,
        output_path: Path,
        tts_provider,
        source_mode: SourceMode = "auto",
        options: RenderOptions | None = None,
    ) -> tuple[RenderMetadata, RenderResult]:
        """Generate TTS audio then render. Returns (metadata, render_result)."""
        audio_stem = f"tts_{uuid.uuid4().hex[:8]}"
        audio_path = self.audio_dir / f"{audio_stem}.wav"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        tts_request = TTSRequest(text=text, output_path=audio_path)
        tts_result: TTSResult = await tts_provider.synthesize(tts_request)

        return await self.render_from_audio(
            avatar_id=avatar_id,
            audio_path=tts_result.audio_path,
            output_path=output_path,
            input_text=text,
            source_mode=source_mode,
            options=options,
        )

    async def render_from_audio(
        self,
        *,
        avatar_id: str,
        audio_path: Path,
        output_path: Path,
        input_text: str | None = None,
        source_mode: SourceMode = "auto",
        options: RenderOptions | None = None,
    ) -> tuple[RenderMetadata, RenderResult]:
        options = options or RenderOptions()
        started_at = datetime.now(timezone.utc)
        render_id = f"render_{output_path.stem}"
        warnings: list[str] = []

        try:
            source_path, source_type = self._resolve_source(avatar_id, source_mode)
        except (AvatarNotFoundError, FileNotFoundError) as exc:
            return self._failed_metadata(
                render_id=render_id,
                avatar_id=avatar_id,
                audio_path=audio_path,
                output_path=output_path,
                input_text=input_text,
                options=options,
                started_at=started_at,
                error=str(exc),
            )

        # Normalize audio to mono 16kHz WAV
        normalized_audio = audio_path.parent / f"{audio_path.stem}_norm.wav"
        try:
            await self._normalize_audio(audio_path, normalized_audio)
        except Exception as exc:
            warnings.append(f"Audio normalization failed, using original: {exc}")
            normalized_audio = audio_path

        # Prepare avatar (cache warm-up hook)
        avatar_dir = self.registry.get_avatar_dir(avatar_id)
        cache_dir = avatar_dir / "cache"
        prepared: PreparedAvatar = self.musetalk.prepare_avatar(
            avatar_id=avatar_id,
            input_path=source_path,
            cache_dir=cache_dir,
        )

        # Render (sync subprocess — run in executor so we don't block the event loop)
        loop = asyncio.get_event_loop()
        render_result: RenderResult = await loop.run_in_executor(
            None,
            lambda: self.musetalk.render(prepared, normalized_audio, output_path, options),
        )

        completed_at = datetime.now(timezone.utc)
        render_duration = (completed_at - started_at).total_seconds()
        backend_root = Path(__file__).resolve().parents[3]

        metadata = RenderMetadata(
            render_id=render_id,
            avatar_id=avatar_id,
            source_type=source_type,
            source_path=_relative(source_path, backend_root),
            input_text=input_text,
            audio_path=_relative(audio_path, backend_root),
            output_path=_relative(output_path, backend_root),
            duration_seconds=render_result.duration_seconds,
            fps=options.fps,
            resolution=options.resolution,
            motion_profile=options.motion_profile,
            engine="musetalk",
            engine_version=render_result.engine_version,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            render_duration_seconds=render_duration,
            status="completed" if render_result.success else "failed",
            warnings=warnings + render_result.warnings,
            error=render_result.error,
        )
        return metadata, render_result

    # ------------------------------------------------------------------
    # Source selection
    # ------------------------------------------------------------------

    def _resolve_source(self, avatar_id: str, mode: SourceMode) -> tuple[Path, str]:
        avatar_dir = self.registry.get_avatar_dir(avatar_id)
        metadata = self.registry.get_metadata(avatar_id)

        idle_path = avatar_dir / metadata.idle_video
        source_path = avatar_dir / metadata.source_image

        if mode == "idle_video":
            if not idle_path.exists():
                raise FileNotFoundError(f"idle_base.mp4 not found for avatar: {avatar_id}")
            return idle_path, "idle_video"

        if mode == "source_image":
            if not source_path.exists():
                raise FileNotFoundError(f"source_original not found for avatar: {avatar_id}")
            return source_path, "source_image"

        # auto: prefer idle_video → fallback source_image
        if idle_path.exists():
            return idle_path, "idle_video"
        if source_path.exists():
            logger.warning("idle_base.mp4 not found, falling back to source image for %s", avatar_id)
            return source_path, "source_image"

        raise FileNotFoundError(
            f"No source asset found for avatar {avatar_id}. "
            f"Expected {idle_path} or {source_path}."
        )

    # ------------------------------------------------------------------
    # Audio normalization
    # ------------------------------------------------------------------

    async def _normalize_audio(self, src: Path, dst: Path) -> None:
        cmd = [
            self.ffmpeg_bin, "-y",
            "-i", str(src),
            "-ac", "1",
            "-ar", "16000",
            "-sample_fmt", "s16",
            str(dst),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Audio normalization failed:\n{stderr.decode()}")

    # ------------------------------------------------------------------
    # Metadata save helper
    # ------------------------------------------------------------------

    def save_metadata(self, metadata: RenderMetadata, output_path: Path) -> Path:
        meta_path = output_path.with_suffix(".json")
        meta_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
        return meta_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _failed_metadata(
        self,
        *,
        render_id: str,
        avatar_id: str,
        audio_path: Path,
        output_path: Path,
        input_text: str | None,
        options: RenderOptions,
        started_at: datetime,
        error: str,
    ) -> tuple[RenderMetadata, RenderResult]:
        now = datetime.now(timezone.utc)
        backend_root = Path(__file__).resolve().parents[3]
        metadata = RenderMetadata(
            render_id=render_id,
            avatar_id=avatar_id,
            source_type="unknown",
            source_path="",
            input_text=input_text,
            audio_path=_relative(audio_path, backend_root),
            output_path=_relative(output_path, backend_root),
            fps=options.fps,
            resolution=options.resolution,
            motion_profile=options.motion_profile,
            started_at=started_at.isoformat(),
            completed_at=now.isoformat(),
            render_duration_seconds=(now - started_at).total_seconds(),
            status="failed",
            warnings=[],
            error=error,
        )
        return metadata, RenderResult(success=False, error=error)


def _relative(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)
