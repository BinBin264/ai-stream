from pathlib import Path
import json

from app.core.config import settings
from app.services.avatar.base import AvatarRenderResult


class FakeAvatarRuntimeClient:
    async def render(self, payload: dict) -> AvatarRenderResult:
        job_id = payload["job_id"]
        output_dir = Path(settings.MEDIA_OUTPUT_DIR) / "avatar"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{job_id}.mp4"
        source = Path(settings.IDLE_VIDEO_PATH)
        if source.exists():
            output_path.write_bytes(source.read_bytes())
        else:
            output_path.write_text(
                f"fake avatar video for {job_id}\n"
                f"motion={payload.get('motion_code')}\n"
                f"text={payload.get('text')}\n"
            )
        metadata_path = output_dir / f"{job_id}.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "source_image_path": (payload.get("profile") or {}).get("source_image_path"),
                    "motion_code": payload.get("motion_code"),
                    "motion_video_url": payload.get("motion_video_url"),
                    "text": payload.get("text"),
                    "audio_url": payload.get("audio_url"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return AvatarRenderResult(status="completed", video_url=str(output_path), duration_ms=1000)
