from __future__ import annotations

import json

import cv2
import numpy as np
from pathlib import Path

from backend.processing.config import SelectorConfig
from backend.processing.config import SelectorConfig
from backend.processing import frame_selector
from backend.processing.frame_selector import evaluate_temporal_bridge, select_frames
from backend.processing.video_reader import get_video_metadata


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


def _use_temporary_output(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    colmap_dir = output_dir / "colmap_input"
    monkeypatch.setattr(frame_selector, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(frame_selector, "SELECTED_DIR", output_dir / "selected_frames")
    monkeypatch.setattr(frame_selector, "REJECTED_DIR", output_dir / "rejected_frames")
    monkeypatch.setattr(frame_selector, "COLMAP_DIR", colmap_dir)
    monkeypatch.setattr(frame_selector, "COLMAP_IMAGES_DIR", colmap_dir / "images")


def test_video_metadata_reads_file(tmp_path):
    video = tmp_path / "sample.mp4"
    _write_test_video(video, fps=10, seconds=1)
    metadata = get_video_metadata(video)
    assert metadata["frame_count"] == 10
    assert metadata["fps"] == 10
    assert metadata["width"] == 160
    assert metadata["height"] == 120


def test_selector_returns_selected_frames(tmp_path, monkeypatch):
    _use_temporary_output(tmp_path, monkeypatch)
    video = tmp_path / "room_walk.mp4"
    _write_test_video(video, fps=10, seconds=2)
    progress_updates = []
    result = select_frames(
        video,
        config=SelectorConfig(window_seconds=1.0, min_frames_per_window=1, max_frames_per_window=4, blur_threshold=50, similarity_threshold=0.9),
        progress_callback=lambda progress, message, updates: progress_updates.append((progress, message, updates)),
    )
    assert result["selected_count"] > 0
    assert result["stats"]["selected_frames"] == result["selected_count"]
    assert len(result["selected_frames"]) >= 1
    assert any("Analyzing frame" in message for _, message, _ in progress_updates)
    assert any("Filtering frames" in message for _, message, _ in progress_updates)
    assert any("Saving selected frames" in message for _, message, _ in progress_updates)
    selected_update = next(updates for _, message, updates in progress_updates if "Saving selected frames" in message)
    assert selected_update["selected_frames"]


def test_multiple_video_exports_are_combined(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    colmap_dir = output_dir / "colmap_input"
    _use_temporary_output(tmp_path, monkeypatch)

    first_video = tmp_path / "first.mp4"
    second_video = tmp_path / "second.mp4"
    _write_test_video(first_video, fps=10, seconds=1)
    _write_test_video(second_video, fps=10, seconds=1)
    config = SelectorConfig(window_seconds=1.0, min_frames_per_window=1, max_frames_per_window=4)

    first = frame_selector.select_frames(first_video, config=config, job_id="first-job")
    second = frame_selector.select_frames(second_video, config=config, job_id="second-job")

    manifest = json.loads((output_dir / "frames.json").read_text())
    assert {video["job_id"] for video in manifest["videos"]} == {"first-job", "second-job"}
    assert len(manifest["selected_frames"]) == first["selected_count"] + second["selected_count"]
    assert all((output_dir / "selected_frames" / frame["output_file"]).exists() for frame in manifest["selected_frames"])
    assert len(list((colmap_dir / "images").glob("*.jpg"))) == len(manifest["selected_frames"])


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
