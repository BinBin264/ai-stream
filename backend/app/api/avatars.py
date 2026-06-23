import logging

from fastapi import APIRouter, HTTPException

from app.services.avatar.avatar_asset_validator import AvatarAssetValidator
from app.services.avatar.avatar_registry import (
    AvatarNotFoundError,
    InvalidAvatarMetadataError,
    avatar_registry,
)
from app.services.avatar.schemas import (
    AvatarAssetsResponse,
    AvatarListResponse,
    AvatarMetadata,
    AvatarValidationReport,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/avatars", tags=["avatars"])
validator = AvatarAssetValidator(avatar_registry)


@router.get("", response_model=AvatarListResponse)
async def list_avatars() -> AvatarListResponse:
    return AvatarListResponse(items=avatar_registry.list_avatars())


@router.get("/{avatar_id}", response_model=AvatarMetadata)
async def get_avatar(avatar_id: str) -> AvatarMetadata:
    try:
        return avatar_registry.get_metadata(avatar_id)
    except AvatarNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidAvatarMetadataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{avatar_id}/assets", response_model=AvatarAssetsResponse)
async def get_avatar_assets(avatar_id: str) -> AvatarAssetsResponse:
    try:
        return avatar_registry.get_assets(avatar_id)
    except AvatarNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidAvatarMetadataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{avatar_id}/validate", response_model=AvatarValidationReport)
async def validate_avatar(avatar_id: str) -> AvatarValidationReport:
    try:
        report = validator.validate(avatar_id, update_metadata=True)
    except AvatarNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidAvatarMetadataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected avatar validation failure", extra={"avatar_id": avatar_id})
        raise HTTPException(status_code=500, detail="Unexpected avatar validation failure") from exc

    if _is_unprocessable_source(report):
        raise HTTPException(status_code=422, detail={"errors": report.errors, "warnings": report.warnings})
    return report


def _is_unprocessable_source(report: AvatarValidationReport) -> bool:
    markers = (
        "Source image is missing",
        "Unsupported image format",
        "Source image is corrupted",
    )
    return any(error.startswith(markers) for error in report.errors)
