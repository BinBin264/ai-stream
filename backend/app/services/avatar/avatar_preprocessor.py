from pathlib import Path

from PIL import Image

from app.services.avatar.avatar_asset_validator import AvatarAssetValidator
from app.services.avatar.avatar_registry import AvatarRegistry
from app.services.avatar.schemas import AvatarValidationReport, CropCoordinates


class AvatarPreprocessor:
    def __init__(
        self,
        registry: AvatarRegistry | None = None,
        validator: AvatarAssetValidator | None = None,
    ) -> None:
        self.registry = registry or AvatarRegistry()
        self.validator = validator or AvatarAssetValidator(self.registry)

    def prepare(
        self,
        avatar_id: str,
        *,
        crop_x: int | None = None,
        crop_y: int | None = None,
        crop_size: int | None = None,
    ) -> AvatarValidationReport:
        metadata = self.registry.get_metadata(avatar_id)
        avatar_dir = self.registry.get_avatar_dir(avatar_id)
        source_path = avatar_dir / metadata.source_image
        self._create_face_crop(
            source_path=source_path,
            output_path=avatar_dir / metadata.face_crop,
            crop=CropCoordinates(x=crop_x, y=crop_y, size=crop_size)
            if crop_x is not None and crop_y is not None and crop_size is not None
            else metadata.crop,
            metadata_crop_callback=lambda crop: setattr(metadata, "crop", crop),
        )
        report = self.validator.validate_metadata(metadata, avatar_dir)
        self.validator.apply_report(metadata, report)
        self.registry.save_metadata(metadata)
        return report

    def _create_face_crop(
        self,
        *,
        source_path: Path,
        output_path: Path,
        crop: CropCoordinates | None,
        metadata_crop_callback,
    ) -> None:
        with Image.open(source_path) as image:
            image = image.convert("RGB")
            width, height = image.size
            if crop is None:
                size = min(width, height)
                x = max(0, (width - size) // 2)
                y = max(0, (height - size) // 2)
                crop = CropCoordinates(x=x, y=y, size=size)
            crop = self._bounded_crop(crop, width, height)
            cropped = image.crop((crop.x, crop.y, crop.x + crop.size, crop.y + crop.size))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(output_path, format="PNG")
            metadata_crop_callback(crop)

    def _bounded_crop(self, crop: CropCoordinates, width: int, height: int) -> CropCoordinates:
        size = max(1, min(crop.size, width, height))
        x = max(0, min(crop.x, width - size))
        y = max(0, min(crop.y, height - size))
        return CropCoordinates(x=x, y=y, size=size)
