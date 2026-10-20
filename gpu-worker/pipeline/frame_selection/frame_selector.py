from __future__ import annotations

import csv
import json
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


def _process_frame_chunk(args: tuple[str, int, int, str, int]) -> list[dict[str, Any]]:
    """Extract a chunk of frames to unique JPEGs on disk; return metadata only.

    Full-resolution pixels stay on disk. Workers return paths + small thumbnails
    so ProcessPoolExecutor results do not ferry multi-megabyte arrays.
    """
    video_path_str, start_frame, count, temp_dir_str, jpeg_quality = args
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
            ret, frame = cap.read()
            if not ret:
                break
            frame_index = start_frame + offset
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

    if (
        previous_overlap >= config.similarity_threshold
        and next_overlap >= config.similarity_threshold
        and direct_overlap >= config.bridge_overlap_threshold
    ):
        return "REDUNDANT", "REDUNDANT"

    return "KEEP", "KEEP"


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

    ensure_disk_space(
        output_dir,
        _estimate_extraction_bytes(metadata, max_frames),
    )
    snapshot(
        "before_extraction",
        output_dir,
        job_id=export_id,
        video=metadata.get("filename"),
        resolution=f"{metadata.get('width')}x{metadata.get('height')}",
        fps=metadata.get("fps"),
        duration=round(float(metadata.get("duration") or 0), 3),
        candidate_frames=max_frames,
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
        chunk_size = max(10, (max_frames + workers - 1) // workers)
        chunks = [
            (str(video_path), start_idx, min(chunk_size, max_frames - start_idx), str(temp_frames_dir), JPEG_QUALITY)
            for start_idx in range(0, max_frames, chunk_size)
        ]
        workers_used = workers
        logger.info(
            "[frame_selection:extraction] Disk-backed parallel extraction — %d workers, %d chunks, %d frames → %s",
            workers, len(chunks), max_frames, temp_frames_dir,
        )
        _progress_callback(
            progress_callback, 1,
            f"[frame_selection:extraction] Starting parallel extraction with {workers} CPU workers "
            f"({len(chunks)} chunks) writing to disk",
        )
        try:
            raw_batches: list[list[dict[str, Any]]] = []
            with ProcessPoolExecutor(max_workers=workers) as executor:
                for batch in executor.map(_process_frame_chunk, chunks):
                    raw_batches.append(batch)
            for batch in raw_batches:
                analyzed_items.extend(_reconstruct_disk_items(batch))
            parallel_ok = len(analyzed_items) >= int(max_frames * 0.9)
            if parallel_ok:
                logger.info(
                    "[frame_selection:extraction] Parallel extraction complete — %d frames staged on disk",
                    len(analyzed_items),
                )
            else:
                logger.warning(
                    "[frame_selection:extraction] Parallel extraction returned only %d/%d frames — retrying sequentially",
                    len(analyzed_items), max_frames,
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
        logger.info("[frame_selection:extraction] Sequential disk-backed extraction — %d frames", max_frames)
        _progress_callback(
            progress_callback, 1,
            f"[frame_selection:extraction] Sequential extraction — {max_frames} frames on 1 worker",
        )
        for frame_index, timestamp, frame in iter_frames(video_path, max_frames=max_frames):
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
    # STAGE 5: Coverage gap filling                                       #
    # ------------------------------------------------------------------ #
    coverage_timer = StageTimer("coverage")
    warnings: list[str] = []
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
        key=lambda item: item.timestamp,
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

    if valid_count < cfg.min_final_selection:
        raise RuntimeError(
            f"Only {valid_count} valid COLMAP images on disk after selection "
            f"(minimum={cfg.min_final_selection}); write_failures={len(write_failures)}"
        )
    if valid_count == 0:
        raise RuntimeError("No valid images in COLMAP input directory after selection")

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
            "extracted_frames": processed_frames,
            "analyzed_frames": len(candidate_frames) + len(rejected_frames),
            "blurry_frames": blurry_count,
            "exposure_rejected": exposure_rejected_count,
            "redundant_frames": redundant_rejections,
            "selected_frames": valid_count,
            "selected_attempted": len(selected_frames),
            "valid_on_disk": valid_count,
            "write_failures": len(write_failures),
            "extraction_failures": extraction_failures,
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

    logger.info(
        "[frame_selection:summary] DONE — %d/%d frames valid on disk for COLMAP (%.1f%%) "
        "| blurry=%d | exposure=%d | redundant=%d | write_failures=%d | path=%s",
        valid_count, total_frames,
        100.0 * valid_count / max(total_frames, 1),
        blurry_count, exposure_rejected_count, redundant_rejections, len(write_failures),
        images_dir.resolve(),
    )
    _progress_callback(
        progress_callback, 100,
        f"[frame_selection:summary] Export complete: {valid_count} valid frames ready for COLMAP "
        f"| blurry={blurry_count} | exposure_rejected={exposure_rejected_count} | redundant={redundant_rejections}",
        selected_count=valid_count,
        stats=result["stats"],
    )

    return result
