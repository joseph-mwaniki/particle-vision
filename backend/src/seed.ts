import { createSplat, listSplats } from "./db";
import * as dotenv from "dotenv";

dotenv.config();

async function main() {
  console.log("Seeding initial 3D Gaussian Splat scenes...");

  const existing = await listSplats();
  if (existing.length > 0) {
    console.log(`Found ${existing.length} existing splats, skipping seed.`);
    return;
  }

  // 1. Published Sample: Bonsai Tree Scene
  const bonsai = await createSplat({
    title: "Bonsai Tree Showcase",
    description: "High-resolution 3D Gaussian Splatting scan of a miniature Bonsai tree with intricate branch topology.",
    splatPath: "/samples/bonsai.splat",
    status: "published",
    isPublic: true,
    cameraConfig: {
      position: [0.5, 1.2, 2.5],
      target: [0, 0, 0],
    },
  });

  console.log("✅ Seeded Published Splat:", bonsai.title, `(Slug: ${bonsai.slug})`);

  // 2. Draft Sample: Architectural Space
  const draftScene = await createSplat({
    title: "Modern Architectural Pavilion (Draft)",
    description: "Draft 3D gaussian reconstruction under review before client sign-off.",
    splatPath: "/samples/bonsai.splat",
    status: "draft",
    isPublic: false,
    cameraConfig: {
      position: [1.0, 1.5, 3.0],
      target: [0, 0, 0],
    },
  });

  console.log("✅ Seeded Draft Splat:", draftScene.title, `(Share Token: ${draftScene.shareToken})`);
  console.log("Seeding complete!");
}

main()
  .catch((e) => {
    console.error("Seeding failed:", e);
  });
