import { Router, Request, Response } from "express";
import { getJob, getJobs } from "../db";
import { getObjectUrl } from "../services/objectStorage";
import { Job } from "../types/job";

async function formatJobResponse(job: Job) {
  const assetUrl = async (key: string | null) =>
    key && !key.startsWith("/") && !/^https?:\/\//i.test(key) ? getObjectUrl(key) : key;
  const [splatUrl, collisionUrl] = await Promise.all([
    assetUrl(job.splatPath),
    assetUrl(job.collisionPath),
  ]);
  return { ...job, splatUrl, collisionUrl };
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

  return router;
}
