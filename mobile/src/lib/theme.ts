// Calm pastel palette. Risk is always shown as icon + text + color together,
// never color alone (roadmap §8.5). Text colors keep WCAG AA contrast on
// their pastel surfaces.

import type { PrimaryLabel, Severity } from "./types";

export const colors = {
  background: "#F6F4FB",
  surface: "#FFFFFF",
  primary: "#6C5FC7",
  primaryDark: "#554AA3",
  text: "#2A2740",
  muted: "#666181",
  border: "#E4E0F0",
  danger: "#B3261E",
  inputBg: "#FBFAFE",
};

export interface SeverityMeta {
  label: string;
  icon: string;
  fg: string;
  bg: string;
  description: string;
}

export const severityMeta: Record<Severity, SeverityMeta> = {
  safe: {
    label: "Safe", icon: "✓", fg: "#1E6B27", bg: "#E7F4E8",
    description: "No clear harmful-language signal detected.",
  },
  caution: {
    label: "Caution", icon: "!", fg: "#7A5E00", bg: "#FFF3D1",
    description: "The text may contain offensive language.",
  },
  high: {
    label: "High", icon: "▲", fg: "#9A3D00", bg: "#FFE7D6",
    description: "The text may contain targeted or identity-based abuse signals.",
  },
  critical: {
    label: "Critical", icon: "⚠", fg: "#A32018", bg: "#FCE1DF",
    description: "The text may contain threatening language.",
  },
};

export const labelText: Record<PrimaryLabel, string> = {
  normal: "Normal",
  offensive: "Offensive",
  harassment: "Harassment",
  hate_speech: "Hate speech",
  threat: "Threat",
};

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function confidencePercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}
