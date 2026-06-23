import logging
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.services.avatar.avatar_registry import AvatarRegistry
from app.services.avatar.schemas import AvatarMetadata, AvatarValidationReport

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MIN_SOURCE_WIDTH = 1280
MIN_SOURCE_HEIGHT = 720
MIN_FACE_CROP_SIZE = 512
MIN_ASPECT_RATIO = 0.45
MAX_ASPECT_RATIO = 2.5


class AvatarAssetValidator:
    def __init__(self, registry: AvatarRegistry | None = None) -> None:
        self.registry = registry or AvatarRegistry()

    def validate(self, avatar_id: str, *, update_metadata: bool = True) -> AvatarValidationReport:
        metadata = self.registry.get_metadata(avatar_id)
        avatar_dir = self.registry.get_avatar_dir(avatar_id)
        report = self.validate_metadata(metadata, avatar_dir)
        if update_metadata:
            self.apply_report(metadata, report)
            self.registry.save_metadata(metadata)
        return report

    def validate_metadata(self, metadata: AvatarMetadata, avatar_dir: Path) -> AvatarValidationReport:
        warnings: list[str] = []
        errors: list[str] = []
        source_width: int | None = None
        source_height: int | None = None
        face_crop_width: int | None = None
        face_crop_height: int | None = None

        source_path = avatar_dir / metadata.source_image
        source_ready = False
        if not source_path.exists():
            errors.append(f"Source image is missing: {metadata.source_image}")
        elif source_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            errors.append(f"Unsupported image format: {source_path.suffix.lower()}")
        else:
            try:
                source_width, source_height = self._image_size(source_path)
                source_ready = True
                if source_width < MIN_SOURCE_WIDTH:
                    warnings.append(
                        f"Source width {source_width}px is below recommended {MIN_SOURCE_WIDTH}px for high-quality lip-sync."
                    )
                if source_height < MIN_SOURCE_HEIGHT:
                    warnings.append(
                        f"Source height {source_height}px is below recommended {MIN_SOURCE_HEIGHT}px for high-quality lip-sync."
                    )
                aspect_ratio = source_width / source_height
                if aspect_ratio < MIN_ASPECT_RATIO or aspect_ratio > MAX_ASPECT_RATIO:
                    errors.append(f"Source image aspect ratio {aspect_ratio:.2f} is outside supported range.")
            except (UnidentifiedImageError, OSError) as exc:
                errors.append(f"Source image is corrupted or unreadable: {exc}")

        face_crop_path = avatar_dir / metadata.face_crop
        face_crop_ready = False
        if face_crop_path.exists():
            try:
                face_crop_width, face_crop_height = self._image_size(face_crop_path)
                face_crop_ready = True
                if face_crop_width < MIN_FACE_CROP_SIZE or face_crop_height < MIN_FACE_CROP_SIZE:
                    warnings.append(
                        f"Face crop {face_crop_width}x{face_crop_height}px is below recommended {MIN_FACE_CROP_SIZE}x{MIN_FACE_CROP_SIZE}px."
                    )
            except (UnidentifiedImageError, OSError) as exc:
                face_crop_ready = False
                errors.append(f"Face crop is corrupted or unreadable: {exc}")

        idle_video_ready = (avatar_dir / metadata.idle_video).exists()
        preview_ready = (avatar_dir / metadata.preview_video).exists()
        is_hd_ready = bool(
            source_ready
            and not errors
            and source_width is not None
            and source_height is not None
            and source_width >= MIN_SOURCE_WIDTH
            and source_height >= MIN_SOURCE_HEIGHT
            and (not face_crop_ready or (face_crop_width or 0) >= MIN_FACE_CROP_SIZE)
            and (not face_crop_ready or (face_crop_height or 0) >= MIN_FACE_CROP_SIZE)
        )

        return AvatarValidationReport(
            avatar_id=metadata.avatar_id,
            valid=source_ready and not errors,
            source_ready=source_ready,
            face_crop_ready=face_crop_ready,
            idle_video_ready=idle_video_ready,
            preview_ready=preview_ready,
            source_width=source_width,
            source_height=source_height,
            face_crop_width=face_crop_width,
            face_crop_height=face_crop_height,
            is_hd_ready=is_hd_ready,
            warnings=warnings,
            errors=errors,
        )

    def apply_report(self, metadata: AvatarMetadata, report: AvatarValidationReport) -> AvatarMetadata:
        metadata.quality.source_width = report.source_width
        metadata.quality.source_height = report.source_height
        metadata.quality.face_crop_width = report.face_crop_width
        metadata.quality.face_crop_height = report.face_crop_height
        metadata.quality.is_hd_ready = report.is_hd_ready
        metadata.quality.warnings = report.warnings
        metadata.asset_status.source_ready = report.source_ready
        metadata.asset_status.face_crop_ready = report.face_crop_ready
        metadata.asset_status.idle_video_ready = report.idle_video_ready
        metadata.asset_status.preview_ready = report.preview_ready
        metadata.status = "ready" if report.valid and report.face_crop_ready else "draft"
        return metadata

    def _image_size(self, path: Path) -> tuple[int, int]:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            return image.size
