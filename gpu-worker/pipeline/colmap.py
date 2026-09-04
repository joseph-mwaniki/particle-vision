"""COLMAP reconstruction stage."""

import logging
import os
import shutil
from pathlib import Path
from typing import Callable, Optional

from config import COLMAP_QUALITY, COLMAP_USE_GPU, find_colmap_binary
from .utils import ensure_dir, extract_images_zip, run_command

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]
ProgressFn = Callable[[str, int, str], None]

# COLMAP quality presets (camera model + feature settings)
_QUALITY_PRESETS = {
    "low": {"max_image_size": 1600, "max_num_features": 4096},
    "medium": {"max_image_size": 2048, "max_num_features": 8192},
    "high": {"max_image_size": 3200, "max_num_features": 16384},
}


def _colmap_quality() -> dict:
    return _QUALITY_PRESETS.get(COLMAP_QUALITY, _QUALITY_PRESETS["medium"])


def _wrap_xvfb_if_needed(cmd: list[str]) -> list[str]:
    """Wrap command with xvfb-run if in headless environment and xvfb-run is available."""
    if COLMAP_USE_GPU == "1" and "DISPLAY" not in os.environ:
        xvfb = shutil.which("xvfb-run")
        if xvfb:
            return [xvfb, "-a", *cmd]
    return cmd


def run_colmap(
    images_dir: Path,
    output_dir: Path,
    zip_path: Optional[Path] = None,
    on_log: Optional[LogFn] = None,
    on_progress: Optional[ProgressFn] = None,
) -> Path:
    """
    Run COLMAP structure-from-motion on uploaded images.

    Pipeline:
      images/ → feature_extractor → exhaustive_matcher → mapper → sparse/0/

    Returns path to COLMAP dataset root (contains images/ + sparse/0/).
    """
    colmap_bin = find_colmap_binary()
    if not colmap_bin:
        raise RuntimeError("COLMAP binary not found. Install COLMAP and ensure it is on PATH.")

    work_dir = ensure_dir(output_dir)
    database_path = work_dir / "database.db"
    sparse_dir = ensure_dir(work_dir / "sparse")

    if zip_path and zip_path.is_file():
        source_images = extract_images_zip(zip_path, work_dir, on_log=on_log)
    else:
        source_images = Path(images_dir)
        if not source_images.is_dir():
            raise RuntimeError(f"Images directory not found: {source_images}")

    # gsplat Parser expects data_dir/images and data_dir/sparse/0
    dataset_images = ensure_dir(work_dir / "images")
    if source_images.resolve() != dataset_images.resolve():
        if dataset_images.exists():
            shutil.rmtree(dataset_images)
        shutil.copytree(source_images, dataset_images)

    preset = _colmap_quality()

    def report(substage: str, progress: int, message: str) -> None:
        logger.info("[COLMAP:%s] %s", substage, message)
        if on_log:
            on_log(f"[COLMAP:{substage}] {message}")
        if on_progress:
            on_progress(substage, progress, message)

    report("extract_features", 12, f"Running feature extraction (GPU={COLMAP_USE_GPU})")
    try:
        run_command(
            _wrap_xvfb_if_needed([
                colmap_bin,
                "feature_extractor",
                "--database_path",
                str(database_path),
                "--image_path",
                str(dataset_images),
                "--ImageReader.single_camera",
                "1",
                "--SiftExtraction.max_image_size",
                str(preset["max_image_size"]),
                "--SiftExtraction.max_num_features",
                str(preset["max_num_features"]),
                "--SiftExtraction.use_gpu",
                str(COLMAP_USE_GPU),
            ]),
            on_log=on_log,
        )
    except Exception as exc:
        if COLMAP_USE_GPU == "1":
            logger.warning("GPU feature extraction failed (%s). Falling back to CPU extraction.", exc)
            if on_log:
                on_log(f"Warning: GPU extraction failed ({exc}). Retrying on CPU...")
            run_command(
                [
                    colmap_bin,
                    "feature_extractor",
                    "--database_path",
                    str(database_path),
                    "--image_path",
                    str(dataset_images),
                    "--ImageReader.single_camera",
                    "1",
                    "--SiftExtraction.max_image_size",
                    str(preset["max_image_size"]),
                    "--SiftExtraction.max_num_features",
                    str(preset["max_num_features"]),
                    "--SiftExtraction.use_gpu",
                    "0",
                ],
                on_log=on_log,
            )
        else:
            raise

    report("match_features", 20, f"Running exhaustive feature matching (GPU={COLMAP_USE_GPU})")
    try:
        run_command(
            _wrap_xvfb_if_needed([
                colmap_bin,
                "exhaustive_matcher",
                "--database_path",
                str(database_path),
                "--SiftMatching.use_gpu",
                str(COLMAP_USE_GPU),
            ]),
            on_log=on_log,
        )
    except Exception as exc:
        if COLMAP_USE_GPU == "1":
            logger.warning("GPU feature matching failed (%s). Falling back to CPU matching.", exc)
            if on_log:
                on_log(f"Warning: GPU matching failed ({exc}). Retrying on CPU...")
            run_command(
                [
                    colmap_bin,
                    "exhaustive_matcher",
                    "--database_path",
                    str(database_path),
                    "--SiftMatching.use_gpu",
                    "0",
                ],
                on_log=on_log,
            )
        else:
            raise

    report("sparse_reconstruction", 28, "Running sparse mapper (SfM)")
    run_command(
        [
            colmap_bin,
            "mapper",
            "--database_path",
            str(database_path),
            "--image_path",
            str(dataset_images),
            "--output_path",
            str(sparse_dir),
        ],
        on_log=on_log,
    )

    sparse_model = sparse_dir / "0"
    if not sparse_model.is_dir():
        # Some COLMAP versions write directly to sparse/
        if (sparse_dir / "cameras.bin").exists() or (sparse_dir / "cameras.txt").exists():
            sparse_model = sparse_dir
        else:
            raise RuntimeError("COLMAP mapper did not produce sparse/0 reconstruction")

    report("undistort", 30, f"Sparse reconstruction ready at {sparse_model}")
    return work_dir
