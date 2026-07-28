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
| `POST` | `/upload` | Upload image ZIP, create job |
| `POST` | `/train` | Start training for a job |
| `GET` | `/job/:id` | Get job status |
| `GET` | `/job` | List all jobs |

Full contract: [docs/api-contract.md](docs/api-contract.md)

## Integration Flow

```
Frontend ──POST /upload──► Backend ──POST /run──► GPU Worker
Frontend ◄──GET /job/:id── Backend ◄──callback── GPU Worker
Frontend ──loads──► scene.splat + collision.glb (future)
```

## What's Implemented

- Frontend ↔ Backend REST communication
- Backend ↔ GPU Worker HTTP contract with callbacks
- Placeholder reconstruction pipeline (all stages raise `NotImplementedError`)
- gsplat.js viewer with local sample `.splat` loading
- Collision mesh architecture (interfaces only)
- JSON file job storage (no production database)

## What's NOT Implemented

- GPU training, COLMAP execution
- Payment, authentication, user management
- Production database, background queues
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
