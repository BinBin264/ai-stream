from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.playout.schemas import PlayoutManifest


class CreatePlayoutProgramRequest(PlayoutManifest):
    overwrite: bool = False


class PlayoutProgramResponse(BaseModel):
    program_id: str
    status: Literal["manifest_created", "metadata_available"]
    manifest_path: str
    metadata: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class PlayoutArtifactResponse(BaseModel):
    program_id: str
    artifact: dict[str, Any]

