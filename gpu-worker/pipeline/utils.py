"""Shared pipeline utilities."""

import json
import logging
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable, Optional

from .frame_selection import SelectorConfig, select_frames

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_images_zip(zip_path: Path, dest_dir: Path, on_log: Optional[LogFn] = None) -> Path:
    """Extract one uploaded ZIP to dest_dir/images/."""
    return extract_images_zips([zip_path], dest_dir, on_log=on_log)


def extract_images_zips(zip_paths: list[Path], dest_dir: Path, on_log: Optional[LogFn] = None) -> Path:
    """Extract image files from source archives into isolated temporary folders."""
    images_dir = ensure_dir(dest_dir / "images")
    image_extensions = IMAGE_EXTENSIONS
    image_count = 0
    for index, zip_path in enumerate(zip_paths, start=1):
        namespace = re.sub(r"[^a-zA-Z0-9_-]+", "-", zip_path.stem).strip("-")[:80]
        source_dir = images_dir / f"{index:03d}-{namespace or 'source'}"
        if on_log:
            on_log(f"Extracting {zip_path.name} to {source_dir}")
        with zipfile.ZipFile(zip_path, "r") as archive:
            for entry in archive.infolist():
                normalized = entry.filename.replace("\\", "/")
                entry_path = PurePosixPath(normalized)
                if entry.is_dir() or entry_path.is_absolute() or ".." in entry_path.parts:
                    continue
                if entry_path.suffix.lower() not in image_extensions:
                    continue
                destination = source_dir.joinpath(*entry_path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry, "r") as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                image_count += 1

    if image_count == 0:
        raise RuntimeError("No images found after extracting the uploaded ZIP files")
    if on_log:
        on_log(f"Extracted {image_count} images from {len(zip_paths)} ZIP file(s)")
    return images_dir


def _clear_dir(path: Path) -> None:
    if not path.exists():
        return
    for item in sorted(path.iterdir(), reverse=True):
        if item.is_file() or item.is_symlink():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)


def extract_frames_from_video(
    video_path: Path,
    dest_dir: Path,
    on_log: Optional[LogFn] = None,
    job_id: Optional[str] = None,
    config: Optional[SelectorConfig] = None,
) -> Path:
    """Run CPU frame selection and return the COLMAP-ready selected-images directory.

    Layout under dest_dir (job workspace):
      frame_selection/          metadata, manifests, temp staging
      colmap/images/            final validated selected JPEGs (COLMAP input)

    Only frames accepted by the selection algorithm are written for COLMAP.
    """
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise RuntimeError(f"Source video is missing or empty: {video_path}")

    selection_root = ensure_dir(dest_dir / "frame_selection")
    colmap_images = ensure_dir(dest_dir / "colmap" / "images")
    _clear_dir(selection_root)
    # Fresh COLMAP images dir for this attempt (avoids stale contamination).
    for stale in sorted(colmap_images.glob("*")):
        if stale.is_file() or stale.is_symlink():
            stale.unlink(missing_ok=True)
        elif stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)

    selector_config = config or SelectorConfig(max_rejected_preview=0)

    def progress_callback(progress: int, message: str, updates: dict[str, Any] | None = None) -> None:
        if on_log:
            extra = ""
            stats = (updates or {}).get("stats") if updates else None
            if isinstance(stats, dict) and stats.get("selected_frames") is not None:
                extra = f" (selected={stats['selected_frames']})"
            on_log(f"[frame_selection:{progress}%] {message}{extra}")

    if on_log:
        on_log(f"Selecting reconstruction frames from {video_path.name} on CPU (disk-backed)")

    try:
        result = select_frames(
            video_path,
            config=selector_config,
            job_id=job_id,
            progress_callback=progress_callback,
            output_root=selection_root,
            colmap_images_dir=colmap_images,
        )
    except ValueError as exc:
        # VideoCapture / metadata failures raise ValueError with "Unable to open".
        if "Unable to open" in str(exc) or "open video" in str(exc).lower():
            raise RuntimeError(f"Video decoding failed: {exc}") from exc
        raise
    except OSError as exc:
        raise RuntimeError(f"Frame selection disk I/O failed: {exc}") from exc

    # Prefer the absolute path reported by the selector when available.
    reported = result.get("colmap_images_dir")
    if reported:
        colmap_images = Path(reported)
    selected_count = int(result.get("selected_count") or 0)
    frame_files = sorted(p for p in colmap_images.glob("*.jpg") if p.is_file())
    valid_on_disk = int((result.get("stats") or {}).get("valid_on_disk") or len(frame_files))
    if selected_count <= 0 or valid_on_disk <= 0 or not frame_files:
        raise RuntimeError("Frame selection produced no usable frames for reconstruction")

    for warning in result.get("warnings") or []:
        if on_log:
            on_log(f"[frame_selection] {warning}")

    stats = result.get("stats", {})
    metadata = {
        "source_video": video_path.name,
        "job_id": result.get("job_id"),
        "frame_count": valid_on_disk,
        "sampling_stride": stats.get("sampling_stride"),
        "retention_percentage": stats.get("retention_percentage"),
        "continuity_verifiable": stats.get("continuity_verifiable"),
        "continuity_guaranteed": stats.get("continuity_guaranteed"),
        "stats": stats,
        "warnings": result.get("warnings", []),
        "ordered_frames": [p.name for p in frame_files],
        "colmap_images_dir": str(colmap_images.resolve()),
        "algorithm": "frame-extractor-algorithm-disk-backed",
        "write_failures": result.get("write_failures", []),
        "validation": result.get("validation", {}),
    }
    (selection_root / "frame_selection.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if on_log:
        on_log(
            f"Frame selection kept {valid_on_disk} of {result.get('stats', {}).get('total_frames', '?')} frames "
            f"at {colmap_images.resolve()}"
        )
    return colmap_images


def run_command(
    cmd: list[str],
    cwd: Optional[Path] = None,
    on_log: Optional[LogFn] = None,
    timeout: Optional[int] = None,
) -> None:
    """Run a subprocess and stream output to logs."""
    cmd_str = " ".join(cmd)
    logger.info("Running: %s", cmd_str)
    if on_log:
        on_log(f"$ {cmd_str}")

    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout and on_log:
        for line in stdout.splitlines()[-20:]:
            on_log(line)
    if result.returncode != 0:
        tail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"Command failed ({result.returncode}): {cmd_str}\n{tail[-2000:]}")


def download_file(url: str, dest_path: Path, on_log: Optional[LogFn] = None) -> Path:
    """Download a file from an HTTP/HTTPS URL to dest_path."""
    import urllib.parse
    import urllib.request

    ensure_dir(dest_path.parent)

    # Encode spaces and special characters in URL path safely
    parsed = urllib.parse.urlsplit(url)
    encoded_path = urllib.parse.quote(urllib.parse.unquote(parsed.path))
    safe_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, encoded_path, parsed.query, parsed.fragment))

    if on_log:
        on_log(f"Downloading source video from object storage...")
    logger.info("Downloading file from %s to %s", safe_url, dest_path)

    urllib.request.urlretrieve(safe_url, str(dest_path))
    if not dest_path.is_file() or dest_path.stat().st_size == 0:
        raise RuntimeError(f"Failed to download or empty file from {safe_url}")
    return dest_path


def find_latest_file(directory: Path, pattern: str) -> Optional[Path]:
    matches = sorted(directory.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None

