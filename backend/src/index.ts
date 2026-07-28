import express from "express";
import cors from "cors";
import multer from "multer";
import * as path from "path";
import * as fs from "fs";
import * as dotenv from "dotenv";

dotenv.config();

import { handleUpload } from "./routes/upload";
import { createTrainRouter } from "./routes/train";
import { createJobRouter } from "./routes/job";
import { createHealthRouter } from "./routes/health";
import { handleWorkerCallback } from "./services/jobManager";
import { validateWorkerCallback } from "./validation/schemas";

const app = express();
const PORT = process.env.PORT || 3001;

const uploadsDir = path.join(__dirname, "../uploads");
if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir, { recursive: true });
}

app.use(cors());
app.use(express.json());
app.use("/uploads", express.static(uploadsDir));

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, uploadsDir),
  filename: (_req, file, cb) => {
    const uniqueSuffix = Date.now() + "-" + Math.round(Math.random() * 1e9);
    cb(null, uniqueSuffix + "-" + file.originalname);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: 500 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    if (path.extname(file.originalname).toLowerCase() === ".zip") {
      cb(null, true);
    } else {
      cb(new Error("Only .zip files are supported"));
    }
  },
});

// Public REST API
app.use("/health", createHealthRouter());
app.use("/job", createJobRouter());
app.post("/upload", upload.single("images"), (req, res) => {
  handleUpload(req, res);
});
app.use("/train", createTrainRouter(uploadsDir));

// Internal: GPU worker callbacks
app.post("/internal/worker/callback", async (req, res) => {
  try {
    const validation = validateWorkerCallback(req.body);
    if ("error" in validation) {
      return res.status(400).json({ error: validation.error });
    }

    await handleWorkerCallback(req.body, uploadsDir);
    res.json({ received: true });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Callback processing failed";
    res.status(500).json({ error: message });
  }
});

app.use((err: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  if (err instanceof multer.MulterError) {
    return res.status(400).json({ error: err.message });
  }
  if (err.message === "Only .zip files are supported") {
    return res.status(400).json({ error: err.message });
  }
  res.status(500).json({ error: err.message || "Internal server error" });
});

app.listen(PORT, () => {
  console.log(`Backend API running at http://localhost:${PORT}`);
  console.log(`  GET  /health`);
  console.log(`  POST /upload`);
  console.log(`  POST /train`);
  console.log(`  GET  /job/:id`);
  console.log(`  GET  /job (list all jobs)`);
  console.log(`Static uploads: http://localhost:${PORT}/uploads`);
});
