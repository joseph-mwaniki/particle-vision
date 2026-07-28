"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.createJob = createJob;
exports.updateJob = updateJob;
exports.getJob = getJob;
exports.getJobs = getJobs;
const client_1 = require("@prisma/client");
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
let prisma = null;
const useFallback = !process.env.DATABASE_URL;
if (!useFallback) {
    try {
        prisma = new client_1.PrismaClient();
    }
    catch (err) {
        console.error("Failed to initialize Prisma client, falling back to local JSON database:", err);
    }
}
const JSON_DB_PATH = path.join(__dirname, "../jobs.json");
function readJsonDb() {
    if (!fs.existsSync(JSON_DB_PATH)) {
        fs.writeFileSync(JSON_DB_PATH, JSON.stringify([]));
        return [];
    }
    try {
        const data = fs.readFileSync(JSON_DB_PATH, "utf8");
        return JSON.parse(data, (key, value) => {
            if (key === "createdAt" || key === "updatedAt") {
                return new Date(value);
            }
            return value;
        });
    }
    catch (err) {
        console.error("Failed to read JSON DB:", err);
        return [];
    }
}
function writeJsonDb(jobs) {
    try {
        fs.writeFileSync(JSON_DB_PATH, JSON.stringify(jobs, null, 2));
    }
    catch (err) {
        console.error("Failed to write JSON DB:", err);
    }
}
async function createJob(imagesPath) {
    const id = "job_" + Math.random().toString(36).substr(2, 9);
    const now = new Date();
    const newJob = {
        id,
        status: "PENDING_PAYMENT",
        progress: 0.0,
        createdAt: now,
        updatedAt: now,
        imagesPath,
        splatPath: null,
        logs: "Job created. Waiting for payment checkout.",
    };
    if (prisma && !useFallback) {
        try {
            return await prisma.job.create({
                data: {
                    id: newJob.id,
                    status: newJob.status,
                    progress: newJob.progress,
                    imagesPath: newJob.imagesPath,
                    logs: newJob.logs,
                },
            });
        }
        catch (err) {
            console.error("Prisma createJob error, falling back:", err);
        }
    }
    const jobs = readJsonDb();
    jobs.push(newJob);
    writeJsonDb(jobs);
    return newJob;
}
async function updateJob(id, data) {
    const now = new Date();
    if (prisma && !useFallback) {
        try {
            return await prisma.job.update({
                where: { id },
                data: {
                    ...data,
                    updatedAt: now,
                },
            });
        }
        catch (err) {
            console.error("Prisma updateJob error, falling back:", err);
        }
    }
    const jobs = readJsonDb();
    const index = jobs.findIndex((j) => j.id === id);
    if (index === -1)
        return null;
    jobs[index] = {
        ...jobs[index],
        ...data,
        updatedAt: now,
    };
    writeJsonDb(jobs);
    return jobs[index];
}
async function getJob(id) {
    if (prisma && !useFallback) {
        try {
            return await prisma.job.findUnique({
                where: { id },
            });
        }
        catch (err) {
            console.error("Prisma getJob error, falling back:", err);
        }
    }
    const jobs = readJsonDb();
    return jobs.find((j) => j.id === id) || null;
}
async function getJobs() {
    if (prisma && !useFallback) {
        try {
            return await prisma.job.findMany({
                orderBy: { createdAt: "desc" },
            });
        }
        catch (err) {
            console.error("Prisma getJobs error, falling back:", err);
        }
    }
    const jobs = readJsonDb();
    return jobs.sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());
}
