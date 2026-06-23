from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.playout import CreatePlayoutProgramRequest, PlayoutArtifactResponse, PlayoutProgramResponse
from app.services.playout.errors import PlayoutError
from app.services.playout.manifest_repository import PlayoutManifestRepository
from app.services.playout.paths import backend_root, relative_to_backend
from app.services.playout.schemas import PlayoutManifest

router = APIRouter(prefix="/api/playout-programs", tags=["playout-programs"])


def _roots() -> tuple[Path, Path, Path]:
    root = backend_root()
    media_root = root / "media"
    program_root = media_root / "playout" / "programs"
    return root, media_root, program_root


def _artifact(program_id: str, filename: str) -> dict:
    root, _, program_root = _roots()
    path = program_root / program_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "playout_output_missing", "message": "artifact not found"})
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("", response_model=PlayoutProgramResponse, status_code=202)
async def create_playout_program(body: CreatePlayoutProgramRequest) -> PlayoutProgramResponse:
    root, media_root, _ = _roots()
    repo = PlayoutManifestRepository(media_root / "playout" / "manifests")
    try:
        manifest = body.model_dump(exclude={"overwrite"})
        path = repo.save(PlayoutManifest.model_validate(manifest), overwrite=body.overwrite)
    except PlayoutError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc
    return PlayoutProgramResponse(
        program_id=body.program_id,
        status="manifest_created",
        manifest_path=relative_to_backend(path, root),
        warnings=["manifest saved; build or enqueue it through the playout runtime"],
    )


@router.get("/{program_id}", response_model=PlayoutProgramResponse)
async def get_playout_program(program_id: str) -> PlayoutProgramResponse:
    root, media_root, program_root = _roots()
    repo = PlayoutManifestRepository(media_root / "playout" / "manifests")
    try:
        manifest_path = repo.path_for(program_id)
    except PlayoutError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail={"code": "playout_manifest_missing", "message": "manifest not found"})
    metadata_path = program_root / program_id / "output_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else None
    return PlayoutProgramResponse(
        program_id=program_id,
        status="metadata_available" if metadata else "manifest_created",
        manifest_path=relative_to_backend(manifest_path, root),
        metadata=metadata,
    )


@router.get("/{program_id}/timeline", response_model=PlayoutArtifactResponse)
async def get_playout_timeline(program_id: str) -> PlayoutArtifactResponse:
    return PlayoutArtifactResponse(program_id=program_id, artifact=_artifact(program_id, "timeline.json"))


@router.get("/{program_id}/validation", response_model=PlayoutArtifactResponse)
async def get_playout_validation(program_id: str) -> PlayoutArtifactResponse:
    return PlayoutArtifactResponse(program_id=program_id, artifact=_artifact(program_id, "validation_report.json"))
