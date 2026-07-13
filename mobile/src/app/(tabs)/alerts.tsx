// In-app alert inbox. Previews show severity, category, person, and time —
// never message content. Opening an alert re-checks authorization server-side.

import { router, useFocusEffect } from "expo-router";
import React, { useCallback, useState } from "react";
import { AppState, FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { EmptyState, ErrorNotice, Loading, SeverityChip } from "../../components/ui";
import { api } from "../../lib/api";
import { colors, formatDateTime, labelText } from "../../lib/theme";
import type { AppAlert } from "../../lib/types";

export default function Alerts() {
  const [alerts, setAlerts] = useState<AppAlert[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      setAlerts(await api<AppAlert[]>("/v1/alerts"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load alerts.");
    }
  }, []);

  // §14.2: refresh on focus, when the app returns to the foreground, and via
  // light polling while the inbox stays open (no push notifications by design).
  useFocusEffect(useCallback(() => {
    load();
    const appState = AppState.addEventListener("change", (state) => {
      if (state === "active") load();
    });
    const poll = setInterval(load, 60_000);
    return () => { appState.remove(); clearInterval(poll); };
  }, [load]));

  const open = async (alert: AppAlert) => {
    if (!alert.readAt) {
      try {
        await api(`/v1/alerts/${alert.id}`, { method: "PATCH", body: { read: true } });
      } catch {
        // Marking read is best-effort; opening the case matters more.
      }
    }
    router.push(`/case/${alert.caseId}`);
  };

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right"]}>
      {error ? <View style={styles.pad}><ErrorNotice message={error} onRetry={load} /></View> : null}
      {alerts === null && !error ? <Loading label="Loading alerts…" /> : null}
      {alerts !== null ? (
        <FlatList
          data={alerts}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listBody}
          refreshing={refreshing}
          onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }}
          ListEmptyComponent={
            <EmptyState title="No alerts"
                        hint="High-risk cases in your scope will appear here. Alerts never include message content." />
          }
          renderItem={({ item }) => (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Alert: ${labelText[item.primaryLabel]} involving ${item.subjectName}, ${item.readAt ? "read" : "unread"}`}
              onPress={() => open(item)}
              style={({ pressed }) => [styles.alertCard, pressed && { opacity: 0.8 },
                                       !item.readAt && styles.alertUnread]}>
              <View style={styles.alertTop}>
                <SeverityChip severity={item.severity} />
                <Text style={styles.alertDate}>{formatDateTime(item.createdAt)}</Text>
              </View>
              <Text style={styles.alertTitle}>
                {item.readAt ? "" : "● "}{labelText[item.primaryLabel]} — {item.subjectName}
              </Text>
              <Text style={styles.alertMeta}>Tap to open the case (access is re-checked).</Text>
            </Pressable>
          )}
        />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  pad: { padding: 16 },
  listBody: { padding: 16, paddingBottom: 40, gap: 10 },
  alertCard: {
    backgroundColor: colors.surface, borderRadius: 14, padding: 14, gap: 6,
    borderWidth: 1, borderColor: colors.border,
  },
  alertUnread: { borderColor: colors.primary, borderWidth: 1.5 },
  alertTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  alertDate: { color: colors.muted, fontSize: 13 },
  alertTitle: { fontSize: 15, fontWeight: "700", color: colors.text },
  alertMeta: { fontSize: 13, color: colors.muted },
});
