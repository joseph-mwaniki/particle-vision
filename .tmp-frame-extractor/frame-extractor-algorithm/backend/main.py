from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.jobs import analyze_video_job, get_job_status, list_jobs, upload_video
from backend.processing.config import SelectorConfig

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / "uploads"
OUTPUT_DIR = ROOT / "output"
FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="Gaussian Splat Frame Selector")

app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_video_endpoint(file: UploadFile = File(...)) -> dict[str, Any]:
    return await upload_video(file)


@app.post("/api/analyze/{job_id}")
def analyze_video_endpoint(job_id: str) -> dict[str, Any]:
    return analyze_video_job(job_id)


@app.post("/api/export-colmap/{job_id}")
def export_colmap_endpoint(job_id: str) -> dict[str, Any]:
    job = get_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] not in {"completed"}:
        raise HTTPException(status_code=409, detail="Job is not complete yet")
    return {
        "job_id": job_id,
        "colmap_dir": str(Path(job["output_dir"]) / "colmap_input"),
        "status": "ready",
    }


@app.get("/api/jobs/{job_id}")
def get_job_endpoint(job_id: str) -> dict[str, Any]:
    job = get_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs")
def list_jobs_endpoint() -> dict[str, Any]:
    return {"jobs": list_jobs()}


@app.get("/")
def read_index() -> FileResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend not built")
    return FileResponse(index_file)


@app.get("/config")
def get_config() -> dict[str, Any]:
    return SelectorConfig().to_dict()


@app.get("/api/pipeline-summary")
def get_pipeline_summary() -> dict[str, Any]:
    return {
        "pipeline": [
            "Video metadata read",
            "Frame extraction",
            "Blur detection",
            "Exposure analysis",
            "Temporal windows",
            "Redundancy filtering",
            "Coverage validation",
            "Export for COLMAP",
        ]
    }


for directory in (UPLOAD_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)
