-- CreateTable
CREATE TABLE "Job" (
    "id" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "progress" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "imagesPath" TEXT NOT NULL,
    "splatPath" TEXT,
    "collisionPath" TEXT,
    "logs" TEXT,

    CONSTRAINT "Job_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Splat" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "description" TEXT,
    "status" TEXT NOT NULL DEFAULT 'draft',
    "splatPath" TEXT NOT NULL,
    "collisionPath" TEXT,
    "thumbnailUrl" TEXT,
    "cameraConfig" JSONB,
    "shareToken" TEXT NOT NULL,
    "views" INTEGER NOT NULL DEFAULT 0,
    "isPublic" BOOLEAN NOT NULL DEFAULT true,
    "publishedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "jobId" TEXT,

    CONSTRAINT "Splat_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "Splat_slug_key" ON "Splat"("slug");

-- CreateIndex
CREATE UNIQUE INDEX "Splat_shareToken_key" ON "Splat"("shareToken");

-- CreateIndex
CREATE INDEX "Splat_slug_idx" ON "Splat"("slug");

-- CreateIndex
CREATE INDEX "Splat_status_idx" ON "Splat"("status");

-- CreateIndex
CREATE INDEX "Splat_shareToken_idx" ON "Splat"("shareToken");

-- AddForeignKey
ALTER TABLE "Splat" ADD CONSTRAINT "Splat_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "Job"("id") ON DELETE SET NULL ON UPDATE CASCADE;
