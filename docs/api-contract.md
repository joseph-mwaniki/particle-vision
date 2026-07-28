# API Contract

## Public API (Backend)

Base URL: `http://localhost:3001` (dev) or your deployed backend URL.

### GET /health

Health check.

**Response `200`:**
```json
{
  "status": "ok",
  "service": "remote-view-backend",
  "timestamp": "2026-07-15T12:00:00.000Z"
}
```

### POST /upload

Upload a ZIP file containing images.

**Request:** `multipart/form-data`
- Field: `images` (file, `.zip` only, max 500 MB)

**Response `201`:**
```json
{
  "id": "job_abc123def",
  "status": "PENDING",
  "progress": 0,
  "createdAt": "2026-07-15T12:00:00.000Z",
  "updatedAt": "2026-07-15T12:00:00.000Z",
  "imagesPath": "uploads/1234567890-photos.zip",
  "splatPath": null,
  "collisionPath": null,
  "logs": "[2026-07-15T12:00:00.000Z] Job created. Upload complete. Ready to train."
}
```

**Errors:**
- `400` — No file, wrong format
- `500` — Server error

### POST /train

Start training for a pending job.

**Request:** `application/json`
```json
{
  "jobId": "job_abc123def"
}
```

**Response `202`:**
```json
{
  "message": "Training request accepted",
  "jobId": "job_abc123def"
}
```

**Errors:**
- `400` — Invalid jobId, job not in trainable state
- `404` — Job not found
- `500` — Server error

### GET /job/:id

Get job status.

**Response `200`:** Job object (same shape as upload response).

**Errors:**
- `404` — Job not found

### GET /job

List all jobs (newest first).

**Response `200`:** Array of Job objects.

---

## Worker API (GPU Worker)

Base URL: `http://localhost:8080` (dev) or RunPod endpoint.

### GET /health

**Response `200`:**
```json
{
  "status": "ok",
  "service": "gpu-worker"
}
```

### POST /run

Accept a training job.

**Request:** `application/json`
```json
{
  "job_id": "job_abc123def",
  "images_path": "/workspace/data/uploads/1234567890-photos.zip",
  "callback_url": "http://localhost:3001/internal/worker/callback"
}
```

**Response `202`:**
```json
{
  "job_id": "job_abc123def",
  "status": "accepted",
  "message": "Job accepted by GPU worker"
}
```

**Errors:**
- `400` — Missing fields, invalid JSON

---

## Internal Callback (Backend)

### POST /internal/worker/callback

GPU worker reports progress. Not called by frontend.

**Request:** `application/json`
```json
{
  "job_id": "job_abc123def",
  "status": "PROCESSING_GSPLAT",
  "progress": 40,
  "log": "[gsplat] Placeholder: optimization loop",
  "splat_path": "/uploads/jobs/job_abc123def/output/scene.splat",
  "collision_path": "/uploads/jobs/job_abc123def/output/collision.glb",
  "error": "optional error message on FAILED"
}
```

**Response `200`:**
```json
{
  "received": true
}
```

### Status Values

| Status | Description |
|--------|-------------|
| `PENDING` | Uploaded, awaiting training |
| `QUEUED` | Training dispatched |
| `PROCESSING_COLMAP` | COLMAP reconstruction |
| `PROCESSING_GSPLAT` | gsplat training |
| `PROCESSING_COLLISION` | Collision mesh generation |
| `PROCESSING_EXPORT` | Format conversion |
| `COMPLETED` | All outputs ready |
| `FAILED` | Pipeline error |

---

## Asset URLs

Completed jobs expose assets via static file serving:

| Asset | Path | Viewer |
|-------|------|--------|
| Splat scene | `/uploads/jobs/{id}/output/scene.splat` | Visible (gsplat.js) |
| Collision mesh | `/uploads/jobs/{id}/output/collision.glb` | Invisible (future) |

Frontend loads via: `{API_BASE}/uploads/jobs/{id}/output/scene.splat`

## RunPod Serverless

For RunPod deployment, `handler.py` exports `runpod_handler(event)` which accepts the same JSON as `POST /run`. See [runpod-deployment.md](runpod-deployment.md).
