# Backend API

Express/TypeScript REST API for job upload, training dispatch, and status tracking.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health check |
| `POST` | `/api/upload-session` | Create a multi-ZIP direct-to-S3/R2 upload session |
| `POST` | `/api/upload-session/:id/file` | Initialize one ZIP multipart upload and return presigned part URLs |
| `POST` | `/api/upload-session/:id/file/:fileId/complete` | Complete one ZIP multipart upload |
| `POST` | `/api/upload-session/:id/complete` | Create a job from completed R2 objects |
| `GET` | `/api/upload-session/:id` | Read upload and job status |
| `POST` | `/api/upload-session/:id/abort` | Abort the session and clean up source objects |
| `POST` | `/train` | Start training (`{ "jobId": "job_abc123" }`) |
| `GET` | `/job/:id` | Get job by ID |
| `GET` | `/job` | List all jobs |
| `POST` | `/internal/worker/callback` | GPU worker status callback (internal) |

## Installation

```bash
npm install
cp .env.example .env
npm run dev
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3001` | HTTP server port |
| `GPU_WORKER_URL` | `http://localhost:8080` | GPU worker endpoint |
| `BACKEND_PUBLIC_URL` | `http://localhost:3001` | Public URL for worker callbacks |
| `USE_MOCK_WORKER` | `true` | Use built-in mock worker when GPU worker unavailable |
| `S3_ENDPOINT` | — | AWS S3 or Cloudflare R2 S3 API endpoint |
| `S3_REGION` | `auto` | S3 region (`auto` for R2) |
| `S3_ACCESS_KEY_ID` | — | Server-only S3/R2 access key |
| `S3_SECRET_ACCESS_KEY` | — | Server-only S3/R2 secret |
| `S3_BUCKET` | — | Bucket used for source archives and generated assets |
| `S3_UPLOAD_PART_SIZE` | `67108864` | Multipart part size in bytes |
| `S3_PRESIGN_EXPIRES_SECONDS` | `900` | Lifetime of browser multipart-part URLs |
| `S3_DOWNLOAD_EXPIRES_SECONDS` | `43200` | Lifetime of signed worker and private viewer URLs |
| `S3_PUBLIC_URL_PREFIX` | — | Optional public R2 delivery prefix for published public splats |

## Job Lifecycle

```
PENDING → QUEUED → PROCESSING_COLMAP → PROCESSING_GSPLAT
       → PROCESSING_COLLISION → PROCESSING_EXPORT → COMPLETED | FAILED
```

## Storage

Upload sessions and object keys are stored in PostgreSQL. The browser uploads ZIP parts directly to R2 with presigned multipart URLs; completion records metadata only and creates a job linked to the session. The worker downloads each source ZIP directly from R2 to temporary `WORK_DIR`, processes it locally, and uploads generated assets directly to R2 with presigned PUT URLs. Vercel handles metadata and signed-URL generation only. Configure bucket CORS for the frontend origin, allow browser `PUT`, `GET`, and `HEAD`, and expose `ETag`, `Content-Length`, and `Accept-Ranges` response headers.

`Job.splatPath` and `Job.collisionPath` store R2 object keys, not filesystem paths. API responses include `splatUrl` and `collisionUrl`: published public splats use `S3_PUBLIC_URL_PREFIX` when configured; other R2 assets use short-lived signed URLs.

## Build

```bash
npm run build
npm start
```

## Worker Communication

The backend dispatches training via `POST {GPU_WORKER_URL}/run` and receives progress via `POST /internal/worker/callback`. See [docs/api-contract.md](../docs/api-contract.md).
