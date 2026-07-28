# Backend API

Express/TypeScript REST API for job upload, training dispatch, and status tracking.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health check |
| `POST` | `/upload` | Upload image ZIP (`multipart/form-data`, field `images`) |
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

## Job Lifecycle

```
PENDING → QUEUED → PROCESSING_COLMAP → PROCESSING_GSPLAT
       → PROCESSING_COLLISION → PROCESSING_EXPORT → COMPLETED | FAILED
```

## Storage

Jobs are persisted in `jobs.json` (no production database). Uploaded files are stored in `uploads/`.

## Build

```bash
npm run build
npm start
```

## Worker Communication

The backend dispatches training via `POST {GPU_WORKER_URL}/run` and receives progress via `POST /internal/worker/callback`. See [docs/api-contract.md](../docs/api-contract.md).
