import { WorkerCallbackPayload, WorkerRunRequest, WorkerRunResponse } from "../types/job";

const GPU_WORKER_URL = process.env.GPU_WORKER_URL || "http://localhost:8080";
const USE_MOCK_WORKER = process.env.USE_MOCK_WORKER !== "false";

export async function dispatchTrainingJob(
  request: WorkerRunRequest
): Promise<WorkerRunResponse> {
  if (USE_MOCK_WORKER) {
    return runMockWorker(request);
  }

  try {
    const response = await fetch(`${GPU_WORKER_URL}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Worker rejected job: ${response.status} ${text}`);
    }

    return (await response.json()) as WorkerRunResponse;
  } catch (err) {
    console.warn("GPU worker unavailable, falling back to mock worker:", err);
    return runMockWorker(request);
  }
}

async function runMockWorker(request: WorkerRunRequest): Promise<WorkerRunResponse> {
  // Simulate async worker processing with callbacks
  simulateMockPipeline(request).catch((err) => {
    console.error(`Mock worker error for ${request.job_id}:`, err);
  });

  return {
    job_id: request.job_id,
    status: "accepted",
    message: "Mock worker accepted job (GPU worker not available)",
  };
}

async function simulateMockPipeline(request: WorkerRunRequest): Promise<void> {
  const callbackUrl = request.callback_url;
  const jobId = request.job_id;

  const sendCallback = async (payload: WorkerCallbackPayload) => {
    await fetch(callbackUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  };

  const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

  await sendCallback({
    job_id: jobId,
    status: "QUEUED",
    progress: 0,
    log: "Job queued on mock GPU worker",
  });

  await delay(800);
  await sendCallback({
    job_id: jobId,
    status: "PROCESSING_COLMAP",
    progress: 10,
    log: "[COLMAP:extract_features] Feature extraction",
  });

  await delay(1000);
  await sendCallback({
    job_id: jobId,
    status: "PROCESSING_COLMAP",
    progress: 18,
    log: "[COLMAP:match_features] Exhaustive feature matching",
  });

  await delay(1000);
  await sendCallback({
    job_id: jobId,
    status: "PROCESSING_COLMAP",
    progress: 25,
    log: "[COLMAP:sparse_reconstruction] Sparse mapper (SfM)",
  });

  await delay(800);
  await sendCallback({
    job_id: jobId,
    status: "PROCESSING_COLMAP",
    progress: 30,
    log: "[COLMAP:undistort] Sparse reconstruction ready",
  });

  await delay(1000);
  await sendCallback({
    job_id: jobId,
    status: "PROCESSING_GSPLAT",
    progress: 40,
    log: "[gsplat] Placeholder: training 3D Gaussians (not implemented)",
  });

  await delay(1200);
  await sendCallback({
    job_id: jobId,
    status: "PROCESSING_COLLISION",
    progress: 70,
    log: "[collision] Placeholder: mesh generation (not implemented)",
  });

  await delay(800);
  await sendCallback({
    job_id: jobId,
    status: "PROCESSING_EXPORT",
    progress: 90,
    log: "[export] Placeholder: converting to .splat format (not implemented)",
  });

  // Use sample splat from HuggingFace as placeholder output
  const splatPath = `/uploads/jobs/${jobId}/output/scene.splat`;
  const collisionPath = `/uploads/jobs/${jobId}/output/collision.glb`;

  await sendCallback({
    job_id: jobId,
    status: "COMPLETED",
    progress: 100,
    log: "[complete] Mock pipeline finished. Sample assets referenced (no real training).",
    splat_path: splatPath,
    collision_path: collisionPath,
  });
}
