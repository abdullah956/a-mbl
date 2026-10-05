// Home: recent activity summary for the signed-in role plus safety framing.

import { router, useFocusEffect } from "expo-router";
import React, { useCallback, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Banner, Body, Button, Card, ErrorNotice, Subtitle, Title } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { colors, labelText, severityMeta } from "../../lib/theme";
import type { PrimaryLabel, Severity, SummaryReport } from "../../lib/types";

export default function Home() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<SummaryReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      setSummary(await api<SummaryReport>("/v1/reports/summary"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the summary.");
    }
  }, []);

  // On every focus, not just the first mount: after analyzing a message the
  // user comes back here and the totals must already include it.
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const scopeLine = user?.role === "guardian"
    ? "Cases below cover you and your linked users."
    : user?.role === "school_admin"
      ? "Cases below cover only what was explicitly shared with your school."
      : "Cases below cover only your own submissions.";

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right"]}>
      <ScrollView
        contentContainerStyle={styles.bodyWrap}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => {
          setRefreshing(true); await load(); setRefreshing(false);
        }} />}>
        <Title>Hi {user?.displayName ?? ""} 👋</Title>
        <Body muted>{scopeLine}</Body>

        {error ? <ErrorNotice message={error} onRetry={load} /> : null}

        {summary ? (
          <Card>
            <Subtitle>Last 30 days</Subtitle>
            <View style={styles.statRow}>
              <Stat label="Harmful cases" value={summary.total} />
              <Stat label="Reviewed" value={summary.reviewed} />
              <Stat label="Pending" value={summary.pending} />
            </View>
            {summary.total > 0 ? (
              <View style={styles.breakdown}>
                {(Object.entries(summary.bySeverity) as [Severity, number][]).map(([key, count]) => (
                  <Body key={key} muted>
                    {severityMeta[key].icon} {severityMeta[key].label}: {count}
                  </Body>
                ))}
                {(Object.entries(summary.byLabel) as [PrimaryLabel, number][]).map(([key, count]) => (
                  <Body key={key} muted>• {labelText[key]}: {count}</Body>
                ))}
              </View>
            ) : (
              <Body muted>No harmful cases in this period.</Body>
            )}
          </Card>
        ) : null}

        <Card tone="info">
          <Subtitle>How a-mbl works</Subtitle>
          <Body>
            You choose what to check. The result is an automated estimate with a
            confidence level — a starting point for a human conversation, not a verdict.
          </Body>
        </Card>

        <Button label="Analyze a message" onPress={() => router.push("/(tabs)/analyze")} />
        <Button label="Reports and PDF export" kind="secondary"
                onPress={() => router.push("/reports")} />
        {user?.role === "school_admin" ? (
          <Button label="Organization members" kind="secondary"
                  onPress={() => router.push("/members")} />
        ) : null}

        <Banner tone="info"
                text="If someone may be in immediate danger, contact a trusted person or an appropriate local service now." />
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.stat} accessibilityLabel={`${label}: ${value}`}>
      <Text style={styles.statValue} maxFontSizeMultiplier={1.5}>{value}</Text>
      <Text style={styles.statLabel} maxFontSizeMultiplier={1.8}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  bodyWrap: { padding: 16, gap: 12, paddingBottom: 40 },
  statRow: { flexDirection: "row", gap: 10 },
  stat: {
    flex: 1, backgroundColor: "#EFECFA", borderRadius: 12, padding: 12,
    alignItems: "center", gap: 2,
  },
  statValue: { fontSize: 24, fontWeight: "800", color: colors.primaryDark },
  statLabel: { fontSize: 12, color: colors.muted, textAlign: "center" },
  breakdown: { gap: 2 },
});
