import { Router, Request, Response } from "express";
import { getJob } from "../db";
import { startTrainingJob } from "../services/jobManager";
import { validateTrainRequest } from "../validation/schemas";

export function createTrainRouter(uploadsDir: string): Router {
  const router = Router();

  router.post("/", async (req: Request, res: Response) => {
    try {
      const validation = validateTrainRequest(req.body);
      if ("error" in validation) {
        return res.status(400).json({ error: validation.error });
      }

      const job = await getJob(validation.jobId);
      if (!job) {
        return res.status(404).json({ error: "Job not found" });
      }

      if (job.status !== "PENDING" && job.status !== "FAILED") {
        return res.status(400).json({
          error: `Job cannot be trained in current status: ${job.status}`,
        });
      }

      startTrainingJob(validation.jobId, uploadsDir).catch((err) => {
        console.error(`Training dispatch failed for ${validation.jobId}:`, err);
      });

      res.status(202).json({
        message: "Training request accepted",
        jobId: validation.jobId,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Training request failed";
      res.status(500).json({ error: message });
    }
  });

  return router;
}
