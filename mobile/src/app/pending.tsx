// Shown to 13–17 users until a guardian approves their one-time link code.

import { router, useLocalSearchParams } from "expo-router";
import React, { useState } from "react";
import { StyleSheet, Text } from "react-native";

import { Banner, Body, Button, Card, Screen, Subtitle, Title } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { colors, formatDateTime } from "../lib/theme";
import type { LinkCode } from "../lib/types";

export default function Pending() {
  const params = useLocalSearchParams<{ code?: string }>();
  const { reloadUser, signOut } = useAuth();
  const [code, setCode] = useState<string | null>(params.code || null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const newCode = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const result = await api<LinkCode>("/v1/guardian-links", { method: "POST" });
      setCode(result.code);
      setExpiresAt(result.expiresAt);
    } catch {
      setNotice("Could not create a code. Check the connection and try again.");
    } finally {
      setBusy(false);
    }
  };

  const checkStatus = async () => {
    setChecking(true);
    setNotice(null);
    const me = await reloadUser();
    setChecking(false);
    if (me?.status === "active") {
      router.replace("/(tabs)");
    } else {
      setNotice("Not approved yet. Ask your guardian to enter the code in their account.");
    }
  };

  return (
    <Screen>
      <Title>One more step</Title>
      <Body>
        Because you’re under 18, a parent or guardian needs to approve your account.
        Share this one-time code with them — they enter it in their own a-mbl account
        under Profile → Linked users.
      </Body>

      <Card>
        <Subtitle>Your link code</Subtitle>
        {code ? (
          <>
            <Text style={styles.code} accessibilityLabel={`Link code ${code.split("").join(" ")}`}>
              {code}
            </Text>
            {expiresAt ? <Body muted>Valid until {formatDateTime(expiresAt)}</Body> : (
              <Body muted>The code works once and expires after 24 hours.</Body>
            )}
          </>
        ) : (
          <Body muted>Create a code to get started.</Body>
        )}
        <Button label={code ? "Create a new code" : "Create code"} kind="secondary"
                onPress={newCode} loading={busy} />
      </Card>

      {notice ? <Banner tone="info" text={notice} /> : null}

      <Button label="I've been approved — check again" onPress={checkStatus} loading={checking} />
      <Button label="Sign out" kind="ghost"
              onPress={async () => { await signOut(); router.replace("/(auth)/welcome"); }} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  code: {
    fontSize: 34, fontWeight: "800", letterSpacing: 6, color: colors.primaryDark,
    textAlign: "center", paddingVertical: 8,
  },
});
