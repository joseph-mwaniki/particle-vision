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

### Direct multipart upload to R2

The browser creates an upload session, requests presigned multipart-part URLs, uploads file chunks directly to R2, and posts only ETags and completion metadata to the backend. The backend records R2 object keys in `UploadFile`; it never receives the ZIP bytes. Session completion creates a job linked to those source-file records and does not assemble or copy ZIPs.

The existing endpoints are `POST /api/upload-session`, `POST /api/upload-session/:id/file`, `POST /api/upload-session/:id/file/:fileId/complete`, `POST /api/upload-session/:id/complete`, and `GET /api/upload-session/:id`.

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
  "source_files": [
    { "download_url": "<presigned R2 GET URL>", "original_name": "photos.zip" }
  ],
  "output_uploads": {
    "splat": { "key": "splats/job_abc123def/scene.splat", "url": "<presigned R2 PUT URL>" },
    "collision": { "key": "splats/job_abc123def/collision.glb", "url": "<presigned R2 PUT URL>" }
  },
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
  "splat_key": "splats/job_abc123def/scene.splat",
  "collision_key": "splats/job_abc123def/collision.glb",
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

Completed jobs store R2 object keys and API responses include a signed viewer URL (or the configured public delivery URL):

| Asset | Path | Viewer |
|-------|------|--------|
| Splat scene | `splats/{id}/scene.splat` | Visible (gsplat.js) |
| Collision mesh | `splats/{id}/collision.glb` | Invisible (future) |

The browser downloads binary assets from R2, not through the API. API responses keep the stable object key in `splatPath`/`collisionPath` and provide ephemeral `splatUrl`/`collisionUrl` fields for viewing.

## RunPod Serverless

For RunPod deployment, `handler.py` exports `runpod_handler(event)` which accepts the same JSON as `POST /run`. See [runpod-deployment.md](runpod-deployment.md).
