// API contract types — mirror backend/app/schemas.py (single source of truth
// is the FastAPI OpenAPI document at /docs on the local server).

export type Role = "user" | "guardian" | "school_admin";
export type PrimaryLabel = "normal" | "offensive" | "harassment" | "hate_speech" | "threat";
export type Severity = "safe" | "caution" | "high" | "critical";

export interface User {
  id: string;
  email: string;
  displayName: string;
  role: Role;
  ageBand: "13-17" | "18+";
  status: "pending_guardian" | "active";
  createdAt: string;
  organizations: { id: string; name: string }[];
  // Advisory: the backend SQL scope is what actually enforces access.
  permissions: Record<string, boolean>;
}

export interface AuthResponse {
  accessToken: string;
  refreshToken: string;
  user: User;
  linkCode?: string | null;
  linkCodeExpiresAt?: string | null;
}

export interface Health {
  status: string;
  modelVersion: string;
  modelReady: boolean;
  ocrReady: boolean;
  time: string;
}

export interface AnalysisResult {
  id: string;
  primaryLabel: PrimaryLabel;
  confidence: number;
  bodyShaming: boolean;
  severity: Severity;
  needsReview: boolean;
  advice: string[];
  modelVersion: string;
  retainedUntil: string | null;
  caseId: string | null;
}

export interface CaseSummary {
  id: string;
  primaryLabel: PrimaryLabel;
  severity: Severity;
  confidence: number;
  bodyShaming: boolean;
  status: "new" | "reviewed";
  sourceType: "text" | "screenshot";
  ownerName: string;
  isOwn: boolean;
  platformName: string | null;
  senderAlias: string | null;
  createdAt: string;
  expiresAt: string;
  hasEvidence: boolean;
  reviewCount: number;
  reviewRequested: boolean;
}

export interface Review {
  id: string;
  reviewerName: string;
  reviewerRole: Role;
  humanLabel: PrimaryLabel | null;
  note: string | null;
  createdAt: string;
}

export interface Share {
  id: string;
  organizationId: string;
  organizationName: string;
  sharedAt: string;
}

export interface Evidence {
  id: string;
  mimeType: string;
  sizeBytes: number;
  createdAt: string;
}

export interface CaseDetail extends CaseSummary {
  text: string;
  maskedPreview: string;
  needsReview: boolean;
  modelVersion: string;
  reviews: Review[];
  shares: Share[];
  evidence: Evidence[];
}

export interface CaseList {
  items: CaseSummary[];
  total: number;
  page: number;
  pageSize: number;
}

export interface AppAlert {
  id: string;
  caseId: string;
  severity: Severity;
  primaryLabel: PrimaryLabel;
  subjectName: string;
  createdAt: string;
  readAt: string | null;
}

export interface GuardianLink {
  id: string;
  status: "active" | "revoked";
  userName: string;
  userAgeBand: string;
  guardianName: string;
  consentedAt: string;
}

export interface LinkCode {
  code: string;
  expiresAt: string;
}

export interface Organization {
  id: string;
  name: string;
}

export interface Member {
  id: string;
  displayName: string;
  email: string;
  orgRole: string;
  status: string;
}

export interface LinkPreview {
  userName: string;
  userAgeBand: string;
  expiresAt: string;
}

export interface OcrResult {
  text: string;
  meanConfidence: number;
  lowConfidence: boolean;
}

export interface SummaryReport {
  rangeFrom: string;
  rangeTo: string;
  total: number;
  byLabel: Partial<Record<PrimaryLabel, number>>;
  bySeverity: Partial<Record<Severity, number>>;
  bySender: Record<string, number>;
  reviewed: number;
  pending: number;
  weekly: { weekStart: string; count: number }[];
  byWeekday: number[]; // Monday..Sunday counts within the range
  topSenders: { alias: string; count: number }[]; // top 5, viewer-scoped
}
