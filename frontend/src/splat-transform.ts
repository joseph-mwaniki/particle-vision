import {
  createChunkDataPool,
  getInputFormat,
  materializeToDataTable,
  MemoryFileSystem,
  MemoryReadFileSystem,
  processSourceBridged,
  readFile,
  writeSource,
  writeVoxel,
  type ProcessAction,
} from "@playcanvas/splat-transform";
import { createGraphicsDevice, Vec3 } from "playcanvas";

export interface SplatTransformOptions {
  translation: [number, number, number];
  rotation: [number, number, number];
  scale: number;
}

export interface GeneratedArtifact {
  filename: string;
  blob: Blob;
}

function asBlob(data: Uint8Array, type: string): Blob {
  const copy = new Uint8Array(data.byteLength);
  copy.set(data);
  return new Blob([copy], { type });
}

async function loadSource(blob: Blob) {
  const filename = "scene.splat";
  const input = new MemoryReadFileSystem();
  input.set(filename, new Uint8Array(await blob.arrayBuffer()));
  const sources = await readFile({
    filename,
    inputFormat: getInputFormat(filename),
    fileSystem: input,
  });
  const source = sources[0];
  if (!source) throw new Error("SplatTransform could not read the source splat.");
  const pool = createChunkDataPool();
  return { source, pool };
}

export async function transformSplat(blob: Blob, transform: SplatTransformOptions): Promise<Blob> {
  if (!Number.isFinite(transform.scale) || transform.scale <= 0) {
    throw new Error("Scale must be a positive number.");
  }

  const { source, pool } = await loadSource(blob);
  const actions: ProcessAction[] = [
    { kind: "translate", value: new Vec3(...transform.translation) },
    { kind: "rotate", value: new Vec3(...transform.rotation) },
    { kind: "scale", value: transform.scale },
  ];

  try {
    const processed = await processSourceBridged(source, actions, pool);
    const output = new MemoryFileSystem();
    await writeSource({
      filename: "processed-scene.splat",
      outputFormat: "splat",
      source: processed,
      pool,
      options: {},
    }, output);
    const data = output.results.get("processed-scene.splat");
    if (!data) throw new Error("SplatTransform did not produce a processed splat.");
    return asBlob(data, "application/octet-stream");
  } finally {
    source.close();
    pool.destroy();
  }
}

export async function voxelizeSplat(
  blob: Blob,
  voxelResolution = 0.2,
  onStage?: (stage: string) => void,
): Promise<GeneratedArtifact[]> {
  onStage?.("Reading splat data...");
  const { source, pool } = await loadSource(blob);
  const output = new MemoryFileSystem();

  try {
    onStage?.("Preparing voxel data...");
    const dataTable = await materializeToDataTable(source, pool);
    onStage?.("Preparing WebGPU...");
    await writeVoxel({
      filename: "scene.voxel.json",
      dataTable,
      voxelResolution,
      opacityCutoff: 0.1,
      collisionMesh: true,
      createDevice: async () => {
        onStage?.("Creating WebGPU device...");
        const canvas = document.createElement("canvas");
        const device = await createGraphicsDevice(canvas, {
          deviceTypes: ["webgpu"],
          depth: false,
          stencil: false,
        });
        if (!device.isWebGPU) {
          device.destroy();
          throw new Error("WebGPU is required for SplatTransform voxelization.");
        }
        onStage?.("Running GPU voxelization...");
        return device;
      },
    }, output);

    onStage?.("Packing voxel files...");
    return [...output.results.entries()].map(([filename, data]) => ({
      filename,
      blob: asBlob(data, filename.endsWith(".glb") ? "model/gltf-binary" : "application/octet-stream"),
    }));
  } finally {
    source.close();
    pool.destroy();
  }
}