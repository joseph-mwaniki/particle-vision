"""Shared pipeline utilities."""

import logging
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_images_zip(zip_path: Path, dest_dir: Path, on_log: Optional[LogFn] = None) -> Path:
    """Extract uploaded ZIP to dest_dir/images/."""
    images_dir = ensure_dir(dest_dir / "images")
    if on_log:
        on_log(f"Extracting {zip_path.name} to {images_dir}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(images_dir)

    # Flatten single top-level folder (common in photo ZIPs)
    entries = [p for p in images_dir.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        nested = entries[0]
        flat_dir = ensure_dir(dest_dir / "images_flat")
        for item in nested.iterdir():
            shutil.move(str(item), str(flat_dir / item.name))
        shutil.rmtree(images_dir)
        flat_dir.rename(images_dir)

    image_count = sum(
        1
        for p in images_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
    )
    if image_count == 0:
        raise RuntimeError(f"No images found after extracting {zip_path}")
    if on_log:
        on_log(f"Found {image_count} images in {images_dir}")
    return images_dir


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


def find_latest_file(directory: Path, pattern: str) -> Optional[Path]:
    matches = sorted(directory.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None
