import * as fs from "fs";
import * as path from "path";
import { Job, JobStatus } from "./types/job";

const JSON_DB_PATH = path.join(__dirname, "../jobs.json");

function readJsonDb(): Job[] {
  if (!fs.existsSync(JSON_DB_PATH)) {
    fs.writeFileSync(JSON_DB_PATH, JSON.stringify([]));
    return [];
  }
  try {
    const data = fs.readFileSync(JSON_DB_PATH, "utf8");
    return JSON.parse(data, (key, value) => {
      if (key === "createdAt" || key === "updatedAt") {
        return new Date(value);
      }
      return value;
    });
  } catch (err) {
    console.error("Failed to read JSON DB:", err);
    return [];
  }
}

function writeJsonDb(jobs: Job[]) {
  fs.writeFileSync(JSON_DB_PATH, JSON.stringify(jobs, null, 2));
}

export async function createJob(imagesPath: string): Promise<Job> {
  const id = "job_" + Math.random().toString(36).substring(2, 11);
  const now = new Date();
  const newJob: Job = {
    id,
    status: "PENDING",
    progress: 0,
    createdAt: now,
    updatedAt: now,
    imagesPath,
    splatPath: null,
    collisionPath: null,
    logs: `[${now.toISOString()}] Job created. Upload complete. Ready to train.`,
  };

  const jobs = readJsonDb();
  jobs.push(newJob);
  writeJsonDb(jobs);
  return newJob;
}

export async function updateJob(
  id: string,
  data: Partial<Omit<Job, "id" | "createdAt">>
): Promise<Job | null> {
  const jobs = readJsonDb();
  const index = jobs.findIndex((j) => j.id === id);
  if (index === -1) return null;

  jobs[index] = {
    ...jobs[index],
    ...data,
    updatedAt: new Date(),
  };
  writeJsonDb(jobs);
  return jobs[index];
}

export async function appendJobLog(id: string, message: string): Promise<Job | null> {
  const job = await getJob(id);
  if (!job) return null;

  const logLine = `[${new Date().toISOString()}] ${message}`;
  const logs = job.logs ? `${job.logs}\n${logLine}` : logLine;
  return updateJob(id, { logs });
}

export async function getJob(id: string): Promise<Job | null> {
  const jobs = readJsonDb();
  return jobs.find((j) => j.id === id) || null;
}

export async function getJobs(): Promise<Job[]> {
  const jobs = readJsonDb();
  return jobs.sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());
}

export function isValidJobStatus(status: string): status is JobStatus {
  return [
    "PENDING",
    "QUEUED",
    "PROCESSING_COLMAP",
    "PROCESSING_GSPLAT",
    "PROCESSING_COLLISION",
    "PROCESSING_EXPORT",
    "COMPLETED",
    "FAILED",
  ].includes(status);
}
