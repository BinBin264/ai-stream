import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.services.avatar.schemas import (
    AvatarAssetInfo,
    AvatarAssetsResponse,
    AvatarListItem,
    AvatarMetadata,
)


def backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


class AvatarNotFoundError(ValueError):
    pass


class InvalidAvatarMetadataError(ValueError):
    pass


class AvatarRegistry:
    def __init__(self, avatars_root: Path | None = None) -> None:
        self.avatars_root = avatars_root or backend_root() / "avatars"

    def list_avatars(self) -> list[AvatarListItem]:
        items: list[AvatarListItem] = []
        if not self.avatars_root.exists():
            return items
        for avatar_dir in sorted(item for item in self.avatars_root.iterdir() if item.is_dir()):
            try:
                metadata = self.get_metadata(avatar_dir.name)
            except (AvatarNotFoundError, InvalidAvatarMetadataError):
                continue
            items.append(
                AvatarListItem(
                    avatar_id=metadata.avatar_id,
                    display_name=metadata.display_name,
                    status=metadata.status,
                    source_ready=metadata.asset_status.source_ready,
                    face_crop_ready=metadata.asset_status.face_crop_ready,
                    idle_video_ready=metadata.asset_status.idle_video_ready,
                    preview_ready=metadata.asset_status.preview_ready,
                )
            )
        return items

    def get_avatar_dir(self, avatar_id: str) -> Path:
        avatar_dir = self.avatars_root / avatar_id
        if not avatar_dir.is_dir():
            raise AvatarNotFoundError(f"Avatar not found: {avatar_id}")
        return avatar_dir

    def get_metadata_path(self, avatar_id: str) -> Path:
        metadata_path = self.get_avatar_dir(avatar_id) / "avatar.json"
        if not metadata_path.is_file():
            raise AvatarNotFoundError(f"Avatar metadata not found: {avatar_id}")
        return metadata_path

    def get_metadata(self, avatar_id: str) -> AvatarMetadata:
        metadata_path = self.get_metadata_path(avatar_id)
        try:
            return AvatarMetadata.model_validate_json(metadata_path.read_text())
        except (json.JSONDecodeError, ValidationError) as exc:
            raise InvalidAvatarMetadataError(f"Invalid avatar metadata: {avatar_id}") from exc

    def save_metadata(self, metadata: AvatarMetadata) -> AvatarMetadata:
        avatar_dir = self.get_avatar_dir(metadata.avatar_id)
        metadata.updated_at = datetime.now(timezone.utc)
        if metadata.created_at is None:
            metadata.created_at = metadata.updated_at
        metadata_path = avatar_dir / "avatar.json"
        metadata_path.write_text(
            metadata.model_dump_json(indent=2, exclude_none=False),
            encoding="utf-8",
        )
        return metadata

    def get_assets(self, avatar_id: str) -> AvatarAssetsResponse:
        avatar_dir = self.get_avatar_dir(avatar_id)
        metadata = self.get_metadata(avatar_id)
        backend = backend_root()
        asset_names = {
            "source_image": metadata.source_image,
            "face_crop": metadata.face_crop,
            "idle_video": metadata.idle_video,
            "preview_video": metadata.preview_video,
            "metadata": "avatar.json",
            "cache": "cache",
        }
        assets: list[AvatarAssetInfo] = []
        for name, filename in asset_names.items():
            path = avatar_dir / filename
            assets.append(
                AvatarAssetInfo(
                    name=name,
                    path=str(path.relative_to(backend)),
                    exists=path.exists(),
                )
            )
        return AvatarAssetsResponse(avatar_id=avatar_id, assets=assets)


avatar_registry = AvatarRegistry()
