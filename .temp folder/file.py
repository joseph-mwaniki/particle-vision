_init_.py
"""Gaussian-splat frame selection algorithm (CPU).

Vendored from the tested frame-extractor-algorithm implementation.
"""

from .config import SelectorConfig
from .frame_selector import evaluate_temporal_bridge, select_frames

__all__ = [
    "SelectorConfig",
    "evaluate_temporal_bridge",
    "select_frames",
]

blur_detector.py
from __future__ import annotations

import cv2
import numpy as np


def variance_of_laplacian(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def classify_blur(sharpness: float, blur_threshold: float) -> str:
    if sharpness >= blur_threshold * 1.15:
        return "sharp"
    if sharpness >= blur_threshold * 0.8:
        return "slightly_blurred"
    return "blurry"

config.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SelectorConfig:
    blur_threshold: float = 80.0
    exposure_dark_threshold: float = 0.12
    exposure_bright_threshold: float = 0.12
    min_brightness: float = 18.0
    max_brightness: float = 240.0
    window_seconds: float = 1.0
    min_frames_per_window: int = 2
    max_frames_per_window: int = 10
    similarity_threshold: float = 0.88
    bridge_similarity_threshold: float = 0.9
    bridge_overlap_threshold: float = 0.55
    feature_match_threshold: float = 0.7
    min_feature_matches: int = 30
    lookahead_window: int = 3
    min_viewpoint_change: float = 0.15
    transition_protection_threshold: float = 0.65
    max_rejected_preview: int = 50
    coverage_gap_seconds: float = 2.5
    frame_resize_width: int = 320
    frame_resize_height: int = 180
    max_analysis_frames: int | None = None
    min_final_selection: int = 8

    def to_dict(self) -> dict[str, Any]:
        return {
            "blur_threshold": self.blur_threshold,
            "exposure_dark_threshold": self.exposure_dark_threshold,
            "exposure_bright_threshold": self.exposure_bright_threshold,
            "min_brightness": self.min_brightness,
            "max_brightness": self.max_brightness,
            "window_seconds": self.window_seconds,
            "min_frames_per_window": self.min_frames_per_window,
            "max_frames_per_window": self.max_frames_per_window,
            "similarity_threshold": self.similarity_threshold,
            "bridge_similarity_threshold": self.bridge_similarity_threshold,
            "bridge_overlap_threshold": self.bridge_overlap_threshold,
            "feature_match_threshold": self.feature_match_threshold,
            "min_feature_matches": self.min_feature_matches,
            "lookahead_window": self.lookahead_window,
            "min_viewpoint_change": self.min_viewpoint_change,
            "transition_protection_threshold": self.transition_protection_threshold,
            "coverage_gap_seconds": self.coverage_gap_seconds,
            "frame_resize_width": self.frame_resize_width,
            "frame_resize_height": self.frame_resize_height,
            "max_analysis_frames": self.max_analysis_frames,
            "min_final_selection": self.min_final_selection,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SelectorConfig":
        return cls(**{key: value for key, value in data.items() if hasattr(cls, key)})

coverage.py

from __future__ import annotations

from typing import Iterable

from .frame import FrameMetrics


def find_large_gaps(selected_frames: Iterable[FrameMetrics], gap_threshold: float) -> list[str]:
    ordered = sorted(selected_frames, key=lambda item: item.timestamp)
    gaps: list[str] = []
    for prev, curr in zip(ordered, ordered[1:]):
        delta = curr.timestamp - prev.timestamp
        if delta > gap_threshold:
            gaps.append(
                f"Large frame-selection gap detected between {prev.timestamp:.2f}s and {curr.timestamp:.2f}s."
            )
    return gaps

exposure_detector.py

from __future__ import annotations

import numpy as np


def analyze_exposure(frame: np.ndarray) -> tuple[float, float, float, str]:
    gray = frame.mean(axis=2)
    brightness = float(gray.mean())
    dark_ratio = float(np.mean(gray < 30))
    bright_ratio = float(np.mean(gray > 245))

    if brightness < 70 and dark_ratio > 0.3:
        label = "too_dark"
    elif brightness > 180 and bright_ratio > 0.2:
        label = "too_bright"
    else:
        label = "good"

    return brightness, dark_ratio, bright_ratio, label

frame_selector.py

from __future__ import annotations

import csv
import json
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

import cv2

from .blur_detector import classify_blur, variance_of_laplacian
from .config import SelectorConfig
from .coverage import find_large_gaps
from .exposure_detector import analyze_exposure
from .frame import FrameMetrics
from .scoring import compute_frame_score
from .similarity import compute_similarity
from .video_reader import get_video_metadata, iter_frames

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


def _resolve_output_dirs(output_root: Path | None) -> tuple[Path, Path, Path, Path, Path]:
    output_dir = Path(output_root) if output_root is not None else OUTPUT_DIR
    selected_dir = output_dir / "selected_frames" if output_root is not None else SELECTED_DIR
    rejected_dir = output_dir / "rejected_frames" if output_root is not None else REJECTED_DIR
    colmap_dir = output_dir / "colmap_input" if output_root is not None else COLMAP_DIR
    colmap_images_dir = colmap_dir / "images" if output_root is not None else COLMAP_IMAGES_DIR
    return output_dir, selected_dir, rejected_dir, colmap_dir, colmap_images_dir


def select_frames(
    video_path: str | Path,
    config: SelectorConfig | None = None,
    job_id: str | None = None,
    progress_callback: Callable | None = None,
    output_root: Path | None = None,
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

    output_dir, selected_dir, rejected_dir, colmap_dir, colmap_images_dir = _resolve_output_dirs(output_root)
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
        (colmap_dir / "frames.json").write_text(json.dumps(export_payload, indent=2))

    result = {
        "job_id": export_id,
        "output_dir": str(output_dir),
        "colmap_dir": str(colmap_dir),
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

frame.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FrameMetrics:
    frame_index: int
    timestamp: float
    sharpness: float = 0.0
    brightness: float = 0.0
    dark_ratio: float = 0.0
    bright_ratio: float = 0.0
    similarity: float = 1.0
    status: str = "pending"
    reason: str = ""
    final_score: float = 0.0
    sharpness_score: float = 0.0
    exposure_score: float = 0.0
    viewpoint_change_score: float = 0.0
    redundancy_score: float = 0.0
    quality_label: str = "unknown"
    exposure_label: str = "unknown"
    selected: bool = False
    in_window: int = 0
    image: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "timestamp": round(self.timestamp, 6),
            "sharpness": round(self.sharpness, 3),
            "brightness": round(self.brightness, 3),
            "dark_ratio": round(self.dark_ratio, 4),
            "bright_ratio": round(self.bright_ratio, 4),
            "similarity": round(self.similarity, 4),
            "status": self.status,
            "reason": self.reason,
            "final_score": round(self.final_score, 4),
            "sharpness_score": round(self.sharpness_score, 4),
            "exposure_score": round(self.exposure_score, 4),
            "viewpoint_change_score": round(self.viewpoint_change_score, 4),
            "redundancy_score": round(self.redundancy_score, 4),
            "quality_label": self.quality_label,
            "exposure_label": self.exposure_label,
            "selected": self.selected,
            "in_window": self.in_window,
            "metadata": self.metadata,
        }

scoring.py

from __future__ import annotations

from .config import SelectorConfig
from .frame import FrameMetrics


def compute_frame_score(frame: FrameMetrics, config: SelectorConfig) -> float:
    sharpness_score = min(1.0, frame.sharpness / max(config.blur_threshold * 1.5, 1.0))
    brightness_score = 1.0 - min(1.0, abs(frame.brightness - 128.0) / 128.0)
    exposure_score = 1.0 if frame.exposure_label == "good" else 0.15
    viewpoint_score = max(0.0, frame.viewpoint_change_score)
    redundancy_penalty = max(0.0, frame.redundancy_score)
    score = (
        sharpness_score * 0.45
        + brightness_score * 0.20
        + exposure_score * 0.25
        + viewpoint_score * 0.25
        - redundancy_penalty * 0.35
    )
    return max(0.0, min(1.0, score))


similarity.py

from __future__ import annotations

import cv2
import numpy as np


def prepare_similarity_frame(frame: np.ndarray, max_size: tuple[int, int] = (64, 64)) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, max_size, interpolation=cv2.INTER_AREA)
    return resized.astype(np.float32)


def compute_similarity(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    a = prepare_similarity_frame(frame_a)
    b = prepare_similarity_frame(frame_b)
    diff = np.abs(a - b)
    normalized = 1.0 - (diff.mean() / 255.0)
    return float(np.clip(normalized, 0.0, 1.0))


def perceptual_hash(frame: np.ndarray, hash_size: int = 8) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(resized.astype(np.float32))
    low = dct[:hash_size, :hash_size]
    mean = float(low.mean())
    bits = (low > mean).astype(np.uint8).reshape(-1)
    return bits


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


def iter_frames(video_path: str | Path, max_frames: int | None = None):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Unable to open video file: {video_path}")

    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        timestamp = frame_index / (cap.get(cv2.CAP_PROP_FPS) or 1.0)
        yield frame_index, timestamp, frame
        frame_index += 1
        if max_frames is not None and frame_index >= max_frames:
            break

    cap.release()
