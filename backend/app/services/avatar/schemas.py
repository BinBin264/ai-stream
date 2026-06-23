from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


AvatarStatus = Literal["draft", "ready", "disabled"]


class CropCoordinates(BaseModel):
    x: int
    y: int
    size: int


class MotionProfile(BaseModel):
    mode: str = "minimal"
    head_motion: str = "low"
    eye_blink: str = "natural"
    shoulder_motion: str = "disabled"
    hand_motion: str = "disabled"
    camera_motion: str = "disabled"


class AvatarQuality(BaseModel):
    source_width: int | None = None
    source_height: int | None = None
    face_crop_width: int | None = None
    face_crop_height: int | None = None
    is_hd_ready: bool = False
    warnings: list[str] = Field(default_factory=list)


class AvatarAssetStatus(BaseModel):
    source_ready: bool = False
    face_crop_ready: bool = False
    idle_video_ready: bool = False
    preview_ready: bool = False


class ManualReview(BaseModel):
    face_frontal: bool | None = None
    eyes_visible: bool | None = None
    mouth_visible: bool | None = None
    lighting_even: bool | None = None
    hands_not_covering_face: bool | None = None
    approved_by_human: bool = False


class AvatarMetadata(BaseModel):
    avatar_id: str
    display_name: str
    status: AvatarStatus = "draft"
    source_image: str = "source_original.jpg"
    face_crop: str = "source_face_crop.png"
    idle_video: str = "idle_base.mp4"
    preview_video: str = "preview.mp4"
    crop: CropCoordinates | None = None
    motion_profile: MotionProfile = Field(default_factory=MotionProfile)
    quality: AvatarQuality = Field(default_factory=AvatarQuality)
    asset_status: AvatarAssetStatus = Field(default_factory=AvatarAssetStatus)
    manual_review: ManualReview = Field(default_factory=ManualReview)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AvatarListItem(BaseModel):
    avatar_id: str
    display_name: str
    status: AvatarStatus
    source_ready: bool
    face_crop_ready: bool
    idle_video_ready: bool
    preview_ready: bool


class AvatarListResponse(BaseModel):
    items: list[AvatarListItem]


class AvatarAssetInfo(BaseModel):
    name: str
    path: str
    exists: bool


class AvatarAssetsResponse(BaseModel):
    avatar_id: str
    assets: list[AvatarAssetInfo]


class AvatarValidationReport(BaseModel):
    avatar_id: str
    valid: bool
    source_ready: bool
    face_crop_ready: bool
    idle_video_ready: bool
    preview_ready: bool
    source_width: int | None = None
    source_height: int | None = None
    face_crop_width: int | None = None
    face_crop_height: int | None = None
    is_hd_ready: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def relative_asset_path(avatar_dir: Path, asset_path: Path) -> str:
    return str(asset_path.relative_to(avatar_dir.parent.parent.parent))
