const API_BASE = import.meta.env.VITE_API_BASE || "/api";
export async function checkHealth() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        if (!res.ok)
            return null;
        return res.json();
    }
    catch {
        return null;
    }
}
export async function listJobs() {
    const res = await fetch(`${API_BASE}/job`);
    if (!res.ok)
        throw new Error(`Failed to list jobs: ${res.status}`);
    return res.json();
}
export async function getJob(id) {
    const res = await fetch(`${API_BASE}/job/${id}`);
    if (!res.ok)
        throw new Error(`Failed to get job: ${res.status}`);
    return res.json();
}
export async function uploadImages(file, onProgress) {
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
            }
            else {
                reject(new Error(xhr.responseText || `Upload failed: ${xhr.status}`));
            }
        };
        xhr.onerror = () => reject(new Error("Network error during upload"));
        xhr.send(formData);
    });
}
function uploadPart(url, body, onProgress) {
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
            if (event.lengthComputable)
                onProgress(event.loaded);
        };
        xhr.send(body);
    });
}
export async function uploadZipFiles(files, onProgress, onStage) {
    const sessionResponse = await fetch(`${API_BASE}/upload-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ originalFileName: files[0]?.name || "dataset.zip" }),
    });
    if (!sessionResponse.ok)
        throw new Error(await sessionResponse.text());
    const session = await sessionResponse.json();
    const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
    let uploadedBytes = 0;
    try {
        for (const file of files) {
            if (!file.name.toLowerCase().endsWith(".zip"))
                throw new Error(`${file.name} is not a ZIP file`);
            onStage?.(`Uploading ${file.name}`);
            const initResponse = await fetch(`${API_BASE}/upload-session/${session.id}/file`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ originalName: file.name, size: file.size }),
            });
            if (!initResponse.ok)
                throw new Error(await initResponse.text());
            const upload = await initResponse.json();
            const parts = [];
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
            if (!completeResponse.ok)
                throw new Error(await completeResponse.text());
        }
        onStage?.("Combining files...");
        const completeResponse = await fetch(`${API_BASE}/upload-session/${session.id}/complete`, { method: "POST" });
        if (!completeResponse.ok)
            throw new Error(await completeResponse.text());
        for (;;) {
            const statusResponse = await fetch(`${API_BASE}/upload-session/${session.id}`);
            if (!statusResponse.ok)
                throw new Error(await statusResponse.text());
            const status = await statusResponse.json();
            onStage?.(status.status === "ASSEMBLED" ? "Files combined. Ready to start training." : "Combining files...");
            if (status.status === "FAILED")
                throw new Error("Upload assembly failed. Check the backend logs for details.");
            if (status.status === "ASSEMBLED" && status.job)
                return status.job;
            await new Promise((resolve) => setTimeout(resolve, 2000));
        }
    }
    catch (error) {
        await fetch(`${API_BASE}/upload-session/${session.id}/abort`, { method: "POST" }).catch(() => undefined);
        throw error;
    }
}
export async function startTraining(jobId) {
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
export async function listSplats(onlyPublished = false) {
    const url = `${API_BASE}/splats${onlyPublished ? "?published=true" : ""}`;
    const res = await fetch(url);
    if (!res.ok)
        throw new Error(`Failed to list splats: ${res.status}`);
    return res.json();
}
export async function getSplat(identifier, token, apiKey) {
    const params = new URLSearchParams();
    if (token)
        params.set("token", token);
    if (apiKey)
        params.set("apiKey", apiKey);
    const query = params.toString() ? `?${params.toString()}` : "";
    const headers = {};
    if (token)
        headers["x-share-token"] = token;
    if (apiKey)
        headers["x-api-key"] = apiKey;
    const res = await fetch(`${API_BASE}/splats/${encodeURIComponent(identifier)}${query}`, {
        headers,
    });
    if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.error || `Failed to fetch splat: ${res.status}`);
    }
    return res.json();
}
export async function createSplat(data) {
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
export async function updateSplat(id, data) {
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
export async function publishSplat(id, status) {
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
export async function deleteSplat(id) {
    const res = await fetch(`${API_BASE}/splats/${id}`, {
        method: "DELETE",
    });
    if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Failed to delete splat: ${res.status}`);
    }
}
export function assetUrl(path) {
    if (!path)
        return "";
    if (path.startsWith("http://") || path.startsWith("https://"))
        return path;
    if (path.startsWith("/"))
        return `${API_BASE}${path}`;
    return `${API_BASE}/${path}`;
}
