import { router } from "expo-router";
import React, { useState } from "react";

import { Banner, Button, Card, Field, Screen, Title } from "../../components/ui";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";

export default function Login() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const user = await signIn(email, password);
      router.replace(user.status === "pending_guardian" ? "/pending" : "/(tabs)");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Title>Welcome back</Title>
      <Card>
        <Field label="Email" value={email} onChangeText={setEmail}
               autoCapitalize="none" autoCorrect={false} keyboardType="email-address" />
        <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry />
      </Card>
      {error ? <Banner tone="error" text={error} /> : null}
      <Button label="Sign in" onPress={submit} loading={busy}
              disabled={!email.trim() || !password} />
      <Button label="Change server address" kind="ghost" onPress={() => router.push("/connect")} />
    </Screen>
  );
}
