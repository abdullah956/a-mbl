// Case detail: immutable model result, deliberate Reveal for sensitive text,
// human reviews, organization sharing, evidence, and deletion.

import * as ImagePicker from "expo-image-picker";
import { Redirect, router, useFocusEffect, useLocalSearchParams } from "expo-router";
import React, { useCallback, useState } from "react";
import { Alert, Image, StyleSheet, View } from "react-native";

import {
  Banner, Body, Button, Card, ErrorNotice, Field, FilterChip, Loading, Row,
  Screen, SeverityChip, Subtitle,
} from "../../components/ui";
import { api, ApiError, apiBinary } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { imageDataUri, screenshotFormData } from "../../lib/images";
import { confidencePercent, formatDate, formatDateTime, labelText } from "../../lib/theme";
import type { CaseDetail, Organization, PrimaryLabel } from "../../lib/types";

const REVIEW_LABELS: (PrimaryLabel | null)[] =
  [null, "normal", "offensive", "harassment", "hate_speech", "threat"];

export default function CaseScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user, ready } = useAuth();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await api<CaseDetail>(`/v1/cases/${id}`);
      setError(null);
      setDetail(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load this case.");
    }
  }, [id]);

  // Reload on every focus, like the tab screens, so a case reopened from the
  // list or an alert always shows its latest reviews and shares.
  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (ready && !user) return <Redirect href="/(auth)/welcome" />;
  if (error) return <Screen><ErrorNotice message={error} onRetry={load} /></Screen>;
  if (!detail) return <Screen scroll={false}><Loading label="Loading case…" /></Screen>;

  const isOwner = detail.isOwn;

  const confirmDelete = () => {
    Alert.alert("Delete this case?",
      "The encrypted text and any attached screenshot are removed permanently.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete", style: "destructive",
          onPress: async () => {
            try {
              await api(`/v1/cases/${detail.id}`, { method: "DELETE" });
              router.back();
            } catch {
              Alert.alert("Deletion failed", "Please try again.");
            }
          },
        },
      ]);
  };

  return (
    <Screen>
      <Card>
        <View style={styles.headRow}>
          <SeverityChip severity={detail.severity} />
          <Body muted>{formatDateTime(detail.createdAt)}</Body>
        </View>
        <Subtitle>{labelText[detail.primaryLabel]}
          {detail.bodyShaming ? " + body-shaming tag" : ""}</Subtitle>
        <Row label="Model confidence" value={confidencePercent(detail.confidence)} />
        <Row label="Model version" value={detail.modelVersion} />
        <Row label="From" value={detail.isOwn ? "You" : detail.ownerName} />
        {detail.platformName ? <Row label="Platform (user-entered)" value={detail.platformName} /> : null}
        {detail.senderAlias ? <Row label="Sender alias (unverified)" value={detail.senderAlias} /> : null}
        <Row label="Deletes automatically" value={formatDate(detail.expiresAt)} />
        {detail.needsReview ? (
          <Banner tone="warn" text="The model was uncertain about this result — a human review matters here." />
        ) : null}
        {detail.reviewRequested && detail.status !== "reviewed" ? (
          <Banner tone="info" text="A human review of this case has been requested." />
        ) : null}
      </Card>

      <Card>
        <Subtitle>Message content</Subtitle>
        {revealed ? (
          <>
            <Body>{detail.text}</Body>
            <Button label="Hide content" kind="ghost" onPress={() => setRevealed(false)} />
          </>
        ) : (
          <>
            <Body muted>{detail.maskedPreview || "Content hidden."}</Body>
            <Button label="Reveal full content" kind="secondary" onPress={() => setRevealed(true)} />
          </>
        )}
      </Card>

      {isOwner ? <ContextCard detail={detail} onChanged={load} /> : null}
      <ReviewsCard detail={detail} onChanged={load} />
      {isOwner ? <SharingCard detail={detail} onChanged={load} /> : null}
      {isOwner || detail.evidence.length ? (
        <EvidenceCard detail={detail} isOwner={isOwner} onChanged={load} />
      ) : null}

      {isOwner ? <Button label="Delete this case" kind="danger" onPress={confirmDelete} /> : null}
    </Screen>
  );
}

function ContextCard({ detail, onChanged }: { detail: CaseDetail; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [platform, setPlatform] = useState(detail.platformName ?? "");
  const [alias, setAlias] = useState(detail.senderAlias ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/cases/${detail.id}`, {
        method: "PATCH", body: { platformName: platform, senderAlias: alias },
      });
      setEditing(false);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the context.");
    }
    setBusy(false);
  };

  const requestReview = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/cases/${detail.id}`, { method: "PATCH", body: { requestReview: true } });
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not request a review.");
    }
    setBusy(false);
  };

  return (
    <Card>
      <Subtitle>Context and review</Subtitle>
      <Body muted>
        You can add or correct where this happened and who sent it (as you know
        it), or ask the people who can see this case for a human review.
      </Body>
      {editing ? (
        <>
          <Field label="Platform (optional, as you describe it)" value={platform}
                 onChangeText={setPlatform} maxLength={60} placeholder="e.g. ChatApp" />
          <Field label="Sender nickname (optional, unverified)" value={alias}
                 onChangeText={setAlias} maxLength={60} placeholder="e.g. anon_17" />
          <Button label="Save context" onPress={save} loading={busy} />
          <Button label="Cancel" kind="ghost" onPress={() => setEditing(false)} />
        </>
      ) : (
        <Button label="Edit context (platform, sender)" kind="secondary"
                onPress={() => {
                  setPlatform(detail.platformName ?? "");
                  setAlias(detail.senderAlias ?? "");
                  setEditing(true);
                }} />
      )}
      {detail.status !== "reviewed" && !detail.reviewRequested ? (
        <Button label="Request a human review" kind="secondary"
                onPress={requestReview} loading={busy} />
      ) : null}
      {error ? <Banner tone="error" text={error} /> : null}
    </Card>
  );
}

function ReviewsCard({ detail, onChanged }: { detail: CaseDetail; onChanged: () => void }) {
  const [adding, setAdding] = useState(false);
  const [humanLabel, setHumanLabel] = useState<PrimaryLabel | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/cases/${detail.id}/reviews`, {
        method: "POST",
        body: { humanLabel, note: note.trim() || null },
      });
      setAdding(false);
      setHumanLabel(null);
      setNote("");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the review.");
    }
    setBusy(false);
  };

  return (
    <Card>
      <Subtitle>Human review</Subtitle>
      <Body muted>
        Reviews are stored next to the model result — the original prediction above
        never changes.
      </Body>
      {detail.reviews.map((review) => (
        <View key={review.id} style={styles.review}>
          <Body>
            {review.reviewerName} ({review.reviewerRole}){review.humanLabel
              ? ` — says: ${labelText[review.humanLabel]}` : ""}
          </Body>
          {review.note ? <Body muted>“{review.note}”</Body> : null}
          <Body muted>{formatDateTime(review.createdAt)}</Body>
        </View>
      ))}
      {adding ? (
        <>
          <Body>What does this look like to you?</Body>
          <View style={styles.chipsWrap}>
            {REVIEW_LABELS.map((value) => (
              <FilterChip
                key={value ?? "none"}
                label={value ? labelText[value] : "No category"}
                active={humanLabel === value}
                onPress={() => setHumanLabel(value)}
              />
            ))}
          </View>
          <Field label="Note (optional)" value={note} onChangeText={setNote} multiline
                 placeholder="What you observed, agreed with, or corrected…"
                 error={error ?? undefined} />
          <Button label="Save review" onPress={submit} loading={busy}
                  disabled={humanLabel === null && !note.trim()} />
          <Button label="Cancel" kind="ghost" onPress={() => setAdding(false)} />
        </>
      ) : (
        <Button label="Add a review" kind="secondary" onPress={() => setAdding(true)} />
      )}
    </Card>
  );
}

function SharingCard({ detail, onChanged }: { detail: CaseDetail; onChanged: () => void }) {
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [busy, setBusy] = useState(false);

  const loadOrgs = async () => {
    try {
      setOrgs(await api<Organization[]>("/v1/organizations"));
    } catch {
      setOrgs([]);
    }
  };

  const share = (org: Organization) => {
    Alert.alert(`Share with ${org.name}?`,
      "Administrators of this organization will be able to open this case until you unshare it.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: `Share with ${org.name}`,
          onPress: async () => {
            setBusy(true);
            try {
              await api(`/v1/cases/${detail.id}/shares`, {
                method: "POST", body: { organizationId: org.id },
              });
              onChanged();
            } catch (err) {
              Alert.alert("Sharing failed",
                          err instanceof ApiError ? err.message : "Please try again.");
            }
            setBusy(false);
          },
        },
      ]);
  };

  const revoke = async (shareId: string) => {
    try {
      await api(`/v1/cases/${detail.id}/shares/${shareId}`, { method: "DELETE" });
      onChanged();
    } catch {
      Alert.alert("Could not unshare", "Please try again.");
    }
  };

  return (
    <Card>
      <Subtitle>Sharing with a school</Subtitle>
      <Body muted>
        Nothing is shared automatically. You choose an organization explicitly, and
        you can unshare at any time — access is removed immediately.
      </Body>
      {detail.shares.map((share) => (
        <View key={share.id} style={styles.review}>
          <Body>Shared with {share.organizationName} since {formatDate(share.sharedAt)}</Body>
          <Button label={`Unshare from ${share.organizationName}`} kind="danger"
                  onPress={() => revoke(share.id)} />
        </View>
      ))}
      {orgs === null ? (
        <Button label="Share with an organization…" kind="secondary" onPress={loadOrgs} />
      ) : orgs.length ? (
        <View style={styles.chipsWrap}>
          {orgs
            .filter((org) => !detail.shares.some((share) => share.organizationId === org.id))
            .map((org) => (
              <FilterChip key={org.id} label={org.name} active={false}
                          onPress={() => !busy && share(org)} />
            ))}
        </View>
      ) : (
        <Body muted>No organizations are registered on this server yet.</Body>
      )}
    </Card>
  );
}

function EvidenceCard({ detail, isOwner, onChanged }: {
  detail: CaseDetail; isOwner: boolean; onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [showImage, setShowImage] = useState(false);
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState(false);
  const [imageError, setImageError] = useState(false);

  const evidence = detail.evidence[0];

  // The image comes through the API client — <Image> request headers are not
  // sent on Android, so an authorized URL would always answer 401 — which
  // also refreshes an expired session. It is shown from memory only.
  const loadImage = async () => {
    if (!evidence) return;
    setImageLoading(true);
    setImageError(false);
    try {
      const buffer = await apiBinary(`/v1/cases/${detail.id}/evidence/${evidence.id}`);
      setImageUri(imageDataUri(buffer, evidence.mimeType));
    } catch {
      setImageError(true);
    }
    setImageLoading(false);
  };

  const toggleImage = () => {
    if (!showImage && !imageUri) loadImage();
    setShowImage((value) => !value);
  };

  const attach = async () => {
    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"], quality: 0.8, exif: false,
    });
    if (picked.canceled || !picked.assets?.length) return;
    setBusy(true);
    try {
      const form = await screenshotFormData(picked.assets[0]);
      await api(`/v1/cases/${detail.id}/evidence`, { formData: form, method: "POST", timeoutMs: 30000 });
      onChanged();
    } catch (err) {
      Alert.alert("Attach failed", err instanceof ApiError ? err.message : "Please try again.");
    }
    setBusy(false);
  };

  return (
    <Card>
      <Subtitle>Screenshot evidence</Subtitle>
      {evidence ? (
        <>
          <Body muted>
            One screenshot attached ({Math.round(evidence.sizeBytes / 1024)} KB, stored
            encrypted, deleted with the case).
          </Body>
          {showImage && imageLoading ? <Loading label="Loading screenshot…" /> : null}
          {showImage && imageUri && !imageError ? (
            <Image
              accessibilityLabel="Attached screenshot evidence"
              source={{ uri: imageUri }}
              style={styles.evidence}
              resizeMode="contain"
              onError={() => setImageError(true)}
            />
          ) : null}
          {showImage && imageError ? (
            <>
              <Banner tone="error" text="The screenshot could not be loaded." />
              <Button label="Try again" kind="secondary" onPress={loadImage} />
            </>
          ) : null}
          <Button label={showImage ? "Hide screenshot" : "View screenshot"} kind="secondary"
                  onPress={toggleImage} />
        </>
      ) : isOwner ? (
        <>
          <Body muted>
            You can attach the original screenshot to this case. It is stored encrypted
            and only people who can open the case can view it.
          </Body>
          <Button label="Attach screenshot" kind="secondary" onPress={attach} loading={busy} />
        </>
      ) : (
        <Body muted>No screenshot attached.</Body>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  headRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  review: { gap: 2, paddingVertical: 6 },
  chipsWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  evidence: { width: "100%", height: 320, borderRadius: 12, backgroundColor: "#EFECFA" },
});
