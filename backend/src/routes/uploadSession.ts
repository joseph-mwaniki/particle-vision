import { Router, Request, Response } from "express";
import crypto from "crypto";
import { prisma } from "../db";
import {
  abortMultipartUpload,
  completeMultipartUpload,
  createMultipartUpload,
  deleteObject,
  objectStorageConfigured,
  presignUploadPart,
} from "../services/objectStorage";

const MAX_FILES = Number(process.env.MAX_UPLOAD_FILES || 20);
const MAX_FILE_SIZE = Number(process.env.MAX_UPLOAD_FILE_SIZE || 5 * 1024 * 1024 * 1024);
const MAX_TOTAL_SIZE = Number(process.env.MAX_UPLOAD_TOTAL_SIZE || 20 * 1024 * 1024 * 1024);
const PART_SIZE = Math.max(5 * 1024 * 1024, Number(process.env.S3_UPLOAD_PART_SIZE || 64 * 1024 * 1024));
const SESSION_TTL_MS = Number(process.env.UPLOAD_SESSION_TTL_MS || 24 * 60 * 60 * 1000);

type CompletedPart = { PartNumber: number; ETag: string };

function requireDatabase() {
  if (!prisma) throw new Error("Database is required for multi-file uploads");
  return prisma;
}

function sessionResponse(session: any) {
  return {
    ...session,
    totalSize: Number(session.totalSize || 0),
    files: session.files?.map((file: any) => ({
      id: file.id,
      originalName: file.originalName,
      size: Number(file.size),
      totalParts: file.totalParts,
      status: file.status,
    })),
  };
}

function isVideoName(name: string) {
  const normalized = name.toLowerCase();
  return [".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".wmv", ".ts"].some((ext) => normalized.endsWith(ext));
}

async function createJobForSession(sessionId: string) {
  const database = requireDatabase();
  const session = await database.uploadSession.findUnique({
    where: { id: sessionId },
    include: { files: true },
  });
  if (!session) throw new Error("Upload session not found");
  const jobId = `job_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  const now = new Date();
  await database.$transaction(async (transaction) => {
    const claimed = await transaction.uploadSession.updateMany({
      where: { id: sessionId, status: "UPLOADING" },
      data: { status: "ASSEMBLING" },
    });
    if (claimed.count !== 1) throw new Error("Upload session is already being finalized");
    await transaction.job.create({
      data: {
        id: jobId,
        status: "PENDING",
        progress: 0,
        imagesPath: session.files[0].objectKey,
        uploadSessionId: sessionId,
        logs: `[${now.toISOString()}] Job created. Source files are stored in object storage. Ready to train.`,
      },
    });
    await transaction.uploadSession.update({
      where: { id: sessionId },
      data: { status: "ASSEMBLED", combinedKey: null },
    });
  });
}

export function createUploadSessionRouter(): Router {
  const router = Router();

  router.post("/", async (req: Request, res: Response) => {
    try {
      if (!objectStorageConfigured) return res.status(503).json({ error: "S3/R2 storage is not configured" });
      const database = requireDatabase();
      const id = `upload_${crypto.randomUUID()}`;
      const session = await database.uploadSession.create({
        data: {
          id,
          originalFileName: typeof req.body?.originalFileName === "string" ? req.body.originalFileName : "dataset.zip",
          storagePrefix: `uploads/${id}`,
          expiresAt: new Date(Date.now() + SESSION_TTL_MS),
        },
        include: { files: true },
      });
      res.status(201).json(sessionResponse(session));
    } catch (error) {
      res.status(500).json({ error: error instanceof Error ? error.message : "Failed to create upload session" });
    }
  });

  router.post("/:id/file", async (req: Request, res: Response) => {
    try {
      const database = requireDatabase();
      const session = await database.uploadSession.findUnique({ where: { id: req.params.id }, include: { files: true } });
      const originalName = typeof req.body?.originalName === "string" ? req.body.originalName : "";
      const size = Number(req.body?.size);
      if (!session) return res.status(404).json({ error: "Upload session not found" });
      if (session.status !== "UPLOADING") return res.status(400).json({ error: `Session is ${session.status}` });
      if (!isVideoName(originalName)) return res.status(400).json({ error: "Only video files are supported" });
      if (!Number.isSafeInteger(size) || size <= 0 || size > MAX_FILE_SIZE) return res.status(400).json({ error: "Invalid or oversized video file" });
      if (session.files.length >= 1) return res.status(400).json({ error: "Only one video file is allowed per job" });
      const currentTotal = session.files.reduce((sum: number, file: any) => sum + Number(file.size), 0);
      if (currentTotal + size > MAX_TOTAL_SIZE) return res.status(400).json({ error: "The total dataset size is too large" });

      const fileId = `file_${crypto.randomUUID()}`;
      const extension = originalName.includes(".") ? originalName.slice(originalName.lastIndexOf(".")) : ".mp4";
      const objectKey = `${session.storagePrefix}/source-${String(session.files.length + 1).padStart(3, "0")}${extension}`;
      const multipartId = await createMultipartUpload(objectKey);
      const totalParts = Math.ceil(size / PART_SIZE);
      const urls = await Promise.all(Array.from({ length: totalParts }, (_, index) => presignUploadPart(objectKey, multipartId, index + 1)));
      const file = await database.uploadFile.create({
        data: { id: fileId, sessionId: session.id, originalName, objectKey, size: BigInt(size), multipartId, partSize: PART_SIZE, totalParts },
      });
      await database.uploadSession.update({ where: { id: session.id }, data: { totalFiles: { increment: 1 }, totalSize: { increment: BigInt(size) } } });
      res.status(201).json({ fileId: file.id, partSize: PART_SIZE, totalParts, urls });
    } catch (error) {
      res.status(500).json({ error: error instanceof Error ? error.message : "Failed to initialize video upload" });
    }
  });

  router.post("/:id/file/:fileId/complete", async (req: Request, res: Response) => {
    try {
      const database = requireDatabase();
      const file = await database.uploadFile.findFirst({ where: { id: req.params.fileId, sessionId: req.params.id } });
      const parts = Array.isArray(req.body?.parts) ? req.body.parts as CompletedPart[] : [];
      if (!file) return res.status(404).json({ error: "Upload file not found" });
      const partNumbers = new Set(parts.map((part) => part.PartNumber));
      if (
        parts.length !== file.totalParts ||
        partNumbers.size !== file.totalParts ||
        parts.some((part) => !Number.isInteger(part.PartNumber) || part.PartNumber < 1 || part.PartNumber > file.totalParts || typeof part.ETag !== "string" || part.ETag.length === 0)
      ) {
        return res.status(400).json({ error: "Every multipart part must be completed" });
      }
      await completeMultipartUpload(file.objectKey, file.multipartId, parts);
      await database.uploadFile.update({ where: { id: file.id }, data: { status: "COMPLETE", completedParts: parts, completedAt: new Date() } });
      res.json({ fileId: file.id, status: "COMPLETE" });
    } catch (error) {
      res.status(500).json({ error: error instanceof Error ? error.message : "Failed to complete ZIP upload" });
    }
  });

  router.post("/:id/complete", async (req: Request, res: Response) => {
    try {
      const database = requireDatabase();
      const session = await database.uploadSession.findUnique({ where: { id: req.params.id }, include: { files: true } });
      if (!session) return res.status(404).json({ error: "Upload session not found" });
      if (!session.files.length || session.files.some((file: any) => file.status !== "COMPLETE")) return res.status(400).json({ error: "The video file must finish uploading first" });
      if (session.status !== "UPLOADING") return res.status(400).json({ error: `Session is already ${session.status}` });
      await createJobForSession(session.id);
      res.status(202).json({ id: session.id, status: "ASSEMBLED" });
    } catch (error) {
      res.status(500).json({ error: error instanceof Error ? error.message : "Failed to complete upload session" });
    }
  });

  router.get("/:id", async (req: Request, res: Response) => {
    try {
      const database = requireDatabase();
      const session = await database.uploadSession.findUnique({ where: { id: req.params.id }, include: { files: true, job: true } });
      if (!session) return res.status(404).json({ error: "Upload session not found" });
      res.json({ ...sessionResponse(session), jobId: session.job?.id || null, job: session.job || null });
    } catch (error) {
      res.status(500).json({ error: error instanceof Error ? error.message : "Failed to read upload session" });
    }
  });

  router.post("/:id/abort", async (req: Request, res: Response) => {
    try {
      const database = requireDatabase();
      const session = await database.uploadSession.findUnique({ where: { id: req.params.id }, include: { files: true } });
      if (!session) return res.status(404).json({ error: "Upload session not found" });
      await Promise.all(session.files.map(async (file: any) => {
        if (file.status === "UPLOADING") await abortMultipartUpload(file.objectKey, file.multipartId).catch(() => undefined);
        if (file.status === "COMPLETE") await deleteObject(file.objectKey).catch(() => undefined);
      }));
      await database.uploadSession.update({ where: { id: session.id }, data: { status: "ABORTED" } });
      res.json({ id: session.id, status: "ABORTED" });
    } catch (error) {
      res.status(500).json({ error: error instanceof Error ? error.message : "Failed to abort upload session" });
    }
  });

  return router;
}
