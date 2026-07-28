# Local Development

## Prerequisites

- Node.js >= 20
- Python 3.10 (for GPU worker)
- Git

Optional: Docker (for GPU worker container)

## Setup

### 1. Clone and enter workspace

```bash
cd remote-view
```

### 2. Build gsplat.js (required for frontend)

```bash
cd gsplat.js
npm install
npm run build
cd ..
```

### 3. Start Backend

```bash
cd backend
cp .env.example .env
npm install
npm run dev
```

Verify: `curl http://localhost:3001/health`

### 4. Start GPU Worker (optional)

Without the GPU worker, the backend uses its built-in mock worker (`USE_MOCK_WORKER=true` by default).

```bash
cd gpu-worker
python handler.py
```

Verify: `curl http://localhost:8080/health`

To use the real worker process:
```bash
# In backend/.env
USE_MOCK_WORKER=false
GPU_WORKER_URL=http://localhost:8080
```

### 5. Start Frontend

```bash
cd frontend
npm install
npm run download-sample
npm run dev
```

Open http://localhost:5173

## Development Workflow

### Test the full flow

1. Open frontend at http://localhost:5173
2. Verify "Backend Online" status indicator
3. Click "Load Sample" to test gsplat.js viewer with local `.splat`
4. Upload a ZIP file (any ZIP for testing)
5. Click "Start Training" on the created job
6. Watch progress in logs panel (placeholder pipeline runs)
7. When complete, the viewer loads `scene.splat` from the backend

### API testing with curl

```bash
# Health
curl http://localhost:3001/health

# Upload
curl -X POST http://localhost:3001/upload \
  -F "images=@test-photos.zip"

# Train
curl -X POST http://localhost:3001/train \
  -H "Content-Type: application/json" \
  -d '{"jobId": "job_abc123"}'

# Job status
curl http://localhost:3001/job/job_abc123
```

### GPU Worker testing

```bash
curl -X POST http://localhost:8080/run \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "job_test123",
    "images_path": "/tmp/test.zip",
    "callback_url": "http://localhost:3001/internal/worker/callback"
  }'
```

## Build Commands

| Service | Dev | Build | Start |
|---------|-----|-------|-------|
| Frontend | `npm run dev` | `npm run build` | `npm run preview` |
| Backend | `npm run dev` | `npm run build` | `npm start` |
| GPU Worker | `python handler.py` | `docker build .` | `docker run` |
| gsplat.js | — | `npm run build` | — |

## Vite Proxy

The frontend dev server proxies `/api/*` to the backend:

```
http://localhost:5173/api/health → http://localhost:3001/health
http://localhost:5173/api/upload → http://localhost:3001/upload
```

Configured in `frontend/vite.config.js`.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Backend Offline | Ensure backend is running on port 3001 |
| gsplat import error | Build gsplat.js first: `cd gsplat.js && npm run build` |
| Sample splat not found | Run `npm run download-sample` in frontend |
| Worker callbacks fail | Check `BACKEND_PUBLIC_URL` in backend `.env` |
| CORS errors | Backend has CORS enabled; use Vite proxy in dev |

## Project Layout

```
frontend/     → Port 5173 (Vite dev server)
backend/      → Port 3001 (Express API)
gpu-worker/   → Port 8080 (Python HTTP)
gsplat.js/    → Library (no server)
gsplat/       → Python training lib (no server in integration layer)
```
