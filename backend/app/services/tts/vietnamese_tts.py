"""
VietnameseTTSProvider — offline-capable TTS for Phase 2 POC.

Priority order (all configurable via env):
  1. edge-tts (free, offline-capable after first use, Vietnamese voices available)
  2. gTTS   (Google, requires internet, free)
  3. Raises RuntimeError if neither is installed.

Install for local POC:
    pip install edge-tts        # preferred
    pip install gtts            # fallback

For higher quality, use the viXTTS provider (TTS_PROVIDER=vixtts).
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path

from app.services.tts.schemas import TTSRequest, TTSResult

logger = logging.getLogger(__name__)

# Default Vietnamese voice for edge-tts
_EDGE_TTS_DEFAULT_VOICE = "vi-VN-HoaiMyNeural"


class VietnameseTTSProvider:
    """
    Pluggable offline-first Vietnamese TTS.
    Attempts edge-tts first, falls back to gTTS.
    """

    def __init__(
        self,
        voice_id: str | None = None,
        ffmpeg_bin: str = "ffmpeg",
    ) -> None:
        self.voice_id = voice_id or _EDGE_TTS_DEFAULT_VOICE
        self.ffmpeg_bin = ffmpeg_bin

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)

        voice = request.voice_id or self.voice_id

        # Try edge-tts first
        try:
            return await self._synthesize_edge_tts(request, voice)
        except ImportError:
            logger.warning("edge-tts not installed, falling back to gTTS")
        except Exception as exc:
            logger.warning("edge-tts failed (%s), falling back to gTTS", exc)

        # Fallback: gTTS
        try:
            return await self._synthesize_gtts(request)
        except ImportError as exc:
            raise RuntimeError(
                "No TTS engine available. Install edge-tts or gtts:\n"
                "  pip install edge-tts\n"
                "  pip install gtts"
            ) from exc

    async def _synthesize_edge_tts(self, request: TTSRequest, voice: str) -> TTSResult:
        import edge_tts  # type: ignore[import]

        communicate = edge_tts.Communicate(request.text, voice)

        # edge-tts outputs MP3; we convert to WAV via ffmpeg
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_mp3 = Path(tmp.name)

        await communicate.save(str(tmp_mp3))
        await self._convert_to_wav(tmp_mp3, request.output_path, request.sample_rate)
        tmp_mp3.unlink(missing_ok=True)

        duration = _probe_duration(request.output_path)
        return TTSResult(
            audio_path=request.output_path,
            duration_seconds=duration,
            sample_rate=request.sample_rate,
            format="wav",
            provider="edge-tts",
        )

    async def _synthesize_gtts(self, request: TTSRequest) -> TTSResult:
        from gtts import gTTS  # type: ignore[import]

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_mp3 = Path(tmp.name)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: gTTS(text=request.text, lang="vi").save(str(tmp_mp3)),
        )
        await self._convert_to_wav(tmp_mp3, request.output_path, request.sample_rate)
        tmp_mp3.unlink(missing_ok=True)

        duration = _probe_duration(request.output_path)
        return TTSResult(
            audio_path=request.output_path,
            duration_seconds=duration,
            sample_rate=request.sample_rate,
            format="wav",
            provider="gtts",
        )

    async def _convert_to_wav(self, src: Path, dst: Path, sample_rate: int) -> None:
        cmd = [
            self.ffmpeg_bin, "-y",
            "-i", str(src),
            "-ac", "1",
            "-ar", str(sample_rate),
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
            raise RuntimeError(f"ffmpeg WAV conversion failed:\n{stderr.decode()}")


def _probe_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return None
