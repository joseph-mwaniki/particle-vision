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


def test_2000_frames_produces_approximately_400_candidates(monkeypatch):
    """Verify iter_frames decodes 400 candidate frames from a 2000-frame video with stride 5."""
    from pipeline.frame_selection.video_reader import iter_frames

    class MockVideoCapture:
        def __init__(self, *args, **kwargs):
            self.grab_count = 0
            self.read_count = 0

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == cv2.CAP_PROP_FPS:
                return 30.0
            return 0.0

        def grab(self):
            self.grab_count += 1
            return True

        def read(self):
            self.read_count += 1
            dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
            return True, dummy_frame

        def release(self):
            pass

    mock_cap = MockVideoCapture()
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args, **kwargs: mock_cap)

    candidates = list(iter_frames("mock_video.mp4", max_frames=2000, stride=5))

    assert len(candidates) == 400
    assert candidates[0][0] == 0
    assert candidates[0][1] == 0.0
    assert candidates[1][0] == 5
    assert candidates[-1][0] == 1995
    assert round(candidates[-1][1], 4) == round(1995 / 30.0, 4)
    assert mock_cap.grab_count == 1600
    assert mock_cap.read_count == 400


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


def test_single_frame_continuity_reported_as_not_verifiable(tmp_path):
    """When only 1 frame survives, continuity is not verifiable and continuity_guaranteed is False."""
    video = tmp_path / "single_frame.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video), fourcc, 10, (160, 120))
    writer.write(np.full((120, 160, 3), 120, dtype=np.uint8))
    writer.release()

    job_root = tmp_path / "job"
    cfg = SelectorConfig(
        sampling_stride=1,
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
    assert result["selected_count"] == 1
    assert result["stats"]["continuity_verifiable"] is False
    assert result["stats"]["continuity_guaranteed"] is False


def test_safety_net_added_tracked_separately(tmp_path):
    """Safety net frame additions must be recorded separately from continuity restoration."""
    video = tmp_path / "safety_test.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video), fourcc, 10, (160, 120))
    # Create 10 frames with progressive brightness
    for i in range(10):
        writer.write(np.full((120, 160, 3), 80 + i * 5, dtype=np.uint8))
    writer.release()

    job_root = tmp_path / "job"
    # min_final_selection=5 requires the safety net to add frames if similarity drops them
    cfg = SelectorConfig(
        sampling_stride=1,
        similarity_threshold=0.5,
        min_final_selection=5,
        adaptive_blur=False,
    )
    result = select_frames(
        video,
        config=cfg,
        output_root=job_root / "frame_selection",
        colmap_images_dir=job_root / "colmap" / "images",
    )
    stats = result["stats"]
    assert "safety_net_added_count" in stats
    assert "safety_net_frames" in stats
    assert isinstance(stats["safety_net_added_count"], int)
    assert stats["decoded_frames"] >= stats["selected_frames"]
    assert stats["quality_analyzed_frames"] == stats["decoded_frames"]


def test_process_frame_chunk_seek_mismatch_raises(tmp_path, monkeypatch):
    """When VideoCapture seek lands on the wrong frame, _process_frame_chunk raises RuntimeError."""
    from pipeline.frame_selection.frame_selector import _process_frame_chunk

    class MismatchedSeekCap:
        def isOpened(self):
            return True

        def set(self, prop, val):
            pass

        def get(self, prop):
            if prop == cv2.CAP_PROP_POS_FRAMES:
                # Land 5 frames off from requested start_frame
                return 15.0
            if prop == cv2.CAP_PROP_FPS:
                return 30.0
            return 0.0

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", lambda *args, **kwargs: MismatchedSeekCap())

    import pytest
    with pytest.raises(RuntimeError, match="VideoCapture seek mismatch"):
        _process_frame_chunk(("dummy.mp4", 25, 10, str(tmp_path), 90, 5))
