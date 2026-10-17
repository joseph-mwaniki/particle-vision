-- AlterTable
ALTER TABLE "Job" ADD COLUMN     "frameSelectionPath" TEXT,
ADD COLUMN     "processedSplatPath" TEXT,
ADD COLUMN     "videoPath" TEXT,
ADD COLUMN     "voxelCollisionPath" TEXT,
ADD COLUMN     "voxelPath" TEXT;

-- AlterTable
ALTER TABLE "Splat" ADD COLUMN     "processedSplatPath" TEXT,
ADD COLUMN     "voxelPath" TEXT;
