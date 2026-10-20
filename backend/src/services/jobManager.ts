import { getJob, prisma, updateJob } from "../db";
import { headObject, presignDownload, presignObjectUpload } from "./objectStorage";
import { dispatchTrainingJob } from "./workerClient";
import { Job, WorkerCallbackPayload } from "../types/job";

const BACKEND_PUBLIC_URL = process.env.BACKEND_PUBLIC_URL || "http://localhost:3001";
const LOGS_MAX_BYTES = 32 * 1024;

function appendCappedLog(existing: string | null | undefined, message: string): string {
  const line = `[${new Date().toISOString()}] ${message}`;
  const combined = existing ? `${existing}\n${line}` : line;
  const byteLength = Buffer.byteLength(combined, "utf8");
  if (byteLength <= LOGS_MAX_BYTES) {
    return combined;
  }
  // Keep the trailing window; drop a partial leading line if we cut mid-line.
  const buf = Buffer.from(combined, "utf8");
  const sliced = buf.subarray(byteLength - LOGS_MAX_BYTES).toString("utf8");
  const firstNewline = sliced.indexOf("\n");
  return firstNewline >= 0 ? sliced.slice(firstNewline + 1) : sliced;
}

function shouldPersistLog(job: Job, payload: WorkerCallbackPayload): boolean {
  if (payload.status === "FAILED" || payload.status === "COMPLETED") {
    return true;
  }
  if (payload.error) {
    return true;
  }
  // Persist only when the job stage changes, not every progress tick.
  return payload.status !== job.status;
}

export async function startTrainingJob(jobId: string): Promise<void> {
  const job = await getJob(jobId);
  if (!job) {
    throw new Error("Job not found");
  }

  if (job.status !== "PENDING" && job.status !== "FAILED") {
    throw new Error(`Job cannot be trained in status: ${job.status}`);
  }

  const callbackUrl = `${BACKEND_PUBLIC_URL}/internal/worker/callback`;
  if (!prisma || !job.uploadSessionId) {
    throw new Error("Training requires a database-backed R2 upload session");
  }
  const sourceFiles = await prisma.uploadFile.findMany({
    where: { sessionId: job.uploadSessionId, status: "COMPLETE" },
    orderBy: { createdAt: "asc" },
    select: { objectKey: true, originalName: true },
  });
  if (!sourceFiles.length) throw new Error("No completed source files are attached to this job");

  const outputUploads = {
    splat: {
      key: `splats/${jobId}/scene.splat`,
      url: "",
    },
    collision: {
      key: `splats/${jobId}/collision.glb`,
      url: "",
    },
  };
  const [sourceUrls, splatUploadUrl, collisionUploadUrl] = await Promise.all([
    Promise.all(sourceFiles.map((file) => presignDownload(file.objectKey))),
    presignObjectUpload(outputUploads.splat.key, "application/octet-stream"),
    presignObjectUpload(outputUploads.collision.key, "model/gltf-binary"),
  ]);
  outputUploads.splat.url = splatUploadUrl;
  outputUploads.collision.url = collisionUploadUrl;

  await updateJob(jobId, {
    status: "QUEUED",
    progress: 0,
    logs: appendCappedLog(job.logs, "Dispatching training request to GPU worker..."),
  });
  await dispatchTrainingJob({
    job_id: jobId,
    source_files: sourceFiles.map((file, index) => ({
      download_url: sourceUrls[index],
      original_name: file.originalName,
    })),
    output_uploads: outputUploads,
    callback_url: callbackUrl,
  });
}

export async function handleWorkerCallback(
  payload: WorkerCallbackPayload
): Promise<void> {
  const job = await getJob(payload.job_id);
  if (!job) {
    throw new Error(`Job not found: ${payload.job_id}`);
  }

  const updatePayload: Partial<Job> = {
    status: payload.status,
    progress: payload.progress,
  };

  if (payload.frame_stats) {
    updatePayload.frameStats = payload.frame_stats;
  }

  const logMessages: string[] = [];
  if (shouldPersistLog(job, payload) && payload.log) {
    logMessages.push(payload.log);
  }
  if (payload.status === "FAILED" && payload.error) {
    logMessages.push(`ERROR: ${payload.error}`);
  }

  if (payload.status === "FAILED") {
    let logs = job.logs;
    for (const message of logMessages) {
      logs = appendCappedLog(logs, message);
    }
    if (logMessages.length > 0) {
      updatePayload.logs = logs;
    }
    await updateJob(payload.job_id, updatePayload);
    return;
  }

  if (payload.status === "COMPLETED") {
    const expectedSplatKey = `splats/${payload.job_id}/scene.splat`;
    const expectedCollisionKey = `splats/${payload.job_id}/collision.glb`;
    if (payload.splat_key && payload.splat_key !== expectedSplatKey) {
      throw new Error("Worker returned an unexpected splat object key");
    }
    if (payload.collision_key && payload.collision_key !== expectedCollisionKey) {
      throw new Error("Worker returned an unexpected collision object key");
    }
    if (payload.splat_key) {
      const splat = await headObject(payload.splat_key);
      if (!splat.ContentLength) throw new Error("Worker splat output is missing or empty in object storage");
    }
    if (payload.collision_key) {
      const collision = await headObject(payload.collision_key);
      if (!collision.ContentLength) throw new Error("Worker collision output is missing or empty in object storage");
    }

    updatePayload.progress = 100;
    updatePayload.splatPath = payload.splat_key || null;
    updatePayload.collisionPath = payload.collision_key || null;
    if (!payload.splat_key) {
      logMessages.push("No splat object was uploaded by the worker.");
    }
    let logs = job.logs;
    for (const message of logMessages) {
      logs = appendCappedLog(logs, message);
    }
    if (logMessages.length > 0) {
      updatePayload.logs = logs;
    }
    await updateJob(payload.job_id, updatePayload);
    return;
  }

  if (logMessages.length > 0) {
    let logs = job.logs;
    for (const message of logMessages) {
      logs = appendCappedLog(logs, message);
    }
    updatePayload.logs = logs;
  }

  await updateJob(payload.job_id, updatePayload);
}
