import { router, useLocalSearchParams } from "expo-router";
import React, { useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { Banner, Body, Button, Card, Field, FilterChip, Screen, Title } from "../../components/ui";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { colors } from "../../lib/theme";

export default function Register() {
  const params = useLocalSearchParams<{ year?: string; month?: string }>();
  const { register } = useAuth();
  const [role, setRole] = useState<"user" | "guardian">("user");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const birthYear = Number(params.year);
  const birthMonth = Number(params.month);

  if (!birthYear || !birthMonth) {
    return (
      <Screen>
        <Banner tone="warn" text="Please answer the age question first." />
        <Button label="Go back" onPress={() => router.replace("/(auth)/age")} />
      </Screen>
    );
  }

  const submit = async () => {
    setBusy(true);
    setError(null);
    setFieldErrors({});
    try {
      const auth = await register({
        email, password, displayName: displayName.trim(), role, birthYear, birthMonth,
      });
      if (auth.user.status === "pending_guardian") {
        router.replace({ pathname: "/pending", params: { code: auth.linkCode ?? "" } });
      } else {
        router.replace("/(tabs)");
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFieldErrors(err.fieldErrors ?? {});
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Title>Create your account</Title>

      <Card>
        <Text style={styles.groupLabel}>I am registering as</Text>
        <View style={styles.roleRow}>
          <FilterChip label="A user checking messages" active={role === "user"}
                      onPress={() => setRole("user")} />
          <FilterChip label="A parent or guardian" active={role === "guardian"}
                      onPress={() => setRole("guardian")} />
        </View>
        <Body muted>
          School staff accounts are set up separately by the server administrator and
          cannot be created here.
        </Body>
      </Card>

      <Card>
        <Field label="Display name" value={displayName} onChangeText={setDisplayName}
               autoCapitalize="words" error={fieldErrors.displayName} />
        <Field label="Email" value={email} onChangeText={setEmail}
               autoCapitalize="none" autoCorrect={false} keyboardType="email-address"
               error={fieldErrors.email} />
        <Field label="Password (at least 8 characters)" value={password}
               onChangeText={setPassword} secureTextEntry error={fieldErrors.password} />
      </Card>

      {error ? <Banner tone="error" text={error} /> : null}
      <Button label="Create account" onPress={submit} loading={busy}
              disabled={!displayName.trim() || !email.trim() || !password} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  groupLabel: { fontSize: 14, fontWeight: "600", color: colors.text },
  roleRow: { gap: 8 },
});
