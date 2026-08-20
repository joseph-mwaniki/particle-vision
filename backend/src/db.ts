import { PrismaClient } from "@prisma/client";
import * as fs from "fs";
import * as path from "path";
import { Job, JobStatus } from "./types/job";

export interface CameraConfig {
  position?: [number, number, number];
  target?: [number, number, number];
  rotation?: [number, number, number, number];
  fov?: number;
}

export interface Splat {
  id: string;
  title: string;
  slug: string;
  description: string | null;
  status: "draft" | "published";
  splatPath: string;
  collisionPath: string | null;
  thumbnailUrl: string | null;
  cameraConfig: CameraConfig | null;
  shareToken: string;
  views: number;
  isPublic: boolean;
  publishedAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
  jobId: string | null;
}

declare global {
  var prismaClientInstance: PrismaClient | undefined;
}

let prisma: PrismaClient | null = null;
let isPrismaAvailable = false;

try {
  if (process.env.DATABASE_URL) {
    prisma = globalThis.prismaClientInstance || new PrismaClient();
    if (process.env.NODE_ENV !== "production") {
      globalThis.prismaClientInstance = prisma;
    }
    isPrismaAvailable = true;
    console.log("[db] Prisma client initialized with DATABASE_URL:", process.env.DATABASE_URL.substring(0, 35) + "...");
  }
} catch (err) {
  console.warn("[db] Failed to initialize Prisma client:", err);
  prisma = null;
  isPrismaAvailable = false;
}

function handlePrismaError(err: any, context: string) {
  if (isPrismaAvailable) {
    console.warn(`[db] Prisma ${context} fallback to local store (${err?.name || "error"}).`);
    if (
      err?.name === "PrismaClientInitializationError" ||
      err?.code === "P1001" ||
      err?.code === "P1000"
    ) {
      isPrismaAvailable = false;
    }
  }
}

export { prisma };

// --- JSON Fallback Storage ---
const JSON_DB_PATH = path.join(__dirname, "../jobs.json");
const JSON_SPLATS_PATH = path.join(__dirname, "../splats.json");

function readJsonFile<T>(filePath: string): T[] {
  if (!fs.existsSync(filePath)) {
    fs.writeFileSync(filePath, JSON.stringify([]));
    return [];
  }
  try {
    const data = fs.readFileSync(filePath, "utf8");
    return JSON.parse(data, (key, value) => {
      if (key === "createdAt" || key === "updatedAt" || key === "publishedAt") {
        return value ? new Date(value) : null;
      }
      return value;
    });
  } catch (err) {
    console.error(`[db] Failed to read ${filePath}:`, err);
    return [];
  }
}

function writeJsonFile<T>(filePath: string, items: T[]) {
  try {
    fs.writeFileSync(filePath, JSON.stringify(items, null, 2));
  } catch (err) {
    console.error(`[db] Failed to write ${filePath}:`, err);
  }
}

// ---------------- JOB REPOSITORY ----------------

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

  if (prisma && isPrismaAvailable) {
    try {
      const created = await prisma.job.create({
        data: {
          id: newJob.id,
          status: newJob.status,
          progress: newJob.progress,
          imagesPath: newJob.imagesPath,
          logs: newJob.logs,
        },
      });
      return created as unknown as Job;
    } catch (err) {
      handlePrismaError(err, "createJob");
    }
  }

  const jobs = readJsonFile<Job>(JSON_DB_PATH);
  jobs.push(newJob);
  writeJsonFile(JSON_DB_PATH, jobs);
  return newJob;
}

export async function updateJob(
  id: string,
  data: Partial<Omit<Job, "id" | "createdAt">>
): Promise<Job | null> {
  const now = new Date();

  if (prisma && isPrismaAvailable) {
    try {
      const updated = await prisma.job.update({
        where: { id },
        data: {
          ...data,
          updatedAt: now,
        },
      });
      return updated as unknown as Job;
    } catch (err) {
      handlePrismaError(err, "updateJob");
    }
  }

  const jobs = readJsonFile<Job>(JSON_DB_PATH);
  const index = jobs.findIndex((j) => j.id === id);
  if (index === -1) return null;

  jobs[index] = {
    ...jobs[index],
    ...data,
    updatedAt: now,
  };
  writeJsonFile(JSON_DB_PATH, jobs);
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
  if (prisma && isPrismaAvailable) {
    try {
      const job = await prisma.job.findUnique({
        where: { id },
      });
      if (job) return job as unknown as Job;
    } catch (err) {
      handlePrismaError(err, "getJob");
    }
  }

  const jobs = readJsonFile<Job>(JSON_DB_PATH);
  return jobs.find((j) => j.id === id) || null;
}

export async function getJobs(): Promise<Job[]> {
  if (prisma && isPrismaAvailable) {
    try {
      const jobs = await prisma.job.findMany({
        orderBy: { createdAt: "desc" },
      });
      return jobs as unknown as Job[];
    } catch (err) {
      handlePrismaError(err, "getJobs");
    }
  }

  const jobs = readJsonFile<Job>(JSON_DB_PATH);
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

// ---------------- SPLAT & SHOWCASE REPOSITORY ----------------

function generateSlug(title: string): string {
  const base = title
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  const randomSuffix = Math.random().toString(36).substring(2, 7);
  return base ? `${base}-${randomSuffix}` : `splat-${randomSuffix}`;
}

export async function createSplat(data: {
  title: string;
  splatPath: string;
  description?: string;
  collisionPath?: string;
  thumbnailUrl?: string;
  cameraConfig?: CameraConfig;
  status?: "draft" | "published";
  isPublic?: boolean;
  jobId?: string;
}): Promise<Splat> {
  const id = "splat_" + Math.random().toString(36).substring(2, 11);
  const now = new Date();
  const slug = generateSlug(data.title);
  const shareToken = "tok_" + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
  const status = data.status || "draft";
  const publishedAt = status === "published" ? now : null;

  const newSplat: Splat = {
    id,
    title: data.title,
    slug,
    description: data.description || null,
    status,
    splatPath: data.splatPath,
    collisionPath: data.collisionPath || null,
    thumbnailUrl: data.thumbnailUrl || null,
    cameraConfig: data.cameraConfig || null,
    shareToken,
    views: 0,
    isPublic: data.isPublic !== undefined ? data.isPublic : true,
    publishedAt,
    createdAt: now,
    updatedAt: now,
    jobId: data.jobId || null,
  };

  if (prisma && isPrismaAvailable) {
    try {
      const created = await prisma.splat.create({
        data: {
          id: newSplat.id,
          title: newSplat.title,
          slug: newSplat.slug,
          description: newSplat.description,
          status: newSplat.status,
          splatPath: newSplat.splatPath,
          collisionPath: newSplat.collisionPath,
          thumbnailUrl: newSplat.thumbnailUrl,
          cameraConfig: newSplat.cameraConfig as any,
          shareToken: newSplat.shareToken,
          views: newSplat.views,
          isPublic: newSplat.isPublic,
          publishedAt: newSplat.publishedAt,
          jobId: newSplat.jobId,
        },
      });
      return created as unknown as Splat;
    } catch (err) {
      handlePrismaError(err, "createSplat");
    }
  }

  const splats = readJsonFile<Splat>(JSON_SPLATS_PATH);
  splats.push(newSplat);
  writeJsonFile(JSON_SPLATS_PATH, splats);
  return newSplat;
}

export async function updateSplat(
  id: string,
  data: Partial<Omit<Splat, "id" | "createdAt" | "shareToken">>
): Promise<Splat | null> {
  const now = new Date();

  if (prisma && isPrismaAvailable) {
    try {
      const updated = await prisma.splat.update({
        where: { id },
        data: {
          ...data,
          cameraConfig: data.cameraConfig ? (data.cameraConfig as any) : undefined,
          updatedAt: now,
        },
      });
      return updated as unknown as Splat;
    } catch (err) {
      handlePrismaError(err, "updateSplat");
    }
  }

  const splats = readJsonFile<Splat>(JSON_SPLATS_PATH);
  const index = splats.findIndex((s) => s.id === id);
  if (index === -1) return null;

  splats[index] = {
    ...splats[index],
    ...data,
    updatedAt: now,
  };
  writeJsonFile(JSON_SPLATS_PATH, splats);
  return splats[index];
}

export async function setSplatPublishStatus(
  id: string,
  status: "draft" | "published"
): Promise<Splat | null> {
  const now = new Date();
  const updateData: Partial<Splat> = {
    status,
    publishedAt: status === "published" ? now : null,
    updatedAt: now,
  };

  return updateSplat(id, updateData);
}

export async function getSplat(identifier: string): Promise<Splat | null> {
  if (prisma && isPrismaAvailable) {
    try {
      const splat = await prisma.splat.findFirst({
        where: {
          OR: [
            { id: identifier },
            { slug: identifier },
            { shareToken: identifier },
          ],
        },
      });
      if (splat) {
        return splat as unknown as Splat;
      }
    } catch (err) {
      handlePrismaError(err, "getSplat");
    }
  }

  const splats = readJsonFile<Splat>(JSON_SPLATS_PATH);
  return (
    splats.find(
      (s) =>
        s.id === identifier ||
        s.slug === identifier ||
        s.shareToken === identifier
    ) || null
  );
}

export async function incrementSplatViews(id: string): Promise<void> {
  if (prisma && isPrismaAvailable) {
    try {
      await prisma.splat.update({
        where: { id },
        data: { views: { increment: 1 } },
      });
      return;
    } catch (err) {
      handlePrismaError(err, "incrementSplatViews");
    }
  }

  const splats = readJsonFile<Splat>(JSON_SPLATS_PATH);
  const index = splats.findIndex((s) => s.id === id);
  if (index !== -1) {
    splats[index].views = (splats[index].views || 0) + 1;
    writeJsonFile(JSON_SPLATS_PATH, splats);
  }
}

export async function listSplats(onlyPublished = false): Promise<Splat[]> {
  if (prisma && isPrismaAvailable) {
    try {
      const splats = await prisma.splat.findMany({
        where: onlyPublished ? { status: "published" } : undefined,
        orderBy: { updatedAt: "desc" },
      });
      return splats as unknown as Splat[];
    } catch (err) {
      handlePrismaError(err, "listSplats");
    }
  }

  const splats = readJsonFile<Splat>(JSON_SPLATS_PATH);
  const filtered = onlyPublished
    ? splats.filter((s) => s.status === "published")
    : splats;
  return filtered.sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
}

export async function deleteSplat(id: string): Promise<boolean> {
  if (prisma && isPrismaAvailable) {
    try {
      await prisma.splat.delete({
        where: { id },
      });
      return true;
    } catch (err) {
      handlePrismaError(err, "deleteSplat");
    }
  }

  const splats = readJsonFile<Splat>(JSON_SPLATS_PATH);
  const index = splats.findIndex((s) => s.id === id);
  if (index === -1) return false;

  splats.splice(index, 1);
  writeJsonFile(JSON_SPLATS_PATH, splats);
  return true;
}
