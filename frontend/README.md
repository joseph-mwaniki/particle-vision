# Frontend

Vite + TypeScript dashboard with gsplat.js 3D viewer.

## Features

- Upload image ZIP files via `POST /upload`
- Start training via `POST /train`
- Poll job status via `GET /job/:id`
- Load completed `scene.splat` from backend
- Load local sample `.splat` via "Load Sample" button
- Architecture ready for invisible `collision.glb` loading

## Installation

```bash
# Build gsplat.js library first (optional — frontend uses npm gsplat by default)
# cd ../gsplat.js && npm install && npm run build

# Install frontend
cd ../frontend
npm install
npm run download-sample
npm run dev
```

Open http://localhost:5173

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE` | `/api` | API base URL (proxied to backend in dev) |

## API Integration

All API calls are in `src/api.ts`:

```typescript
checkHealth()     // GET  /health
uploadImages()    // POST /upload
startTraining()   // POST /train
getJob(id)        // GET  /job/:id
listJobs()        // GET  /job
```

## Viewer Architecture

`src/viewer/viewer.ts` wraps gsplat.js:

- `loadSplat(url)` — loads `scene.splat` for rendering
- `loadCollisionMesh(url)` — placeholder for invisible `collision.glb` (future physics/navigation)

## Build

```bash
npm run build
npm run preview
```

## Sample Splat

Download the bundled sample:

```bash
npm run download-sample
```

This fetches `bonsai-7k-mini.splat` from HuggingFace into `public/samples/bonsai.splat`.
