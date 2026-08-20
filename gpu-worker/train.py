"""Training orchestration — coordinates the full reconstruction pipeline."""

import logging
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

from config import (
    BACKEND_UPLOADS_DIR,
    STAGE_COLMAP,
    STAGE_COLLISION,
    STAGE_COMPLETED,
    STAGE_EXPORT,
    STAGE_GSPLAT,
    STAGE_QUEUED,
    WORK_DIR,
)
from pipeline import (
    convert_to_splat,
    generate_collision_mesh,
    run_colmap,
    train_gsplat,
    upload_results,
)
from pipeline.utils import download_file

logger = logging.getLogger(__name__)

CallbackFn = Callable[..., None]


def _resolve_work_dir(job_id: str, images_path: str, on_log: Optional[CallbackFn] = None) -> tuple[Path, Path]:
    """Resolve job workspace and uploaded ZIP path (downloading if URL)."""
    work_dir = WORK_DIR / "jobs" / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    if images_path.startswith("http://") or images_path.startswith("https://"):
        zip_path = work_dir / "images.zip"
        download_file(images_path, zip_path, on_log=on_log)
    else:
        zip_path = Path(images_path)

    return work_dir, zip_path



def run_placeholder_pipeline(
    job_id: str,
    images_path: str,
    callback_url: str,
    on_status: CallbackFn,
) -> None:
    """
    Run the placeholder training pipeline with status callbacks.

    Simulates the full pipeline stages without executing GPU work.
    """
    logger.info("Starting placeholder pipeline for job %s", job_id)

    stages = [
        (STAGE_QUEUED, "Job accepted by GPU worker", 0),
        (STAGE_COLMAP, "[COLMAP:extract_features] Placeholder: feature extraction", 10),
        (STAGE_COLMAP, "[COLMAP:match_features] Placeholder: feature matching", 18),
        (STAGE_COLMAP, "[COLMAP:sparse_reconstruction] Placeholder: structure-from-motion", 25),
        (STAGE_GSPLAT, "[gsplat:init] Placeholder: initializing Gaussians", 40),
        (STAGE_GSPLAT, "[gsplat:train] Placeholder: optimization loop", 60),
        (STAGE_COLLISION, "[collision] Placeholder: sparse point cloud → collision.glb", 75),
        (STAGE_EXPORT, "[export] Placeholder: PLY → scene.splat conversion", 90),
    ]

    for status, log_msg, progress in stages:
        on_status(status, log_msg, progress)
        time.sleep(0.8)

    splat_path = f"/uploads/jobs/{job_id}/output/scene.splat"
    collision_path = f"/uploads/jobs/{job_id}/output/collision.glb"

    on_status(
        STAGE_COMPLETED,
        "[complete] Placeholder pipeline finished. Set USE_MOCK=false for real training.",
        100,
        splat_path=splat_path,
        collision_path=collision_path,
    )


def run_full_pipeline(
    job_id: str,
    images_path: str,
    callback_url: str,
    on_status: CallbackFn,
) -> None:
    """
    Run the full reconstruction pipeline using COLMAP + gsplat.

    Pipeline order:
      1. run_colmap()
      2. train_gsplat()
      3. generate_collision_mesh()
      4. convert_to_splat()
      5. upload_results()
    """
    work_dir, zip_path = _resolve_work_dir(job_id, images_path)
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    backend_uploads = zip_path.parent if zip_path.parent.name == "uploads" else BACKEND_UPLOADS_DIR

    def on_log(message: str) -> None:
        on_status(STAGE_COLMAP, message, _last_progress["value"])

    def on_colmap_progress(_substage: str, progress: int, message: str) -> None:
        _last_progress["value"] = progress
        on_status(STAGE_COLMAP, message, progress)

    def on_gsplat_progress(_substage: str, progress: int, message: str) -> None:
        _last_progress["value"] = progress
        on_status(STAGE_GSPLAT, message, progress)

    _last_progress: dict[str, int] = {"value": 5}

    on_status(STAGE_QUEUED, "Job accepted — starting COLMAP reconstruction", 5)

    colmap_dir = run_colmap(
        work_dir / "images",
        work_dir / "colmap",
        zip_path=zip_path,
        on_log=on_log,
        on_progress=on_colmap_progress,
    )

    on_status(STAGE_GSPLAT, "COLMAP complete — starting gsplat training", 32)
    model_path = train_gsplat(
        colmap_dir,
        work_dir / "training",
        on_log=lambda msg: on_status(STAGE_GSPLAT, msg, _last_progress["value"]),
        on_progress=on_gsplat_progress,
    )

    on_status(STAGE_COLLISION, "Generating collision mesh from sparse reconstruction", 72)
    collision_path = generate_collision_mesh(
        colmap_dir,
        output_dir,
        on_log=lambda msg: on_status(STAGE_COLLISION, msg, 78),
    )

    on_status(STAGE_EXPORT, "Converting trained model to .splat format", 85)
    splat_path = convert_to_splat(
        model_path,
        output_dir,
        on_log=lambda msg: on_status(STAGE_EXPORT, msg, 88),
    )

    on_status(STAGE_EXPORT, "Copying results to backend uploads", 95)
    result = upload_results(
        splat_path,
        collision_path,
        callback_url,
        job_id,
        backend_uploads_dir=backend_uploads,
    )

    on_status(
        STAGE_COMPLETED,
        "Pipeline complete — scene ready for viewing",
        100,
        splat_path=result["splat_path"],
        collision_path=result["collision_path"],
    )


def run_pipeline(
    job_id: str,
    images_path: str,
    callback_url: str,
    on_status: CallbackFn,
    use_mock: bool = False,
) -> None:
    """Dispatch to placeholder or real pipeline."""
    if use_mock:
        run_placeholder_pipeline(job_id, images_path, callback_url, on_status)
    else:
        run_full_pipeline(job_id, images_path, callback_url, on_status)
