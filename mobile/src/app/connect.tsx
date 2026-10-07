// Pre-login connection screen (roadmap §9.3): the server address is editable
// here, checked against /v1/health, and saved without touching source code.

import { router } from "expo-router";
import React, { useEffect, useState } from "react";

import { Banner, Body, Button, Card, Field, Screen, Subtitle, Title } from "../components/ui";
import { checkHealth, getApiUrl, normalizeServerUrl, setApiUrl } from "../lib/api";
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
      const address = normalizeServerUrl(url);
      const result = await checkHealth(address);
      await setApiUrl(address);
      setUrl(address);
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
      <Title>Connect to the a-mbl server</Title>
      <Body muted>
        a-mbl checks messages with a small server. Enter the address you were
        given: an http:// address when the phone is on the same Wi-Fi as the
        server, or an https:// link when testing from anywhere.
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
            Common fixes: confirm the server is still running, copy the address
            exactly as you received it, and for an http:// address make sure the
            phone and the server share one Wi-Fi network (port 8000) and the
            server’s firewall allows incoming connections (Windows: the
            &quot;a-mbl API&quot; rule; macOS: allow Python).
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
        text="This test server is for practice with made-up content only. Do not submit real sensitive conversations here."
      />
    </Screen>
  );
}
