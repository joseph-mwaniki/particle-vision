import {
  AbortMultipartUploadCommand,
  CompleteMultipartUploadCommand,
  CreateMultipartUploadCommand,
  DeleteObjectCommand,
  GetObjectCommand,
  HeadObjectCommand,
  PutObjectCommand,
  S3Client,
  UploadPartCommand,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { Readable } from "stream";

const bucket = process.env.S3_BUCKET;
const endpoint = process.env.S3_ENDPOINT;

export const objectStorageConfigured = Boolean(
  bucket && process.env.S3_ACCESS_KEY_ID && process.env.S3_SECRET_ACCESS_KEY
);

const client = objectStorageConfigured
  ? new S3Client({
      region: process.env.S3_REGION || "auto",
      endpoint,
      forcePathStyle: process.env.S3_FORCE_PATH_STYLE === "true",
      credentials: {
        accessKeyId: process.env.S3_ACCESS_KEY_ID as string,
        secretAccessKey: process.env.S3_SECRET_ACCESS_KEY as string,
      },
    })
  : null;

function requireStorage(): { client: S3Client; bucket: string } {
  if (!client || !bucket) {
    throw new Error("S3/R2 storage is not configured. Set S3_ENDPOINT, S3_REGION, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, and S3_BUCKET.");
  }
  return { client, bucket };
}

export async function createMultipartUpload(key: string, contentType = "application/zip") {
  const storage = requireStorage();
  const result = await storage.client.send(new CreateMultipartUploadCommand({
    Bucket: storage.bucket,
    Key: key,
    ContentType: contentType,
  }));
  if (!result.UploadId) throw new Error("Object storage did not return a multipart upload ID");
  return result.UploadId;
}

export async function presignUploadPart(key: string, uploadId: string, partNumber: number) {
  const storage = requireStorage();
  return getSignedUrl(
    storage.client,
    new UploadPartCommand({
      Bucket: storage.bucket,
      Key: key,
      UploadId: uploadId,
      PartNumber: partNumber,
    }),
    { expiresIn: Number(process.env.S3_PRESIGN_EXPIRES_SECONDS || 900) }
  );
}

export async function completeMultipartUpload(
  key: string,
  uploadId: string,
  parts: Array<{ PartNumber: number; ETag: string }>
) {
  const storage = requireStorage();
  await storage.client.send(new CompleteMultipartUploadCommand({
    Bucket: storage.bucket,
    Key: key,
    UploadId: uploadId,
    MultipartUpload: { Parts: parts.sort((a, b) => a.PartNumber - b.PartNumber) },
  }));
}

export async function abortMultipartUpload(key: string, uploadId: string) {
  const storage = requireStorage();
  await storage.client.send(new AbortMultipartUploadCommand({
    Bucket: storage.bucket,
    Key: key,
    UploadId: uploadId,
  }));
}

export async function deleteObject(key: string) {
  const storage = requireStorage();
  await storage.client.send(new DeleteObjectCommand({ Bucket: storage.bucket, Key: key }));
}

export async function getObjectStream(key: string): Promise<Readable> {
  const storage = requireStorage();
  const result = await storage.client.send(new GetObjectCommand({ Bucket: storage.bucket, Key: key }));
  if (!result.Body) throw new Error(`Object storage returned an empty body for ${key}`);
  return result.Body as Readable;
}

export async function putObjectStream(key: string, body: Readable, contentLength?: number) {
  const storage = requireStorage();
  await storage.client.send(new PutObjectCommand({
    Bucket: storage.bucket,
    Key: key,
    Body: body,
    ContentLength: contentLength,
    ContentType: "application/zip",
  }));
}

export async function headObject(key: string) {
  const storage = requireStorage();
  return storage.client.send(new HeadObjectCommand({ Bucket: storage.bucket, Key: key }));
}

export async function presignDownload(key: string) {
  const storage = requireStorage();
  return getSignedUrl(
    storage.client,
    new GetObjectCommand({ Bucket: storage.bucket, Key: key }),
    { expiresIn: Number(process.env.S3_DOWNLOAD_EXPIRES_SECONDS || 43200) }
  );
}
