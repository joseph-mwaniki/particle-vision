from __future__ import annotations

import json

import cv2
import numpy as np
from pathlib import Path

from backend.processing.config import SelectorConfig
from backend.processing import frame_selector
from backend.models.frame import FrameMetrics
from backend.processing.frame_selector import (
    enforce_continuity,
    evaluate_temporal_bridge,
    select_frames,
)
from backend.processing.video_reader import get_video_metadata, iter_frames


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
        config=SelectorConfig(
            window_seconds=1.0,
            min_frames_per_window=1,
            max_frames_per_window=4,
            blur_threshold=50,
            similarity_threshold=0.9,
            radical_uniform_sampling=False,
        ),
        progress_callback=lambda progress, message, updates: progress_updates.append((progress, message, updates)),
    )
    assert result["selected_count"] > 0
    assert result["stats"]["selected_frames"] == result["selected_count"]
    assert result["stats"]["analyzed_frames"] < result["stats"]["total_source_frames"]
    assert result["stats"]["sampling_stride"] == 2
    assert len(result["selected_frames"]) >= 1
    assert any("Analyzing frame" in message for _, message, _ in progress_updates)
    assert any("Filtering frames" in message for _, message, _ in progress_updates)
    assert any("Saving selected frames" in message for _, message, _ in progress_updates)
    selected_update = next(updates for _, message, updates in progress_updates if "Saving selected frames" in message)
    assert selected_update["selected_frames"]
    assert not list((tmp_path / "output" / "temp_frames").glob("*/*.jpg"))


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


def test_conservative_redundancy_requires_stronger_direct_overlap():
    config = SelectorConfig(
        similarity_threshold=0.88,
        bridge_overlap_threshold=0.55,
        conservative_redundancy=True,
    )

    status, _ = evaluate_temporal_bridge(0.96, 0.96, 0.80, "sharp", config)

    assert status == "KEEP"


def test_selector_config_includes_advanced_defaults_and_legacy_aliases():
    config = SelectorConfig.from_dict({
        "sample_stride": 3,
        "max_source_frame_gap": 15,
        "enforce_continuity": False,
        "experimental_uniform_sampling": True,
        "experimental_interval_seconds": 2.0,
        "experimental_start_seconds": 1.5,
        "radical_uniform_sampling": False,
        "radical_interval_seconds": 4.0,
        "radical_start_seconds": 2.0,
    })

    assert config.sampling_stride == 3
    assert config.max_frame_gap == 15
    assert config.continuity_aware is False
    config_dict = config.to_dict()
    assert config_dict["conservative_redundancy"] is True
    assert config_dict["experimental_uniform_sampling"] is True
    assert config_dict["experimental_interval_seconds"] == 2.0
    assert config_dict["experimental_start_seconds"] == 1.5
    assert config_dict["radical_uniform_sampling"] is False
    assert config_dict["radical_interval_seconds"] == 4.0
    assert config_dict["radical_start_seconds"] == 2.0


def test_radical_uniform_sampling_uses_three_second_gap_without_fallback(
    tmp_path, monkeypatch
):
    _use_temporary_output(tmp_path, monkeypatch)
    video = tmp_path / "radical.mp4"
    _write_test_video(video, fps=10, seconds=8)
    progress_updates = []

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Similarity or continuity logic should be bypassed")

    monkeypatch.setattr(frame_selector, "prepare_similarity_frame", fail_if_called)
    monkeypatch.setattr(frame_selector, "compute_similarity", fail_if_called)
    monkeypatch.setattr(frame_selector, "evaluate_temporal_bridge", fail_if_called)
    monkeypatch.setattr(frame_selector, "enforce_continuity", fail_if_called)
    monkeypatch.setattr(
        frame_selector, "analyze_exposure", lambda _frame: (100.0, 0.0, 0.0, "good")
    )

    result = select_frames(
        video,
        config=SelectorConfig(
            adaptive_blur=False,
            blur_threshold=0,
            min_final_selection=100,
            sampling_stride=5,
        ),
        progress_callback=lambda progress, message, updates: progress_updates.append(
            (progress, message, updates)
        ),
    )

    timestamps = [frame["timestamp"] for frame in result["selected_frames"]]
    filenames = [frame["output_file"] for frame in result["selected_frames"]]
    assert timestamps == [3.0, 6.0]
    assert result["selected_count"] == 2
    assert result["stats"]["selected_frames"] == 2
    assert result["stats"]["radical_uniform_sampling"] is True
    assert result["stats"]["sampling_stride"] == 5
    assert filenames == [
        f"{result['job_id'][:12]}_frame_000001.jpg",
        f"{result['job_id'][:12]}_frame_000002.jpg",
    ]
    assert all(
        (tmp_path / "output" / "colmap_input" / "images" / filename).is_file()
        for filename in filenames
    )
    assert any(
        message == "Applying radical 3s uniform downsampling"
        for _, message, _ in progress_updates
    )


def test_experimental_uniform_sampling_skips_similarity_and_continuity(
    tmp_path, monkeypatch
):
    _use_temporary_output(tmp_path, monkeypatch)
    video = tmp_path / "uniform.mp4"
    _write_test_video(video, fps=10, seconds=8)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Similarity or continuity logic should be bypassed")

    monkeypatch.setattr(frame_selector, "prepare_similarity_frame", fail_if_called)
    monkeypatch.setattr(frame_selector, "compute_similarity", fail_if_called)
    monkeypatch.setattr(frame_selector, "evaluate_temporal_bridge", fail_if_called)
    monkeypatch.setattr(frame_selector, "enforce_continuity", fail_if_called)
    monkeypatch.setattr(
        frame_selector, "analyze_exposure", lambda _frame: (100.0, 0.0, 0.0, "good")
    )

    result = select_frames(
        video,
        config=SelectorConfig(
            experimental_uniform_sampling=True,
            adaptive_blur=False,
            blur_threshold=0,
            radical_uniform_sampling=False,
        ),
    )

    timestamps = [frame["timestamp"] for frame in result["selected_frames"]]
    assert timestamps == [3.0, 5.5]
    assert result["selected_count"] == 2
    assert result["stats"]["selected_frames"] == 2
    assert result["stats"]["experimental_uniform_sampling"] is True
    assert "Experimental uniform sampling was used" in result["warnings"][0]
    assert all(
        abs(current - previous - 2.5) < 0.1
        for previous, current in zip(timestamps, timestamps[1:])
    )


def test_iter_frames_samples_source_indices_with_stride(monkeypatch):
    class MockVideoCapture:
        def __init__(self):
            self.grab_count = 0
            self.read_count = 0

        def isOpened(self):
            return True

        def get(self, prop):
            return 10.0 if prop == cv2.CAP_PROP_FPS else 0.0

        def grab(self):
            self.grab_count += 1
            return True

        def read(self):
            self.read_count += 1
            return True, np.zeros((10, 10, 3), dtype=np.uint8)

        def release(self):
            pass

    capture = MockVideoCapture()
    monkeypatch.setattr(cv2, "VideoCapture", lambda *_args, **_kwargs: capture)

    frames = list(iter_frames("mock.mp4", max_frames=20, stride=5))

    assert [frame[0] for frame in frames] == [0, 5, 10, 15]
    assert [frame[1] for frame in frames] == [0.0, 0.5, 1.0, 1.5]
    assert capture.read_count == 4
    assert capture.grab_count == 16


def test_continuity_restores_high_quality_frame_to_bridge_source_gap(tmp_path):
    image_path = tmp_path / "candidate.jpg"
    assert cv2.imwrite(str(image_path), np.full((32, 32, 3), 128, dtype=np.uint8))

    selected = [
        FrameMetrics(frame_index=index, timestamp=index / 10, image_path=str(image_path))
        for index in (100, 150)
    ]
    candidates = [
        FrameMetrics(
            frame_index=index,
            timestamp=index / 10,
            final_score=0.9 if index == 125 else 0.5,
            quality_label="sharp",
            exposure_label="good",
            image_path=str(image_path),
        )
        for index in (105, 110, 115, 120, 125, 130, 135, 140, 145)
    ]

    final_selection, restored, gaps = enforce_continuity(selected, candidates, 25)

    assert gaps == []
    assert [frame.frame_index for frame in final_selection] == [100, 125, 150]
    assert [frame.frame_index for frame in restored] == [125]


def test_continuity_does_not_restore_corrupt_candidate(tmp_path):
    corrupt_path = tmp_path / "corrupt.jpg"
    corrupt_path.write_bytes(b"not an image")
    selected = [
        FrameMetrics(frame_index=index, timestamp=index / 10)
        for index in (100, 150)
    ]
    candidate = FrameMetrics(
        frame_index=125,
        timestamp=12.5,
        exposure_label="good",
        image_path=str(corrupt_path),
    )

    final_selection, restored, gaps = enforce_continuity([*selected], [candidate], 25)

    assert len(final_selection) == 2
    assert restored == []
    assert len(gaps) == 1
