from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioNormalizer:
    """Converts audio to 16-bit PCM WAV, mono, 16 kHz using ffmpeg."""

    async def normalize(self, input_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg audio normalization failed (exit {proc.returncode}): "
                f"{stderr.decode(errors='replace')[:500]}"
            )
        logger.debug("Audio normalized", extra={"output": str(output_path)})
        return output_path


audio_normalizer = AudioNormalizer()
