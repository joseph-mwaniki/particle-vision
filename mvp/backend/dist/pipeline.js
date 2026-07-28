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
Object.defineProperty(exports, "__esModule", { value: true });
exports.runMockPipeline = runMockPipeline;
exports.runRealPipeline = runRealPipeline;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const http = __importStar(require("http"));
const https = __importStar(require("https"));
const db_1 = require("./db");
// Helper to download a file
function downloadFile(url, dest) {
    return new Promise((resolve, reject) => {
        const file = fs.createWriteStream(dest);
        const client = url.startsWith("https") ? https : http;
        client.get(url, (response) => {
            if (response.statusCode !== 200) {
                reject(new Error(`Failed to download: ${response.statusCode}`));
                return;
            }
            response.pipe(file);
            file.on("finish", () => {
                file.close();
                resolve();
            });
        }).on("error", (err) => {
            fs.unlink(dest, () => { });
            reject(err);
        });
    });
}
async function runMockPipeline(jobId, uploadsDir) {
    const jobDir = path.join(uploadsDir, "jobs", jobId);
    const outputDir = path.join(jobDir, "output");
    fs.mkdirSync(outputDir, { recursive: true });
    const appendLog = async (currentLogs, newLog) => {
        const updated = currentLogs + "\n" + `[${new Date().toISOString()}] ${newLog}`;
        await (0, db_1.updateJob)(jobId, { logs: updated });
        return updated;
    };
    let logs = `[${new Date().toISOString()}] Starting mock training pipeline...`;
    await (0, db_1.updateJob)(jobId, { status: "QUEUED", progress: 0.0, logs });
    // 1. Queue phase
    await new Promise((r) => setTimeout(r, 1500));
    logs = await appendLog(logs, "Job dequeued. Assigning to local execution slot...");
    // 2. COLMAP phase
    await (0, db_1.updateJob)(jobId, { status: "PROCESSING_COLMAP", progress: 10.0 });
    await new Promise((r) => setTimeout(r, 1500));
    logs = await appendLog(logs, "[COLMAP] Extracting features from uploaded images...");
    await new Promise((r) => setTimeout(r, 1500));
    logs = await appendLog(logs, "[COLMAP] Matching features (exhaustive matcher)...");
    await new Promise((r) => setTimeout(r, 1500));
    logs = await appendLog(logs, "[COLMAP] Running structure-from-motion mapper...");
    // 3. GSPLAT training phase
    await (0, db_1.updateJob)(jobId, { status: "PROCESSING_GSPLAT", progress: 30.0 });
    logs = await appendLog(logs, "[gsplat] Initializing 3D Gaussians from COLMAP sparse point cloud...");
    const totalSteps = 7000;
    for (let step = 1000; step <= totalSteps; step += 1000) {
        await new Promise((r) => setTimeout(r, 1000));
        const progress = 30 + Math.floor((step / totalSteps) * 60);
        const loss = (0.15 - (step / totalSteps) * 0.12).toFixed(5);
        const psnr = (20.5 + (step / totalSteps) * 8.2).toFixed(2);
        logs = await appendLog(logs, `[gsplat] Step ${step}/${totalSteps} | Loss: ${loss} | PSNR: ${psnr}dB`);
        await (0, db_1.updateJob)(jobId, { progress, logs });
    }
    // 4. Exporting and conversion phase
    logs = await appendLog(logs, "[gsplat] Optimization complete. Exporting parameters to PLY file...");
    await (0, db_1.updateJob)(jobId, { progress: 95.0, logs });
    await new Promise((r) => setTimeout(r, 1000));
    logs = await appendLog(logs, "[gsplat.js] Converting PLY format to compressed Web Splat (.splat) format...");
    await (0, db_1.updateJob)(jobId, { logs });
    const splatFileUrl = "https://huggingface.co/datasets/dylanebert/3dgs/resolve/main/bonsai/bonsai-7k-mini.splat";
    const localSplatPath = path.join(outputDir, "scene.splat");
    try {
        // Download sample splat file to simulate final generated splat
        await downloadFile(splatFileUrl, localSplatPath);
        logs = await appendLog(logs, "[gsplat.js] Splat compression complete. Saved scene.splat.");
        await (0, db_1.updateJob)(jobId, {
            status: "COMPLETED",
            progress: 100.0,
            splatPath: `/uploads/jobs/${jobId}/output/scene.splat`,
            logs,
        });
    }
    catch (err) {
        logs = await appendLog(logs, `[ERROR] Failed to save splat file: ${err.message}`);
        await (0, db_1.updateJob)(jobId, {
            status: "FAILED",
            logs,
        });
    }
}
async function runRealPipeline(jobId, uploadsDir) {
    // Real training wrapper (COLMAP + gsplat simple_trainer.py)
    // For the local MVP setup, we default to the mock pipeline,
    // but if the user runs the server on a machine with CUDA & COLMAP,
    // we could run real commands here.
    const jobDir = path.join(uploadsDir, "jobs", jobId);
    const imagesDir = path.join(jobDir, "images");
    const outputDir = path.join(jobDir, "output");
    fs.mkdirSync(outputDir, { recursive: true });
    const appendLog = async (currentLogs, newLog) => {
        const updated = currentLogs + "\n" + `[${new Date().toISOString()}] ${newLog}`;
        await (0, db_1.updateJob)(jobId, { logs: updated });
        return updated;
    };
    let logs = `[${new Date().toISOString()}] Starting real training pipeline...`;
    await (0, db_1.updateJob)(jobId, { status: "QUEUED", progress: 0.0, logs });
    // 1. Unzip images (placeholder logic, assuming ZIP contains images directly)
    // 2. Run COLMAP sequence
    // 3. Run simple_trainer.py using child_process.spawn
    // For the MVP, we run the Mock pipeline by default, but we provide this structure.
    console.log("Real pipeline execution requested for job", jobId);
    await runMockPipeline(jobId, uploadsDir);
}
