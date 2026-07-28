"""Result upload stage — copy outputs to backend uploads directory."""

import logging
import shutil
from pathlib import Path

from config import BACKEND_UPLOADS_DIR

logger = logging.getLogger(__name__)


def upload_results(
    splat_path: Path,
    collision_path: Path,
    callback_url: str,
    job_id: str,
    backend_uploads_dir: Path | None = None,
) -> dict:
    """
    Copy training results into the backend uploads tree.

    The backend serves files from /uploads/jobs/{job_id}/output/.
    """
    uploads_root = Path(backend_uploads_dir or BACKEND_UPLOADS_DIR)
    dest_dir = uploads_root / "jobs" / job_id / "output"
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_splat = dest_dir / "scene.splat"
    dest_collision = dest_dir / "collision.glb"

    if not splat_path.is_file():
        raise RuntimeError(f"scene.splat not found at {splat_path}")
    if not collision_path.is_file():
        raise RuntimeError(f"collision.glb not found at {collision_path}")

    shutil.copy2(splat_path, dest_splat)
    shutil.copy2(collision_path, dest_collision)

    logger.info("[upload] Copied results to %s", dest_dir)

    return {
        "job_id": job_id,
        "splat_path": f"/uploads/jobs/{job_id}/output/scene.splat",
        "collision_path": f"/uploads/jobs/{job_id}/output/collision.glb",
        "callback_url": callback_url,
        "local_splat": str(dest_splat),
        "local_collision": str(dest_collision),
    }
