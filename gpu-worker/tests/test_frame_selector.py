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
