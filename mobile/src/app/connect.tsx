// Pre-login connection screen (roadmap §9.3): the Mac's address is editable
// here, checked against /v1/health, and saved without touching source code.

import { router } from "expo-router";
import React, { useEffect, useState } from "react";

import { Banner, Body, Button, Card, Field, Screen, Subtitle, Title } from "../components/ui";
import { checkHealth, getApiUrl, setApiUrl } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Health } from "../lib/types";

export default function Connect() {
  const { markServerConfigured } = useAuth();
  const [url, setUrl] = useState(process.env.EXPO_PUBLIC_API_URL ?? "");
  const [checking, setChecking] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getApiUrl().then((stored) => { if (stored) setUrl(stored); });
  }, []);

  const testAndSave = async () => {
    setChecking(true);
    setError(null);
    setHealth(null);
    try {
      const trimmed = url.trim().replace(/\/+$/, "");
      // Browsers silently add the scheme; do the same so "192.168.1.20:8000" works.
      const normalized = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
      const result = await checkHealth(normalized);
      await setApiUrl(normalized);
      setUrl(normalized);
      markServerConfigured();
      setHealth(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed.");
    } finally {
      setChecking(false);
    }
  };

  return (
    <Screen>
      <Title>Connect to your local server</Title>
      <Body muted>
        a-mbl runs against a small server on a computer you control. Start it
        there, then enter the address it prints — the phone and that computer
        must be on the same Wi-Fi.
      </Body>

      <Card>
        <Field
          label="Server address"
          value={url}
          onChangeText={setUrl}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="http://192.168.1.20:8000"
        />
        <Button label={checking ? "Checking…" : "Check connection"} onPress={testAndSave}
                loading={checking} />
      </Card>

      {error ? (
        <Card tone="danger">
          <Banner tone="error" text={error} />
          <Body muted>
            Common fixes: confirm the server is running, both devices share one
            Wi-Fi network, the address ends with :8000, and the computer&apos;s
            firewall allows incoming connections (Windows: the &quot;a-mbl API&quot;
            rule; macOS: allow Python).
          </Body>
        </Card>
      ) : null}

      {health ? (
        <Card>
          <Subtitle>Connected ✓</Subtitle>
          <Body>Model: {health.modelVersion}</Body>
          <Body>Screenshot text extraction: {health.ocrReady ? "available" : "not installed on the server yet"}</Body>
          <Button label="Continue" onPress={() => router.replace("/")} />
        </Card>
      ) : null}

      <Banner
        tone="warn"
        text="This local connection is for practice with made-up content only. Do not submit real sensitive conversations here."
      />
    </Screen>
  );
}
