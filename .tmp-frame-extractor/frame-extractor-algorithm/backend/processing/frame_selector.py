from __future__ import annotations

import csv
import json
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from backend.models.frame import FrameMetrics
from backend.processing.blur_detector import classify_blur, variance_of_laplacian
from backend.processing.config import SelectorConfig
from backend.processing.coverage import find_large_gaps
from backend.processing.exposure_detector import analyze_exposure
from backend.processing.scoring import compute_frame_score
from backend.processing.similarity import compute_similarity
from backend.processing.video_reader import get_video_metadata, iter_frames

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output"
SELECTED_DIR = OUTPUT_DIR / "selected_frames"
REJECTED_DIR = OUTPUT_DIR / "rejected_frames"
COLMAP_DIR = OUTPUT_DIR / "colmap_input"
COLMAP_IMAGES_DIR = COLMAP_DIR / "images"
_EXPORT_LOCK = threading.Lock()


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


def select_frames(
    video_path: str | Path,
    config: SelectorConfig | None = None,
    job_id: str | None = None,
    progress_callback: Callable | None = None,
) -> dict[str, Any]:
    cfg = config or SelectorConfig()
    export_id = job_id or uuid.uuid4().hex
    metadata = get_video_metadata(video_path)
    total_frames = int(metadata["frame_count"])
    max_frames = cfg.max_analysis_frames or total_frames

    candidate_frames: list[FrameMetrics] = []
    rejected_frames: list[FrameMetrics] = []
    processed_frames = 0
    blurry_count = 0
    exposure_rejected_count = 0
    redundant_rejections = 0

    for frame_index, timestamp, frame in iter_frames(video_path, max_frames=max_frames):
        processed_frames += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharpness = variance_of_laplacian(gray)
        brightness, dark_ratio, bright_ratio, exposure_label = analyze_exposure(frame)
        quality_label = classify_blur(sharpness, cfg.blur_threshold)

        candidate = FrameMetrics(
            frame_index=frame_index,
            timestamp=float(timestamp),
            sharpness=float(sharpness),
            brightness=float(brightness),
            dark_ratio=float(dark_ratio),
            bright_ratio=float(bright_ratio),
            quality_label=quality_label,
            exposure_label=exposure_label,
            image=frame.copy(),
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
            progress = 1 + int(49 * processed_frames / max(max_frames, 1))
            _progress_callback(
                progress_callback,
                progress,
                f"Analyzing frame {processed_frames} of {max_frames}",
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

        candidate.sharpness_score = min(1.0, max(0.0, candidate.sharpness / max(cfg.blur_threshold * 1.5, 1.0)))
        candidate.exposure_score = 1.0
        candidate.viewpoint_change_score = 0.25
        candidate.final_score = compute_frame_score(candidate, cfg)
        candidate_frames.append(candidate)

        progress = 1 + int(49 * processed_frames / max(max_frames, 1))
        _progress_callback(
            progress_callback,
            progress,
            f"Analyzing frame {processed_frames} of {max_frames}",
            stats={
                "analyzed_frames": processed_frames,
                "blurry_frames": blurry_count,
                "exposure_rejected": exposure_rejected_count,
                "redundant_frames": redundant_rejections,
                "selected_frames": 0,
            },
            selected_count=0,
        )

    windowed_candidates: dict[int, list[FrameMetrics]] = {}
    for candidate in candidate_frames:
        window_id = int(candidate.timestamp // cfg.window_seconds)
        windowed_candidates.setdefault(window_id, []).append(candidate)

    selected_frames: list[FrameMetrics] = []
    selection_processed = 0
    selection_total = max(len(candidate_frames), 1)

    def report_selection_progress(selected_count: int) -> None:
        nonlocal selection_processed
        selection_processed += 1
        progress = 50 + int(25 * selection_processed / selection_total)
        _progress_callback(
            progress_callback,
            progress,
            f"Filtering frames {selection_processed} of {len(candidate_frames)}",
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
            previous_selected = recent_selected[-1] if recent_selected else None
            next_candidates = current_window[index + 1 : index + 1 + cfg.lookahead_window]
            next_frame = next_candidates[0] if next_candidates else None
            next_similarity = 0.0
            if next_frame is not None:
                next_similarity = compute_similarity(candidate.image, next_frame.image)
            previous_similarity = 1.0 if previous_selected is None else compute_similarity(previous_selected.image, candidate.image)
            direct_overlap = 0.0
            if previous_selected is not None and next_frame is not None:
                direct_overlap = compute_similarity(previous_selected.image, next_frame.image)

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
                report_selection_progress(len(selected_frames) + len(selected_window))
                continue

            if status in {"BLURRY", "BLURRY_BRIDGE"}:
                if status == "BLURRY_BRIDGE":
                    candidate.status = "selected"
                    candidate.selected = True
                    candidate.reason = "BLURRY_BRIDGE"
                    candidate.viewpoint_change_score = max(0.6, 1.0 - direct_overlap)
                    selected_window.append(candidate)
                    recent_selected.append(candidate)
                    report_selection_progress(len(selected_frames) + len(selected_window))
                    continue
                candidate.status = "rejected"
                candidate.selected = False
                candidate.reason = "BLURRY"
                rejected_frames.append(candidate)
                blurry_count += 1
                report_selection_progress(len(selected_frames) + len(selected_window))
                continue

            if previous_selected is not None and previous_similarity >= cfg.similarity_threshold and next_similarity >= cfg.similarity_threshold:
                candidate.status = "rejected"
                candidate.selected = False
                candidate.reason = "REDUNDANT"
                rejected_frames.append(candidate)
                redundant_rejections += 1
                report_selection_progress(len(selected_frames) + len(selected_window))
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
            report_selection_progress(len(selected_frames) + len(selected_window))

        if len(selected_window) < cfg.min_frames_per_window:
            fallback_candidates = sorted(
                [c for c in current_window if c not in selected_window],
                key=lambda item: item.final_score,
                reverse=True,
            )
            for fallback in fallback_candidates:
                if fallback.status != "rejected":
                    fallback.status = "selected"
                    fallback.selected = True
                    fallback.reason = "Minimum-frame protection"
                    selected_window.append(fallback)
                    if len(selected_window) >= cfg.min_frames_per_window:
                        break

        selected_frames.extend(selected_window)

    selected_frames = sorted({frame.frame_index: frame for frame in selected_frames}.values(), key=lambda item: item.timestamp)

    warnings: list[str] = []
    warnings.extend(find_large_gaps(selected_frames, cfg.coverage_gap_seconds))

    coverage_total = max(len(selected_frames) - 1, 1)
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
        progress = 75 + int(2 * idx / coverage_total)
        _progress_callback(
            progress_callback,
            progress,
            f"Checking coverage gaps {idx} of {len(selected_frames) - 1}",
            selected_count=len(selected_frames),
        )

    _progress_callback(
        progress_callback,
        77,
        "Coverage validation complete",
        selected_count=len(selected_frames),
    )

    selected_frames = sorted({frame.frame_index: frame for frame in selected_frames}.values(), key=lambda item: item.timestamp)

    if len(selected_frames) < cfg.min_final_selection:
        warnings.append(
            f"Only {len(selected_frames)} frames survived selection. This may be insufficient for reliable reconstruction."
        )
    if len(selected_frames) > max(1, int(total_frames * 0.9)):
        warnings.append(
            "Very little redundancy was removed. The input may contain substantial camera movement or weak similarity thresholds."
        )

    output_dir = OUTPUT_DIR
    selected_dir = SELECTED_DIR
    rejected_dir = REJECTED_DIR
    colmap_images_dir = COLMAP_IMAGES_DIR
    prefix = export_id[:12]
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    colmap_images_dir.mkdir(parents=True, exist_ok=True)

    video_entry = {
        "job_id": export_id,
        "source_video": metadata["filename"],
        "fps": metadata["fps"],
        "duration": round(metadata["duration"], 3),
    }
    with _EXPORT_LOCK:
        for folder in (selected_dir, rejected_dir, colmap_images_dir):
            for old_image in folder.glob(f"{prefix}_*.jpg"):
                old_image.unlink()

        selected_entries: list[dict[str, Any]] = []
        for order, frame in enumerate(selected_frames, 1):
            output_name = f"{prefix}_frame_{order:06d}.jpg"
            cv2.imwrite(str(selected_dir / output_name), frame.image)
            selected_entries.append(
                {
                    "job_id": export_id,
                    "source_video": metadata["filename"],
                    "output_file": output_name,
                    "original_frame": frame.frame_index,
                    "timestamp": round(float(frame.timestamp), 6),
                    "status": "selected",
                    "reason": frame.reason,
                }
            )
            progress = 78 + int(12 * order / max(len(selected_frames), 1))
            _progress_callback(
                progress_callback,
                progress,
                f"Saving selected frames {order} of {len(selected_frames)}",
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

        rejected_preview: list[dict[str, Any]] = []
        for order, frame in enumerate(rejected_frames[: cfg.max_rejected_preview], 1):
            output_name = f"{prefix}_rejected_{order:06d}.jpg"
            cv2.imwrite(str(rejected_dir / output_name), frame.image)
            rejected_preview.append(
                {
                    "job_id": export_id,
                    "source_video": metadata["filename"],
                    "output_file": output_name,
                    "original_frame": frame.frame_index,
                    "timestamp": round(float(frame.timestamp), 6),
                    "status": "rejected",
                    "reason": frame.reason,
                }
            )
            progress = 90 + int(7 * order / max(min(len(rejected_frames), cfg.max_rejected_preview), 1))
            _progress_callback(
                progress_callback,
                progress,
                f"Saving rejected previews {order} of {min(len(rejected_frames), cfg.max_rejected_preview)}",
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
            fieldnames = ["job_id", "source_video", "output_file", "original_frame", "timestamp", "status", "reason"]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(export_payload["selected_frames"])

        for order, entry in enumerate(selected_entries, 1):
            source = selected_dir / entry["output_file"]
            destination = colmap_images_dir / entry["output_file"]
            shutil.copy2(source, destination)
            progress = 97 + int(2 * order / max(len(selected_entries), 1))
            _progress_callback(
                progress_callback,
                progress,
                f"Preparing COLMAP images {order} of {len(selected_entries)}",
            )
        (COLMAP_DIR / "frames.json").write_text(json.dumps(export_payload, indent=2))

    result = {
        "job_id": export_id,
        "output_dir": str(output_dir),
        "colmap_dir": str(COLMAP_DIR),
        "selected_count": len(selected_entries),
        "stats": {
            "duration": round(metadata["duration"], 3),
            "fps": metadata["fps"],
            "resolution": f"{metadata['width']}x{metadata['height']}",
            "total_frames": total_frames,
            "analyzed_frames": len(candidate_frames) + len(rejected_frames),
            "blurry_frames": blurry_count,
            "exposure_rejected": exposure_rejected_count,
            "redundant_frames": redundant_rejections,
            "selected_frames": len(selected_entries),
            "selected_files": [item["output_file"] for item in selected_entries],
        },
        "warnings": warnings,
        "selected_frames": selected_entries,
        "rejected_preview": rejected_preview,
        "metadata": metadata,
    }
    _progress_callback(progress_callback, 100, "Export complete")
    return result
