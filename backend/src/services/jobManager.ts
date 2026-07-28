import * as fs from "fs";
import * as path from "path";
import { appendJobLog, getJob, updateJob } from "../db";
import { dispatchTrainingJob } from "./workerClient";
import { WorkerCallbackPayload } from "../types/job";

const BACKEND_PUBLIC_URL = process.env.BACKEND_PUBLIC_URL || "http://localhost:3001";

function resolveOutputPaths(jobId: string, payload: WorkerCallbackPayload, uploadsDir: string) {
  const outputDir = path.join(uploadsDir, "jobs", jobId, "output");
  const splatRel = payload.splat_path || `/uploads/jobs/${jobId}/output/scene.splat`;
  const collisionRel = payload.collision_path || `/uploads/jobs/${jobId}/output/collision.glb`;
  const splatLocal = path.join(uploadsDir, splatRel.replace(/^\/uploads\/?/, ""));
  const collisionLocal = path.join(uploadsDir, collisionRel.replace(/^\/uploads\/?/, ""));
  return { outputDir, splatRel, collisionRel, splatLocal, collisionLocal };
}

export async function startTrainingJob(jobId: string, uploadsDir: string): Promise<void> {
  const job = await getJob(jobId);
  if (!job) {
    throw new Error("Job not found");
  }

  if (job.status !== "PENDING" && job.status !== "FAILED") {
    throw new Error(`Job cannot be trained in status: ${job.status}`);
  }

  await updateJob(jobId, {
    status: "QUEUED",
    progress: 0,
    logs: `${job.logs || ""}\n[${new Date().toISOString()}] Dispatching training request to GPU worker...`,
  });

  const callbackUrl = `${BACKEND_PUBLIC_URL}/internal/worker/callback`;
  const imagesPath = path.isAbsolute(job.imagesPath)
    ? job.imagesPath
    : path.join(uploadsDir, path.basename(job.imagesPath));

  await dispatchTrainingJob({
    job_id: jobId,
    images_path: imagesPath,
    callback_url: callbackUrl,
  });
}

export async function handleWorkerCallback(
  payload: WorkerCallbackPayload,
  uploadsDir: string
): Promise<void> {
  const job = await getJob(payload.job_id);
  if (!job) {
    throw new Error(`Job not found: ${payload.job_id}`);
  }

  if (payload.log) {
    await appendJobLog(payload.job_id, payload.log);
  }

  if (payload.status === "FAILED") {
    await updateJob(payload.job_id, {
      status: "FAILED",
      progress: payload.progress,
    });
    if (payload.error) {
      await appendJobLog(payload.job_id, `ERROR: ${payload.error}`);
    }
    return;
  }

  if (payload.status === "COMPLETED") {
    const { outputDir, splatRel, collisionRel, splatLocal, collisionLocal } = resolveOutputPaths(
      payload.job_id,
      payload,
      uploadsDir
    );
    fs.mkdirSync(outputDir, { recursive: true });

    const splatExists = fs.existsSync(splatLocal);
    const collisionExists = fs.existsSync(collisionLocal);

    if (!splatExists) {
      await appendJobLog(
        payload.job_id,
        `Warning: scene.splat not found at ${splatLocal}. Viewer may not load until assets are available.`
      );
    }
    if (!collisionExists) {
      await appendJobLog(
        payload.job_id,
        `Warning: collision.glb not found at ${collisionLocal}.`
      );
    }

    await updateJob(payload.job_id, {
      status: "COMPLETED",
      progress: 100,
      splatPath: splatExists ? splatRel : job.splatPath,
      collisionPath: collisionExists ? collisionRel : job.collisionPath,
    });
    return;
  }

  await updateJob(payload.job_id, {
    status: payload.status,
    progress: payload.progress,
  });
}
