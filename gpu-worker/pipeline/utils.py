"""Shared pipeline utilities."""

import json
import logging
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Callable, Optional

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_images_zip(zip_path: Path, dest_dir: Path, on_log: Optional[LogFn] = None) -> Path:
    """Extract one uploaded ZIP to dest_dir/images/."""
    return extract_images_zips([zip_path], dest_dir, on_log=on_log)


def extract_images_zips(zip_paths: list[Path], dest_dir: Path, on_log: Optional[LogFn] = None) -> Path:
    """Extract image files from source archives into isolated temporary folders."""
    images_dir = ensure_dir(dest_dir / "images")
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
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


def extract_frames_from_video(
    video_path: Path,
    dest_dir: Path,
    on_log: Optional[LogFn] = None,
    fps: float = 1.0,
) -> Path:
    """Extract a video into an ordered image sequence under dest_dir/frames/.

    This acts as an adapter around the frame-selection stage. If an external frame-
    extractor implementation is available via FRAME_EXTRACTOR_PATH, it is invoked.
    Otherwise this falls back to ffmpeg to produce a stable sequence of JPEG frames
    suitable for COLMAP.
    """
    frames_dir = ensure_dir(dest_dir / "frames")
    if frames_dir.exists():
        for item in sorted(frames_dir.iterdir(), reverse=True):
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

    external = Path(__import__("os").environ.get("FRAME_EXTRACTOR_PATH", "")).expanduser()
    if external and external.is_file():
        if on_log:
            on_log(f"Using external frame extractor: {external}")
        subprocess.run([str(external), str(video_path), str(frames_dir)], check=True)
        image_files = sorted(frames_dir.glob("*"))
        if not image_files:
            raise RuntimeError("External frame extractor produced no output frames")
        return frames_dir

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to extract frames from video, and no external frame extractor is configured")

    if on_log:
        on_log(f"Extracting frames from {video_path.name} into {frames_dir}")
    subprocess.run([
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps}",
        "-q:v",
        "2",
        str(frames_dir / "%06d.jpg"),
    ], check=True, capture_output=True, text=True)

    frame_files = sorted(frames_dir.glob("*.jpg"))
    if not frame_files:
        raise RuntimeError("No frames were extracted from the video input")

    metadata = {
        "source_video": video_path.name,
        "frame_count": len(frame_files),
        "fps": fps,
        "ordered_frames": [p.name for p in frame_files],
    }
    (frames_dir / "frame_selection.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return frames_dir


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
        on_log(f"Downloading input archive from {safe_url}...")
    logger.info("Downloading file from %s to %s", safe_url, dest_path)

    urllib.request.urlretrieve(safe_url, str(dest_path))
    if not dest_path.is_file() or dest_path.stat().st_size == 0:
        raise RuntimeError(f"Failed to download or empty file from {safe_url}")
    return dest_path


def find_latest_file(directory: Path, pattern: str) -> Optional[Path]:
    matches = sorted(directory.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None

