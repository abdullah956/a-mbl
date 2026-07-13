// Client-side screenshot normalization before upload (roadmap §7.3, §13):
// deliberately re-encode to JPEG (strips EXIF/metadata and bakes orientation)
// and cap the longest edge so uploads stay small and under the server's
// dimension limit. The picker already requests exif:false; this makes the
// normalization explicit instead of a side effect.

import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import { Image } from "react-native";

const MAX_DIMENSION = 2000;

export interface UploadImage {
  uri: string;
  name: string;
  type: string;
}

async function measure(uri: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve) => {
    Image.getSize(uri,
      (width, height) => resolve({ width, height }),
      () => resolve({ width: 0, height: 0 }));
  });
}

export async function normalizeScreenshot(asset: {
  uri: string;
  width?: number;
  height?: number;
  fileName?: string | null;
  mimeType?: string | null;
}): Promise<UploadImage> {
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
  return { uri: normalized.uri, name: "screenshot.jpg", type: "image/jpeg" };
}
