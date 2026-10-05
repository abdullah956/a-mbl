// Profile: account info, guardian links, privacy controls, sign-out.

import Constants from "expo-constants";
import { router, useFocusEffect } from "expo-router";
import React, { useCallback, useState } from "react";
import { Alert, Share, StyleSheet, Text } from "react-native";

import {
  Banner, Body, Button, Card, Field, Row, Screen, Subtitle, Title,
} from "../../components/ui";
import { api, ApiError, getApiUrl } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { colors, formatDate, formatDateTime } from "../../lib/theme";
import type { GuardianLink, LinkCode, LinkPreview, User } from "../../lib/types";

export default function Profile() {
  const { user, signOut, reloadUser } = useAuth();
  const [links, setLinks] = useState<GuardianLink[]>([]);
  const [linksError, setLinksError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [serverUrl, setServerUrl] = useState<string | null>(null);

  // Depend on stable primitives, not the user object: reloadUser() replaces
  // the object on every /v1/me response, which would otherwise re-trigger the
  // focus effect forever.
  const role = user?.role;
  const loadLinks = useCallback(async () => {
    if (!role || role === "school_admin") return;
    try {
      setLinksError(null);
      setLinks(await api<GuardianLink[]>("/v1/guardian-links"));
    } catch (err) {
      setLinksError(err instanceof ApiError ? err.message
        : "Could not load your links. Pull back to this tab to retry.");
    }
  }, [role]);

  // The server address is re-read on focus: it may have just been changed on
  // the connect screen.
  useFocusEffect(useCallback(() => {
    loadLinks();
    reloadUser();
    getApiUrl().then(setServerUrl);
  }, [loadLinks, reloadUser]));

  if (!user) return null;

  return (
    <Screen>
      <Title>{user.displayName}</Title>
      <Card>
        <Row label="Email" value={user.email} />
        <Row label="Role" value={user.role === "school_admin" ? "School administrator"
          : user.role === "guardian" ? "Guardian" : "User"} />
        <Row label="Age band" value={user.ageBand} />
        <Row label="Member since" value={formatDate(user.createdAt)} />
        {user.organizations.map((org) => (
          <Row key={org.id} label="Organization" value={org.name} />
        ))}
        <EditNameSection user={user} onSaved={reloadUser} />
      </Card>

      {notice ? <Banner tone="info" text={notice} /> : null}
      {linksError ? <Banner tone="error" text={linksError} /> : null}

      {user.role === "user" ? <UserLinkSection links={links} onChanged={loadLinks} /> : null}
      {user.role === "guardian" ? <GuardianLinkSection links={links} onChanged={loadLinks} /> : null}
      {user.role === "school_admin" ? (
        <Card>
          <Subtitle>Organization</Subtitle>
          <Button label="Manage members" kind="secondary" onPress={() => router.push("/members")} />
          <Button label="Reports and PDF export" kind="secondary" onPress={() => router.push("/reports")} />
        </Card>
      ) : null}

      <PrivacySection onNotice={setNotice} />

      <Card>
        <Subtitle>App</Subtitle>
        <Row label="App version" value={Constants.expoConfig?.version ?? "—"} />
        <Row label="Server" value={serverUrl ?? "—"} />
        <Button label="Change server address" kind="secondary" onPress={() => router.push("/connect")} />
        <Button label="Sign out" kind="secondary"
                onPress={async () => { await signOut(); router.replace("/(auth)/welcome"); }} />
      </Card>

      <Banner tone="info"
              text="a-mbl is a prototype for practice with made-up content. Results are estimates, not judgments." />
    </Screen>
  );
}

function EditNameSection({ user, onSaved }: { user: User; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(user.displayName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api("/v1/me", { method: "PATCH", body: { displayName: name.trim() } });
      onSaved();
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update your name.");
    }
    setBusy(false);
  };

  if (!editing) {
    return <Button label="Edit display name" kind="ghost"
                   onPress={() => { setName(user.displayName); setEditing(true); }} />;
  }
  return (
    <>
      <Field label="Display name" value={name} onChangeText={setName}
             maxLength={60} error={error ?? undefined} />
      <Button label="Save name" onPress={save} loading={busy} disabled={!name.trim()} />
      <Button label="Cancel" kind="ghost" onPress={() => setEditing(false)} />
    </>
  );
}

function LinkList({ links, onChanged }: { links: GuardianLink[]; onChanged: () => void }) {
  const revoke = (link: GuardianLink) => {
    Alert.alert("Remove this link?",
      "The other account is kept — only the connection is removed.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Remove link", style: "destructive",
          onPress: async () => {
            try {
              await api(`/v1/guardian-links/${link.id}`, { method: "DELETE" });
              onChanged();
            } catch (err) {
              Alert.alert("Could not remove the link",
                          err instanceof ApiError ? err.message : "Please try again.");
            }
          },
        },
      ]);
  };

  if (!links.length) return <Body muted>No links yet.</Body>;
  return (
    <>
      {links.map((link) => (
        <Card key={link.id}>
          <Body>
            {link.userName} ⇄ {link.guardianName} ({link.status})
          </Body>
          <Body muted>Linked {formatDateTime(link.consentedAt)}</Body>
          {link.status === "active" ? (
            <Button label="Remove link" kind="danger" onPress={() => revoke(link)} />
          ) : null}
        </Card>
      ))}
    </>
  );
}

function UserLinkSection({ links, onChanged }: {
  links: GuardianLink[]; onChanged: () => void;
}) {
  const [code, setCode] = useState<LinkCode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createCode = async () => {
    setBusy(true);
    setError(null);
    try {
      setCode(await api<LinkCode>("/v1/guardian-links", { method: "POST" }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create a code. Try again.");
    }
    setBusy(false);
  };

  return (
    <Card>
      <Subtitle>Guardian links</Subtitle>
      <Body muted>
        A linked guardian can see your harmful cases and receives an alert for
        high-risk ones. You can remove the link at any time.
      </Body>
      {code ? (
        <>
          <Text style={styles.code}>{code.code}</Text>
          <Body muted>Share this code with your guardian. Valid until {formatDateTime(code.expiresAt)}, single use.</Body>
        </>
      ) : null}
      {error ? <Banner tone="error" text={error} /> : null}
      <Button label="Create a link code" kind="secondary" onPress={createCode} loading={busy} />
      <LinkList links={links} onChanged={onChanged} />
    </Card>
  );
}

function GuardianLinkSection({ links, onChanged }: {
  links: GuardianLink[]; onChanged: () => void;
}) {
  const [input, setInput] = useState("");
  const [preview, setPreview] = useState<LinkPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // §7.1 step 7: review WHO the code belongs to before approving anything.
  const review = async () => {
    setBusy(true);
    setError(null);
    try {
      setPreview(await api<LinkPreview>("/v1/guardian-links/preview", {
        method: "POST", body: { code: input.trim() },
      }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not check this code.");
    }
    setBusy(false);
  };

  const accept = async () => {
    setBusy(true);
    setError(null);
    try {
      await api("/v1/guardian-links/accept", { method: "POST", body: { code: input.trim() } });
      setInput("");
      setPreview(null);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not approve this code.");
    }
    setBusy(false);
  };

  return (
    <Card>
      <Subtitle>Linked users</Subtitle>
      <Body muted>
        Enter the one-time code a young person shared with you. You will see who
        it belongs to before you approve the link.
      </Body>
      <Field label="Link code" value={input}
             onChangeText={(value) => { setInput(value); setPreview(null); }}
             autoCapitalize="characters" autoCorrect={false} error={error ?? undefined} />
      {preview ? (
        <>
          <Banner tone="info"
                  text={`This code links you to ${preview.userName} (age band ${preview.userAgeBand}). Approving activates their account and lets you see their harmful cases.`} />
          <Button label={`Approve link to ${preview.userName}`} onPress={accept} loading={busy} />
          <Button label="Not now" kind="ghost"
                  onPress={() => { setPreview(null); setInput(""); }} />
        </>
      ) : (
        <Button label="Review code" onPress={review} loading={busy} disabled={!input.trim()} />
      )}
      <LinkList links={links} onChanged={onChanged} />
    </Card>
  );
}

function PrivacySection({ onNotice }: { onNotice: (text: string) => void }) {
  const { signOut } = useAuth();
  const [password, setPassword] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const exportData = async () => {
    try {
      const data = await api<unknown>("/v1/privacy/export");
      await Share.share({ message: JSON.stringify(data, null, 2) });
    } catch {
      onNotice("Export failed. Check the connection and try again.");
    }
  };

  const deleteAccount = async () => {
    setBusy(true);
    setError(null);
    try {
      await api("/v1/privacy/account", { method: "DELETE", body: { password } });
      await signOut();
      router.replace("/(auth)/welcome");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Deletion failed.");
    }
    setBusy(false);
  };

  return (
    <Card>
      <Subtitle>Privacy</Subtitle>
      <Body muted>
        Harmful cases delete themselves after 30 days. You can export your data, or
        delete your account and everything it owns right now.
      </Body>
      <Button label="Export my data" kind="secondary" onPress={exportData} />
      {confirming ? (
        <>
          <Banner tone="warn"
                  text="This permanently deletes your account, cases, evidence, links, and alerts." />
          <Field label="Confirm your password" value={password} onChangeText={setPassword}
                 secureTextEntry error={error ?? undefined} />
          <Button label="Delete my account permanently" kind="danger" onPress={deleteAccount}
                  loading={busy} disabled={!password} />
          <Button label="Keep my account" kind="ghost"
                  onPress={() => { setConfirming(false); setPassword(""); setError(null); }} />
        </>
      ) : (
        <Button label="Delete my account…" kind="danger" onPress={() => setConfirming(true)} />
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  code: {
    fontSize: 30, fontWeight: "800", letterSpacing: 5, color: colors.primaryDark,
    textAlign: "center", paddingVertical: 4,
  },
});
