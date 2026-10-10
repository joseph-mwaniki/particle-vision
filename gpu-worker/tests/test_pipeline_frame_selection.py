from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from pipeline.colmap import run_colmap
from pipeline.utils import extract_frames_from_video
from pipeline.frame_selection.config import SelectorConfig
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


def test_extract_frames_uses_real_algorithm_not_ffmpeg(tmp_path, monkeypatch):
    video = tmp_path / "walk.mp4"
    _write_test_video(video, fps=10, seconds=2)

    def fake_which(name):
        raise AssertionError(f"ffmpeg fallback should not run ({name})")

    monkeypatch.setattr("pipeline.utils.shutil.which", fake_which)

    logs: list[str] = []
    selected_dir = extract_frames_from_video(
        video,
        tmp_path / "job",
        on_log=logs.append,
        job_id="job_testframesel",
        config=SelectorConfig(window_seconds=1.0, min_frames_per_window=1, max_frames_per_window=4, max_rejected_preview=0),
    )

    selected = list(selected_dir.glob("*.jpg"))
    metadata = get_video_metadata(video)
    assert selected
    assert len(selected) < metadata["frame_count"] or metadata["frame_count"] <= 8
    assert selected_dir == tmp_path / "job" / "frame_selection" / "colmap_input" / "images"
    assert (tmp_path / "job" / "frame_selection" / "frame_selection.json").is_file()
    assert any("Selecting reconstruction frames" in line for line in logs)
    assert not any(p.suffix.lower() == ".mp4" for p in selected_dir.rglob("*"))


def test_extract_frames_fails_on_missing_video(tmp_path):
    missing = tmp_path / "missing.mp4"
    with pytest.raises(RuntimeError, match="missing or empty"):
        extract_frames_from_video(missing, tmp_path / "job")


def test_extract_frames_fails_when_decode_fails(tmp_path):
    bogus = tmp_path / "broken.mp4"
    bogus.write_bytes(b"not a video")
    with pytest.raises(RuntimeError, match="Video decoding failed"):
        extract_frames_from_video(bogus, tmp_path / "job")


def test_extract_frames_fails_when_no_frames_selected(tmp_path, monkeypatch):
    video = tmp_path / "walk.mp4"
    _write_test_video(video, fps=10, seconds=1)

    monkeypatch.setattr(
        "pipeline.utils.select_frames",
        lambda *args, **kwargs: {"selected_count": 0, "warnings": [], "stats": {"total_frames": 10}},
    )
    with pytest.raises(RuntimeError, match="no usable frames"):
        extract_frames_from_video(video, tmp_path / "job")


def test_colmap_copies_only_selected_images(tmp_path, monkeypatch):
    images = tmp_path / "frame_selection" / "colmap_input" / "images"
    images.mkdir(parents=True)
    (images / "keep_000001.jpg").write_bytes(b"jpeg")
    (images / "keep_000002.jpg").write_bytes(b"jpeg")
    (images / "frames.json").write_text("{}")
    source_video = tmp_path / "source-videos"
    source_video.mkdir()
    (source_video / "001-original.mp4").write_bytes(b"video")

    monkeypatch.setattr("pipeline.colmap.find_colmap_binary", lambda: "/usr/bin/colmap")
    commands: list[list[str]] = []

    def fake_run(cmd, on_log=None):
        commands.append(cmd)
        sparse = tmp_path / "colmap" / "sparse" / "0"
        sparse.mkdir(parents=True, exist_ok=True)
        (sparse / "cameras.bin").write_bytes(b"ok")

    monkeypatch.setattr("pipeline.colmap.run_command", fake_run)
    monkeypatch.setattr("pipeline.colmap._wrap_xvfb_if_needed", lambda cmd: cmd)

    result = run_colmap(images, tmp_path / "colmap")
    copied = sorted(p.name for p in (result / "images").iterdir() if p.is_file())
    assert copied == ["keep_000001.jpg", "keep_000002.jpg"]
    assert "frames.json" not in copied
    assert not any(name.endswith(".mp4") for name in copied)
    assert commands
    image_path_args = [cmd[cmd.index("--image_path") + 1] for cmd in commands if "--image_path" in cmd]
    assert image_path_args
    assert all(Path(path) == result / "images" for path in image_path_args)


def test_full_pipeline_does_not_start_colmap_before_selection(tmp_path, monkeypatch):
    import train as train_mod

    video = tmp_path / "source.mp4"
    _write_test_video(video, fps=10, seconds=1)
    work_root = tmp_path / "workspace"
    monkeypatch.setattr(train_mod, "WORK_DIR", work_root)

    order: list[str] = []

    def fake_download(job_id, source_files, on_log=None):
        job_dir = work_root / "jobs" / job_id
        source_dir = job_dir / "source-videos"
        source_dir.mkdir(parents=True)
        dest = source_dir / "001-source.mp4"
        dest.write_bytes(video.read_bytes())
        order.append("download")
        return job_dir, [dest]

    def fake_extract(video_path, dest_dir, on_log=None, job_id=None, config=None):
        order.append("select")
        images = dest_dir / "frame_selection" / "colmap_input" / "images"
        images.mkdir(parents=True)
        (images / "frame_000001.jpg").write_bytes(b"jpeg")
        return images

    def fake_colmap(images_dir, output_dir, zip_path=None, on_log=None, on_progress=None):
        order.append("colmap")
        assert images_dir.name == "images"
        assert "frame_selection" in str(images_dir)
        assert list(images_dir.glob("*.jpg"))
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "images").mkdir(exist_ok=True)
        for src in images_dir.glob("*.jpg"):
            (output_dir / "images" / src.name).write_bytes(src.read_bytes())
        return output_dir

    monkeypatch.setattr(train_mod, "_download_source_archives", fake_download)
    monkeypatch.setattr(train_mod, "extract_frames_from_video", fake_extract)
    monkeypatch.setattr(train_mod, "run_colmap", fake_colmap)
    monkeypatch.setattr(train_mod, "train_gsplat", lambda *args, **kwargs: tmp_path / "model.ply")
    monkeypatch.setattr(train_mod, "generate_collision_mesh", lambda *args, **kwargs: tmp_path / "collision.glb")
    monkeypatch.setattr(train_mod, "convert_to_splat", lambda *args, **kwargs: tmp_path / "scene.splat")
    monkeypatch.setattr(
        train_mod,
        "upload_results",
        lambda *args, **kwargs: {"splat_key": "splats/job_abc123/scene.splat", "collision_key": "splats/job_abc123/collision.glb"},
    )

    statuses: list[str] = []
    train_mod.run_full_pipeline(
        "job_abc123",
        [{"download_url": "https://example.invalid/video.mp4", "original_name": "source.mp4"}],
        {
            "splat": {"key": "splats/job_abc123/scene.splat", "url": "https://example.invalid/put-splat"},
            "collision": {"key": "splats/job_abc123/collision.glb", "url": "https://example.invalid/put-collision"},
        },
        lambda status, log_msg, progress, **kwargs: statuses.append(status),
    )

    assert order == ["download", "select", "colmap"]
    assert statuses[0] == "QUEUED"
    assert "PROCESSING_FRAME_SELECTION" in statuses
    frame_idx = statuses.index("PROCESSING_FRAME_SELECTION")
    colmap_idx = statuses.index("PROCESSING_COLMAP")
    assert frame_idx < colmap_idx


def test_full_pipeline_propagates_selection_failure(tmp_path, monkeypatch):
    import train as train_mod

    monkeypatch.setattr(train_mod, "WORK_DIR", tmp_path / "workspace")

    def fake_download(job_id, source_files, on_log=None):
        job_dir = tmp_path / "workspace" / "jobs" / job_id
        source_dir = job_dir / "source-videos"
        source_dir.mkdir(parents=True)
        dest = source_dir / "001-source.mp4"
        dest.write_bytes(b"video")
        return job_dir, [dest]

    def fake_extract(*args, **kwargs):
        raise RuntimeError("Frame selection produced no usable frames for reconstruction")

    monkeypatch.setattr(train_mod, "_download_source_archives", fake_download)
    monkeypatch.setattr(train_mod, "extract_frames_from_video", fake_extract)
    monkeypatch.setattr(train_mod, "run_colmap", MagicMock(side_effect=AssertionError("COLMAP must not start")))

    with pytest.raises(RuntimeError, match="no usable frames"):
        train_mod.run_full_pipeline(
            "job_abc123",
            [{"download_url": "https://example.invalid/video.mp4", "original_name": "source.mp4"}],
            {
                "splat": {"key": "k", "url": "u"},
                "collision": {"key": "k", "url": "u"},
            },
            lambda *args, **kwargs: None,
        )
