"""Training orchestration — coordinates the full reconstruction pipeline."""

import logging
import time
from pathlib import Path
from typing import Any, Callable, Optional

from config import (
    STAGE_COLMAP,
    STAGE_COLLISION,
    STAGE_COMPLETED,
    STAGE_EXPORT,
    STAGE_FRAME_SELECTION,
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
from pipeline.utils import download_file, extract_frames_from_video

logger = logging.getLogger(__name__)

CallbackFn = Callable[..., None]


def _download_source_archives(
    job_id: str,
    source_files: list[dict[str, str]],
    on_log: Optional[CallbackFn] = None,
) -> tuple[Path, list[Path]]:
    """Download source videos from signed object URLs into the temporary job workspace."""
    work_dir = WORK_DIR / "jobs" / job_id
    source_dir = work_dir / "source-videos"
    source_dir.mkdir(parents=True, exist_ok=True)
    archives = []
    for index, source in enumerate(source_files, start=1):
        original_name = source["original_name"].replace("\\", "/").rsplit("/", 1)[-1]
        archive_path = source_dir / f"{index:03d}-{original_name}"
        download_file(source["download_url"], archive_path, on_log=on_log)
        archives.append(archive_path)
    return work_dir, archives



def run_placeholder_pipeline(
    job_id: str,
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

    on_status(
        STAGE_COMPLETED,
        "[complete] Placeholder pipeline finished without generated assets. Set USE_MOCK=false for real training.",
        100,
    )


def run_full_pipeline(
    job_id: str,
    source_files: list[dict[str, str]],
    output_uploads: dict[str, dict[str, str]],
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
    work_dir, source_archives = _download_source_archives(job_id, source_files)
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    def on_log(message: str) -> None:
        on_status(STAGE_COLMAP, message, _last_progress["value"])

    def on_colmap_progress(_substage: str, progress: int, message: str) -> None:
        _last_progress["value"] = progress
        on_status(STAGE_COLMAP, message, progress)

    def on_gsplat_progress(_substage: str, progress: int, message: str) -> None:
        _last_progress["value"] = progress
        on_status(STAGE_GSPLAT, message, progress)

    _last_progress: dict[str, int] = {"value": 5}

    on_status(STAGE_QUEUED, "Job accepted — starting video frame selection", 5)

    video_path = source_archives[0]
    if not video_path.exists():
        raise RuntimeError(f"Video input is missing: {video_path}")

    selected_frames = extract_frames_from_video(video_path, work_dir, on_log=on_log)
    on_status(STAGE_FRAME_SELECTION, f"Selected {len(list(selected_frames.glob('*.jpg')))} ordered frames for reconstruction", 18)

    colmap_dir = run_colmap(
        selected_frames,
        work_dir / "colmap",
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

    on_status(STAGE_EXPORT, "Uploading generated assets directly to object storage", 95)
    result = upload_results(
        splat_path,
        collision_path,
        output_uploads,
        on_log=lambda msg: on_status(STAGE_EXPORT, msg, 96),
    )

    on_status(
        STAGE_COMPLETED,
        "Pipeline complete — scene ready for viewing",
        100,
        splat_key=result["splat_key"],
        collision_key=result["collision_key"],
    )


def run_pipeline(
    job_id: str,
    source_files: list[dict[str, str]],
    output_uploads: dict[str, dict[str, str]],
    on_status: CallbackFn,
    use_mock: bool = False,
) -> None:
    """Dispatch to placeholder or real pipeline."""
    if use_mock:
        run_placeholder_pipeline(job_id, on_status)
    else:
        run_full_pipeline(job_id, source_files, output_uploads, on_status)
