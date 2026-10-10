from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from backend.processing.frame_selector import select_frames

ROOT = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = ROOT / "uploads"
OUTPUT_DIR = ROOT / "output"

JOB_STORE: dict[str, dict[str, Any]] = {}


def _job_snapshot(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "filename": job.get("filename"),
        "uploaded_at": job.get("uploaded_at"),
        "progress": job.get("progress", 0),
        "message": job.get("message", "Waiting"),
        "stats": job.get("stats", {}),
        "warnings": job.get("warnings", []),
        "selected_count": job.get("selected_count", 0),
        "output_dir": str(job.get("output_dir", OUTPUT_DIR)),
        "selected_frames": job.get("selected_frames", []),
        "rejected_preview": job.get("rejected_preview", []),
    }


async def upload_video(file: UploadFile) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    filename = file.filename or "upload.mp4"
    file_path = UPLOAD_DIR / f"{job_id}_{Path(filename).name}"
    content = await file.read()
    file_path.write_bytes(content)

    job = {
        "job_id": job_id,
        "status": "uploaded",
        "filename": filename,
        "path": str(file_path),
        "uploaded_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "progress": 0,
        "message": "Uploaded and ready to analyze",
        "stats": {},
        "warnings": [],
        "output_dir": str(OUTPUT_DIR),
    }
    JOB_STORE[job_id] = job
    return {"job_id": job_id, "filename": filename, "status": "uploaded"}


def analyze_video_job(job_id: str) -> dict[str, Any]:
    job = JOB_STORE.get(job_id)
    if job is None:
        return {"error": "Job not found"}
    if job["status"] == "processing":
        return _job_snapshot(job)

    job["status"] = "processing"
    job["message"] = "Starting video analysis"
    job["progress"] = 5

    thread = threading.Thread(target=_run_analysis, args=(job_id,), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "processing"}


def _run_analysis(job_id: str) -> None:
    job = JOB_STORE.get(job_id)
    if job is None:
        return

    try:
        result = select_frames(
            job["path"],
            job_id=job_id,
            progress_callback=lambda progress, message, updates: _update_job(job_id, progress, message, updates),
        )
        job["status"] = "completed"
        job["progress"] = 100
        job["message"] = "Analysis complete"
        job["stats"] = result["stats"]
        job["warnings"] = result.get("warnings", [])
        job["selected_count"] = result["selected_count"]
        job["output_dir"] = result["output_dir"]
        job["selected_frames"] = result.get("selected_frames", [])
        job["rejected_preview"] = result.get("rejected_preview", [])
        job["result"] = result
    except Exception as exc:  # pragma: no cover - failure path
        job["status"] = "failed"
        job["progress"] = 100
        job["message"] = f"Analysis failed: {exc}"
        job["warnings"] = [str(exc)]


def _update_job(job_id: str, progress: int, message: str, updates: dict[str, Any] | None = None) -> None:
    job = JOB_STORE.get(job_id)
    if job is None:
        return
    job["progress"] = max(0, min(100, progress))
    job["message"] = message
    if updates:
        job.update(updates)


def get_job_status(job_id: str) -> dict[str, Any] | None:
    job = JOB_STORE.get(job_id)
    if job is None:
        return None
    return _job_snapshot(job)


def list_jobs() -> list[dict[str, Any]]:
    return [_job_snapshot(job) for job in JOB_STORE.values()]
