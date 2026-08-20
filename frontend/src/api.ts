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

export async function uploadImages(file: File, onProgress?: (pct: number) => void): Promise<Job> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("images", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/upload`);

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress((e.loaded / e.total) * 100);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status === 201) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(xhr.responseText || `Upload failed: ${xhr.status}`));
      }
    };

    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(formData);
  });
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
  if (path.startsWith("/")) return `${API_BASE}${path}`;
  return `${API_BASE}/${path}`;
}
