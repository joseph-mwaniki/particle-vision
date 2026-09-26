# Remote View

Deployment-ready monorepo for 3D Gaussian Splatting reconstruction and browser viewing.

## Project Structure

```
remote-view/
├── frontend/          # Vite + TypeScript + gsplat.js viewer
├── backend/           # Express REST API + job orchestration
├── gpu-worker/        # RunPod-ready Python worker (placeholder pipeline)
├── gsplat/            # Vendored gsplat training library (CUDA)
├── gsplat.js/         # Vendored gsplat.js viewer library (WebGL)
└── docs/              # Architecture, API, dependencies, deployment
```

## Quick Start

### Prerequisites

| Software | Version |
|----------|---------|
| Node.js | >= 20.0.0 |
| Python | 3.10 (GPU worker) |
| Docker | Optional (GPU worker) |

See [docs/dependencies.md](docs/dependencies.md) for verified CUDA/PyTorch/gsplat versions.

### 1. Backend

```bash
cd backend
cp .env.example .env
npm install
npm run dev
# → http://localhost:3001
```

### 2. GPU Worker (optional — backend falls back to mock worker)

```bash
cd gpu-worker
python handler.py
# → http://localhost:8080
```

Or with Docker:

```bash
cd gpu-worker
docker build -t remote-view-worker .
docker run -p 8080:8080 remote-view-worker
```

Set `USE_MOCK_WORKER=false` and `GPU_WORKER_URL=http://localhost:8080` in `backend/.env`.

### 3. Frontend

```bash
cd frontend
npm install
npm run download-sample   # downloads sample .splat for local viewer testing
npm run dev
# → http://localhost:5173
```

> The frontend uses the published `gsplat` npm package (1.2.9). The vendored `gsplat.js/` directory is available for customization. To use the local copy, build it with Emscripten and set `"gsplat": "file:../gsplat.js"` in `frontend/package.json`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/upload-session` | Create a direct-to-R2 multipart upload session |
| `POST` | `/train` | Start training for a job |
| `GET` | `/job/:id` | Get job status |
| `GET` | `/job` | List all jobs |

Full contract: [docs/api-contract.md](docs/api-contract.md)

## Integration Flow

```
Browser ──multipart PUT──► R2 ──object keys──► Backend ──job + signed URLs──► GPU Worker
Browser ◄──signed/public R2 URL── R2 ◄──direct PUT── GPU Worker
Frontend ◄──status + keys── Backend ◄──metadata callback── GPU Worker
```

## What's Implemented

- Frontend ↔ Backend REST communication
- Backend ↔ GPU Worker HTTP contract with callbacks
- Browser-to-R2 multipart source uploads and worker-to-R2 output uploads
- Postgres metadata and stable object-key references; temporary worker-only processing files
- Direct signed/public R2 asset delivery to the viewer
- Placeholder reconstruction pipeline (all stages raise `NotImplementedError`)
- gsplat.js viewer with local sample `.splat` loading
- Collision mesh architecture (interfaces only)
- Local JSON metadata fallback for development only; production requires Postgres

## What's NOT Implemented

- GPU training, COLMAP execution
- Payment, authentication, user management
- Background queues
- Cloud deployment automation

## Documentation

- [Architecture](docs/architecture.md)
- [API Contract](docs/api-contract.md)
- [Dependencies](docs/dependencies.md)
- [Local Development](docs/local-development.md)
- [RunPod Deployment](docs/runpod-deployment.md)
- [frontend/README.md](frontend/README.md)
- [backend/README.md](backend/README.md)
- [gpu-worker/README.md](gpu-worker/README.md)

## Future RunPod Deployment

See [docs/runpod-deployment.md](docs/runpod-deployment.md) for the planned deployment process. The GPU worker `handler.py` already implements the RunPod serverless entry point pattern.
