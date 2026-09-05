"""Result upload stage — copy outputs to backend uploads directory."""

import logging
import shutil
from pathlib import Path

from typing import Callable, Optional
from config import BACKEND_CALLBACK_URL, BACKEND_UPLOADS_DIR

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]


def _upload_to_remote_backend(
    splat_path: Path,
    collision_path: Path,
    upload_url: str,
    on_log: Optional[LogFn] = None,
) -> None:
    """Stream scene.splat and collision.glb to the backend via multipart POST."""
    import urllib.request
    import uuid

    splat_mb = (splat_path.stat().st_size / (1024 * 1024)) if splat_path.is_file() else 0
    collision_mb = (collision_path.stat().st_size / (1024 * 1024)) if collision_path.is_file() else 0
    if on_log:
        on_log(f"[upload] Preparing upload to {upload_url} (splat: {splat_mb:.1f} MB, collision: {collision_mb:.1f} MB)...")

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    data = bytearray()

    def add_file(field_name: str, file_path: Path) -> None:
        nonlocal data
        data.extend(f"--{boundary}\r\n".encode("utf-8"))
        data.extend(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{file_path.name}"\r\n'.encode("utf-8")
        )
        data.extend(b"Content-Type: application/octet-stream\r\n\r\n")
        data.extend(file_path.read_bytes())
        data.extend(b"\r\n")

    if splat_path.is_file():
        add_file("splat", splat_path)
    if collision_path.is_file():
        add_file("collision", collision_path)

    data.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        upload_url,
        data=bytes(data),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    # Increased timeout to 300 seconds for large 3D scene files
    with urllib.request.urlopen(req, timeout=300) as resp:
        logger.info("[upload] Remote upload to %s status: %d", upload_url, resp.status)
        if on_log:
            on_log(f"[upload] Assets successfully uploaded to backend ({resp.status} OK)")


def upload_results(
    splat_path: Path,
    collision_path: Path,
    callback_url: str,
    job_id: str,
    backend_uploads_dir: Path | None = None,
    on_log: Optional[LogFn] = None,
) -> dict:
    """
    Copy training results into the backend uploads tree, or upload via HTTP if remote.
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

    # Local filesystem copy
    if splat_path != dest_splat:
        shutil.copy2(splat_path, dest_splat)
    if collision_path != dest_collision:
        shutil.copy2(collision_path, dest_collision)

    # Determine upload URL
    target_url = callback_url
    if ("localhost" in target_url or "127.0.0.1" in target_url) and BACKEND_CALLBACK_URL and "localhost" not in BACKEND_CALLBACK_URL:
        target_url = f"{BACKEND_CALLBACK_URL.rstrip('/')}/internal/worker/callback"

    # If backend is on a remote host, upload files directly over HTTP
    if target_url.startswith("http://") or target_url.startswith("https://"):
        if "localhost" not in target_url and "127.0.0.1" not in target_url:
            upload_url = target_url.replace("/callback", f"/upload-result/{job_id}")
            try:
                logger.info("[upload] Uploading outputs to remote backend: %s", upload_url)
                _upload_to_remote_backend(dest_splat, dest_collision, upload_url, on_log=on_log)
            except Exception as exc:
                logger.error("[upload] Remote upload failed: %s", exc)
                if on_log:
                    on_log(f"[upload] WARNING: Remote upload failed: {exc}")

    logger.info("[upload] Results ready for job %s", job_id)

    return {
        "job_id": job_id,
        "splat_path": f"/uploads/jobs/{job_id}/output/scene.splat",
        "collision_path": f"/uploads/jobs/{job_id}/output/collision.glb",
        "callback_url": callback_url,
        "local_splat": str(dest_splat),
        "local_collision": str(dest_collision),
    }

