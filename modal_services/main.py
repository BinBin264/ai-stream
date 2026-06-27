"""
ai-stream Modal GPU Services
═══════════════════════════════════════════════════════════════

Hai service chạy GPU trên Modal:
  • TTSService   — viXTTS (T4 GPU) → POST /tts
  • AvatarService — MuseTalk (A10G GPU) → POST /avatar-render

Deploy lần đầu:
  pip install modal
  modal token new          # login
  modal volume create ai-stream-models
  modal volume create ai-stream-avatars
  # Upload speaker WAV:
  modal volume put ai-stream-avatars speaker_reference.wav /model_01/speaker_reference.wav
  modal deploy modal_services/main.py

Sau khi deploy, copy 2 URL endpoint vào .env:
  MODAL_TTS_URL=https://...
  MODAL_AVATAR_URL=https://...

Auth (tùy chọn): tạo secret trên Modal dashboard:
  MODAL_API_TOKEN=<random-token>
  Rồi set cùng giá trị vào .env.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import modal
from fastapi import HTTPException, Request, Response

# ─── App & Volumes ────────────────────────────────────────────────────────────

app = modal.App("ai-stream-gpu")

model_vol = modal.Volume.from_name("ai-stream-models", create_if_missing=True)
avatar_vol = modal.Volume.from_name("ai-stream-avatars", create_if_missing=True)

# ─── Container Images ─────────────────────────────────────────────────────────

vixtts_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(["ffmpeg", "libsndfile1", "gcc", "g++"])
    .pip_install(
        "numpy<2",
        "torch==2.2.2",
        "torchaudio==2.2.2",
        "TTS==0.22.0",
        "transformers==4.37.2",
        "huggingface_hub>=0.23.0",
        "vinorm>=2.0.7",
        "fastapi[standard]",
    )
    .run_commands(
        'python -c "from TTS.tts.configs.xtts_config import XttsConfig; '
        'from TTS.tts.models.xtts import Xtts; '
        'import torch, torchaudio; '
        'print(\'XTTS import ok\', torch.__version__, torchaudio.__version__)"'
    )
)

musetalk_image = (
    modal.Image.from_registry(
        "nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04",
        add_python="3.10",
    )
    .apt_install([
        "git", "ffmpeg", "wget",
        "libgl1-mesa-glx", "libglib2.0-0",
        "libsm6", "libxext6", "libxrender-dev",
    ])
    .run_commands("git clone https://github.com/TMElyralab/MuseTalk /opt/musetalk")
    .pip_install(
        "torch==2.0.1+cu118",
        "torchvision==0.15.2+cu118",
        "torchaudio==2.0.2+cu118",
        extra_index_url="https://download.pytorch.org/whl/cu118",
    )
    .run_commands("pip install -r /opt/musetalk/requirements.txt")
    .pip_install(["openmim", "fastapi[standard]", "python-multipart", "huggingface_hub>=0.23.0", "pyyaml", "gdown"])
    .run_commands(
        "mim install mmengine",
        'mim install "mmcv>=2.0.1"',
        'mim install "mmdet>=3.1.0"',
        'mim install "mmpose>=1.1.0"',
    )
)


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _check_token(request: Request) -> None:
    token = os.environ.get("MODAL_API_TOKEN", "")
    if token and request.headers.get("x-api-token") != token:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ─── TTS Service (viXTTS, T4 GPU) ────────────────────────────────────────────

@app.cls(
    image=vixtts_image,
    gpu="T4",
    volumes={"/models": model_vol, "/avatars": avatar_vol},
    scaledown_window=300,
)
class TTSService:
    MODEL_DIR = "/models/vixtts"
    SPEAKER_WAV = "/avatars/model_01/speaker_reference.wav"

    @modal.enter()
    def load_model(self) -> None:
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts
        from huggingface_hub import snapshot_download

        model_dir = Path(self.MODEL_DIR)
        if not (model_dir / "config.json").exists():
            print("[viXTTS] Downloading model from capleaf/viXTTS ...")
            snapshot_download("capleaf/viXTTS", local_dir=str(model_dir))
            model_vol.commit()

        config = XttsConfig()
        config.load_json(str(model_dir / "config.json"))
        model = Xtts.init_from_config(config)
        model.load_checkpoint(config, checkpoint_dir=str(model_dir), use_deepspeed=False)
        model.cuda()

        gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
            audio_path=[self.SPEAKER_WAV]
        )
        self._model = model
        self._gpt = gpt_cond_latent
        self._spk = speaker_embedding
        print("[viXTTS] Ready")

    @modal.fastapi_endpoint(method="POST", label="tts")
    async def synthesize(self, request: Request) -> Response:
        import torch
        import torchaudio

        _check_token(request)
        body = await request.json()
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="text is required")

        try:
            from vinorm import TTSnorm
            text = TTSnorm(text)
        except Exception:
            pass

        language = body.get("language") or "en"
        if language == "vi":
            language = "en"

        out = self._model.inference(
            text, language,
            self._gpt, self._spk,
            temperature=0.75,
            repetition_penalty=5.0,
        )
        wav = torch.tensor(out["wav"]).unsqueeze(0)
        buf = io.BytesIO()
        torchaudio.save(buf, wav, 24000, format="wav")
        return Response(content=buf.getvalue(), media_type="audio/wav")

    @modal.fastapi_endpoint(method="GET", label="tts-health")
    def health(self, request: Request) -> dict:
        return {"status": "ok", "model": "viXTTS", "gpu": "T4"}


# ─── Avatar Service (MuseTalk, A10G GPU) ──────────────────────────────────────

MUSETALK_HOME = "/opt/musetalk"
MUSETALK_WEIGHTS_DIR = "/models/musetalk-weights"
MUSETALK_WEIGHTS_MARKER = ".downloaded_v4"


@app.function(
    image=musetalk_image,
    volumes={"/models": model_vol},
    timeout=3600,
)
def download_musetalk_weights():
    """One-time weight download. Run with: modal run modal_services/main.py::download_musetalk_weights"""
    import subprocess as sp
    from huggingface_hub import hf_hub_download, snapshot_download

    weights_dir = Path(MUSETALK_WEIGHTS_DIR)
    weights_dir.mkdir(parents=True, exist_ok=True)
    marker = weights_dir / MUSETALK_WEIGHTS_MARKER

    if marker.exists():
        print("[MuseTalk] Weights already downloaded — nothing to do.")
        return

    print("[MuseTalk] Downloading all required weights …")

    # 1. MuseTalk model (v1 + v15)
    snapshot_download(
        "TMElyralab/MuseTalk",
        local_dir=str(weights_dir),
        ignore_patterns=["*.git*", "*.md"],
    )

    # 2. SD-VAE (stabilityai/sd-vae-ft-mse → weights_dir/sd-vae/)
    vae_dir = weights_dir / "sd-vae"
    vae_dir.mkdir(exist_ok=True)
    for fname in ["config.json", "diffusion_pytorch_model.bin"]:
        if not (vae_dir / fname).exists():
            hf_hub_download("stabilityai/sd-vae-ft-mse", fname, local_dir=str(vae_dir))

    # 3. Whisper tiny (openai/whisper-tiny → weights_dir/whisper/)
    whisper_dir = weights_dir / "whisper"
    whisper_dir.mkdir(exist_ok=True)
    for fname in ["config.json", "pytorch_model.bin", "preprocessor_config.json"]:
        if not (whisper_dir / fname).exists():
            hf_hub_download("openai/whisper-tiny", fname, local_dir=str(whisper_dir))

    # 4. DWPose (yzd-v/DWPose → weights_dir/dwpose/)
    dwpose_dir = weights_dir / "dwpose"
    dwpose_dir.mkdir(exist_ok=True)
    if not (dwpose_dir / "dw-ll_ucoco_384.pth").exists():
        hf_hub_download("yzd-v/DWPose", "dw-ll_ucoco_384.pth", local_dir=str(dwpose_dir))

    # 5. SyncNet (ByteDance/LatentSync → weights_dir/syncnet/)
    syncnet_dir = weights_dir / "syncnet"
    syncnet_dir.mkdir(exist_ok=True)
    if not (syncnet_dir / "latentsync_syncnet.pt").exists():
        hf_hub_download("ByteDance/LatentSync", "latentsync_syncnet.pt", local_dir=str(syncnet_dir))

    # 6. Face-parse-bisent
    import urllib.request
    fp_dir = weights_dir / "face-parse-bisent"
    fp_dir.mkdir(exist_ok=True)
    if not (fp_dir / "resnet18-5c106cde.pth").exists():
        print("[MuseTalk] Downloading resnet18 …")
        urllib.request.urlretrieve(
            "https://download.pytorch.org/models/resnet18-5c106cde.pth",
            str(fp_dir / "resnet18-5c106cde.pth"),
        )
    if not (fp_dir / "79999_iter.pth").exists():
        print("[MuseTalk] Downloading 79999_iter.pth via gdown …")
        sp.run(
            ["gdown", "154JgKpzCPW82qINcVieuPH3fZ2e0P812",
             "-O", str(fp_dir / "79999_iter.pth")],
            check=True,
        )

    marker.touch()
    model_vol.commit()
    print("[MuseTalk] All weights downloaded and committed to volume.")


@app.cls(
    image=musetalk_image,
    gpu="A10G",
    volumes={"/models": model_vol, "/avatars": avatar_vol},
    scaledown_window=300,
)
class AvatarService:
    MUSETALK_HOME = MUSETALK_HOME
    WEIGHTS_DIR = MUSETALK_WEIGHTS_DIR

    @modal.enter()
    def setup(self) -> None:
        """Lightweight startup: just verify weights exist and set up symlink."""
        weights_dir = Path(self.WEIGHTS_DIR)
        marker = weights_dir / MUSETALK_WEIGHTS_MARKER
        if not marker.exists():
            raise RuntimeError(
                "MuseTalk weights not found on volume. "
                "Run: modal run modal_services/main.py::download_musetalk_weights"
            )
        musetalk_models = Path(self.MUSETALK_HOME) / "models"
        if not musetalk_models.exists():
            musetalk_models.symlink_to(weights_dir)
        print("[MuseTalk] Weights ready")

    @modal.fastapi_endpoint(method="POST", label="avatar-render")
    async def render(self, request: Request) -> Response:
        import subprocess
        import tempfile
        import yaml

        _check_token(request)

        form = await request.form()
        audio_file = form.get("audio")
        source_file = form.get("source")
        if not audio_file or not source_file:
            raise HTTPException(status_code=422, detail="audio and source fields required")

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            result_dir = tmpdir / "results"
            result_dir.mkdir()

            audio_path = tmpdir / "input.wav"
            audio_path.write_bytes(await audio_file.read())

            fname = getattr(source_file, "filename", "") or "source.png"
            ext = ".mp4" if fname.endswith(".mp4") else ".png"
            source_path = tmpdir / f"source{ext}"
            source_path.write_bytes(await source_file.read())

            # MuseTalk v15 uses a YAML inference config
            config = {
                "task_0": {
                    "video_path": str(source_path),
                    "audio_path": str(audio_path),
                }
            }
            config_path = tmpdir / "inference.yaml"
            config_path.write_text(yaml.dump(config))

            weights_dir = Path(self.WEIGHTS_DIR)
            # HF repo stores config as musetalk.json; inference.py defaults to config.json
            unet_config = weights_dir / "musetalk" / "musetalk.json"
            unet_model = weights_dir / "musetalkV15" / "unet.pth"

            inference_script = Path(self.MUSETALK_HOME) / "scripts" / "inference.py"
            cmd = [
                "python", str(inference_script),
                "--inference_config", str(config_path),
                "--unet_config", str(unet_config),
                "--unet_model_path", str(unet_model),
                "--result_dir", str(result_dir),
                "--fps", "25",
            ]
            env = os.environ.copy()
            env["PYTHONPATH"] = self.MUSETALK_HOME
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.MUSETALK_HOME,
                env=env,
            )
            if result.returncode != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"MuseTalk failed (exit {result.returncode}):\nSTDOUT:{result.stdout[-400:]}\nSTDERR:{result.stderr[-800:]}",
                )

            mp4s = list(result_dir.glob("**/*.mp4"))
            if not mp4s:
                raise HTTPException(
                    status_code=500,
                    detail=f"MuseTalk produced no output MP4. stdout={result.stdout[-400:]}",
                )

            return Response(content=mp4s[0].read_bytes(), media_type="video/mp4")

    @modal.fastapi_endpoint(method="GET", label="avatar-health")
    def health(self, request: Request) -> dict:
        return {"status": "ok", "model": "MuseTalk", "gpu": "A10G"}
