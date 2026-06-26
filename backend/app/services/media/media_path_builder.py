from __future__ import annotations

from pathlib import Path

from app.core.config import settings


class MediaPathBuilder:
    def _root(self) -> Path:
        return Path(settings.MEDIA_OUTPUT_DIR)

    def audio_path(self, job_id: str) -> Path:
        return self._root() / "audio" / "avatar-renders" / f"{job_id}.wav"

    def audio_normalized_path(self, job_id: str) -> Path:
        return self._root() / "audio" / "avatar-renders" / f"{job_id}_norm.wav"

    def video_path(self, job_id: str) -> Path:
        return self._root() / "renders" / "avatar-renders" / f"{job_id}.mp4"

    def metadata_path(self, job_id: str) -> Path:
        return self._root() / "reports" / "avatar-renders" / f"{job_id}_metadata.json"

    def quality_report_path(self, job_id: str) -> Path:
        return self._root() / "reports" / "avatar-renders" / f"{job_id}_quality.json"


media_path_builder = MediaPathBuilder()

