// Role-scoped case history with severity filters.

import { router, useFocusEffect } from "expo-router";
import React, { useCallback, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { EmptyState, ErrorNotice, FilterChip, Loading, SeverityChip } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { colors, formatDate, labelText } from "../../lib/theme";
import type { CaseList, CaseSummary, Severity } from "../../lib/types";

const FILTERS: { key: Severity | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "caution", label: "Caution" },
  { key: "high", label: "High" },
  { key: "critical", label: "Critical" },
];

export default function Cases() {
  const { user } = useAuth();
  const [filter, setFilter] = useState<Severity | "all">("all");
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (activeFilter: Severity | "all") => {
    try {
      setError(null);
      const query = activeFilter === "all" ? "" : `&severity=${activeFilter}`;
      const list = await api<CaseList>(`/v1/cases?pageSize=100${query}`);
      setCases(list.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load cases.");
    }
  }, []);

  useFocusEffect(useCallback(() => { load(filter); }, [load, filter]));

  const emptyHint = user?.role === "school_admin"
    ? "Cases appear here only after someone explicitly shares them with your school."
    : user?.role === "guardian"
      ? "Cases from you or your linked users will appear here."
      : "When an analysis finds possibly harmful content, the case is kept here for 30 days.";

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right"]}>
      <View style={styles.filters}>
        {FILTERS.map((item) => (
          <FilterChip key={item.key} label={item.label} active={filter === item.key}
                      onPress={() => { setFilter(item.key); setCases(null); }} />
        ))}
      </View>

      {error ? <View style={styles.pad}><ErrorNotice message={error} onRetry={() => load(filter)} /></View> : null}

      {cases === null && !error ? <Loading label="Loading cases…" /> : null}

      {cases !== null ? (
        <FlatList
          data={cases}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listBody}
          refreshing={refreshing}
          onRefresh={async () => { setRefreshing(true); await load(filter); setRefreshing(false); }}
          ListEmptyComponent={<EmptyState title="No cases here" hint={emptyHint} />}
          renderItem={({ item }) => <CaseRow item={item} onPress={() => router.push(`/case/${item.id}`)} />}
        />
      ) : null}
    </SafeAreaView>
  );
}

function CaseRow({ item, onPress }: { item: CaseSummary; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Case: ${labelText[item.primaryLabel]}, severity ${item.severity}, ${formatDate(item.createdAt)}`}
      onPress={onPress}
      style={({ pressed }) => [styles.caseCard, pressed && { opacity: 0.8 }]}>
      <View style={styles.caseTop}>
        <SeverityChip severity={item.severity} />
        <Text style={styles.caseDate}>{formatDate(item.createdAt)}</Text>
      </View>
      <Text style={styles.caseTitle}>{labelText[item.primaryLabel]}
        {item.bodyShaming ? " · body-shaming tag" : ""}</Text>
      <Text style={styles.caseMeta}>
        {item.isOwn ? "Your submission" : `From ${item.ownerName}`}
        {item.platformName ? ` · ${item.platformName}` : ""}
        {item.status === "reviewed" ? " · reviewed" : " · pending review"}
        {item.hasEvidence ? " · 📎" : ""}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  filters: { flexDirection: "row", gap: 8, padding: 16, flexWrap: "wrap" },
  pad: { paddingHorizontal: 16 },
  listBody: { paddingHorizontal: 16, paddingBottom: 40, gap: 10 },
  caseCard: {
    backgroundColor: colors.surface, borderRadius: 14, padding: 14, gap: 6,
    borderWidth: 1, borderColor: colors.border,
  },
  caseTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  caseDate: { color: colors.muted, fontSize: 13 },
  caseTitle: { fontSize: 16, fontWeight: "700", color: colors.text },
  caseMeta: { fontSize: 13, color: colors.muted },
});
