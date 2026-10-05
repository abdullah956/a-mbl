"""Pydantic request/response models.

Field names are camelCase because they ARE the JSON contract used by the
mobile client (mirrored in mobile/src/lib/types.ts).
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import config

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PrimaryLabel = Literal["normal", "offensive", "harassment", "hate_speech", "threat"]
Severity = Literal["safe", "caution", "high", "critical"]


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=config.MIN_PASSWORD_CHARS, max_length=128)
    displayName: str = Field(min_length=1, max_length=60)
    role: Literal["user", "guardian"]
    birthYear: int = Field(ge=1900, le=2100)
    birthMonth: int = Field(ge=1, le=12)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL.match(value):
            raise ValueError("Enter a valid email address.")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refreshToken: str


class UserOut(BaseModel):
    id: str
    email: str
    displayName: str
    role: str
    ageBand: str
    status: str
    createdAt: str
    organizations: list[dict] = []
    permissions: dict[str, bool] = {}


class AuthResponse(BaseModel):
    accessToken: str
    refreshToken: str
    user: UserOut
    linkCode: str | None = None
    linkCodeExpiresAt: str | None = None


class PatchMeRequest(BaseModel):
    displayName: str | None = Field(default=None, min_length=1, max_length=60)


class CreateLinkCodeResponse(BaseModel):
    code: str
    expiresAt: str


class AcceptLinkRequest(BaseModel):
    code: str = Field(min_length=4, max_length=16)


class LinkPreviewOut(BaseModel):
    userName: str
    userAgeBand: str
    expiresAt: str


class GuardianLinkOut(BaseModel):
    id: str
    status: str
    userName: str
    userAgeBand: str
    guardianName: str
    consentedAt: str


class AnalysisRequest(BaseModel):
    text: str
    sourceType: Literal["text", "screenshot"] = "text"
    platformName: str | None = Field(default=None, max_length=60)
    senderAlias: str | None = Field(default=None, max_length=60)
    # §6.3: a user may manually flag ANY result — even Normal — for human
    # review; the flagged text is kept as a case with the user's consent.
    flagForReview: bool = False

    @field_validator("text")
    @classmethod
    def text_bounds(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Text must not be empty.")
        if len(stripped) > config.MAX_TEXT_CHARS:
            raise ValueError(f"Text must be at most {config.MAX_TEXT_CHARS} characters.")
        return stripped


class AnalysisResult(BaseModel):
    id: str
    primaryLabel: PrimaryLabel
    confidence: float
    bodyShaming: bool
    severity: Severity
    needsReview: bool
    advice: list[str]
    modelVersion: str
    retainedUntil: str | None
    caseId: str | None = None


class CaseSummary(BaseModel):
    id: str
    primaryLabel: str
    severity: str
    confidence: float
    bodyShaming: bool
    status: str
    sourceType: str
    ownerName: str
    isOwn: bool
    platformName: str | None
    senderAlias: str | None
    createdAt: str
    expiresAt: str
    hasEvidence: bool
    reviewCount: int
    reviewRequested: bool


class ReviewOut(BaseModel):
    id: str
    reviewerName: str
    reviewerRole: str
    humanLabel: str | None
    note: str | None
    createdAt: str


class ShareOut(BaseModel):
    id: str
    organizationId: str
    organizationName: str
    sharedAt: str


class EvidenceOut(BaseModel):
    id: str
    mimeType: str
    sizeBytes: int
    createdAt: str


class CaseDetail(CaseSummary):
    text: str
    maskedPreview: str
    needsReview: bool
    modelVersion: str
    reviews: list[ReviewOut]
    shares: list[ShareOut]
    evidence: list[EvidenceOut]


class CaseListResponse(BaseModel):
    items: list[CaseSummary]
    total: int
    page: int
    pageSize: int


class PatchCaseRequest(BaseModel):
    platformName: str | None = Field(default=None, max_length=60)
    senderAlias: str | None = Field(default=None, max_length=60)
    requestReview: bool | None = None


class ReviewRequest(BaseModel):
    humanLabel: PrimaryLabel | None = None
    note: str | None = Field(default=None, max_length=2000)


class ShareRequest(BaseModel):
    organizationId: str


class OrganizationOut(BaseModel):
    id: str
    name: str


class MemberOut(BaseModel):
    id: str
    displayName: str
    email: str
    orgRole: str
    status: str


class AddMemberRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL.match(value):
            raise ValueError("Enter a valid email address.")
        return value


class AlertOut(BaseModel):
    id: str
    caseId: str
    severity: str
    primaryLabel: str
    subjectName: str
    createdAt: str
    readAt: str | None


class PatchAlertRequest(BaseModel):
    read: bool = True


class OcrResponse(BaseModel):
    text: str
    meanConfidence: float
    lowConfidence: bool


class SummaryReport(BaseModel):
    rangeFrom: str
    rangeTo: str
    total: int
    byLabel: dict[str, int]
    bySeverity: dict[str, int]
    # Grouped by the alias the submitting user typed — unverified by design.
    bySender: dict[str, int]
    reviewed: int
    pending: int
    weekly: list[dict]


class PdfRequest(BaseModel):
    rangeFrom: str | None = None
    rangeTo: str | None = None


class DeleteAccountRequest(BaseModel):
    password: str


class HealthResponse(BaseModel):
    status: str
    modelVersion: str
    modelReady: bool
    ocrReady: bool
    time: str
