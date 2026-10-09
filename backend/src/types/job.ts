export type JobStatus =
  | "PENDING"
  | "QUEUED"
  | "PROCESSING_FRAME_SELECTION"
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
  videoPath?: string | null;
  frameSelectionPath?: string | null;
  splatPath: string | null;
  collisionPath: string | null;
  processedSplatPath?: string | null;
  voxelPath?: string | null;
  voxelCollisionPath?: string | null;
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
