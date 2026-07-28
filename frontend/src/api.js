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
export function assetUrl(path) {
    if (path.startsWith("http"))
        return path;
    return `${API_BASE}${path}`;
}
