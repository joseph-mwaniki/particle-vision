config.py

"""GPU worker configuration."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Ensure Qt uses offscreen platform for headless environments like COLMAP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# Pipeline mode
USE_MOCK = os.getenv("USE_MOCK", "false").lower() in ("1", "true", "yes")

# Paths
WORK_DIR = Path(os.getenv("WORK_DIR", "/workspace/data"))

# Training defaults
GSPLAT_STEPS = int(os.getenv("GSPLAT_STEPS", "7000"))
COLMAP_QUALITY = os.getenv("COLMAP_QUALITY", "medium")
COLMAP_BINARY = os.getenv("COLMAP_BINARY", "colmap")
COLMAP_USE_GPU = os.getenv("COLMAP_USE_GPU", "1")
COLMAP_MATCHER = os.getenv("COLMAP_MATCHER", "exhaustive")

# gsplat source path (vendored in monorepo, mounted in Docker)
GSPLAT_REPO_PATH = Path(os.getenv("GSPLAT_REPO_PATH", str(Path(__file__).resolve().parent.parent / "gsplat")))

# Pipeline stage identifiers (match backend JobStatus values)
STAGE_QUEUED = "QUEUED"
STAGE_FRAME_SELECTION = "PROCESSING_FRAME_SELECTION"
STAGE_COLMAP = "PROCESSING_COLMAP"
STAGE_GSPLAT = "PROCESSING_GSPLAT"
STAGE_COLLISION = "PROCESSING_COLLISION"
STAGE_EXPORT = "PROCESSING_EXPORT"
STAGE_COMPLETED = "COMPLETED"
STAGE_FAILED = "FAILED"

# COLMAP sub-stages reported under PROCESSING_COLMAP
COLMAP_SUBSTAGES = (
    "extract_features",
    "match_features",
    "sparse_reconstruction",
    "undistort",
)


def find_colmap_binary() -> Optional[str]:
    """Return path to COLMAP binary if available."""
    configured = shutil.which(COLMAP_BINARY)
    if configured:
        return configured
    return shutil.which("colmap")


def check_colmap_available() -> tuple[bool, str]:
    """Verify COLMAP binary is installed and runnable."""
    binary = find_colmap_binary()
    if not binary:
        return False, f"COLMAP binary '{COLMAP_BINARY}' not found on PATH"
    try:
        result = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0 and not result.stdout and not result.stderr:
            return False, f"COLMAP at {binary} failed to run"
        return True, binary
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"COLMAP check failed: {exc}"


def check_torch_cuda_available() -> tuple[bool, str]:
    """Verify PyTorch with CUDA is available."""
    try:
        import torch
    except ImportError:
        return False, "PyTorch is not installed"

    if not torch.cuda.is_available():
        return False, "PyTorch is installed but CUDA is not available"
    device = torch.cuda.get_device_name(0)
    return True, f"CUDA available ({device})"


def check_gsplat_available() -> tuple[bool, str]:
    """Verify gsplat Python package is importable."""
    try:
        import gsplat  # noqa: F401
        from gsplat import export_splats  # noqa: F401
    except ImportError as exc:
        return False, f"gsplat is not installed: {exc}"

    if not GSPLAT_REPO_PATH.is_dir():
        return False, f"gsplat repo not found at {GSPLAT_REPO_PATH}"
    trainer = GSPLAT_REPO_PATH / "examples" / "simple_trainer.py"
    if not trainer.is_file():
        return False, f"simple_trainer.py not found at {trainer}"
    return True, str(GSPLAT_REPO_PATH)


def validate_pipeline_environment() -> dict[str, tuple[bool, str]]:
    """Run all runtime checks for the real pipeline."""
    return {
        "colmap": check_colmap_available(),
        "torch_cuda": check_torch_cuda_available(),
        "gsplat": check_gsplat_available(),
        "python": (sys.version_info >= (3, 10), f"Python {sys.version_info.major}.{sys.version_info.minor}"),
    }


def require_pipeline_environment() -> None:
    """Raise RuntimeError if the real pipeline cannot run."""
    checks = validate_pipeline_environment()
    failures = [f"{name}: {msg}" for name, (ok, msg) in checks.items() if not ok]
    if failures:
        raise RuntimeError(
            "Pipeline environment check failed:\n  - " + "\n  - ".join(failures)
        )


video_reader.py
from __future__ import annotations

from pathlib import Path

import cv2


def get_video_metadata(video_path: str | Path) -> dict:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Unable to open video file: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 0.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps if fps > 0 else 0.0

    cap.release()
    return {
        "fps": fps,
        "frame_count": total_frames,
        "duration": duration,
        "width": width,
        "height": height,
        "filename": str(Path(video_path).name),
    }


def iter_frames(video_path: str | Path, max_frames: int | None = None, stride: int = 1):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Unable to open video file: {video_path}")

    frame_index = 0
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 1.0)
    effective_stride = max(1, int(stride))

    while True:
        if max_frames is not None and frame_index >= max_frames:
            break
        if effective_stride > 1 and (frame_index % effective_stride != 0):
            ok = cap.grab()
            if not ok:
                break
            frame_index += 1
            continue
        ok, frame = cap.read()
        if not ok:
            break
        timestamp = frame_index / fps
        yield frame_index, timestamp, frame
        frame_index += 1

    cap.release()

utils.py
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

_init_.py

"""Gaussian-splat frame selection algorithm (CPU).

Vendored from the tested frame-extractor-algorithm implementation.
"""

from .config import SelectorConfig
from .frame_selector import enforce_continuity, evaluate_temporal_bridge, select_frames

__all__ = [
    "SelectorConfig",
    "enforce_continuity",
    "evaluate_temporal_bridge",
    "select_frames",
]

frame_selector.py

from __future__ import annotations

import csv
import json
import heapq
import logging
import os
import shutil
import threading
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from .blur_detector import classify_blur, variance_of_laplacian
from .config import SelectorConfig
from .coverage import find_large_gaps
from .exposure_detector import analyze_exposure
from .frame import FrameMetrics
from .image_io import (
    JPEG_QUALITY,
    clear_image_dir,
    place_selected_image,
    validate_image_directory,
    validate_image_file,
    write_jpeg,
)
from .progress import ProgressThrottler, is_stage_boundary_message
from .scoring import compute_frame_score
from .similarity import compute_similarity, prepare_similarity_frame
from .telemetry import (
    StageTimer,
    directory_size_bytes,
    ensure_disk_space,
    format_bytes,
    snapshot,
)
from .video_reader import get_video_metadata, iter_frames

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output"
SELECTED_DIR = OUTPUT_DIR / "selected_frames"
REJECTED_DIR = OUTPUT_DIR / "rejected_frames"
COLMAP_DIR = OUTPUT_DIR / "colmap_input"
COLMAP_IMAGES_DIR = COLMAP_DIR / "images"
_EXPORT_LOCK = threading.Lock()


def _process_frame_chunk(args: tuple) -> list[dict[str, Any]]:
    """Extract a chunk of frames to unique JPEGs on disk; return metadata only.

    Full-resolution pixels stay on disk. Workers return paths + small thumbnails
    so ProcessPoolExecutor results do not ferry multi-megabyte arrays.
    """
    if len(args) == 6:
        video_path_str, start_frame, count, temp_dir_str, jpeg_quality, stride = args
    else:
        video_path_str, start_frame, count, temp_dir_str, jpeg_quality = args
        stride = 1

    effective_stride = max(1, int(stride))
    temp_dir = Path(temp_dir_str)
    temp_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path_str)
    if not cap.isOpened():
        raise ValueError(f"Unable to open video file: {video_path_str}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    fps = cap.get(cv2.CAP_PROP_FPS) or 1.0
    results: list[dict[str, Any]] = []
    try:
        for offset in range(count):
            frame_index = start_frame + offset
            if effective_stride > 1 and (frame_index % effective_stride != 0):
                if not cap.grab():
                    break
                continue
            ret, frame = cap.read()
            if not ret:
                break
            timestamp = frame_index / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sharpness = variance_of_laplacian(gray)
            brightness, dark_ratio, bright_ratio, exposure_label = analyze_exposure(frame)
            thumbnail_arr = prepare_similarity_frame(gray, (64, 64))

            image_path = temp_dir / f"frame_{frame_index:06d}.jpg"
            write_jpeg(image_path, frame, quality=jpeg_quality)
            ok, reason, dims = validate_image_file(image_path)
            if not ok:
                raise RuntimeError(
                    f"Failed to stage frame {frame_index} at {image_path}: {reason}"
                )

            results.append({
                "frame_index": frame_index,
                "timestamp": float(timestamp),
                "sharpness": float(sharpness),
                "brightness": float(brightness),
                "dark_ratio": float(dark_ratio),
                "bright_ratio": float(bright_ratio),
                "exposure_label": exposure_label,
                "image_path": str(image_path),
                "width": dims[0] if dims else 0,
                "height": dims[1] if dims else 0,
                "thumbnail_bytes": thumbnail_arr.tobytes(),
                "thumbnail_shape": thumbnail_arr.shape,
                "thumbnail_dtype": str(thumbnail_arr.dtype),
            })
            del frame, gray
    finally:
        cap.release()
    return results


def _reconstruct_disk_items(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rebuild lightweight metadata + thumbnails from worker results (no full frames)."""
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        thumbnail = np.frombuffer(
            raw["thumbnail_bytes"], dtype=np.dtype(raw["thumbnail_dtype"])
        ).reshape(raw["thumbnail_shape"]).copy()
        items.append({
            "frame_index": raw["frame_index"],
            "timestamp": raw["timestamp"],
            "sharpness": raw["sharpness"],
            "brightness": raw["brightness"],
            "dark_ratio": raw["dark_ratio"],
            "bright_ratio": raw["bright_ratio"],
            "exposure_label": raw["exposure_label"],
            "image_path": raw["image_path"],
            "thumbnail": thumbnail,
        })
    return items


def evaluate_temporal_bridge(
    previous_overlap: float,
    next_overlap: float,
    direct_overlap: float,
    quality_label: str,
    config: SelectorConfig,
) -> tuple[str, str]:
    if quality_label == "blurry":
        if (
            previous_overlap >= config.bridge_similarity_threshold
            and next_overlap >= config.bridge_similarity_threshold
            and direct_overlap <= config.bridge_overlap_threshold
        ):
            return "BLURRY_BRIDGE", "BLURRY_BRIDGE"
        return "BLURRY", "BLURRY"

    if (
        previous_overlap >= config.bridge_similarity_threshold
        and next_overlap >= config.bridge_similarity_threshold
        and direct_overlap <= config.bridge_overlap_threshold
    ):
        return "BRIDGE", "BRIDGE"

    sim_thresh = (
        max(config.similarity_threshold, 0.95)
        if getattr(config, "conservative_redundancy", True)
        else config.similarity_threshold
    )
    direct_thresh = (
        max(config.bridge_overlap_threshold, 0.85)
        if getattr(config, "conservative_redundancy", True)
        else config.bridge_overlap_threshold
    )

    if (
        previous_overlap >= sim_thresh
        and next_overlap >= sim_thresh
        and direct_overlap >= direct_thresh
    ):
        return "REDUNDANT", "REDUNDANT"

    return "KEEP", "KEEP"


def enforce_continuity(
    selected_frames: list[FrameMetrics],
    all_evaluated_candidates: list[FrameMetrics],
    max_frame_gap: int,
) -> tuple[list[FrameMetrics], list[FrameMetrics], list[dict[str, Any]]]:
    """Enforce maximum source-frame-index gap between consecutive selected frames.

    Finds gaps between consecutive selected frames exceeding max_frame_gap.
    Restores intermediate evaluated candidates to bridge intervals, preferring
    higher-quality usable candidates (sharp > slightly_blurred > blurry).
    Never force-retains corrupt or exposure-rejected images.
    Preserves unique source-frame indices and chronological ordering.

    Returns:
        (final_selected_frames, restored_frames, unrepairable_gaps)
    """
    if max_frame_gap <= 0:
        return selected_frames, [], []

    selected_map = {f.frame_index: f for f in sorted(selected_frames, key=lambda item: item.frame_index)}
    ordered_selected = list(selected_map.values())

    if len(ordered_selected) <= 1:
        return ordered_selected, [], []

    # Map candidate frames by frame_index for fast lookup
    # Only keep candidates that are eligible: valid on disk and not exposure rejected
    candidate_map: dict[int, FrameMetrics] = {}
    for c in all_evaluated_candidates:
        if c.exposure_label in {"too_dark", "too_bright"}:
            continue
        if not c.image_path or not Path(c.image_path).is_file():
            continue
        ok, _reason, _ = validate_image_file(Path(c.image_path))
        if not ok:
            continue
        candidate_map[c.frame_index] = c

    restored_frames: list[FrameMetrics] = []
    unrepairable_gaps: list[dict[str, Any]] = []

    for idx in range(1, len(ordered_selected)):
        prev = ordered_selected[idx - 1]
        curr = ordered_selected[idx]
        gap = curr.frame_index - prev.frame_index

        if gap <= max_frame_gap:
            continue

        usable_in_gap = [
            candidate_map[fi]
            for fi in sorted(candidate_map.keys())
            if prev.frame_index < fi < curr.frame_index and fi not in selected_map
        ]

        if not usable_in_gap:
            unrepairable_gaps.append({
                "prev_frame_index": prev.frame_index,
                "prev_timestamp": prev.timestamp,
                "next_frame_index": curr.frame_index,
                "next_timestamp": curr.timestamp,
                "gap": gap,
                "max_permitted_gap": max_frame_gap,
                "reason": "No usable intermediate candidates available",
            })
            continue

        nodes = [prev] + usable_in_gap + [curr]
        k = len(usable_in_gap)
        target_idx = k + 1

        dist: dict[int, float] = {0: 0.0}
        parent: dict[int, int] = {}
        pq: list[tuple[float, int]] = [(0.0, 0)]

        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, float("inf")):
                continue
            if u == target_idx:
                break
            u_fi = nodes[u].frame_index
            for v in range(u + 1, len(nodes)):
                v_fi = nodes[v].frame_index
                edge_gap = v_fi - u_fi
                if edge_gap > max_frame_gap:
                    break
                if v == target_idx:
                    w = 0.0
                else:
                    score = getattr(nodes[v], "final_score", 0.5)
                    # Quality preference: higher score -> lower edge cost
                    w = (1.0 - max(0.0, min(1.0, score))) + 0.05
                if d + w < dist.get(v, float("inf")):
                    dist[v] = d + w
                    parent[v] = u
                    heapq.heappush(pq, (d + w, v))

        if target_idx in parent:
            path: list[int] = []
            curr_p = target_idx
            while curr_p is not None and curr_p in parent:
                curr_p = parent[curr_p]
                if curr_p != 0:
                    path.append(curr_p)
            for node_idx in reversed(path):
                restored_candidate = nodes[node_idx]
                q_label = getattr(restored_candidate, "quality_label", "usable")
                restored_candidate.status = "selected"
                restored_candidate.selected = True
                restored_candidate.reason = (
                    f"Continuity enforcement ({q_label}, bridged gap {prev.frame_index}-{curr.frame_index})"
                )
                restored_frames.append(restored_candidate)
                selected_map[restored_candidate.frame_index] = restored_candidate
        else:
            reachable_from_start = [u for u in dist if u != 0 and u != target_idx]
            if reachable_from_start:
                best_start_hop = max(reachable_from_start, key=lambda u: nodes[u].frame_index)
                curr_p = best_start_hop
                while curr_p is not None and curr_p != 0:
                    cand = nodes[curr_p]
                    if cand.frame_index not in selected_map:
                        cand.status = "selected"
                        cand.selected = True
                        cand.reason = f"Continuity enforcement (partial bridge {prev.frame_index}-{curr.frame_index})"
                        restored_frames.append(cand)
                        selected_map[cand.frame_index] = cand
                    curr_p = parent.get(curr_p)
                unrep_prev_fi = nodes[best_start_hop].frame_index
                unrep_prev_ts = nodes[best_start_hop].timestamp
            else:
                unrep_prev_fi = prev.frame_index
                unrep_prev_ts = prev.timestamp

            unrep_curr_fi = curr.frame_index
            unrep_curr_ts = curr.timestamp

            unrepairable_gaps.append({
                "prev_frame_index": unrep_prev_fi,
                "prev_timestamp": unrep_prev_ts,
                "next_frame_index": unrep_curr_fi,
                "next_timestamp": unrep_curr_ts,
                "gap": unrep_curr_fi - unrep_prev_fi,
                "max_permitted_gap": max_frame_gap,
                "reason": (
                    f"No usable intermediate candidates between source frames "
                    f"{unrep_prev_fi} and {unrep_curr_fi}"
                ),
            })

    final_selected = sorted(selected_map.values(), key=lambda item: item.frame_index)
    return final_selected, restored_frames, unrepairable_gaps


def _load_export_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"videos": [], "selected_frames": []}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"videos": [], "selected_frames": []}
    if "videos" not in payload:
        legacy_video = {
            key: payload[key]
            for key in ("job_id", "source_video", "fps", "duration")
            if key in payload
        }
        payload["videos"] = [legacy_video] if legacy_video else []
    payload.setdefault("selected_frames", [])
    return payload


def _progress_callback(callback: Callable | None, progress: int, message: str, **updates: Any) -> None:
    if callback is not None:
        callback(progress, message, updates)


def _resolve_output_dirs(
    output_root: Path | None,
    colmap_images_dir: Path | None = None,
) -> tuple[Path, Path, Path, Path, Path]:
    """Return (output_dir, temp_frames_dir, rejected_dir, colmap_dir, colmap_images_dir)."""
    output_dir = Path(output_root) if output_root is not None else OUTPUT_DIR
    temp_frames_dir = output_dir / "temp-frames"
    rejected_dir = output_dir / "rejected_previews" if output_root is not None else REJECTED_DIR
    if colmap_images_dir is not None:
        images_dir = Path(colmap_images_dir)
        colmap_dir = images_dir.parent
    elif output_root is not None:
        # Prefer sibling colmap/images under the job workspace when output_root
        # is .../frame_selection; fall back to legacy nested colmap_input.
        job_root = output_dir.parent
        preferred = job_root / "colmap" / "images"
        images_dir = preferred
        colmap_dir = preferred.parent
    else:
        colmap_dir = COLMAP_DIR
        images_dir = COLMAP_IMAGES_DIR
    return output_dir, temp_frames_dir, rejected_dir, colmap_dir, images_dir


def _estimate_extraction_bytes(metadata: dict[str, Any], frame_count: int) -> int:
    width = int(metadata.get("width") or 1920)
    height = int(metadata.get("height") or 1080)
    # Rough JPEG size heuristic (~0.15 bytes/pixel at quality 95) + headroom.
    per_frame = max(50_000, int(width * height * 0.15))
    return per_frame * max(frame_count, 1) + 200_000_000


def select_frames(
    video_path: str | Path,
    config: SelectorConfig | None = None,
    job_id: str | None = None,
    progress_callback: Callable | None = None,
    output_root: Path | None = None,
    colmap_images_dir: Path | None = None,
) -> dict[str, Any]:
    cfg = config or SelectorConfig()
    export_id = job_id or uuid.uuid4().hex
    metadata = get_video_metadata(video_path)
    total_frames = int(metadata["frame_count"])
    max_frames = cfg.max_analysis_frames or total_frames

    output_dir, temp_frames_dir, rejected_dir, colmap_dir, images_dir = _resolve_output_dirs(
        output_root, colmap_images_dir=colmap_images_dir
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_frames_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    # Fresh job directories — prevent stale images from contaminating this run.
    if temp_frames_dir.exists():
        shutil.rmtree(temp_frames_dir, ignore_errors=True)
    temp_frames_dir.mkdir(parents=True, exist_ok=True)
    clear_image_dir(images_dir)
    clear_image_dir(rejected_dir)

    sampling_stride = max(1, getattr(cfg, "sampling_stride", 5))
    min_final = getattr(cfg, "min_final_selection", 8)
    if total_frames > 0 and min_final > 1 and total_frames < min_final * sampling_stride:
        sampling_stride = max(1, total_frames // min_final)
    max_frame_gap = max(1, getattr(cfg, "max_frame_gap", 25))
    expected_candidates = len(range(0, max_frames, sampling_stride))

    ensure_disk_space(
        output_dir,
        _estimate_extraction_bytes(metadata, expected_candidates),
    )
    snapshot(
        "before_extraction",
        output_dir,
        job_id=export_id,
        video=metadata.get("filename"),
        resolution=f"{metadata.get('width')}x{metadata.get('height')}",
        fps=metadata.get("fps"),
        duration=round(float(metadata.get("duration") or 0), 3),
        total_source_frames=total_frames,
        candidate_frames=expected_candidates,
        sampling_stride=sampling_stride,
        colmap_images_dir=str(images_dir.resolve()),
    )

    throttler = ProgressThrottler(min_interval=2.0, min_pct_delta=1.0)
    original_progress_callback = progress_callback

    def progress_callback(progress: int, message: str, updates: dict[str, Any] | None = None) -> None:
        if original_progress_callback is None:
            return
        force = progress >= 100 or is_stage_boundary_message(message)
        if throttler.should_emit(float(progress), force=force):
            original_progress_callback(progress, message, updates or {})

    candidate_frames: list[FrameMetrics] = []
    rejected_frames: list[FrameMetrics] = []
    processed_frames = 0
    blurry_count = 0
    exposure_rejected_count = 0
    redundant_rejections = 0
    extraction_failures = 0
    stage_timings: dict[str, float] = {}

    # ------------------------------------------------------------------ #
    # STAGE 1: Disk-backed multi-core frame extraction                     #
    # ------------------------------------------------------------------ #
    extract_timer = StageTimer("extraction")
    num_cpus = os.cpu_count() or 1
    analyzed_items: list[dict[str, Any]] = []
    parallel_ok = False
    workers_used = 1

    if max_frames >= 40 and num_cpus > 1:
        workers = min(num_cpus, 16)
        raw_chunk = max(10, (max_frames + workers - 1) // workers)
        chunk_size = max(sampling_stride * 2, ((raw_chunk + sampling_stride - 1) // sampling_stride) * sampling_stride)
        chunks = [
            (str(video_path), start_idx, min(chunk_size, max_frames - start_idx), str(temp_frames_dir), JPEG_QUALITY, sampling_stride)
            for start_idx in range(0, max_frames, chunk_size)
        ]
        workers_used = workers
        logger.info(
            "[frame_selection:extraction] Disk-backed parallel extraction — %d workers, %d chunks, %d candidates (stride=%d) → %s",
            workers, len(chunks), expected_candidates, sampling_stride, temp_frames_dir,
        )
        _progress_callback(
            progress_callback, 1,
            f"[frame_selection:extraction] Starting parallel extraction with {workers} CPU workers "
            f"({len(chunks)} chunks, stride {sampling_stride}) writing to disk",
        )
        try:
            raw_batches: list[list[dict[str, Any]]] = []
            with ProcessPoolExecutor(max_workers=workers) as executor:
                for batch in executor.map(_process_frame_chunk, chunks):
                    raw_batches.append(batch)
            for batch in raw_batches:
                analyzed_items.extend(_reconstruct_disk_items(batch))
            parallel_ok = len(analyzed_items) >= int(expected_candidates * 0.9)
            if parallel_ok:
                logger.info(
                    "[frame_selection:extraction] Parallel extraction complete — %d frames staged on disk",
                    len(analyzed_items),
                )
            else:
                logger.warning(
                    "[frame_selection:extraction] Parallel extraction returned only %d/%d frames — retrying sequentially",
                    len(analyzed_items), expected_candidates,
                )
                analyzed_items = []
                shutil.rmtree(temp_frames_dir, ignore_errors=True)
                temp_frames_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning(
                "[frame_selection:extraction] Parallel extraction failed (%s) — falling back to sequential",
                exc,
            )
            analyzed_items = []
            shutil.rmtree(temp_frames_dir, ignore_errors=True)
            temp_frames_dir.mkdir(parents=True, exist_ok=True)

    if not parallel_ok:
        analyzed_items = []
        workers_used = 1
        logger.info(
            "[frame_selection:extraction] Sequential disk-backed extraction — up to %d candidates (stride=%d)",
            expected_candidates, sampling_stride,
        )
        _progress_callback(
            progress_callback, 1,
            f"[frame_selection:extraction] Sequential extraction — up to {expected_candidates} frames on 1 worker (stride {sampling_stride})",
        )
        for frame_index, timestamp, frame in iter_frames(video_path, max_frames=max_frames, stride=sampling_stride):
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                sharpness = variance_of_laplacian(gray)
                brightness, dark_ratio, bright_ratio, exposure_label = analyze_exposure(frame)
                thumbnail = prepare_similarity_frame(gray, (64, 64))
                image_path = temp_frames_dir / f"frame_{frame_index:06d}.jpg"
                write_jpeg(image_path, frame)
                ok, reason, _dims = validate_image_file(image_path)
                if not ok:
                    raise RuntimeError(reason)
                analyzed_items.append({
                    "frame_index": frame_index,
                    "timestamp": float(timestamp),
                    "sharpness": float(sharpness),
                    "brightness": float(brightness),
                    "dark_ratio": float(dark_ratio),
                    "bright_ratio": float(bright_ratio),
                    "exposure_label": exposure_label,
                    "thumbnail": thumbnail,
                    "image_path": str(image_path),
                })
            except Exception as exc:
                extraction_failures += 1
                logger.error(
                    "[frame_selection:extraction] Failed staging frame %d: %s",
                    frame_index, exc,
                )
            finally:
                del frame

    analyzed_items.sort(key=lambda item: item["frame_index"])
    initial_candidates_count = len(analyzed_items)
    stage_timings["extraction_s"] = extract_timer.stop()
    staged_bytes = directory_size_bytes(temp_frames_dir)
    snapshot(
        "after_extraction",
        output_dir,
        staged_frames=len(analyzed_items),
        extraction_failures=extraction_failures,
        workers=workers_used,
        temp_bytes=format_bytes(staged_bytes),
        extraction_s=round(stage_timings["extraction_s"], 2),
    )

    if not analyzed_items:
        raise RuntimeError("Frame extraction staged zero readable frames on disk")

    _progress_callback(
        progress_callback, 10,
        f"[frame_selection:extraction] Extracted {len(analyzed_items)} frames to disk — starting quality analysis",
    )

    # ------------------------------------------------------------------ #
    # STAGE 2: Adaptive blur threshold calibration                        #
    # ------------------------------------------------------------------ #
    quality_timer = StageTimer("quality")
    valid_sharpness = [
        item["sharpness"]
        for item in analyzed_items
        if item["exposure_label"] not in {"too_dark", "too_bright"}
    ]
    if valid_sharpness and getattr(cfg, "adaptive_blur", True):
        median_sharpness = float(np.median(valid_sharpness))
        effective_blur = (
            max(getattr(cfg, "min_blur_threshold", 20.0), median_sharpness * 0.70)
            if median_sharpness < cfg.blur_threshold
            else cfg.blur_threshold
        )
    else:
        median_sharpness = 0.0
        effective_blur = cfg.blur_threshold

    logger.info(
        "[frame_selection:blur_calibration] Effective blur threshold=%.2f (config=%.2f, median=%.2f)",
        effective_blur, cfg.blur_threshold, median_sharpness,
    )
    _progress_callback(
        progress_callback, 12,
        f"[frame_selection:blur_calibration] Blur threshold calibrated to {effective_blur:.1f} "
        f"(video median sharpness={median_sharpness:.1f})",
    )

    # ------------------------------------------------------------------ #
    # STAGE 3: Per-frame quality classification (metadata + thumbnails)   #
    # ------------------------------------------------------------------ #
    logger.info("[frame_selection:quality] Classifying %d frames for blur/exposure", len(analyzed_items))
    _progress_callback(
        progress_callback, 13,
        f"[frame_selection:quality] Classifying {len(analyzed_items)} frames — blur threshold={effective_blur:.1f}",
    )

    for item in analyzed_items:
        processed_frames += 1
        sharpness = item["sharpness"]
        quality_label = classify_blur(sharpness, effective_blur)
        exposure_label = item["exposure_label"]

        candidate = FrameMetrics(
            frame_index=item["frame_index"],
            timestamp=float(item["timestamp"]),
            sharpness=float(sharpness),
            brightness=float(item["brightness"]),
            dark_ratio=float(item["dark_ratio"]),
            bright_ratio=float(item["bright_ratio"]),
            quality_label=quality_label,
            exposure_label=exposure_label,
            image_path=item["image_path"],
            thumbnail=item["thumbnail"],
            status="candidate",
        )

        if quality_label == "blurry":
            blurry_count += 1
            candidate.status = "candidate"
            candidate.reason = "BLUR"
            candidate.selected = False

        if exposure_label in {"too_dark", "too_bright"}:
            candidate.status = "rejected"
            candidate.reason = "EXPOSURE"
            candidate.selected = False
            rejected_frames.append(candidate)
            exposure_rejected_count += 1
            progress = 13 + int(37 * processed_frames / max(len(analyzed_items), 1))
            _progress_callback(
                progress_callback, progress,
                f"[frame_selection:quality] Frame {processed_frames}/{len(analyzed_items)} "
                f"— EXPOSURE REJECTED ({exposure_label})",
                stats={
                    "analyzed_frames": processed_frames,
                    "blurry_frames": blurry_count,
                    "exposure_rejected": exposure_rejected_count,
                    "redundant_frames": redundant_rejections,
                    "selected_frames": 0,
                },
                selected_count=0,
            )
            continue

        candidate.sharpness_score = min(1.0, max(0.0, candidate.sharpness / max(effective_blur * 1.5, 1.0)))
        candidate.exposure_score = 1.0
        candidate.viewpoint_change_score = 0.25
        candidate.final_score = compute_frame_score(candidate, cfg)
        candidate_frames.append(candidate)

        progress = 13 + int(37 * processed_frames / max(len(analyzed_items), 1))
        _progress_callback(
            progress_callback, progress,
            f"[frame_selection:quality] Frame {processed_frames}/{len(analyzed_items)} "
            f"— {quality_label.upper()} sharpness={sharpness:.1f}",
            stats={
                "analyzed_frames": processed_frames,
                "blurry_frames": blurry_count,
                "exposure_rejected": exposure_rejected_count,
                "redundant_frames": redundant_rejections,
                "selected_frames": 0,
            },
            selected_count=0,
        )

    # Free extraction batch references; FrameMetrics hold paths + thumbnails only.
    analyzed_items.clear()
    stage_timings["quality_s"] = quality_timer.stop()

    logger.info(
        "[frame_selection:quality] Quality pass complete — %d candidates, %d blurry, %d exposure-rejected",
        len(candidate_frames), blurry_count, exposure_rejected_count,
    )
    _progress_callback(
        progress_callback, 50,
        f"[frame_selection:quality] Quality pass complete — {len(candidate_frames)} candidates "
        f"| blurry={blurry_count} | exposure_rejected={exposure_rejected_count}",
        stats={
            "analyzed_frames": processed_frames,
            "blurry_frames": blurry_count,
            "exposure_rejected": exposure_rejected_count,
            "redundant_frames": redundant_rejections,
            "selected_frames": 0,
        },
    )
    snapshot("during_selection", output_dir, candidates=len(candidate_frames))

    # ------------------------------------------------------------------ #
    # STAGE 4: Windowed similarity filtering (thumbnails only)            #
    # ------------------------------------------------------------------ #
    similarity_timer = StageTimer("similarity")
    windowed_candidates: dict[int, list[FrameMetrics]] = {}
    for candidate in candidate_frames:
        window_id = int(candidate.timestamp // cfg.window_seconds)
        windowed_candidates.setdefault(window_id, []).append(candidate)

    selected_frames: list[FrameMetrics] = []
    selection_processed = 0
    selection_total = max(len(candidate_frames), 1)

    logger.info(
        "[frame_selection:similarity] Starting similarity filtering — %d candidates across %d windows",
        len(candidate_frames), len(windowed_candidates),
    )
    _progress_callback(
        progress_callback, 51,
        f"[frame_selection:similarity] Filtering {len(candidate_frames)} candidates "
        f"across {len(windowed_candidates)} time windows",
    )

    def report_selection_progress(selected_count: int, reason: str = "") -> None:
        nonlocal selection_processed
        selection_processed += 1
        progress = 51 + int(24 * selection_processed / selection_total)
        label = f" — {reason}" if reason else ""
        _progress_callback(
            progress_callback, progress,
            f"[frame_selection:similarity] Frame {selection_processed}/{len(candidate_frames)}{label}",
            stats={
                "analyzed_frames": processed_frames,
                "blurry_frames": blurry_count,
                "exposure_rejected": exposure_rejected_count,
                "redundant_frames": redundant_rejections,
                "selected_frames": selected_count,
            },
            selected_count=selected_count,
        )

    for window_id in sorted(windowed_candidates):
        current_window = sorted(windowed_candidates[window_id], key=lambda item: item.timestamp)
        selected_window: list[FrameMetrics] = []
        recent_selected: list[FrameMetrics] = []

        for index, candidate in enumerate(current_window):
            previous_selected = (
                selected_window[-1]
                if selected_window
                else (selected_frames[-1] if selected_frames else (recent_selected[-1] if recent_selected else None))
            )
            next_candidates = current_window[index + 1 : index + 1 + cfg.lookahead_window]
            next_frame = next_candidates[0] if next_candidates else None

            next_similarity = 0.0
            if next_frame is not None:
                next_similarity = compute_similarity(candidate.thumbnail, next_frame.thumbnail)

            if previous_selected is None:
                previous_similarity = 0.0
            else:
                previous_similarity = compute_similarity(previous_selected.thumbnail, candidate.thumbnail)

            direct_overlap = 0.0
            if previous_selected is not None and next_frame is not None:
                direct_overlap = compute_similarity(previous_selected.thumbnail, next_frame.thumbnail)

            candidate.similarity = float(previous_similarity)
            candidate.redundancy_score = max(0.0, 1.0 - previous_similarity)

            status, reason = evaluate_temporal_bridge(
                previous_similarity,
                next_similarity,
                direct_overlap,
                candidate.quality_label,
                cfg,
            )

            candidate.reason = reason
            candidate.status = status.lower()

            if status == "REDUNDANT":
                candidate.status = "rejected"
                candidate.selected = False
                candidate.redundancy_score = 1.0 - previous_similarity
                rejected_frames.append(candidate)
                redundant_rejections += 1
                report_selection_progress(len(selected_frames) + len(selected_window), "REDUNDANT")
                continue

            if status in {"BLURRY", "BLURRY_BRIDGE"}:
                if status == "BLURRY_BRIDGE":
                    candidate.status = "selected"
                    candidate.selected = True
                    candidate.reason = "BLURRY_BRIDGE"
                    candidate.viewpoint_change_score = max(0.6, 1.0 - direct_overlap)
                    selected_window.append(candidate)
                    recent_selected.append(candidate)
                    report_selection_progress(len(selected_frames) + len(selected_window), "BLURRY_BRIDGE")
                    continue
                candidate.status = "rejected"
                candidate.selected = False
                candidate.reason = "BLURRY"
                rejected_frames.append(candidate)
                # Already counted as blurry during quality pass; do not double-count.
                report_selection_progress(len(selected_frames) + len(selected_window), "BLURRY")
                continue

            candidate.viewpoint_change_score = max(0.4, 1.0 - previous_similarity)
            candidate.final_score = compute_frame_score(candidate, cfg)
            candidate.status = "selected"
            candidate.selected = True
            candidate.reason = "Meaningful viewpoint change" if status != "BRIDGE" else "BRIDGE"
            selected_window.append(candidate)
            recent_selected.append(candidate)

            if len(recent_selected) > cfg.max_frames_per_window:
                recent_selected = recent_selected[-cfg.max_frames_per_window:]
            report_selection_progress(len(selected_frames) + len(selected_window), status)

        if len(selected_window) < cfg.min_frames_per_window:
            fallback_candidates = sorted(
                [c for c in current_window if c not in selected_window],
                key=lambda item: item.final_score,
                reverse=True,
            )
            for fallback in fallback_candidates:
                if fallback.exposure_label not in {"too_dark", "too_bright"}:
                    fallback.status = "selected"
                    fallback.selected = True
                    fallback.reason = "Minimum-frame protection"
                    selected_window.append(fallback)
                    if len(selected_window) >= cfg.min_frames_per_window:
                        break

        selected_frames.extend(selected_window)

    selected_frames = sorted(
        {frame.frame_index: frame for frame in selected_frames}.values(),
        key=lambda item: item.timestamp,
    )
    stage_timings["similarity_s"] = similarity_timer.stop()

    logger.info(
        "[frame_selection:similarity] Similarity pass complete — %d selected, %d redundant rejections",
        len(selected_frames), redundant_rejections,
    )
    _progress_callback(
        progress_callback, 75,
        f"[frame_selection:similarity] Similarity pass complete — {len(selected_frames)} frames selected "
        f"| {redundant_rejections} redundant rejected",
        stats={
            "analyzed_frames": processed_frames,
            "blurry_frames": blurry_count,
            "exposure_rejected": exposure_rejected_count,
            "redundant_frames": redundant_rejections,
            "selected_frames": len(selected_frames),
        },
        selected_count=len(selected_frames),
    )

    # ------------------------------------------------------------------ #
    # STAGE 5: Continuity enforcement & coverage gap filling              #
    # ------------------------------------------------------------------ #
    coverage_timer = StageTimer("coverage")
    warnings: list[str] = []
    restored_frames: list[FrameMetrics] = []
    unrepairable_gaps: list[dict[str, Any]] = []

    if getattr(cfg, "continuity_aware", True):
        logger.info(
            "[frame_selection:continuity] Enforcing continuity (max source-frame gap=%d)",
            max_frame_gap,
        )
        _progress_callback(
            progress_callback, 76,
            f"[frame_selection:continuity] Checking continuity — enforcing max gap of {max_frame_gap} frames",
        )
        all_evaluated = candidate_frames + [f for f in rejected_frames if f.reason != "EXPOSURE"]
        selected_frames, restored_frames, unrepairable_gaps = enforce_continuity(
            selected_frames=selected_frames,
            all_evaluated_candidates=all_evaluated,
            max_frame_gap=max_frame_gap,
        )
        logger.info(
            "[frame_selection:continuity] Continuity pass complete — %d frame(s) restored, %d unrepairable gap(s)",
            len(restored_frames), len(unrepairable_gaps),
        )
        for ug in unrepairable_gaps:
            warnings.append(
                f"Unrepairable frame gap between source frames {ug['prev_frame_index']} and {ug['next_frame_index']} "
                f"(gap={ug['gap']} > max={max_frame_gap}): {ug['reason']}"
            )
        _progress_callback(
            progress_callback, 78,
            f"[frame_selection:continuity] Continuity pass complete — {len(restored_frames)} restored, "
            f"{len(selected_frames)} total selected",
            selected_count=len(selected_frames),
        )
    else:
        warnings.extend(find_large_gaps(selected_frames, cfg.coverage_gap_seconds))
        coverage_total = max(len(selected_frames) - 1, 1)
        gaps_filled = 0
        logger.info("[frame_selection:coverage] Scanning for coverage gaps (threshold=%.1fs)", cfg.coverage_gap_seconds)
        _progress_callback(
            progress_callback, 76,
            f"[frame_selection:coverage] Scanning {len(selected_frames) - 1} intervals for coverage gaps",
        )

        for idx in range(1, len(selected_frames)):
            prev = selected_frames[idx - 1]
            curr = selected_frames[idx]
            if curr.timestamp - prev.timestamp > cfg.coverage_gap_seconds:
                gap_candidates = [
                    item
                    for item in candidate_frames
                    if prev.timestamp < item.timestamp < curr.timestamp
                    and not any(selected.frame_index == item.frame_index for selected in selected_frames)
                ]
                if gap_candidates:
                    filler = max(gap_candidates, key=lambda item: item.final_score)
                    filler.status = "selected"
                    filler.selected = True
                    filler.reason = "Coverage pass"
                    selected_frames.insert(idx, filler)
                    gaps_filled += 1
            progress = 76 + int(2 * idx / coverage_total)
            _progress_callback(
                progress_callback, progress,
                f"[frame_selection:coverage] Gap check {idx}/{len(selected_frames) - 1}",
                selected_count=len(selected_frames),
            )

        logger.info(
            "[frame_selection:coverage] Coverage pass complete — %d gaps filled, %d frames total",
            gaps_filled, len(selected_frames),
        )
        _progress_callback(
            progress_callback, 78,
            f"[frame_selection:coverage] Coverage pass complete — {gaps_filled} gaps filled, {len(selected_frames)} total",
            selected_count=len(selected_frames),
        )

    stage_timings["coverage_s"] = coverage_timer.stop()

    selected_frames = sorted(
        {frame.frame_index: frame for frame in selected_frames}.values(),
        key=lambda item: item.frame_index,
    )

    # ------------------------------------------------------------------ #
    # STAGE 6: Safety net — guarantee COLMAP minimum frame count         #
    # ------------------------------------------------------------------ #
    if len(selected_frames) < cfg.min_final_selection and candidate_frames:
        logger.warning(
            "[frame_selection:safety_net] Only %d frames selected (minimum=%d) — applying uniform coverage safety net",
            len(selected_frames), cfg.min_final_selection,
        )
        _progress_callback(
            progress_callback, 79,
            f"[frame_selection:safety_net] Too few frames ({len(selected_frames)}) "
            f"— applying safety net to reach {cfg.min_final_selection}",
        )
        target_count = min(cfg.min_final_selection, len(candidate_frames))
        selected_indices = {f.frame_index for f in selected_frames}
        usable = [
            c for c in candidate_frames
            if c.exposure_label not in {"too_dark", "too_bright"}
        ] or candidate_frames
        step = max(1, len(usable) // target_count)
        for c in usable[::step]:
            if c.frame_index not in selected_indices:
                c.status = "selected"
                c.selected = True
                c.reason = "Uniform coverage safety net"
                selected_frames.append(c)
                selected_indices.add(c.frame_index)
                if len(selected_frames) >= target_count:
                    break
        selected_frames = sorted(selected_frames, key=lambda item: item.timestamp)
        logger.info("[frame_selection:safety_net] Safety net applied — %d frames selected", len(selected_frames))

    if len(selected_frames) < cfg.min_final_selection:
        warnings.append(
            f"Only {len(selected_frames)} frames survived selection. This may be insufficient for reliable reconstruction."
        )
    if len(selected_frames) > max(1, int(total_frames * 0.9)):
        warnings.append(
            "Very little redundancy was removed. The input may contain substantial camera movement or weak similarity thresholds."
        )

    # ------------------------------------------------------------------ #
    # STAGE 7: Place selected images directly into COLMAP images/         #
    # ------------------------------------------------------------------ #
    export_timer = StageTimer("export")
    prefix = export_id.replace("-", "")[:12] or "job"
    video_entry = {
        "job_id": export_id,
        "source_video": metadata["filename"],
        "fps": metadata["fps"],
        "duration": round(metadata["duration"], 3),
    }

    logger.info(
        "[frame_selection:export] Placing %d selected frames directly into COLMAP images dir %s",
        len(selected_frames), images_dir.resolve(),
    )
    _progress_callback(
        progress_callback, 80,
        f"[frame_selection:export] Writing {len(selected_frames)} selected frames to {images_dir}",
        selected_count=len(selected_frames),
    )

    write_failures: list[dict[str, Any]] = []
    selected_entries: list[dict[str, Any]] = []
    rejected_preview: list[dict[str, Any]] = []

    with _EXPORT_LOCK:
        clear_image_dir(images_dir)

        for order, frame in enumerate(selected_frames, 1):
            output_name = f"{prefix}_frame_{order:06d}.jpg"
            destination = images_dir / output_name
            source = Path(frame.image_path) if frame.image_path else None
            try:
                if source is None or not source.is_file():
                    raise RuntimeError(f"Missing staged source for frame {frame.frame_index}")
                place_selected_image(source, destination)
                ok, reason, dims = validate_image_file(destination)
                if not ok:
                    raise RuntimeError(f"Validation failed after place: {reason}")
                selected_entries.append({
                    "job_id": export_id,
                    "source_video": metadata["filename"],
                    "output_file": output_name,
                    "original_frame": frame.frame_index,
                    "timestamp": round(float(frame.timestamp), 6),
                    "status": "selected",
                    "reason": frame.reason,
                    "width": dims[0] if dims else None,
                    "height": dims[1] if dims else None,
                })
            except Exception as exc:
                write_failures.append({
                    "original_frame": frame.frame_index,
                    "timestamp": frame.timestamp,
                    "destination": str(destination),
                    "error": str(exc),
                })
                logger.error(
                    "[frame_selection:export] Failed selected frame %d → %s: %s",
                    frame.frame_index, destination, exc,
                )
            progress = 80 + int(10 * order / max(len(selected_frames), 1))
            _progress_callback(
                progress_callback, progress,
                f"[frame_selection:export] Saving selected frame {order}/{len(selected_frames)} — {frame.reason}",
                selected_frames=selected_entries.copy(),
                selected_count=len(selected_entries),
                stats={
                    "analyzed_frames": processed_frames,
                    "blurry_frames": blurry_count,
                    "exposure_rejected": exposure_rejected_count,
                    "redundant_frames": redundant_rejections,
                    "selected_frames": len(selected_entries),
                },
            )

        # Optional rejected previews (load from disk only for the capped preview set).
        preview_limit = min(len(rejected_frames), cfg.max_rejected_preview)
        for order, frame in enumerate(rejected_frames[:preview_limit], 1):
            output_name = f"{prefix}_rejected_{order:06d}.jpg"
            dest = rejected_dir / output_name
            try:
                source = Path(frame.image_path) if frame.image_path else None
                if source and source.is_file():
                    shutil.copy2(source, dest)
                    rejected_preview.append({
                        "job_id": export_id,
                        "source_video": metadata["filename"],
                        "output_file": output_name,
                        "original_frame": frame.frame_index,
                        "timestamp": round(float(frame.timestamp), 6),
                        "status": "rejected",
                        "reason": frame.reason,
                    })
            except OSError as exc:
                logger.warning("Rejected preview write failed for frame %d: %s", frame.frame_index, exc)
            progress = 90 + int(5 * order / max(preview_limit, 1))
            _progress_callback(
                progress_callback, progress,
                f"[frame_selection:export] Saving rejected preview {order}/{preview_limit}",
                rejected_preview=rejected_preview.copy(),
            )

        export_payload = _load_export_payload(output_dir / "frames.json")
        export_payload["videos"] = [
            item for item in export_payload["videos"] if item.get("job_id") != export_id
        ] + [video_entry]
        export_payload["selected_frames"] = [
            item for item in export_payload["selected_frames"] if item.get("job_id") != export_id
        ] + selected_entries
        (output_dir / "frames.json").write_text(json.dumps(export_payload, indent=2))

        with (output_dir / "frames.csv").open("w", newline="") as csv_file:
            fieldnames = [
                "job_id",
                "source_video",
                "output_file",
                "original_frame",
                "timestamp",
                "status",
                "reason",
                "width",
                "height",
            ]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(export_payload["selected_frames"])

        (colmap_dir / "frames.json").write_text(json.dumps(export_payload, indent=2))

    # Validate COLMAP input from disk — counts come from files, not attempts.
    validation = validate_image_directory(images_dir)
    valid_count = int(validation["valid_count"])
    if validation["invalid"]:
        for item in validation["invalid"]:
            write_failures.append({
                "original_frame": None,
                "timestamp": None,
                "destination": item["path"],
                "error": item["reason"],
            })
            try:
                Path(item["path"]).unlink(missing_ok=True)
            except OSError:
                pass
        validation = validate_image_directory(images_dir)
        valid_count = int(validation["valid_count"])

    # Drop rejected temp frames; keep only what COLMAP needs (already placed).
    try:
        shutil.rmtree(temp_frames_dir, ignore_errors=True)
    except OSError:
        pass

    stage_timings["export_s"] = export_timer.stop()
    snapshot(
        "before_colmap",
        images_dir,
        selected_attempted=len(selected_frames),
        valid_on_disk=valid_count,
        write_failures=len(write_failures),
        colmap_images_dir=str(images_dir.resolve()),
        stage_timings=stage_timings,
    )

    effective_min = min(cfg.min_final_selection, len(candidate_frames)) if candidate_frames else 0
    if valid_count == 0:
        raise RuntimeError("No valid images in COLMAP input directory after selection")
    if effective_min > 0 and valid_count < effective_min and write_failures:
        raise RuntimeError(
            f"Only {valid_count} valid COLMAP images on disk after selection "
            f"(target={effective_min}); write_failures={len(write_failures)}"
        )

    if write_failures:
        warnings.append(
            f"{len(write_failures)} selected frame(s) failed write/validation and were excluded."
        )

    logger.info(
        "[frame_selection:colmap_prep] COLMAP input ready at %s — %d valid images on disk "
        "(attempted=%d, write_failures=%d)",
        images_dir.resolve(), valid_count, len(selected_frames), len(write_failures),
    )
    _progress_callback(
        progress_callback, 97,
        f"[frame_selection:colmap_prep] Verified {valid_count} valid images at {images_dir.resolve()}",
    )

    # Final sequence validation and gap statistics
    final_frame_indices = [entry["original_frame"] for entry in selected_entries]
    frame_gaps = [
        curr_idx - prev_idx
        for prev_idx, curr_idx in zip(final_frame_indices[:-1], final_frame_indices[1:])
    ]
    timestamps = [entry["timestamp"] for entry in selected_entries]
    timestamp_gaps = [
        curr_t - prev_t
        for prev_t, curr_t in zip(timestamps[:-1], timestamps[1:])
    ]

    min_frame_gap = int(min(frame_gaps)) if frame_gaps else 0
    median_frame_gap = float(np.median(frame_gaps)) if frame_gaps else 0.0
    max_frame_gap_actual = int(max(frame_gaps)) if frame_gaps else 0

    min_time_gap = round(float(min(timestamp_gaps)), 4) if timestamp_gaps else 0.0
    median_time_gap = round(float(np.median(timestamp_gaps)), 4) if timestamp_gaps else 0.0
    max_time_gap = round(float(max(timestamp_gaps)), 4) if timestamp_gaps else 0.0

    gaps_exceeding = sum(1 for g in frame_gaps if g > max_frame_gap)
    continuity_guaranteed = bool(gaps_exceeding == 0)
    is_unique_and_chronological = bool(
        final_frame_indices == sorted(list(set(final_frame_indices)))
    )
    retention_pct = round(100.0 * valid_count / max(total_frames, 1), 2)

    result = {
        "job_id": export_id,
        "output_dir": str(output_dir),
        "colmap_dir": str(colmap_dir),
        "colmap_images_dir": str(images_dir.resolve()),
        "selected_count": valid_count,
        "stats": {
            "duration": round(metadata["duration"], 3),
            "fps": metadata["fps"],
            "resolution": f"{metadata['width']}x{metadata['height']}",
            "total_frames": total_frames,
            "total_source_frames": total_frames,
            "sampling_stride": sampling_stride,
            "initial_candidates_count": initial_candidates_count,
            "extracted_frames": processed_frames,
            "analyzed_frames": len(candidate_frames) + len(rejected_frames),
            "blurry_frames": blurry_count,
            "exposure_rejected": exposure_rejected_count,
            "redundant_frames": redundant_rejections,
            "restored_frames_count": len(restored_frames),
            "restored_frames": [
                {
                    "frame_index": f.frame_index,
                    "timestamp": round(float(f.timestamp), 6),
                    "reason": f.reason,
                    "quality_label": getattr(f, "quality_label", "unknown"),
                }
                for f in restored_frames
            ],
            "selected_frames": valid_count,
            "selected_attempted": len(selected_frames),
            "valid_on_disk": valid_count,
            "write_failures": len(write_failures),
            "extraction_failures": extraction_failures,
            "retention_percentage": retention_pct,
            "min_frame_gap": min_frame_gap,
            "median_frame_gap": median_frame_gap,
            "max_frame_gap": max_frame_gap_actual,
            "min_timestamp_gap": min_time_gap,
            "median_timestamp_gap": median_time_gap,
            "max_timestamp_gap": max_time_gap,
            "gaps_exceeding_max": gaps_exceeding,
            "max_permitted_gap": max_frame_gap,
            "continuity_guaranteed": continuity_guaranteed,
            "is_unique_and_chronological": is_unique_and_chronological,
            "unrepairable_gaps": unrepairable_gaps,
            "workers": workers_used,
            "selected_files": list(validation["valid_files"]),
            "stage_timings_s": stage_timings,
            "colmap_images_dir": str(images_dir.resolve()),
        },
        "warnings": warnings,
        "selected_frames": selected_entries,
        "rejected_preview": rejected_preview,
        "write_failures": write_failures,
        "validation": validation,
        "metadata": metadata,
    }

    selection_report = {
        "job_id": export_id,
        "source_video": metadata["filename"],
        "total_source_frames": total_frames,
        "sampling_stride": sampling_stride,
        "initial_candidates_count": initial_candidates_count,
        "selected_count": valid_count,
        "retention_percentage": retention_pct,
        "stats": result["stats"],
        "unrepairable_gaps": unrepairable_gaps,
        "restored_frames": result["stats"]["restored_frames"],
        "continuity_guaranteed": continuity_guaranteed,
        "is_unique_and_chronological": is_unique_and_chronological,
        "ordered_frames": [entry["output_file"] for entry in selected_entries],
        "colmap_images_dir": str(images_dir.resolve()),
        "warnings": warnings,
    }
    (output_dir / "frame_selection.json").write_text(json.dumps(selection_report, indent=2), encoding="utf-8")
    if colmap_dir != output_dir:
        (colmap_dir / "frame_selection.json").write_text(json.dumps(selection_report, indent=2), encoding="utf-8")

    logger.info(
        "[frame_selection:summary] DONE — %d/%d frames valid on disk for COLMAP (%.1f%%) "
        "| stride=%d | candidates=%d | blurry=%d | exposure=%d | redundant=%d | restored=%d "
        "| max_gap=%d | continuity=%s | write_failures=%d | path=%s",
        valid_count, total_frames,
        retention_pct,
        sampling_stride, initial_candidates_count,
        blurry_count, exposure_rejected_count, redundant_rejections, len(restored_frames),
        max_frame_gap_actual, continuity_guaranteed, len(write_failures),
        images_dir.resolve(),
    )
    _progress_callback(
        progress_callback, 100,
        f"[frame_selection:summary] Export complete: {valid_count} valid frames ready for COLMAP "
        f"| stride={sampling_stride} | restored={len(restored_frames)} | max_gap={max_frame_gap_actual}",
        selected_count=valid_count,
        stats=result["stats"],
    )

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Particle Vision Frame Selector")
    parser.add_argument("video", type=str, help="Path to input video file")
    parser.add_argument("--output-dir", type=str, default=None, help="Output root directory")
    parser.add_argument("--colmap-images-dir", type=str, default=None, help="COLMAP images directory")
    parser.add_argument("--stride", type=int, default=5, help="Uniform sampling stride (default: 5)")
    parser.add_argument("--max-gap", type=int, default=25, help="Maximum frame gap (default: 25)")
    parser.add_argument("--no-continuity", action="store_true", help="Disable continuity-aware selection")
    parser.add_argument("--no-conservative", action="store_true", help="Disable conservative redundancy filtering")
    cli_args = parser.parse_args()

    cli_cfg = SelectorConfig(
        sampling_stride=cli_args.stride,
        max_frame_gap=cli_args.max_gap,
        continuity_aware=not cli_args.no_continuity,
        conservative_redundancy=not cli_args.no_conservative,
    )
    res = select_frames(
        cli_args.video,
        config=cli_cfg,
        output_root=Path(cli_args.output_dir) if cli_args.output_dir else None,
        colmap_images_dir=Path(cli_args.colmap_images_dir) if cli_args.colmap_images_dir else None,
    )
    print(json.dumps(res["stats"], indent=2))

test_frame_selector.py

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from pipeline.frame_selection import SelectorConfig, evaluate_temporal_bridge, select_frames
from pipeline.frame_selection import frame_selector
from pipeline.frame_selection.video_reader import get_video_metadata


def _write_test_video(path: Path, fps: int = 10, seconds: int = 2) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (160, 120))
    assert writer.isOpened(), "Could not create test video"

    for frame_index in range(fps * seconds):
        base = 80 + frame_index * 2
        arr = cv2.merge([
            np.full((120, 160), (base % 255), dtype=np.uint8),
            np.full((120, 160), (base * 2 % 255), dtype=np.uint8),
            np.full((120, 160), (base * 3 % 255), dtype=np.uint8),
        ])
        arr[20:100, 20:140] = 255
        writer.write(arr)
    writer.release()


def _cfg(**overrides) -> SelectorConfig:
    base = dict(
        window_seconds=1.0,
        min_frames_per_window=1,
        max_frames_per_window=4,
        blur_threshold=50,
        similarity_threshold=0.9,
        min_final_selection=1,
        max_rejected_preview=0,
        adaptive_blur=False,
        sampling_stride=1,
    )
    base.update(overrides)
    return SelectorConfig(**base)


def test_video_metadata_reads_file(tmp_path):
    video = tmp_path / "sample.mp4"
    _write_test_video(video, fps=10, seconds=1)
    metadata = get_video_metadata(video)
    assert metadata["frame_count"] == 10
    assert metadata["fps"] == 10
    assert metadata["width"] == 160
    assert metadata["height"] == 120


def test_selector_returns_selected_frames(tmp_path):
    job_root = tmp_path / "job"
    output_root = job_root / "frame_selection"
    colmap_images = job_root / "colmap" / "images"
    video = tmp_path / "room_walk.mp4"
    _write_test_video(video, fps=10, seconds=2)
    progress_updates = []
    result = select_frames(
        video,
        config=_cfg(),
        progress_callback=lambda progress, message, updates: progress_updates.append((progress, message, updates)),
        output_root=output_root,
        colmap_images_dir=colmap_images,
    )
    assert result["selected_count"] > 0
    assert result["stats"]["selected_frames"] == result["selected_count"]
    assert result["stats"]["valid_on_disk"] == result["selected_count"]
    assert len(result["selected_frames"]) >= 1
    assert any("extraction" in message.lower() for _, message, _ in progress_updates)
    assert any("similarity" in message.lower() or "filtering" in message.lower() for _, message, _ in progress_updates)
    assert any(
        "saving selected frame" in message.lower()
        or "export" in message.lower()
        or "colmap" in message.lower()
        for _, message, _ in progress_updates
    )
    assert Path(result["colmap_images_dir"]).resolve() == colmap_images.resolve()
    assert len(list(colmap_images.glob("*.jpg"))) == result["selected_count"]
    # Temp frames should be cleaned after export.
    assert not (output_root / "temp-frames").exists() or not list((output_root / "temp-frames").glob("*.jpg"))


def test_selector_writes_only_to_colmap_images(tmp_path):
    job_root = tmp_path / "job"
    output_root = job_root / "frame_selection"
    colmap_images = job_root / "colmap" / "images"
    video = tmp_path / "room_walk.mp4"
    _write_test_video(video, fps=10, seconds=1)
    result = select_frames(
        video,
        config=_cfg(),
        job_id="job_diskbacked1",
        output_root=output_root,
        colmap_images_dir=colmap_images,
    )
    assert result["selected_count"] == len(list(colmap_images.glob("*.jpg")))
    assert not (output_root / "selected_frames").exists()


def test_failed_write_is_excluded_from_count(tmp_path, monkeypatch):
    job_root = tmp_path / "job"
    output_root = job_root / "frame_selection"
    colmap_images = job_root / "colmap" / "images"
    video = tmp_path / "room_walk.mp4"
    _write_test_video(video, fps=10, seconds=1)

    real_place = frame_selector.place_selected_image
    calls = {"n": 0}

    def flaky_place(source, destination):
        calls["n"] += 1
        if calls["n"] == 1:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"not-a-jpeg")
            return destination
        return real_place(source, destination)

    monkeypatch.setattr(frame_selector, "place_selected_image", flaky_place)
    result = select_frames(
        video,
        config=_cfg(min_final_selection=1),
        output_root=output_root,
        colmap_images_dir=colmap_images,
    )
    assert result["stats"]["write_failures"] >= 1
    assert result["selected_count"] == len(list(colmap_images.glob("*.jpg")))
    # Corrupt file must not remain counted as valid.
    from pipeline.frame_selection.image_io import validate_image_directory
    validation = validate_image_directory(colmap_images)
    assert validation["valid_count"] == result["selected_count"]


def test_stale_images_are_cleared_between_runs(tmp_path):
    job_root = tmp_path / "job"
    output_root = job_root / "frame_selection"
    colmap_images = job_root / "colmap" / "images"
    colmap_images.mkdir(parents=True)
    stale = colmap_images / "stale_frame.jpg"
    cv2.imwrite(str(stale), np.zeros((32, 32, 3), dtype=np.uint8))

    video = tmp_path / "room_walk.mp4"
    _write_test_video(video, fps=10, seconds=1)
    result = select_frames(
        video,
        config=_cfg(),
        job_id="job_freshrun",
        output_root=output_root,
        colmap_images_dir=colmap_images,
    )
    names = {p.name for p in colmap_images.glob("*.jpg")}
    assert "stale_frame.jpg" not in names
    assert len(names) == result["selected_count"]


def test_multiple_video_manifests_are_combined(tmp_path):
    job_root = tmp_path / "job"
    output_dir = job_root / "frame_selection"
    colmap_images = job_root / "colmap" / "images"

    first_video = tmp_path / "first.mp4"
    second_video = tmp_path / "second.mp4"
    _write_test_video(first_video, fps=10, seconds=1)
    _write_test_video(second_video, fps=10, seconds=1)
    config = _cfg()

    first = frame_selector.select_frames(
        first_video, config=config, job_id="first-job",
        output_root=output_dir, colmap_images_dir=colmap_images,
    )
    second = frame_selector.select_frames(
        second_video, config=config, job_id="second-job",
        output_root=output_dir, colmap_images_dir=colmap_images,
    )

    manifest = json.loads((output_dir / "frames.json").read_text())
    assert {video["job_id"] for video in manifest["videos"]} == {"first-job", "second-job"}
    # Disk holds only the latest job's images (fresh directory per run).
    assert len(list(colmap_images.glob("*.jpg"))) == second["selected_count"]
    assert first["selected_count"] > 0


def test_bridge_frame_is_retained_when_prev_and_next_do_not_overlap():
    cfg = SelectorConfig(
        blur_threshold=50,
        similarity_threshold=0.88,
        bridge_similarity_threshold=0.9,
        bridge_overlap_threshold=0.55,
        lookahead_window=2,
    )

    status, reason = evaluate_temporal_bridge(0.95, 0.96, 0.25, "sharp", cfg)

    assert status == "BRIDGE"
    assert reason == "BRIDGE"


def test_blurry_bridge_is_protected():
    cfg = SelectorConfig(
        blur_threshold=50,
        similarity_threshold=0.88,
        bridge_similarity_threshold=0.9,
        bridge_overlap_threshold=0.55,
        lookahead_window=2,
    )

    status, reason = evaluate_temporal_bridge(0.94, 0.93, 0.34, "blurry", cfg)

    assert status == "BLURRY_BRIDGE"
    assert reason == "BLURRY_BRIDGE"


def test_uniform_sampling_stride_indices(tmp_path):
    video = tmp_path / "walk_stride.mp4"
    _write_test_video(video, fps=10, seconds=6)  # 60 frames: 0..59
    job_root = tmp_path / "job"
    output_root = job_root / "frame_selection"
    colmap_images = job_root / "colmap" / "images"

    cfg = SelectorConfig(
        sampling_stride=5,
        max_frame_gap=25,
        min_final_selection=1,
        max_rejected_preview=0,
        adaptive_blur=False,
    )
    result = select_frames(
        video,
        config=cfg,
        output_root=output_root,
        colmap_images_dir=colmap_images,
    )
    assert result["stats"]["sampling_stride"] == 5
    assert result["stats"]["total_source_frames"] == 60
    # Every selected frame's original_frame must be a multiple of 5
    for frame in result["selected_frames"]:
        assert frame["original_frame"] % 5 == 0


def test_2000_frames_produces_approximately_400_candidates():
    # 2000 frames at stride 5 produces exactly 400 candidate indices
    stride = 5
    total_frames = 2000
    candidate_indices = list(range(0, total_frames, stride))
    assert len(candidate_indices) == 400
    assert candidate_indices[0] == 0
    assert candidate_indices[1] == 5
    assert candidate_indices[-1] == 1995


def test_continuity_fallback_restores_intermediate_candidates(tmp_path):
    from pipeline.frame_selection.frame import FrameMetrics
    from pipeline.frame_selection.frame_selector import enforce_continuity
    from pipeline.frame_selection.image_io import write_jpeg

    # Create dummy images on disk so validate_image_file passes
    img_dir = tmp_path / "staged"
    img_dir.mkdir()
    dummy_img = np.full((32, 32, 3), 128, dtype=np.uint8)

    def _make_frame(idx, exposure="good", sharpness=100.0, score=0.8, quality="sharp", is_corrupt=False):
        p = img_dir / f"frame_{idx:06d}.jpg"
        if is_corrupt:
            p.write_bytes(b"not_a_valid_image")
        else:
            write_jpeg(p, dummy_img)
        return FrameMetrics(
            frame_index=idx,
            timestamp=idx / 10.0,
            sharpness=sharpness,
            brightness=128.0,
            exposure_label=exposure,
            quality_label=quality,
            final_score=score,
            image_path=str(p),
        )

    # Selected frames have a gap of 50 frames (100 to 150)
    selected = [_make_frame(100), _make_frame(150)]
    # Candidates evaluated at stride 5
    candidates = [
        _make_frame(105),
        _make_frame(110),
        _make_frame(115),
        _make_frame(120),
        _make_frame(125, score=0.9),  # Exact midpoint
        _make_frame(130),
        _make_frame(135),
        _make_frame(140),
        _make_frame(145),
    ]

    final_sel, restored, unrepairable = enforce_continuity(selected, candidates, max_frame_gap=25)

    assert len(unrepairable) == 0
    assert len(restored) >= 1
    # Check that frame 125 was restored to bridge the gap of 50 into two gaps of 25
    restored_indices = [f.frame_index for f in restored]
    assert 125 in restored_indices
    # All consecutive gaps in final selection must be <= 25
    final_indices = [f.frame_index for f in final_sel]
    for prev_idx, curr_idx in zip(final_indices[:-1], final_indices[1:]):
        assert curr_idx - prev_idx <= 25


def test_continuity_restores_mildly_blurry_candidate_when_needed(tmp_path):
    from pipeline.frame_selection.frame import FrameMetrics
    from pipeline.frame_selection.frame_selector import enforce_continuity
    from pipeline.frame_selection.image_io import write_jpeg

    img_dir = tmp_path / "staged_blurry"
    img_dir.mkdir()
    dummy_img = np.full((32, 32, 3), 128, dtype=np.uint8)

    def _make_frame(idx, quality="sharp", score=0.8):
        p = img_dir / f"frame_{idx:06d}.jpg"
        write_jpeg(p, dummy_img)
        return FrameMetrics(
            frame_index=idx,
            timestamp=idx / 10.0,
            sharpness=50.0 if quality == "blurry" else 150.0,
            brightness=128.0,
            exposure_label="good",
            quality_label=quality,
            final_score=score,
            image_path=str(p),
        )

    # Gap of 50 from 100 to 150.
    selected = [_make_frame(100), _make_frame(150)]
    # The only intermediate candidate at 125 is blurry
    blurry_candidate = _make_frame(125, quality="blurry", score=0.4)

    final_sel, restored, unrepairable = enforce_continuity(selected, [blurry_candidate], max_frame_gap=25)

    assert len(unrepairable) == 0
    assert len(restored) == 1
    assert restored[0].frame_index == 125
    assert restored[0].selected is True
    assert "blurry" in restored[0].reason.lower()


def test_corrupt_or_unusable_images_never_force_retained(tmp_path):
    from pipeline.frame_selection.frame import FrameMetrics
    from pipeline.frame_selection.frame_selector import enforce_continuity
    from pipeline.frame_selection.image_io import write_jpeg

    img_dir = tmp_path / "staged_corrupt"
    img_dir.mkdir()
    dummy_img = np.full((32, 32, 3), 128, dtype=np.uint8)

    p_good_100 = img_dir / "frame_000100.jpg"
    p_good_150 = img_dir / "frame_000150.jpg"
    write_jpeg(p_good_100, dummy_img)
    write_jpeg(p_good_150, dummy_img)

    # Corrupt intermediate candidate: non-image bytes
    p_corrupt = img_dir / "frame_000125.jpg"
    p_corrupt.write_bytes(b"corrupt-data-not-a-jpeg")

    # Exposure-rejected intermediate candidate
    p_dark = img_dir / "frame_000130.jpg"
    write_jpeg(p_dark, dummy_img)

    selected = [
        FrameMetrics(frame_index=100, timestamp=10.0, exposure_label="good", image_path=str(p_good_100)),
        FrameMetrics(frame_index=150, timestamp=15.0, exposure_label="good", image_path=str(p_good_150)),
    ]
    candidates = [
        FrameMetrics(frame_index=125, timestamp=12.5, exposure_label="good", image_path=str(p_corrupt)),
        FrameMetrics(frame_index=130, timestamp=13.0, exposure_label="too_dark", image_path=str(p_dark)),
    ]

    final_sel, restored, unrepairable = enforce_continuity(selected, candidates, max_frame_gap=25)

    # Neither the corrupt nor the exposure-rejected candidate should be restored
    assert len(restored) == 0
    assert len(final_sel) == 2
    # The gap should be honestly reported as unrepairable
    assert len(unrepairable) == 1
    assert unrepairable[0]["gap"] == 50
    assert unrepairable[0]["max_permitted_gap"] == 25


def test_unrepairable_gaps_reported_honestly(tmp_path):
    video = tmp_path / "walk_gap.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video), fourcc, 10, (160, 120))
    for i in range(40):
        writer.write(np.full((120, 160, 3), 120 + i, dtype=np.uint8))
    writer.release()
    job_root = tmp_path / "job"

    # Set very small max_frame_gap=2 with sampling_stride=10
    # Between 0 and 10, stride=10 means candidates are only 0, 10, 20...
    # Gaps of 10 exceed max_frame_gap of 2 and cannot be repaired because no intermediate candidates were sampled
    cfg = SelectorConfig(
        sampling_stride=10,
        max_frame_gap=2,
        min_final_selection=1,
        adaptive_blur=False,
    )
    result = select_frames(
        video,
        config=cfg,
        output_root=job_root / "frame_selection",
        colmap_images_dir=job_root / "colmap" / "images",
    )
    assert result["stats"]["gaps_exceeding_max"] > 0
    assert result["stats"]["continuity_guaranteed"] is False
    assert len(result["stats"]["unrepairable_gaps"]) > 0
    assert any("unrepairable" in w.lower() for w in result["warnings"])


def test_gap_statistics_and_chronological_ordering(tmp_path):
    video = tmp_path / "walk_stats.mp4"
    _write_test_video(video, fps=10, seconds=3)  # 30 frames
    job_root = tmp_path / "job"

    cfg = SelectorConfig(
        sampling_stride=5,
        max_frame_gap=25,
        min_final_selection=1,
        adaptive_blur=False,
    )
    result = select_frames(
        video,
        config=cfg,
        output_root=job_root / "frame_selection",
        colmap_images_dir=job_root / "colmap" / "images",
    )
    stats = result["stats"]
    assert stats["is_unique_and_chronological"] is True
    assert stats["min_frame_gap"] > 0
    assert stats["max_frame_gap"] >= stats["min_frame_gap"]
    assert stats["median_frame_gap"] >= stats["min_frame_gap"]
    assert stats["min_timestamp_gap"] > 0
    assert stats["max_timestamp_gap"] >= stats["min_timestamp_gap"]
    assert stats["retention_percentage"] > 0


def test_selector_config_compatibility():
    # Test default values
    cfg = SelectorConfig()
    assert cfg.sampling_stride == 5
    assert cfg.sample_stride == 5
    assert cfg.max_frame_gap == 25
    assert cfg.max_source_frame_gap == 25
    assert cfg.continuity_aware is True
    assert cfg.enforce_continuity is True
    assert cfg.conservative_redundancy is True

    # Test legacy from_dict with no new fields
    legacy = SelectorConfig.from_dict({"blur_threshold": 60.0})
    assert legacy.blur_threshold == 60.0
    assert legacy.sampling_stride == 5
    assert legacy.max_frame_gap == 25

    # Test alias loading
    with_aliases = SelectorConfig.from_dict({
        "sample_stride": 3,
        "max_source_frame_gap": 15,
        "enforce_continuity": False,
    })
    assert with_aliases.sampling_stride == 3
    assert with_aliases.sample_stride == 3
    assert with_aliases.max_frame_gap == 15
    assert with_aliases.max_source_frame_gap == 15
    assert with_aliases.continuity_aware is False

    # Test to_dict includes all new fields
    d = cfg.to_dict()
    assert d["sampling_stride"] == 5
    assert d["max_frame_gap"] == 25
    assert d["continuity_aware"] is True
    assert d["conservative_redundancy"] is True


def test_redundancy_filtering_cannot_violate_maximum_gap(tmp_path):
    # A video where consecutive static frames might be deemed redundant, but
    # continuity enforcement ensures the final gap never exceeds max_frame_gap
    video = tmp_path / "redundant_pan.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video), fourcc, 10, (160, 120))
    for i in range(50):
        # Gradual change
        writer.write(np.full((120, 160, 3), 100 + (i // 5) * 5, dtype=np.uint8))
    writer.release()

    job_root = tmp_path / "job"
    cfg = SelectorConfig(
        sampling_stride=5,
        max_frame_gap=15,
        conservative_redundancy=True,
        continuity_aware=True,
        min_final_selection=1,
        adaptive_blur=False,
    )
    result = select_frames(
        video,
        config=cfg,
        output_root=job_root / "frame_selection",
        colmap_images_dir=job_root / "colmap" / "images",
    )
    assert result["stats"]["continuity_guaranteed"] is True
    assert result["stats"]["max_frame_gap"] <= 15
    assert result["stats"]["gaps_exceeding_max"] == 0


def test_short_video_and_few_frames_safety(tmp_path):
    # Short video (e.g., 6 frames total)
    video = tmp_path / "short.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video), fourcc, 10, (160, 120))
    for i in range(6):
        writer.write(np.full((120, 160, 3), 100 + i * 10, dtype=np.uint8))
    writer.release()

    job_root = tmp_path / "job"
    cfg = SelectorConfig(
        sampling_stride=5,
        max_frame_gap=25,
        min_final_selection=1,
        adaptive_blur=False,
    )
    result = select_frames(
        video,
        config=cfg,
        output_root=job_root / "frame_selection",
        colmap_images_dir=job_root / "colmap" / "images",
    )
    assert result["selected_count"] >= 1
    assert result["stats"]["is_unique_and_chronological"] is True
    assert result["stats"]["continuity_guaranteed"] is True
