export function validateTrainRequest(body: unknown): { jobId: string } | { error: string } {
  if (!body || typeof body !== "object") {
    return { error: "Request body must be a JSON object" };
  }

  const { jobId } = body as Record<string, unknown>;

  if (typeof jobId !== "string" || jobId.trim().length === 0) {
    return { error: "jobId is required and must be a non-empty string" };
  }

  if (!/^job_[a-z0-9]+$/.test(jobId)) {
    return { error: "jobId format is invalid" };
  }

  return { jobId };
}

export function validateWorkerCallback(body: unknown): { valid: true } | { error: string } {
  if (!body || typeof body !== "object") {
    return { error: "Request body must be a JSON object" };
  }

  const payload = body as Record<string, unknown>;

  if (typeof payload.job_id !== "string") {
    return { error: "job_id is required" };
  }

  if (typeof payload.status !== "string") {
    return { error: "status is required" };
  }

  if (typeof payload.progress !== "number") {
    return { error: "progress is required and must be a number" };
  }

  return { valid: true };
}
