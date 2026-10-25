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
