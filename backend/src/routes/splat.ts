import { Router, Request, Response } from "express";
import {
  createSplat,
  getSplat,
  listSplats,
  updateSplat,
  setSplatPublishStatus,
  deleteSplat,
  incrementSplatViews,
} from "../db";
import { getObjectUrl, headObject, presignObjectUpload } from "../services/objectStorage";

const SPLAT_ARTIFACT_TYPES = {
  "processed-splat": { extension: "processed.splat", contentType: "application/octet-stream", field: "processedSplatPath" },
  "voxel-json": { extension: "voxel/scene.voxel.json", contentType: "application/json", field: "voxelPath" },
  "voxel-bin": { extension: "voxel/scene.voxel.bin", contentType: "application/octet-stream", field: null },
  "voxel-collision": { extension: "voxel/scene.collision.glb", contentType: "model/gltf-binary", field: "collisionPath" },
} as const;

type SplatArtifactType = keyof typeof SPLAT_ARTIFACT_TYPES;

function isSplatArtifactType(value: string): value is SplatArtifactType {
  return Object.hasOwn(SPLAT_ARTIFACT_TYPES, value);
}

function artifactAuthorized(req: Request): boolean {
  const configuredKey = process.env.API_KEY;
  return !configuredKey || req.headers["x-api-key"] === configuredKey;
}

function getBaseUrls(req: Request) {
  const frontendUrl =
    process.env.FRONTEND_URL || `${req.protocol}://${req.get("host")?.replace(/:\d+$/, ":5173")}`;
  const backendUrl =
    process.env.BACKEND_PUBLIC_URL || `${req.protocol}://${req.get("host")}`;
  return { frontendUrl, backendUrl };
}

async function formatSplatResponse(splat: any, req: Request) {
  const { frontendUrl } = getBaseUrls(req);
  const publicUrl = `${frontendUrl}/?view=${splat.slug}`;
  const previewDraftUrl = `${frontendUrl}/?view=${splat.slug}&token=${splat.shareToken}`;
  const embedCode = `<iframe src="${publicUrl}" width="100%" height="600" frameborder="0" allowfullscreen allow="accelerometer; gyroscope; vr"></iframe>`;
  const usePublicDelivery = splat.status === "published" && splat.isPublic;
  const assetUrl = (key: string | null) => {
    if (!key) return Promise.resolve(null);
    if (key.startsWith("/") || /^https?:\/\//i.test(key)) return Promise.resolve(key);
    return getObjectUrl(key, usePublicDelivery);
  };
  const [splatUrl, collisionUrl, processedSplatUrl, voxelUrl] = await Promise.all([
    assetUrl(splat.splatPath),
    assetUrl(splat.collisionPath),
    assetUrl(splat.processedSplatPath || null),
    assetUrl(splat.voxelPath || null),
  ]);

  return {
    ...splat,
    splatUrl,
    collisionUrl,
    processedSplatUrl,
    voxelUrl,
    publicUrl,
    previewDraftUrl,
    embedCode,
  };
}

export function createSplatRouter(): Router {
  const router = Router();

  // List all splats
  router.get("/", async (req: Request, res: Response) => {
    try {
      const onlyPublished = req.query.published === "true";
      const splats = await listSplats(onlyPublished);
      res.json(await Promise.all(splats.map((s) => formatSplatResponse(s, req))));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to list splats";
      res.status(500).json({ error: message });
    }
  });

  // Get splat by id, slug, or shareToken
  router.get("/:identifier", async (req: Request, res: Response) => {
    try {
      const { identifier } = req.params;
      const token = (req.query.token as string) || req.headers["x-share-token"];
      const apiKey = req.headers["x-api-key"] || req.query.apiKey;

      const splat = await getSplat(identifier);
      if (!splat) {
        return res.status(404).json({ error: "Splat scene not found" });
      }

      const isOwnerOrAdmin =
        apiKey && process.env.API_KEY && apiKey === process.env.API_KEY;
      const hasValidDraftToken =
        token && (token === splat.shareToken || identifier === splat.shareToken);

      // If draft and not authorized via token/admin, return 403
      if (splat.status === "draft" && !hasValidDraftToken && !isOwnerOrAdmin) {
        return res.status(403).json({
          error: "This 3D scene is currently in draft mode. Provide a valid share token to preview.",
          isDraft: true,
          slug: splat.slug,
        });
      }

      // If published, increment views count
      if (splat.status === "published") {
        incrementSplatViews(splat.id).catch(() => {});
      }

      res.json(await formatSplatResponse(splat, req));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to get splat";
      res.status(500).json({ error: message });
    }
  });

  // Create new splat scene
  router.post("/", async (req: Request, res: Response) => {
    try {
      const {
        title,
        splatPath,
        description,
        collisionPath,
        thumbnailUrl,
        cameraConfig,
        status = "draft",
        isPublic = true,
        jobId,
      } = req.body;

      if (!title || !splatPath) {
        return res.status(400).json({ error: "title and splatPath are required" });
      }

      const splat = await createSplat({
        title,
        splatPath,
        description,
        collisionPath,
        thumbnailUrl,
        cameraConfig,
        status,
        isPublic,
        jobId,
      });

      res.status(201).json(await formatSplatResponse(splat, req));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to create splat";
      res.status(500).json({ error: message });
    }
  });

  // Update splat scene
  router.patch("/:id", async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const updated = await updateSplat(id, req.body);
      if (!updated) {
        return res.status(404).json({ error: "Splat not found" });
      }
      res.json(await formatSplatResponse(updated, req));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to update splat";
      res.status(500).json({ error: message });
    }
  });

  // Toggle draft <-> published (inspired by Crusta's publish endpoint)
  router.post("/:id/publish", async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const { status = "published" } = req.body;

      if (status !== "published" && status !== "draft") {
        return res.status(400).json({ error: "status must be 'published' or 'draft'" });
      }

      const updated = await setSplatPublishStatus(id, status);
      if (!updated) {
        return res.status(404).json({ error: "Splat not found" });
      }

      const formatted = await formatSplatResponse(updated, req);
      res.json({
        message: status === "published" ? "Splat published successfully!" : "Splat unpublished to draft.",
        splat: formatted,
        publicUrl: formatted.publicUrl,
        status: updated.status,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to publish splat";
      res.status(500).json({ error: message });
    }
  });

  // Delete splat
  router.delete("/:id", async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const deleted = await deleteSplat(id);
      if (!deleted) {
        return res.status(404).json({ error: "Splat not found" });
      }
      res.json({ success: true, message: "Splat deleted successfully" });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to delete splat";
      res.status(500).json({ error: message });
    }
  });

  // Prepare artifact upload for Splat scene
  router.post("/:id/artifacts/:kind", async (req: Request, res: Response) => {
    try {
      if (!artifactAuthorized(req)) return res.status(401).json({ error: "Unauthorized" });
      const splat = await getSplat(req.params.id);
      if (!splat) return res.status(404).json({ error: "Splat not found" });
      if (!isSplatArtifactType(req.params.kind)) return res.status(400).json({ error: "Unsupported artifact type" });

      const artifact = SPLAT_ARTIFACT_TYPES[req.params.kind];
      const key = `splats/${splat.id}/${artifact.extension}`;
      const url = await presignObjectUpload(key, artifact.contentType);
      res.json({ key, url });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to prepare splat artifact upload";
      res.status(500).json({ error: message });
    }
  });

  // Complete artifact upload for Splat scene
  router.post("/:id/artifacts/:kind/complete", async (req: Request, res: Response) => {
    try {
      if (!artifactAuthorized(req)) return res.status(401).json({ error: "Unauthorized" });
      const splat = await getSplat(req.params.id);
      if (!splat) return res.status(404).json({ error: "Splat not found" });
      if (!isSplatArtifactType(req.params.kind)) return res.status(400).json({ error: "Unsupported artifact type" });

      const artifact = SPLAT_ARTIFACT_TYPES[req.params.kind];
      const key = `splats/${splat.id}/${artifact.extension}`;
      const stored = await headObject(key);
      if (!stored.ContentLength) return res.status(400).json({ error: "Uploaded artifact is missing or empty" });

      const updated = artifact.field
        ? await updateSplat(splat.id, { [artifact.field]: key })
        : splat;
      if (!updated) return res.status(404).json({ error: "Splat not found" });
      res.json(await formatSplatResponse(updated, req));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to confirm splat artifact upload";
      res.status(500).json({ error: message });
    }
  });

  return router;
}
