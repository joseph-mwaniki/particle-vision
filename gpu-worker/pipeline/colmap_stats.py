"""Inspect COLMAP sparse models for registered-image / point counts."""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _read_images_bin_count(path: Path) -> int | None:
    try:
        with path.open("rb") as handle:
            num_images = struct.unpack("<Q", handle.read(8))[0]
            return int(num_images)
    except Exception as exc:
        logger.warning("Failed to read images.bin count from %s: %s", path, exc)
        return None


def _read_images_txt_count(path: Path) -> int | None:
    try:
        count = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                # Each image occupies two lines; count only the pose/header line.
                parts = stripped.split()
                if len(parts) >= 9:
                    count += 1
        return count
    except Exception as exc:
        logger.warning("Failed to read images.txt count from %s: %s", path, exc)
        return None


def _read_points3d_bin_count(path: Path) -> int | None:
    try:
        with path.open("rb") as handle:
            return int(struct.unpack("<Q", handle.read(8))[0])
    except Exception as exc:
        logger.warning("Failed to read points3D.bin count from %s: %s", path, exc)
        return None


def _read_points3d_txt_count(path: Path) -> int | None:
    try:
        count = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                count += 1
        return count
    except Exception as exc:
        logger.warning("Failed to read points3D.txt count from %s: %s", path, exc)
        return None


def inspect_sparse_model(sparse_model: Path) -> dict[str, Any]:
    """Return registered image / 3D point counts from a COLMAP sparse model directory."""
    result: dict[str, Any] = {
        "sparse_model": str(sparse_model),
        "registered_images": None,
        "num_points3d": None,
    }
    images_bin = sparse_model / "images.bin"
    images_txt = sparse_model / "images.txt"
    points_bin = sparse_model / "points3D.bin"
    points_txt = sparse_model / "points3D.txt"

    if images_bin.is_file():
        result["registered_images"] = _read_images_bin_count(images_bin)
    elif images_txt.is_file():
        result["registered_images"] = _read_images_txt_count(images_txt)

    if points_bin.is_file():
        result["num_points3d"] = _read_points3d_bin_count(points_bin)
    elif points_txt.is_file():
        result["num_points3d"] = _read_points3d_txt_count(points_txt)

    return result
