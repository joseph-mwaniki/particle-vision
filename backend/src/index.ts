import express from "express";
import cors from "cors";
import * as dotenv from "dotenv";

dotenv.config();

import { createTrainRouter } from "./routes/train";
import { createJobRouter } from "./routes/job";
import { createHealthRouter } from "./routes/health";
import { createSplatRouter } from "./routes/splat";
import { handleWorkerCallback } from "./services/jobManager";
import { validateWorkerCallback } from "./validation/schemas";
import { createUploadSessionRouter } from "./routes/uploadSession";

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

// Optional API Key validation helper
export function requireApiKey(req: express.Request, res: express.Response, next: express.NextFunction) {
  const configuredKey = process.env.API_KEY;
  if (!configuredKey) {
    return next(); // If no API key configured, pass through
  }
  const authHeader = req.headers["x-api-key"] || req.query.apiKey;
  if (authHeader === configuredKey) {
    return next();
  }
  return res.status(401).json({ error: "Unauthorized: Invalid or missing API key" });
}

// Public & Splat API
const splatRouter = createSplatRouter();
const jobRouter = createJobRouter();
const healthRouter = createHealthRouter();

app.use("/health", healthRouter);
app.use("/job", jobRouter);
app.use("/splat", splatRouter);
app.use("/splats", splatRouter);

// Aliases under /api
app.use("/api/health", healthRouter);
app.use("/api/job", jobRouter);
app.use("/api/splat", splatRouter);
app.use("/api/splats", splatRouter);

const uploadSessionRouter = createUploadSessionRouter();
app.use("/upload-session", uploadSessionRouter);
app.use("/api/upload-session", uploadSessionRouter);

app.use("/train", createTrainRouter());
app.use("/api/train", createTrainRouter());

// Internal: GPU worker callbacks
app.post("/internal/worker/callback", async (req, res) => {
  try {
    const validation = validateWorkerCallback(req.body);
    if ("error" in validation) {
      return res.status(400).json({ error: validation.error });
    }

    await handleWorkerCallback(req.body);
    res.json({ received: true });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Callback processing failed";
    res.status(500).json({ error: message });
  }
});

app.use((err: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  res.status(500).json({ error: err.message || "Internal server error" });
});

if (process.env.NODE_ENV !== "production") {
  app.listen(PORT, () => {
    console.log(`Backend API running at http://localhost:${PORT}`);
    console.log(`  GET  /health`);
    console.log(`  POST /train`);
    console.log(`  GET  /job/:id`);
    console.log(`  GET  /splats (list showcase splats)`);
    console.log(`  GET  /splats/:identifier (get splat by id, slug, or shareToken)`);
    console.log(`  POST /splats (create draft splat)`);
    console.log(`  POST /splats/:id/publish (publish / unpublish splat)`);
  });
}

export default app;
