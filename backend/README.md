# Backend API

Express/TypeScript REST API for job upload, training dispatch, and status tracking.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health check |
| `POST` | `/upload` | Upload image ZIP (`multipart/form-data`, field `images`) |
| `POST` | `/api/upload-session` | Create a multi-ZIP direct-to-S3/R2 upload session |
| `POST` | `/api/upload-session/:id/file` | Initialize one ZIP multipart upload and return presigned part URLs |
| `POST` | `/api/upload-session/:id/file/:fileId/complete` | Complete one ZIP multipart upload |
| `POST` | `/api/upload-session/:id/complete` | Assemble uploaded ZIPs and start processing |
| `GET` | `/api/upload-session/:id` | Read upload, assembly, and job status |
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
| `S3_BUCKET` | — | Bucket used for source and combined ZIPs |
| `S3_UPLOAD_PART_SIZE` | `67108864` | Multipart part size in bytes |

## Job Lifecycle

```
PENDING → QUEUED → PROCESSING_COLMAP → PROCESSING_GSPLAT
       → PROCESSING_COLLISION → PROCESSING_EXPORT → COMPLETED | FAILED
```

## Storage

Jobs are persisted in PostgreSQL when configured, with the existing JSON fallback for local development. Legacy uploads are stored in `uploads/`. The multi-ZIP flow uploads source archives directly from the browser to S3/R2, assembles image entries into `datasets/{sessionId}/combined.zip`, and sends the GPU worker a presigned GET URL. Configure bucket CORS to allow browser `PUT` requests and expose the `ETag` response header.

## Build

```bash
npm run build
npm start
```

## Worker Communication

The backend dispatches training via `POST {GPU_WORKER_URL}/run` and receives progress via `POST /internal/worker/callback`. See [docs/api-contract.md](../docs/api-contract.md).
