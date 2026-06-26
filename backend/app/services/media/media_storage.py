from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.services.media.media_path_builder import media_path_builder


@dataclass
class StoredMedia:
    video_path: str | None
    audio_path: str | None
    metadata_path: str | None
    quality_report_path: str | None


class MediaStorage:
    def persist(
        self,
        job_id: str,
        *,
        rendered_video_src: Path | None = None,
        audio_src: Path | None = None,
        metadata: dict | None = None,
        quality_report: dict | None = None,
    ) -> StoredMedia:
        stored_video: str | None = None
        stored_audio: str | None = None
        stored_meta: str | None = None
        stored_report: str | None = None

        if rendered_video_src and rendered_video_src.exists():
            dest = media_path_builder.video_path(job_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rendered_video_src, dest)
            stored_video = str(dest)

        if audio_src and audio_src.exists():
            dest = media_path_builder.audio_path(job_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(audio_src, dest)
            stored_audio = str(dest)

        if metadata is not None:
            dest = media_path_builder.metadata_path(job_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
            stored_meta = str(dest)

        if quality_report is not None:
            dest = media_path_builder.quality_report_path(job_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(quality_report, indent=2, default=str), encoding="utf-8")
            stored_report = str(dest)

        return StoredMedia(
            video_path=stored_video,
            audio_path=stored_audio,
            metadata_path=stored_meta,
            quality_report_path=stored_report,
        )


media_storage = MediaStorage()

