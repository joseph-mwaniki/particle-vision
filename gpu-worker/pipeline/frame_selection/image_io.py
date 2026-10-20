"""Disk-backed image write/read/validation helpers."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

JPEG_QUALITY = 95
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def write_jpeg(path: Path, image: np.ndarray, quality: int = JPEG_QUALITY) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError(f"cv2.imwrite failed for {path}")
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Wrote empty or missing image file: {path}")


def validate_image_file(path: Path, min_dim: int = 16) -> tuple[bool, str, tuple[int, int] | None]:
    """Return (ok, reason, (width, height)|None)."""
    try:
        if not path.is_file():
            return False, "missing", None
        size = path.stat().st_size
        if size <= 0:
            return False, "empty", None
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            return False, "unreadable", None
        height, width = image.shape[:2]
        if height < min_dim or width < min_dim:
            return False, f"too_small:{width}x{height}", (width, height)
        return True, "ok", (width, height)
    except OSError as exc:
        return False, f"os_error:{exc}", None


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise RuntimeError(f"Unable to decode image: {path}")
    return image


def place_selected_image(source: Path, destination: Path) -> Path:
    """Move selected frame into COLMAP images dir without keeping a duplicate full-size copy.

    Prefers hard-link, then rename (same filesystem), then copy+unlink.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    try:
        os_link = getattr(__import__("os"), "link")
        os_link(source, destination)
    except OSError:
        try:
            source.replace(destination)
            return destination
        except OSError:
            shutil.copy2(source, destination)
            try:
                source.unlink(missing_ok=True)
            except OSError:
                pass
            return destination
    try:
        source.unlink(missing_ok=True)
    except OSError:
        pass
    return destination


def enumerate_images(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def validate_image_directory(directory: Path) -> dict[str, Any]:
    files = enumerate_images(directory)
    valid: list[Path] = []
    invalid: list[dict[str, str]] = []
    for path in files:
        ok, reason, dims = validate_image_file(path)
        if ok:
            valid.append(path)
        else:
            invalid.append({"path": str(path), "reason": reason})
    return {
        "directory": str(directory.resolve()),
        "file_count": len(files),
        "valid_count": len(valid),
        "invalid": invalid,
        "valid_files": [p.name for p in valid],
    }


def clear_image_dir(directory: Path) -> None:
    if not directory.exists():
        directory.mkdir(parents=True, exist_ok=True)
        return
    for path in enumerate_images(directory):
        path.unlink(missing_ok=True)
    # Also remove non-image leftovers that could confuse COLMAP.
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() not in IMAGE_EXTENSIONS:
            if path.name in {"frames.json", "frame_selection.json"}:
                continue
            path.unlink(missing_ok=True)
