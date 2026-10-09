const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export interface Job {
  id: string;
  status: string;
  progress: number;
  createdAt: string;
  updatedAt: string;
  imagesPath: string;
  splatPath: string | null;
  collisionPath: string | null;
  splatUrl?: string | null;
  collisionUrl?: string | null;
  logs: string | null;
}

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
  processedSplatPath?: string | null;
  voxelPath?: string | null;
  voxelCollisionPath?: string | null;
  splatUrl?: string | null;
  collisionUrl?: string | null;
  processedSplatUrl?: string | null;
  voxelUrl?: string | null;
  voxelCollisionUrl?: string | null;
  thumbnailUrl: string | null;
  cameraConfig: CameraConfig | null;
  shareToken: string;
  views: number;
  isPublic: boolean;
  publishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  jobId: string | null;
  publicUrl?: string;
  previewDraftUrl?: string;
  embedCode?: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  timestamp: string;
}

export async function checkHealth(): Promise<HealthResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function listJobs(): Promise<Job[]> {
  const res = await fetch(`${API_BASE}/job`);
  if (!res.ok) throw new Error(`Failed to list jobs: ${res.status}`);
  return res.json();
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/job/${id}`);
  if (!res.ok) throw new Error(`Failed to get job: ${res.status}`);
  return res.json();
}

interface UploadFileInit {
  fileId: string;
  partSize: number;
  totalParts: number;
  urls: string[];
}

interface UploadSessionStatus {
  id: string;
  status: string;
  jobId: string | null;
  job: Job | null;
}

function uploadPart(url: string, body: Blob, onProgress: (loaded: number) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(`Object storage part upload failed: ${xhr.status}`));
        return;
      }
      const etag = xhr.getResponseHeader("ETag");
      if (!etag) {
        reject(new Error("Object storage did not expose the ETag header. Check the bucket CORS configuration."));
        return;
      }
      resolve(etag);
    };
    xhr.onerror = () => reject(new Error("Network error during object storage upload"));
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded);
    };
    xhr.send(body);
  });
}

export async function uploadVideoFiles(
  files: File[],
  onProgress?: (pct: number) => void,
  onStage?: (stage: string) => void,
): Promise<Job> {
  const sessionResponse = await fetch(`${API_BASE}/upload-session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ originalFileName: files[0]?.name || "capture.mp4" }),
  });
  if (!sessionResponse.ok) throw new Error(await sessionResponse.text());
  const session = await sessionResponse.json() as { id: string };
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  let uploadedBytes = 0;

  try {
    for (const file of files) {
      const isVideoFile = /\.(mp4|mov|m4v|mkv|avi|webm|wmv|ts)$/i.test(file.name);
      if (!isVideoFile) throw new Error(`${file.name} is not a supported video file`);
      onStage?.(`Uploading ${file.name}`);
      const initResponse = await fetch(`${API_BASE}/upload-session/${session.id}/file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ originalName: file.name, size: file.size }),
      });
      if (!initResponse.ok) throw new Error(await initResponse.text());
      const upload = await initResponse.json() as UploadFileInit;
      const parts: Array<{ PartNumber: number; ETag: string }> = [];
      for (let partNumber = 1; partNumber <= upload.totalParts; partNumber += 1) {
        const start = (partNumber - 1) * upload.partSize;
        const end = Math.min(start + upload.partSize, file.size);
        let partLoaded = 0;
        const etag = await uploadPart(upload.urls[partNumber - 1], file.slice(start, end), (loaded) => {
          uploadedBytes += loaded - partLoaded;
          partLoaded = loaded;
          onProgress?.((uploadedBytes / totalBytes) * 100);
        });
        uploadedBytes += (end - start) - partLoaded;
        onProgress?.((uploadedBytes / totalBytes) * 100);
        parts.push({ PartNumber: partNumber, ETag: etag });
      }
      const completeResponse = await fetch(`${API_BASE}/upload-session/${session.id}/file/${upload.fileId}/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ parts }),
      });
      if (!completeResponse.ok) throw new Error(await completeResponse.text());
    }

    onStage?.("Finalizing upload...");
    const completeResponse = await fetch(`${API_BASE}/upload-session/${session.id}/complete`, { method: "POST" });
    if (!completeResponse.ok) throw new Error(await completeResponse.text());

    for (;;) {
      const statusResponse = await fetch(`${API_BASE}/upload-session/${session.id}`);
      if (!statusResponse.ok) throw new Error(await statusResponse.text());
      const status = await statusResponse.json() as UploadSessionStatus;
      onStage?.(status.status === "ASSEMBLED" ? "Upload complete. Ready to start training." : "Finalizing upload...");
      if (status.status === "FAILED") throw new Error("Upload assembly failed. Check the backend logs for details.");
      if (status.status === "ASSEMBLED" && status.job) return status.job;
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  } catch (error) {
    await fetch(`${API_BASE}/upload-session/${session.id}/abort`, { method: "POST" }).catch(() => undefined);
    throw error;
  }
}

export async function uploadZipFiles(
  files: File[],
  onProgress?: (pct: number) => void,
  onStage?: (stage: string) => void,
): Promise<Job> {
  return uploadVideoFiles(files, onProgress, onStage);
}

export async function startTraining(jobId: string): Promise<{ message: string; jobId: string }> {
  const res = await fetch(`${API_BASE}/train`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jobId }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Training request failed: ${res.status}`);
  }

  return res.json();
}

export type JobArtifactKind = "processed-splat" | "voxel-json" | "voxel-bin" | "voxel-collision";

export async function uploadJobArtifact(jobId: string, kind: JobArtifactKind, blob: Blob): Promise<Job> {
  const apiKey = localStorage.getItem("pv_api_key");
  const headers: Record<string, string> = {};
  if (apiKey) headers["x-api-key"] = apiKey;

  const initResponse = await fetch(`${API_BASE}/job/${encodeURIComponent(jobId)}/artifacts/${kind}`, {
    method: "POST",
    headers,
  });
  if (!initResponse.ok) throw new Error(await initResponse.text());
  const upload = await initResponse.json() as { key: string; url: string };

  const uploadResponse = await fetch(upload.url, {
    method: "PUT",
    headers: { "Content-Type": kind === "voxel-json" ? "application/json" : kind === "voxel-collision" ? "model/gltf-binary" : "application/octet-stream" },
    body: blob,
  });
  if (!uploadResponse.ok) throw new Error(`R2 artifact upload failed: ${uploadResponse.status}`);

  const completeResponse = await fetch(`${API_BASE}/job/${encodeURIComponent(jobId)}/artifacts/${kind}/complete`, {
    method: "POST",
    headers,
  });
  if (!completeResponse.ok) throw new Error(await completeResponse.text());
  return completeResponse.json() as Promise<Job>;
}

// ---------------- SPLATS & SHOWCASE API ----------------

export async function listSplats(onlyPublished = false): Promise<Splat[]> {
  const url = `${API_BASE}/splats${onlyPublished ? "?published=true" : ""}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to list splats: ${res.status}`);
  return res.json();
}

export async function getSplat(identifier: string, token?: string, apiKey?: string): Promise<Splat> {
  const params = new URLSearchParams();
  if (token) params.set("token", token);
  if (apiKey) params.set("apiKey", apiKey);

  const query = params.toString() ? `?${params.toString()}` : "";
  const headers: Record<string, string> = {};
  if (token) headers["x-share-token"] = token;
  if (apiKey) headers["x-api-key"] = apiKey;

  const res = await fetch(`${API_BASE}/splats/${encodeURIComponent(identifier)}${query}`, {
    headers,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error || `Failed to fetch splat: ${res.status}`);
  }

  return res.json();
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
  const res = await fetch(`${API_BASE}/splats`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to create splat: ${res.status}`);
  }

  return res.json();
}

export async function updateSplat(
  id: string,
  data: Partial<Omit<Splat, "id" | "createdAt" | "shareToken">>
): Promise<Splat> {
  const res = await fetch(`${API_BASE}/splats/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to update splat: ${res.status}`);
  }

  return res.json();
}

export async function publishSplat(
  id: string,
  status: "draft" | "published"
): Promise<{ message: string; splat: Splat; publicUrl: string; status: string }> {
  const res = await fetch(`${API_BASE}/splats/${id}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to change publish status: ${res.status}`);
  }

  return res.json();
}

export async function deleteSplat(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/splats/${id}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to delete splat: ${res.status}`);
  }
}

export function assetUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  if (path.startsWith("/samples/")) return path;
  if (path.startsWith("/")) return `${API_BASE}${path}`;
  return `${API_BASE}/${path}`;
}
