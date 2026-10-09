import { Router, Request, Response } from "express";
import { getJob, getJobs, updateJob } from "../db";
import { getObjectUrl, headObject, presignObjectUpload } from "../services/objectStorage";
import { Job } from "../types/job";

const ARTIFACT_TYPES = {
  "processed-splat": { extension: "processed.splat", contentType: "application/octet-stream", field: "processedSplatPath" },
  "voxel-json": { extension: "voxel/scene.voxel.json", contentType: "application/json", field: "voxelPath" },
  "voxel-bin": { extension: "voxel/scene.voxel.bin", contentType: "application/octet-stream", field: null },
  "voxel-collision": { extension: "voxel/scene.collision.glb", contentType: "model/gltf-binary", field: "voxelCollisionPath" },
} as const;

type ArtifactType = keyof typeof ARTIFACT_TYPES;

function isArtifactType(value: string): value is ArtifactType {
  return Object.hasOwn(ARTIFACT_TYPES, value);
}

function artifactAuthorized(req: Request): boolean {
  const configuredKey = process.env.API_KEY;
  return !configuredKey || req.headers["x-api-key"] === configuredKey;
}

async function formatJobResponse(job: Job) {
  const assetUrl = async (key: string | null) =>
    key && !key.startsWith("/") && !/^https?:\/\//i.test(key) ? getObjectUrl(key) : key;
  const [splatUrl, collisionUrl] = await Promise.all([
    assetUrl(job.splatPath),
    assetUrl(job.collisionPath),
  ]);
  const [processedSplatUrl, voxelUrl, voxelCollisionUrl] = await Promise.all([
    assetUrl(job.processedSplatPath || null),
    assetUrl(job.voxelPath || null),
    assetUrl(job.voxelCollisionPath || null),
  ]);
  return { ...job, splatUrl, collisionUrl, processedSplatUrl, voxelUrl, voxelCollisionUrl };
}

export function createJobRouter(): Router {
  const router = Router();

  router.get("/", async (_req: Request, res: Response) => {
    try {
      const jobs = await getJobs();
      res.json(await Promise.all(jobs.map(formatJobResponse)));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to list jobs";
      res.status(500).json({ error: message });
    }
  });

  router.get("/:id", async (req: Request, res: Response) => {
    try {
      const job = await getJob(req.params.id);
      if (!job) {
        return res.status(404).json({ error: "Job not found" });
      }
      res.json(await formatJobResponse(job));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to get job";
      res.status(500).json({ error: message });
    }
  });

  router.post("/:id/artifacts/:kind", async (req: Request, res: Response) => {
    try {
      if (!artifactAuthorized(req)) return res.status(401).json({ error: "Unauthorized" });
      const job = await getJob(req.params.id);
      if (!job) return res.status(404).json({ error: "Job not found" });
      if (job.status !== "COMPLETED" || !job.splatPath) {
        return res.status(409).json({ error: "Artifacts can only be attached to completed jobs" });
      }
      if (!isArtifactType(req.params.kind)) return res.status(400).json({ error: "Unsupported artifact type" });

      const artifact = ARTIFACT_TYPES[req.params.kind];
      const key = `splats/${job.id}/${artifact.extension}`;
      const url = await presignObjectUpload(key, artifact.contentType);
      res.json({ key, url });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to prepare artifact upload";
      res.status(500).json({ error: message });
    }
  });

  router.post("/:id/artifacts/:kind/complete", async (req: Request, res: Response) => {
    try {
      if (!artifactAuthorized(req)) return res.status(401).json({ error: "Unauthorized" });
      const job = await getJob(req.params.id);
      if (!job) return res.status(404).json({ error: "Job not found" });
      if (!job.splatPath) return res.status(409).json({ error: "Job has no source splat" });
      if (!isArtifactType(req.params.kind)) return res.status(400).json({ error: "Unsupported artifact type" });

      const artifact = ARTIFACT_TYPES[req.params.kind];
      const key = `splats/${job.id}/${artifact.extension}`;
      const stored = await headObject(key);
      if (!stored.ContentLength) return res.status(400).json({ error: "Uploaded artifact is missing or empty" });

      const updated = artifact.field
        ? await updateJob(job.id, { [artifact.field]: key })
        : job;
      if (!updated) return res.status(404).json({ error: "Job not found" });
      res.json(await formatJobResponse(updated));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to confirm artifact upload";
      res.status(500).json({ error: message });
    }
  });

  return router;
}
