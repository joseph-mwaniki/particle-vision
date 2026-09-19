import { PassThrough } from "stream";
import unzipper from "unzipper";

type Archive = {
  on(event: string, listener: (error: Error) => void): Archive;
  pipe(destination: PassThrough): Archive;
  append(source: NodeJS.ReadableStream, options: { name: string }): Archive;
  finalize(): Promise<void>;
  destroy(): void;
};
import { getObjectStream, headObject, putObjectStream } from "./objectStorage";

const imageExtensions = new Set([".jpg", ".jpeg", ".png", ".webp"]);

function safeEntryName(value: string): string | null {
  const normalized = value.replace(/\\/g, "/").replace(/^\/+/, "");
  if (!normalized || normalized.split("/").some((part) => part === "..")) return null;
  const clean = normalized.split("/").filter(Boolean).join("/");
  return clean || null;
}

function sourceNamespace(originalName: string, index: number): string {
  const base = originalName.replace(/\.zip$/i, "").replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-|-$/g, "");
  return `${String(index + 1).padStart(3, "0")}-${base || "source"}`;
}

export async function assembleZip(
  sessionId: string,
  files: Array<{ objectKey: string; originalName: string }>,
  combinedKey: string,
  onLog?: (message: string) => void,
): Promise<number> {
  const archiver = (await import("archiver")) as unknown as (
    format: string,
    options?: { zlib?: { level?: number } },
  ) => Archive;
  const archive = archiver("zip", { zlib: { level: 0 } });
  const output = new PassThrough();
  const uploadPromise = putObjectStream(combinedKey, output);
  let imageCount = 0;

  archive.on("warning", (error: Error) => onLog?.(`ZIP warning: ${error.message}`));
  archive.on("error", (error: Error) => output.destroy(error));
  archive.pipe(output);

  try {
    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      onLog?.(`Reading ${file.originalName}`);
      const parser = getObjectStream(file.objectKey).then((stream) => stream.pipe(unzipper.Parse({ forceStream: true })));
      for await (const entry of await parser) {
        const entryName = safeEntryName(entry.path);
        const extension = entryName ? entryName.slice(entryName.lastIndexOf(".")).toLowerCase() : "";
        if (!entryName || entry.type === "Directory" || !imageExtensions.has(extension)) {
          entry.autodrain();
          continue;
        }
        archive.append(entry, { name: `${sourceNamespace(file.originalName, index)}/${entryName}` });
        imageCount += 1;
      }
    }

    if (imageCount === 0) throw new Error("No supported images were found in the uploaded ZIP files");
    await archive.finalize();
    await uploadPromise;
    const head = await headObject(combinedKey);
    if (!head.ContentLength) throw new Error("Combined ZIP was uploaded but is empty");
    onLog?.(`Created combined ZIP with ${imageCount} images (${head.ContentLength} bytes)`);
    return imageCount;
  } catch (error) {
    archive.destroy();
    output.destroy(error instanceof Error ? error : new Error(String(error)));
    await uploadPromise.catch(() => undefined);
    throw error;
  }
}
