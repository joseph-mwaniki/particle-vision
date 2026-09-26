export type JobStatus =
  | "PENDING"
  | "QUEUED"
  | "PROCESSING_COLMAP"
  | "PROCESSING_GSPLAT"
  | "PROCESSING_COLLISION"
  | "PROCESSING_EXPORT"
  | "COMPLETED"
  | "FAILED";

export interface Job {
  id: string;
  status: JobStatus;
  progress: number;
  createdAt: Date;
  updatedAt: Date;
  imagesPath: string;
  splatPath: string | null;
  collisionPath: string | null;
  logs: string | null;
  uploadSessionId?: string | null;
}

export interface WorkerRunRequest {
  job_id: string;
  source_files: Array<{ download_url: string; original_name: string }>;
  output_uploads: {
    splat: { key: string; url: string };
    collision: { key: string; url: string };
  };
  callback_url: string;
}

export interface WorkerRunResponse {
  job_id: string;
  status: "accepted" | "rejected";
  message?: string;
}

export interface WorkerCallbackPayload {
  job_id: string;
  status: JobStatus;
  progress: number;
  log?: string;
  splat_key?: string;
  collision_key?: string;
  error?: string;
}
