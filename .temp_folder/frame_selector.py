from __future__ import annotations

import bisect
import csv
import heapq
import json
import re
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
from backend.processing.similarity import compute_similarity, prepare_similarity_frame
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
        previous_overlap
        >= (
            max(config.similarity_threshold, 0.95)
            if config.conservative_redundancy
            else config.similarity_threshold
        )
        and next_overlap
        >= (
            max(config.similarity_threshold, 0.95)
            if config.conservative_redundancy
            else config.similarity_threshold
        )
        and direct_overlap
        >= (
            max(config.bridge_overlap_threshold, 0.85)
            if config.conservative_redundancy
            else config.bridge_overlap_threshold
        )
    ):
        return "REDUNDANT", "REDUNDANT"

    return "KEEP", "KEEP"


def enforce_continuity(
    selected_frames: list[FrameMetrics],
    candidates: list[FrameMetrics],
    max_frame_gap: int,
) -> tuple[list[FrameMetrics], list[FrameMetrics], list[dict[str, Any]]]:
    """Restore the best usable sampled frames needed to bound source-frame gaps."""
    if max_frame_gap <= 0:
        return selected_frames, [], []

    selected_by_index = {frame.frame_index: frame for frame in selected_frames}
    candidate_by_index = {
        frame.frame_index: frame
        for frame in candidates
        if frame.exposure_label not in {"too_dark", "too_bright"}
        and frame.image_path
        and Path(frame.image_path).is_file()
    }
    candidate_indices = sorted(candidate_by_index)
    restored: list[FrameMetrics] = []
    unrepairable: list[dict[str, Any]] = []

    ordered_selected = sorted(
        selected_by_index.values(), key=lambda item: item.frame_index
    )
    for previous, current in zip(ordered_selected, ordered_selected[1:]):
        gap = current.frame_index - previous.frame_index
        if gap <= max_frame_gap:
            continue

        start = bisect.bisect_right(candidate_indices, previous.frame_index)
        end = bisect.bisect_left(candidate_indices, current.frame_index)
        intermediate = [
            candidate_by_index[index]
            for index in candidate_indices[start:end]
            if index not in selected_by_index
        ]
        intermediate = [
            frame
            for frame in intermediate
            if frame.image_path
            and cv2.imread(frame.image_path, cv2.IMREAD_COLOR) is not None
        ]
        nodes = [previous, *intermediate, current]
        target = len(nodes) - 1
        distances = {0: 0.0}
        parents: dict[int, int] = {}
        queue = [(0.0, 0)]

        while queue:
            distance, node_index = heapq.heappop(queue)
            if distance > distances.get(node_index, float("inf")):
                continue
            if node_index == target:
                break
            for next_index in range(node_index + 1, len(nodes)):
                edge_gap = nodes[next_index].frame_index - nodes[node_index].frame_index
                if edge_gap > max_frame_gap:
                    break
                score = max(0.0, min(1.0, nodes[next_index].final_score))
                cost = 0.0 if next_index == target else 1.05 - score
                next_distance = distance + cost
                if next_distance < distances.get(next_index, float("inf")):
                    distances[next_index] = next_distance
                    parents[next_index] = node_index
                    heapq.heappush(queue, (next_distance, next_index))

        if target in parents:
            path: list[int] = []
            node_index = target
            while node_index in parents:
                node_index = parents[node_index]
                if node_index:
                    path.append(node_index)
            for node_index in reversed(path):
                frame = nodes[node_index]
                frame.status = "selected"
                frame.selected = True
                frame.reason = f"Continuity enforcement ({frame.quality_label})"
                selected_by_index[frame.frame_index] = frame
                restored.append(frame)
        else:
            unrepairable.append({
                "prev_frame_index": previous.frame_index,
                "prev_timestamp": previous.timestamp,
                "next_frame_index": current.frame_index,
                "next_timestamp": current.timestamp,
                "gap": gap,
                "max_permitted_gap": max_frame_gap,
                "reason": "No usable intermediate candidates can bridge this gap",
            })

    return sorted(selected_by_index.values(), key=lambda item: item.frame_index), restored, unrepairable


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
    if cfg.experimental_uniform_sampling and cfg.experimental_interval_seconds <= 0:
        raise ValueError("experimental_interval_seconds must be positive")
    if cfg.experimental_uniform_sampling and cfg.experimental_start_seconds < 0:
        raise ValueError("experimental_start_seconds cannot be negative")
    if cfg.radical_uniform_sampling and cfg.radical_interval_seconds <= 0:
        raise ValueError("radical_interval_seconds must be positive")
    if cfg.radical_uniform_sampling and cfg.radical_start_seconds < 0:
        raise ValueError("radical_start_seconds cannot be negative")
    export_id = job_id or uuid.uuid4().hex
    metadata = get_video_metadata(video_path)
    total_frames = int(metadata["frame_count"])
    max_frames = cfg.max_analysis_frames or total_frames
    sampling_stride = max(1, int(cfg.sampling_stride))
    effective_max_frame_gap = max(1, int(cfg.max_frame_gap))
    if (
        not cfg.radical_uniform_sampling
        and total_frames > 0
        and cfg.min_final_selection > 1
        and total_frames < cfg.min_final_selection * sampling_stride
    ):
        sampling_stride = max(1, total_frames // cfg.min_final_selection)
    expected_candidates = len(range(0, max_frames, sampling_stride))

    output_dir = OUTPUT_DIR
    prefix = re.sub(r"[^A-Za-z0-9_-]", "", export_id[:12]) or uuid.uuid4().hex[:12]
    temp_dir = output_dir / "temp_frames" / uuid.uuid4().hex
    temp_dir.mkdir(parents=True, exist_ok=True)

    candidate_frames: list[FrameMetrics] = []
    rejected_frames: list[FrameMetrics] = []
    processed_frames = 0
    blurry_count = 0
    exposure_rejected_count = 0
    redundant_rejections = 0

    extracted: list[FrameMetrics] = []
    for frame_index, timestamp, frame in iter_frames(
        video_path, max_frames=max_frames, stride=sampling_stride
    ):
        processed_frames += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharpness = variance_of_laplacian(gray)
        brightness, dark_ratio, bright_ratio, exposure_label = analyze_exposure(frame)
        image_path = temp_dir / f"frame_{frame_index:06d}.jpg"
        if not cv2.imwrite(str(image_path), frame):
            raise RuntimeError(f"Unable to stage video frame {frame_index}: {image_path}")
        candidate = FrameMetrics(
            frame_index=frame_index,
            timestamp=float(timestamp),
            sharpness=float(sharpness),
            brightness=float(brightness),
            dark_ratio=float(dark_ratio),
            bright_ratio=float(bright_ratio),
            exposure_label=exposure_label,
            image_path=str(image_path),
            thumbnail=(
                None
                if cfg.radical_uniform_sampling or cfg.experimental_uniform_sampling
                else prepare_similarity_frame(gray)
            ),
            status="candidate",
        )
        extracted.append(candidate)
        del frame, gray
        progress = 1 + int(49 * processed_frames / max(expected_candidates, 1))
        _progress_callback(
            progress_callback,
            progress,
            f"Analyzing frame {processed_frames} of {expected_candidates}",
            stats={
                "analyzed_frames": processed_frames,
                "blurry_frames": blurry_count,
                "exposure_rejected": exposure_rejected_count,
                "redundant_frames": redundant_rejections,
                "selected_frames": 0,
            },
            selected_count=0,
        )

    usable_sharpness = [
        frame.sharpness
        for frame in extracted
        if frame.exposure_label not in {"too_dark", "too_bright"}
    ]
    if usable_sharpness and cfg.adaptive_blur:
        median_sharpness = float(np.median(usable_sharpness))
        effective_blur_threshold = (
            max(cfg.min_blur_threshold, median_sharpness * 0.70)
            if median_sharpness < cfg.blur_threshold
            else cfg.blur_threshold
        )
    else:
        median_sharpness = 0.0
        effective_blur_threshold = cfg.blur_threshold
    _progress_callback(
        progress_callback,
        50,
        f"Blur threshold calibrated to {effective_blur_threshold:.1f} "
        f"(median sharpness {median_sharpness:.1f})",
    )

    for candidate in extracted:
        candidate.quality_label = classify_blur(
            candidate.sharpness, effective_blur_threshold
        )
        if (
            candidate.exposure_label not in {"too_dark", "too_bright"}
            and candidate.quality_label == "blurry"
        ):
            blurry_count += 1
        if candidate.exposure_label in {"too_dark", "too_bright"}:
            candidate.status = "rejected"
            candidate.reason = "EXPOSURE"
            candidate.selected = False
            rejected_frames.append(candidate)
            exposure_rejected_count += 1
            continue
        if (
            (cfg.radical_uniform_sampling or cfg.experimental_uniform_sampling)
            and candidate.quality_label == "blurry"
        ):
            candidate.status = "rejected"
            candidate.reason = "BLURRY"
            candidate.selected = False
            rejected_frames.append(candidate)
            continue

        candidate.sharpness_score = min(
            1.0,
            max(0.0, candidate.sharpness / max(effective_blur_threshold * 1.5, 1.0)),
        )
        candidate.exposure_score = 1.0
        candidate.viewpoint_change_score = 0.25
        candidate.final_score = compute_frame_score(candidate, cfg)
        candidate_frames.append(candidate)

    windowed_candidates: dict[int, list[FrameMetrics]] = {}
    if not cfg.radical_uniform_sampling and not cfg.experimental_uniform_sampling:
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

        for index, candidate in enumerate(current_window):
            previous_selected = (
                selected_window[-1]
                if selected_window
                else (selected_frames[-1] if selected_frames else None)
            )
            next_candidates = current_window[index + 1 : index + 1 + cfg.lookahead_window]
            next_frame = next_candidates[0] if next_candidates else None
            next_similarity = 0.0
            if next_frame is not None:
                next_similarity = compute_similarity(candidate.thumbnail, next_frame.thumbnail)
            previous_similarity = (
                0.0
                if previous_selected is None
                else compute_similarity(previous_selected.thumbnail, candidate.thumbnail)
            )
            direct_overlap = 0.0
            if previous_selected is not None and next_frame is not None:
                direct_overlap = compute_similarity(
                    previous_selected.thumbnail, next_frame.thumbnail
                )

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
                    report_selection_progress(len(selected_frames) + len(selected_window))
                    continue
                candidate.status = "rejected"
                candidate.selected = False
                candidate.reason = "BLURRY"
                rejected_frames.append(candidate)
                report_selection_progress(len(selected_frames) + len(selected_window))
                continue

            candidate.viewpoint_change_score = max(0.4, 1.0 - previous_similarity)
            candidate.final_score = compute_frame_score(candidate, cfg)
            candidate.status = "selected"
            candidate.selected = True
            candidate.reason = "Meaningful viewpoint change" if status != "BRIDGE" else "BRIDGE"
            selected_window.append(candidate)
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
    restored_frames: list[FrameMetrics] = []
    unrepairable_gaps: list[dict[str, Any]] = []
    if cfg.radical_uniform_sampling:
        warnings.append(
            "Radical uniform sampling was used "
            f"(every {cfg.radical_interval_seconds:g}s starting at "
            f"{cfg.radical_start_seconds:g}s)."
        )
        last_kept_timestamp = (
            cfg.radical_start_seconds - cfg.radical_interval_seconds
        )
        for candidate in candidate_frames:
            if (
                candidate.timestamp >= cfg.radical_start_seconds
                and candidate.timestamp - last_kept_timestamp
                >= cfg.radical_interval_seconds
            ):
                candidate.status = "selected"
                candidate.selected = True
                candidate.reason = "Radical uniform sampling"
                selected_frames.append(candidate)
                last_kept_timestamp = candidate.timestamp
        _progress_callback(
            progress_callback,
            75,
            f"Applying radical {cfg.radical_interval_seconds:g}s uniform downsampling",
            selected_count=len(selected_frames),
            stats={
                "analyzed_frames": processed_frames,
                "blurry_frames": blurry_count,
                "exposure_rejected": exposure_rejected_count,
                "redundant_frames": redundant_rejections,
                "selected_frames": len(selected_frames),
            },
        )
    elif cfg.experimental_uniform_sampling:
        warnings.append(
            "Experimental uniform sampling was used "
            f"(every {cfg.experimental_interval_seconds:g}s starting at "
            f"{cfg.experimental_start_seconds:g}s)."
        )
        tolerance = 0.05
        next_target = cfg.experimental_start_seconds
        for candidate in sorted(candidate_frames, key=lambda item: item.timestamp):
            if candidate.timestamp < next_target - tolerance:
                continue
            while candidate.timestamp > next_target + tolerance:
                next_target += cfg.experimental_interval_seconds
            if abs(candidate.timestamp - next_target) <= tolerance:
                candidate.status = "selected"
                candidate.selected = True
                candidate.reason = "Experimental uniform sampling"
                selected_frames.append(candidate)
                next_target += cfg.experimental_interval_seconds
        _progress_callback(
            progress_callback,
            75,
            "Experimental uniform sampling complete",
            selected_count=len(selected_frames),
            stats={
                "analyzed_frames": processed_frames,
                "blurry_frames": blurry_count,
                "exposure_rejected": exposure_rejected_count,
                "redundant_frames": redundant_rejections,
                "selected_frames": len(selected_frames),
            },
        )
    if (
        cfg.continuity_aware
        and not cfg.radical_uniform_sampling
        and not cfg.experimental_uniform_sampling
    ):
        selected_frames, restored_frames, unrepairable_gaps = enforce_continuity(
            selected_frames, candidate_frames, effective_max_frame_gap
        )
        if unrepairable_gaps:
            warnings.append(
                f"{len(unrepairable_gaps)} source-frame gap(s) could not be repaired "
                "with the available sampled candidates."
            )
    if not cfg.radical_uniform_sampling and not cfg.experimental_uniform_sampling:
        warnings.extend(find_large_gaps(selected_frames, cfg.coverage_gap_seconds))

    coverage_total = max(len(selected_frames) - 1, 1)
    for idx in (
        range(1, len(selected_frames))
        if not cfg.radical_uniform_sampling and not cfg.experimental_uniform_sampling
        else ()
    ):
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
        (
            f"Applying radical {cfg.radical_interval_seconds:g}s uniform downsampling"
            if cfg.radical_uniform_sampling
            else "Coverage validation complete"
        ),
        selected_count=len(selected_frames),
    )

    selected_frames = sorted({frame.frame_index: frame for frame in selected_frames}.values(), key=lambda item: item.timestamp)

    safety_net_added_frames: list[dict[str, Any]] = []
    if (
        not cfg.radical_uniform_sampling
        and not cfg.experimental_uniform_sampling
        and len(selected_frames) < cfg.min_final_selection
        and candidate_frames
    ):
        selected_indices = {frame.frame_index for frame in selected_frames}
        target_count = min(cfg.min_final_selection, len(candidate_frames))
        ordered_candidates = sorted(candidate_frames, key=lambda item: item.frame_index)
        step = max(1, len(ordered_candidates) // target_count)
        for candidate in ordered_candidates[::step]:
            if candidate.frame_index in selected_indices:
                continue
            candidate.status = "selected"
            candidate.selected = True
            candidate.reason = "Uniform coverage safety net"
            selected_frames.append(candidate)
            selected_indices.add(candidate.frame_index)
            safety_net_added_frames.append({
                "frame_index": candidate.frame_index,
                "timestamp": round(candidate.timestamp, 6),
                "reason": candidate.reason,
            })
            if len(selected_frames) >= target_count:
                break
        selected_frames.sort(key=lambda item: item.frame_index)

    if (
        not cfg.radical_uniform_sampling
        and len(selected_frames) < cfg.min_final_selection
    ):
        warnings.append(
            f"Only {len(selected_frames)} frames survived selection. This may be insufficient for reliable reconstruction."
        )
    if (
        not cfg.radical_uniform_sampling
        and not cfg.experimental_uniform_sampling
        and len(selected_frames) > max(1, int(total_frames * 0.9))
    ):
        warnings.append(
            "Very little redundancy was removed. The input may contain substantial camera movement or weak similarity thresholds."
        )

    output_dir = OUTPUT_DIR
    selected_dir = SELECTED_DIR
    rejected_dir = REJECTED_DIR
    colmap_images_dir = COLMAP_IMAGES_DIR
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
            image = cv2.imread(frame.image_path, cv2.IMREAD_COLOR) if frame.image_path else None
            if image is None:
                raise RuntimeError(f"Unable to read staged selected frame {frame.frame_index}")
            if not cv2.imwrite(str(selected_dir / output_name), image):
                raise RuntimeError(f"Unable to write selected frame {selected_dir / output_name}")
            del image
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
            image = cv2.imread(frame.image_path, cv2.IMREAD_COLOR) if frame.image_path else None
            if image is None:
                raise RuntimeError(f"Unable to read staged rejected frame {frame.frame_index}")
            if not cv2.imwrite(str(rejected_dir / output_name), image):
                raise RuntimeError(f"Unable to write rejected frame {rejected_dir / output_name}")
            del image
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

    shutil.rmtree(temp_dir, ignore_errors=True)

    frame_gaps = [
        current.frame_index - previous.frame_index
        for previous, current in zip(selected_frames, selected_frames[1:])
    ]
    timestamp_gaps = [
        current.timestamp - previous.timestamp
        for previous, current in zip(selected_frames, selected_frames[1:])
    ]
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
            "total_source_frames": total_frames,
            "sampling_stride": sampling_stride,
            "experimental_uniform_sampling": cfg.experimental_uniform_sampling,
            "experimental_interval_seconds": cfg.experimental_interval_seconds,
            "experimental_start_seconds": cfg.experimental_start_seconds,
            "radical_uniform_sampling": cfg.radical_uniform_sampling,
            "radical_interval_seconds": cfg.radical_interval_seconds,
            "radical_start_seconds": cfg.radical_start_seconds,
            "sampled_candidates_count": processed_frames,
            "analyzed_frames": processed_frames,
            "effective_blur_threshold": effective_blur_threshold,
            "blurry_frames": blurry_count,
            "exposure_rejected": exposure_rejected_count,
            "redundant_frames": redundant_rejections,
            "restored_frames_count": len(restored_frames),
            "restored_frames": [
                {
                    "frame_index": frame.frame_index,
                    "timestamp": round(frame.timestamp, 6),
                    "reason": frame.reason,
                    "quality_label": frame.quality_label,
                }
                for frame in restored_frames
            ],
            "safety_net_added_count": len(safety_net_added_frames),
            "safety_net_frames": safety_net_added_frames,
            "selected_frames": len(selected_entries),
            "selected_files": [item["output_file"] for item in selected_entries],
            "min_frame_gap": min(
                (b.frame_index - a.frame_index for a, b in zip(selected_frames, selected_frames[1:])),
                default=0,
            ),
            "max_frame_gap": max(
                frame_gaps, default=0
            ),
            "median_frame_gap": float(np.median(frame_gaps)) if frame_gaps else 0.0,
            "min_timestamp_gap": round(min(timestamp_gaps), 4) if timestamp_gaps else 0.0,
            "median_timestamp_gap": (
                round(float(np.median(timestamp_gaps)), 4) if timestamp_gaps else 0.0
            ),
            "max_timestamp_gap": round(max(timestamp_gaps), 4) if timestamp_gaps else 0.0,
            "max_permitted_gap": effective_max_frame_gap,
            "gaps_exceeding_max": sum(gap > effective_max_frame_gap for gap in frame_gaps),
            "continuity_verifiable": len(selected_frames) >= 2,
            "continuity_guaranteed": (
                len(selected_frames) >= 2
                and all(gap <= effective_max_frame_gap for gap in frame_gaps)
            ),
            "is_unique_and_chronological": len(
                {frame.frame_index for frame in selected_frames}
            ) == len(selected_frames)
            and selected_frames == sorted(selected_frames, key=lambda item: item.frame_index),
            "retention_percentage": round(
                100.0 * len(selected_entries) / max(total_frames, 1), 2
            ),
            "unrepairable_gaps": unrepairable_gaps,
        },
        "warnings": warnings,
        "selected_frames": selected_entries,
        "rejected_preview": rejected_preview,
        "metadata": metadata,
    }
    _progress_callback(progress_callback, 100, "Export complete")
    return result
