"""Upload generated assets directly from temporary worker storage to R2."""

import logging
from pathlib import Path

from typing import Callable, Optional

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]


def upload_results(
    splat_path: Path,
    collision_path: Path,
    output_uploads: dict[str, dict[str, str]],
    on_log: Optional[LogFn] = None,
) -> dict:
    if not splat_path.is_file():
        raise RuntimeError(f"scene.splat not found at {splat_path}")
    if not collision_path.is_file():
        raise RuntimeError(f"collision.glb not found at {collision_path}")
    import requests

    for asset, file_path, content_type in (
        ("splat", splat_path, "application/octet-stream"),
        ("collision", collision_path, "model/gltf-binary"),
    ):
        destination = output_uploads[asset]
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if on_log:
            on_log(f"[upload] Sending {file_path.name} directly to object storage ({size_mb:.1f} MB)")
        with file_path.open("rb") as body:
            response = requests.put(
                destination["url"],
                data=body,
                headers={"Content-Type": content_type},
                timeout=(10, 300),
            )
        response.raise_for_status()
        logger.info("[upload] Uploaded %s to object key %s", asset, destination["key"])

    if on_log:
        on_log("[upload] Generated assets uploaded directly to object storage")
    return {
        "splat_key": output_uploads["splat"]["key"],
        "collision_key": output_uploads["collision"]["key"],
    }

