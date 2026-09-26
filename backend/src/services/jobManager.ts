import { appendJobLog, getJob, prisma, updateJob } from "../db";
import { headObject, presignDownload, presignObjectUpload } from "./objectStorage";
import { dispatchTrainingJob } from "./workerClient";
import { WorkerCallbackPayload } from "../types/job";

const BACKEND_PUBLIC_URL = process.env.BACKEND_PUBLIC_URL || "http://localhost:3001";

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
    logs: `${job.logs || ""}\n[${new Date().toISOString()}] Dispatching training request to GPU worker...`,
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

    await updateJob(payload.job_id, {
      status: "COMPLETED",
      progress: 100,
      splatPath: payload.splat_key || null,
      collisionPath: payload.collision_key || null,
    });
    if (!payload.splat_key) await appendJobLog(payload.job_id, "No splat object was uploaded by the worker.");
    return;
  }

  await updateJob(payload.job_id, {
    status: payload.status,
    progress: payload.progress,
  });
}
