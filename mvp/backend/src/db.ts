import { PrismaClient } from "@prisma/client";
import * as fs from "fs";
import * as path from "path";

export interface Job {
  id: string;
  status: string;
  progress: number;
  createdAt: Date;
  updatedAt: Date;
  imagesPath: string;
  splatPath: string | null;
  logs: string | null;
}

let prisma: PrismaClient | null = null;
const useFallback = !process.env.DATABASE_URL;

if (!useFallback) {
  try {
    prisma = new PrismaClient();
  } catch (err) {
    console.error("Failed to initialize Prisma client, falling back to local JSON database:", err);
  }
}

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
  try {
    fs.writeFileSync(JSON_DB_PATH, JSON.stringify(jobs, null, 2));
  } catch (err) {
    console.error("Failed to write JSON DB:", err);
  }
}

export async function createJob(imagesPath: string): Promise<Job> {
  const id = "job_" + Math.random().toString(36).substr(2, 9);
  const now = new Date();
  const newJob: Job = {
    id,
    status: "PENDING_PAYMENT",
    progress: 0.0,
    createdAt: now,
    updatedAt: now,
    imagesPath,
    splatPath: null,
    logs: "Job created. Waiting for payment checkout.",
  };

  if (prisma && !useFallback) {
    try {
      return await prisma.job.create({
        data: {
          id: newJob.id,
          status: newJob.status,
          progress: newJob.progress,
          imagesPath: newJob.imagesPath,
          logs: newJob.logs,
        },
      }) as Job;
    } catch (err) {
      console.error("Prisma createJob error, falling back:", err);
    }
  }

  const jobs = readJsonDb();
  jobs.push(newJob);
  writeJsonDb(jobs);
  return newJob;
}

export async function updateJob(id: string, data: Partial<Omit<Job, "id" | "createdAt" | "updatedAt">>): Promise<Job | null> {
  const now = new Date();

  if (prisma && !useFallback) {
    try {
      return await prisma.job.update({
        where: { id },
        data: {
          ...data,
          updatedAt: now,
        },
      }) as Job;
    } catch (err) {
      console.error("Prisma updateJob error, falling back:", err);
    }
  }

  const jobs = readJsonDb();
  const index = jobs.findIndex((j) => j.id === id);
  if (index === -1) return null;

  jobs[index] = {
    ...jobs[index],
    ...data,
    updatedAt: now,
  };
  writeJsonDb(jobs);
  return jobs[index];
}

export async function getJob(id: string): Promise<Job | null> {
  if (prisma && !useFallback) {
    try {
      return await prisma.job.findUnique({
        where: { id },
      }) as Job | null;
    } catch (err) {
      console.error("Prisma getJob error, falling back:", err);
    }
  }

  const jobs = readJsonDb();
  return jobs.find((j) => j.id === id) || null;
}

export async function getJobs(): Promise<Job[]> {
  if (prisma && !useFallback) {
    try {
      return await prisma.job.findMany({
        orderBy: { createdAt: "desc" },
      }) as Job[];
    } catch (err) {
      console.error("Prisma getJobs error, falling back:", err);
    }
  }

  const jobs = readJsonDb();
  return jobs.sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());
}
