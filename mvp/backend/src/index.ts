import express from "express";
import cors from "cors";
import multer from "multer";
import * as path from "path";
import * as fs from "fs";
import * as dotenv from "dotenv";

// Load environment variables
dotenv.config();

import { createJob, getJob, getJobs, updateJob } from "./db";
import { runMockPipeline } from "./pipeline";

const app = express();
const PORT = process.env.PORT || 3001;

// Middlewares
app.use(cors());
app.use(express.json());

// Ensure uploads folder exists
const uploadsDir = path.join(__dirname, "../uploads");
if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir, { recursive: true });
}

// Serve uploaded assets statically
app.use("/uploads", express.static(uploadsDir));

// Multer disk storage setup for zip files
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, uploadsDir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + "-" + Math.round(Math.random() * 1e9);
    cb(null, uniqueSuffix + "-" + file.originalname);
  },
});

const upload = multer({
  storage,
  fileFilter: (req, file, cb) => {
    if (path.extname(file.originalname).toLowerCase() === ".zip") {
      cb(null, true);
    } else {
      cb(new Error("Only ZIP files are supported."));
    }
  },
});

// Endpoints

// 1. Get all training jobs
app.get("/api/jobs", async (req, res) => {
  try {
    const jobs = await getJobs();
    res.json(jobs);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 2. Get status of a single job
app.get("/api/jobs/:id", async (req, res) => {
  try {
    const job = await getJob(req.params.id);
    if (!job) {
      return res.status(404).json({ error: "Job not found" });
    }
    res.json(job);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 3. Upload a new batch of images (as a ZIP) to create a training job
app.post("/api/jobs", upload.single("images"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No ZIP file uploaded. Please upload a .zip file containing images." });
    }

    // Create job with PENDING_PAYMENT status
    const job = await createJob(req.file.path);
    res.json(job);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 4. Start processing / Mock Checkout success endpoint
app.post("/api/jobs/:id/start", async (req, res) => {
  try {
    const job = await getJob(req.params.id);
    if (!job) {
      return res.status(404).json({ error: "Job not found" });
    }

    if (job.status !== "PENDING_PAYMENT") {
      return res.status(400).json({ error: `Job has already started or completed (Status: ${job.status})` });
    }

    // Update job status to QUEUED
    await updateJob(job.id, {
      status: "QUEUED",
      logs: `[${new Date().toISOString()}] Checkout successful! Job queued for training...`,
    });

    // Start background processing pipeline asynchronously
    // (We don't await this so the response returns immediately)
    runMockPipeline(job.id, uploadsDir).catch((err) => {
      console.error(`Pipeline error on job ${job.id}:`, err);
    });

    res.json({ message: "Job processing started.", jobId: job.id });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// Start API Server
app.listen(PORT, () => {
  console.log(`SaaS MVP Backend running at http://localhost:${PORT}`);
  console.log(`Static uploads available at http://localhost:${PORT}/uploads`);
});
