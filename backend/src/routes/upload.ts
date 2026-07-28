import { Request, Response } from "express";
import { createJob } from "../db";

export async function handleUpload(req: Request, res: Response): Promise<void> {
  try {
    const file = req.file;
    if (!file) {
      res.status(400).json({
        error: "No file uploaded. Send multipart/form-data with field 'images' containing a .zip file.",
      });
      return;
    }

    const job = await createJob(file.path);
    res.status(201).json(job);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Upload failed";
    res.status(500).json({ error: message });
  }
}
