// Client-side screenshot normalization before upload (roadmap §7.3, §13):
// deliberately re-encode to JPEG (strips EXIF/metadata and bakes orientation)
// and cap the longest edge so uploads stay small and under the server's
// dimension limit. The picker already requests exif:false; this makes the
// normalization explicit instead of a side effect.

import { File } from "expo-file-system";
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import { Image } from "react-native";

const MAX_DIMENSION = 2000;

async function measure(uri: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve) => {
    Image.getSize(uri,
      (width, height) => resolve({ width, height }),
      () => resolve({ width: 0, height: 0 }));
  });
}

async function normalizeScreenshot(asset: {
  uri: string;
  width?: number;
  height?: number;
}): Promise<string> {
  // The picker reports width/height as 0 for some cloud-backed items, so an
  // unknown size is measured rather than assumed small — otherwise an oversized
  // screenshot would skip the resize and be rejected by the server.
  let { width = 0, height = 0 } = asset;
  if (width <= 0 || height <= 0) ({ width, height } = await measure(asset.uri));

  // Always re-encode, even when no resize is needed: the JPEG round-trip is
  // what actually drops metadata and bakes in the orientation.
  const oversized = Math.max(width, height) > MAX_DIMENSION;
  const actions = oversized
    ? [{ resize: width >= height ? { width: MAX_DIMENSION } : { height: MAX_DIMENSION } }]
    : [];
  const normalized = await manipulateAsync(asset.uri, actions,
                                           { compress: 0.8, format: SaveFormat.JPEG });
  return normalized.uri;
}

// An image downloaded through the API client, as a data: URI for <Image>.
// The bytes stay in memory — decrypted evidence is never written to the
// phone's storage. Built in chunks so a large screenshot never exceeds the
// engine's argument limit for String.fromCharCode.
export function imageDataUri(buffer: ArrayBuffer, mimeType: string): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x2000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x2000));
  }
  return `data:${mimeType};base64,${btoa(binary)}`;
}

// The multipart body for POST /v1/ocr and /v1/cases/{id}/evidence ("file").
// Expo's global fetch (expo/fetch) only accepts Blob-like FormData parts and
// rejects React Native's { uri, name, type } objects before the request
// leaves the phone, so the file goes in as an expo-file-system File, which
// implements Blob (name, type, bytes).
export async function screenshotFormData(asset: {
  uri: string;
  width?: number;
  height?: number;
}): Promise<FormData> {
  const form = new FormData();
  form.append("file", new File(await normalizeScreenshot(asset)));
  return form;
}
