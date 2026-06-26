from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

from app.services.tts.schemas import TTSRequest, TTSResult

logger = logging.getLogger(__name__)

_MODEL_REPO = "capleaf/viXTTS"
_SAMPLE_RATE = 24_000


class ViXTTSProvider:
    """Vietnamese TTS via viXTTS (XTTS-v2 fine-tuned on Vietnamese).

    The model is downloaded from HuggingFace on first use and cached at
    model_dir. A 6-second speaker reference WAV is required for voice cloning.
    """

    def __init__(self, model_dir: str, speaker_wav: str) -> None:
        self.model_dir = Path(model_dir)
        self.speaker_wav = speaker_wav
        self._model = None
        self._gpt_cond_latent = None
        self._speaker_embedding = None

    def _load(self) -> None:
        if self._model is not None:
            return

        import torch
        from huggingface_hub import snapshot_download
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        if not self.model_dir.exists() or not any(self.model_dir.iterdir()):
            logger.info("Downloading viXTTS model to %s …", self.model_dir)
            snapshot_download(_MODEL_REPO, local_dir=str(self.model_dir))

        logger.info("Loading viXTTS from %s", self.model_dir)
        config = XttsConfig()
        config.load_json(str(self.model_dir / "config.json"))
        model = Xtts.init_from_config(config)
        model.load_checkpoint(config, checkpoint_dir=str(self.model_dir))
        if torch.cuda.is_available():
            model.cuda()
        model.eval()
        self._model = model

        logger.info("Computing speaker embeddings from %s", self.speaker_wav)
        self._gpt_cond_latent, self._speaker_embedding = model.get_conditioning_latents(
            audio_path=self.speaker_wav,
            gpt_cond_len=30,
            gpt_cond_chunk_len=4,
            max_ref_length=60,
        )

    def _synthesize_sync(self, request: TTSRequest) -> TTSResult:
        import torch
        import torchaudio

        self._load()

        text = request.text
        try:
            from vinorm import TTSnorm  # type: ignore[import]
            text = TTSnorm(text)
        except Exception:
            pass

        out = self._model.inference(  # type: ignore[union-attr]
            text,
            "vi",
            self._gpt_cond_latent,
            self._speaker_embedding,
            repetition_penalty=5.0,
            temperature=0.75,
            enable_text_splitting=True,
        )

        wav = torch.tensor(out["wav"]).unsqueeze(0)
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        torchaudio.save(str(request.output_path), wav, _SAMPLE_RATE)

        duration = _probe_duration(request.output_path) or (len(out["wav"]) / _SAMPLE_RATE)
        return TTSResult(
            audio_path=request.output_path,
            duration_seconds=duration,
            sample_rate=_SAMPLE_RATE,
            format="wav",
            provider="vixtts",
        )

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, request)


def _probe_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return None
