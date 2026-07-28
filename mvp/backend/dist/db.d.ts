export interface Job {
    id: string;
    status: string;
    progress: number;
    createdAt: Date;
    updatedAt: Date;
    imagesPath: string;
    splatPath: string | null;
    logs: string | null;
}
export declare function createJob(imagesPath: string): Promise<Job>;
export declare function updateJob(id: string, data: Partial<Omit<Job, "id" | "createdAt" | "updatedAt">>): Promise<Job | null>;
export declare function getJob(id: string): Promise<Job | null>;
export declare function getJobs(): Promise<Job[]>;
