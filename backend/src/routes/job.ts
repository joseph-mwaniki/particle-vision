import { Router, Request, Response } from "express";
import { getJob, getJobs } from "../db";

export function createJobRouter(): Router {
  const router = Router();

  router.get("/", async (_req: Request, res: Response) => {
    try {
      const jobs = await getJobs();
      res.json(jobs);
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
      res.json(job);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to get job";
      res.status(500).json({ error: message });
    }
  });

  return router;
}
