from __future__ import annotations

from pathlib import Path

from app.services.playout.errors import PLAYOUT_PATH_INVALID, PlayoutError


def backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def ensure_relative_safe(path: str, *, field: str = "path") -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PlayoutError(PLAYOUT_PATH_INVALID, f"{field} must be a safe relative path")
    return candidate


def safe_join(root: Path, relative_path: str, *, field: str = "path") -> Path:
    candidate = ensure_relative_safe(relative_path, field=field)
    full = (root / candidate).resolve()
    root_resolved = root.resolve()
    if full != root_resolved and root_resolved not in full.parents:
        raise PlayoutError(PLAYOUT_PATH_INVALID, f"{field} escapes the configured root")
    return full


def relative_to_backend(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))

