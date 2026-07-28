import * as fs from "fs";
import * as path from "path";
import * as http from "http";
import * as https from "https";
import { spawn } from "child_process";
import { updateJob } from "./db";

// Helper to download a file
function downloadFile(url: string, dest: string): Promise<void> {
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
      fs.unlink(dest, () => {});
      reject(err);
    });
  });
}

export async function runMockPipeline(jobId: string, uploadsDir: string) {
  const jobDir = path.join(uploadsDir, "jobs", jobId);
  const outputDir = path.join(jobDir, "output");
  fs.mkdirSync(outputDir, { recursive: true });

  const appendLog = async (currentLogs: string, newLog: string) => {
    const updated = currentLogs + "\n" + `[${new Date().toISOString()}] ${newLog}`;
    await updateJob(jobId, { logs: updated });
    return updated;
  };

  let logs = `[${new Date().toISOString()}] Starting mock training pipeline...`;
  await updateJob(jobId, { status: "QUEUED", progress: 0.0, logs });

  // 1. Queue phase
  await new Promise((r) => setTimeout(r, 1500));
  logs = await appendLog(logs, "Job dequeued. Assigning to local execution slot...");

  // 2. COLMAP phase
  await updateJob(jobId, { status: "PROCESSING_COLMAP", progress: 10.0 });
  await new Promise((r) => setTimeout(r, 1500));
  logs = await appendLog(logs, "[COLMAP] Extracting features from uploaded images...");
  await new Promise((r) => setTimeout(r, 1500));
  logs = await appendLog(logs, "[COLMAP] Matching features (exhaustive matcher)...");
  await new Promise((r) => setTimeout(r, 1500));
  logs = await appendLog(logs, "[COLMAP] Running structure-from-motion mapper...");
  
  // 3. GSPLAT training phase
  await updateJob(jobId, { status: "PROCESSING_GSPLAT", progress: 30.0 });
  logs = await appendLog(logs, "[gsplat] Initializing 3D Gaussians from COLMAP sparse point cloud...");
  
  const totalSteps = 7000;
  for (let step = 1000; step <= totalSteps; step += 1000) {
    await new Promise((r) => setTimeout(r, 1000));
    const progress = 30 + Math.floor((step / totalSteps) * 60);
    const loss = (0.15 - (step / totalSteps) * 0.12).toFixed(5);
    const psnr = (20.5 + (step / totalSteps) * 8.2).toFixed(2);
    logs = await appendLog(logs, `[gsplat] Step ${step}/${totalSteps} | Loss: ${loss} | PSNR: ${psnr}dB`);
    await updateJob(jobId, { progress, logs });
  }

  // 4. Exporting and conversion phase
  logs = await appendLog(logs, "[gsplat] Optimization complete. Exporting parameters to PLY file...");
  await updateJob(jobId, { progress: 95.0, logs });
  await new Promise((r) => setTimeout(r, 1000));
  
  logs = await appendLog(logs, "[gsplat.js] Converting PLY format to compressed Web Splat (.splat) format...");
  await updateJob(jobId, { logs });
  
  const splatFileUrl = "https://huggingface.co/datasets/dylanebert/3dgs/resolve/main/bonsai/bonsai-7k-mini.splat";
  const localSplatPath = path.join(outputDir, "scene.splat");
  
  try {
    // Download sample splat file to simulate final generated splat
    await downloadFile(splatFileUrl, localSplatPath);
    logs = await appendLog(logs, "[gsplat.js] Splat compression complete. Saved scene.splat.");
    
    await updateJob(jobId, {
      status: "COMPLETED",
      progress: 100.0,
      splatPath: `/uploads/jobs/${jobId}/output/scene.splat`,
      logs,
    });
  } catch (err: any) {
    logs = await appendLog(logs, `[ERROR] Failed to save splat file: ${err.message}`);
    await updateJob(jobId, {
      status: "FAILED",
      logs,
    });
  }
}

export async function runRealPipeline(jobId: string, uploadsDir: string) {
  // Real training wrapper (COLMAP + gsplat simple_trainer.py)
  // For the local MVP setup, we default to the mock pipeline,
  // but if the user runs the server on a machine with CUDA & COLMAP,
  // we could run real commands here.
  const jobDir = path.join(uploadsDir, "jobs", jobId);
  const imagesDir = path.join(jobDir, "images");
  const outputDir = path.join(jobDir, "output");
  fs.mkdirSync(outputDir, { recursive: true });

  const appendLog = async (currentLogs: string, newLog: string) => {
    const updated = currentLogs + "\n" + `[${new Date().toISOString()}] ${newLog}`;
    await updateJob(jobId, { logs: updated });
    return updated;
  };

  let logs = `[${new Date().toISOString()}] Starting real training pipeline...`;
  await updateJob(jobId, { status: "QUEUED", progress: 0.0, logs });

  // 1. Unzip images (placeholder logic, assuming ZIP contains images directly)
  // 2. Run COLMAP sequence
  // 3. Run simple_trainer.py using child_process.spawn
  // For the MVP, we run the Mock pipeline by default, but we provide this structure.
  console.log("Real pipeline execution requested for job", jobId);
  await runMockPipeline(jobId, uploadsDir);
}
