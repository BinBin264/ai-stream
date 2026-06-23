from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.services.playout.errors import (
    PLAYOUT_MANIFEST_INVALID,
    PLAYOUT_MANIFEST_MISSING,
    PLAYOUT_PATH_INVALID,
    PlayoutError,
)
from app.services.playout.paths import ensure_relative_safe
from app.services.playout.schemas import PlayoutManifest


class PlayoutManifestRepository:
    def __init__(self, manifest_dir: Path) -> None:
        self.manifest_dir = manifest_dir

    def path_for(self, program_id: str) -> Path:
        ensure_relative_safe(f"{program_id}.json", field="program_id")
        return self.manifest_dir / f"{program_id}.json"

    def load(self, path_or_program_id: str | Path) -> PlayoutManifest:
        path = Path(path_or_program_id)
        if not path.suffix:
            path = self.path_for(str(path_or_program_id))
        if not path.exists():
            raise PlayoutError(PLAYOUT_MANIFEST_MISSING, "playout manifest does not exist", status_code=404)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return PlayoutManifest(**payload)
        except ValidationError as exc:
            raise PlayoutError(PLAYOUT_MANIFEST_INVALID, "playout manifest is invalid") from exc
        except json.JSONDecodeError as exc:
            raise PlayoutError(PLAYOUT_MANIFEST_INVALID, "playout manifest is not valid JSON") from exc

    def save(self, manifest: PlayoutManifest, *, overwrite: bool = False) -> Path:
        path = self.path_for(manifest.program_id)
        if path.exists() and not overwrite:
            raise PlayoutError("playout_program_exists", "manifest already exists", status_code=409)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def load_relative_to_root(self, media_root: Path, relative_path: str) -> PlayoutManifest:
        if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise PlayoutError(PLAYOUT_PATH_INVALID, "manifest path must be relative to media root")
        return self.load(media_root / relative_path)

