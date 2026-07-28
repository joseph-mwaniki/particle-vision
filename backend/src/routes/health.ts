import { Router, Request, Response } from "express";

export function createHealthRouter(): Router {
  const router = Router();

  router.get("/", (_req: Request, res: Response) => {
    res.json({
      status: "ok",
      service: "remote-view-backend",
      timestamp: new Date().toISOString(),
    });
  });

  return router;
}
