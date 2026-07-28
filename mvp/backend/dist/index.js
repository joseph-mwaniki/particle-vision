"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const express_1 = __importDefault(require("express"));
const cors_1 = __importDefault(require("cors"));
const multer_1 = __importDefault(require("multer"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const dotenv = __importStar(require("dotenv"));
// Load environment variables
dotenv.config();
const db_1 = require("./db");
const pipeline_1 = require("./pipeline");
const app = (0, express_1.default)();
const PORT = process.env.PORT || 3001;
// Middlewares
app.use((0, cors_1.default)());
app.use(express_1.default.json());
// Ensure uploads folder exists
const uploadsDir = path.join(__dirname, "../uploads");
if (!fs.existsSync(uploadsDir)) {
    fs.mkdirSync(uploadsDir, { recursive: true });
}
// Serve uploaded assets statically
app.use("/uploads", express_1.default.static(uploadsDir));
// Multer disk storage setup for zip files
const storage = multer_1.default.diskStorage({
    destination: (req, file, cb) => {
        cb(null, uploadsDir);
    },
    filename: (req, file, cb) => {
        const uniqueSuffix = Date.now() + "-" + Math.round(Math.random() * 1e9);
        cb(null, uniqueSuffix + "-" + file.originalname);
    },
});
const upload = (0, multer_1.default)({
    storage,
    fileFilter: (req, file, cb) => {
        if (path.extname(file.originalname).toLowerCase() === ".zip") {
            cb(null, true);
        }
        else {
            cb(new Error("Only ZIP files are supported."));
        }
    },
});
// Endpoints
// 1. Get all training jobs
app.get("/api/jobs", async (req, res) => {
    try {
        const jobs = await (0, db_1.getJobs)();
        res.json(jobs);
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// 2. Get status of a single job
app.get("/api/jobs/:id", async (req, res) => {
    try {
        const job = await (0, db_1.getJob)(req.params.id);
        if (!job) {
            return res.status(404).json({ error: "Job not found" });
        }
        res.json(job);
    }
    catch (err) {
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
        const job = await (0, db_1.createJob)(req.file.path);
        res.json(job);
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// 4. Start processing / Mock Checkout success endpoint
app.post("/api/jobs/:id/start", async (req, res) => {
    try {
        const job = await (0, db_1.getJob)(req.params.id);
        if (!job) {
            return res.status(404).json({ error: "Job not found" });
        }
        if (job.status !== "PENDING_PAYMENT") {
            return res.status(400).json({ error: `Job has already started or completed (Status: ${job.status})` });
        }
        // Update job status to QUEUED
        await (0, db_1.updateJob)(job.id, {
            status: "QUEUED",
            logs: `[${new Date().toISOString()}] Checkout successful! Job queued for training...`,
        });
        // Start background processing pipeline asynchronously
        // (We don't await this so the response returns immediately)
        (0, pipeline_1.runMockPipeline)(job.id, uploadsDir).catch((err) => {
            console.error(`Pipeline error on job ${job.id}:`, err);
        });
        res.json({ message: "Job processing started.", jobId: job.id });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// Start API Server
app.listen(PORT, () => {
    console.log(`SaaS MVP Backend running at http://localhost:${PORT}`);
    console.log(`Static uploads available at http://localhost:${PORT}/uploads`);
});
