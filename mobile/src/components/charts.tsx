// Minimal View-based charts for the dashboard — no chart library, so nothing
// new has to exist in Expo Go. Single-series magnitude bars: one theme hue,
// values as direct labels (counts are small), zero-anchored baseline, and a
// per-bar accessibility label because touch has no hover.

import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors } from "../lib/theme";

const BAR_MAX_HEIGHT = 72;

export function ColumnChart({ data, unit }: {
  data: { label: string; value: number }[];
  unit: string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <View style={styles.columnRow} accessibilityRole="list">
      {data.map((d, i) => {
        const height = d.value > 0 ? Math.max(4, Math.round((d.value / max) * BAR_MAX_HEIGHT)) : 0;
        return (
          <View key={`${d.label}-${i}`} style={styles.column}
                accessibilityLabel={`${d.label}: ${d.value} ${unit}`}>
            <Text style={styles.value}>{d.value > 0 ? d.value : ""}</Text>
            <View style={styles.barSlot}>
              {height > 0 ? <View style={[styles.bar, { height }]} /> : null}
            </View>
            <Text style={styles.axisLabel} numberOfLines={1}>{d.label}</Text>
          </View>
        );
      })}
    </View>
  );
}

export function BarRows({ rows, unit }: {
  rows: { label: string; value: number }[];
  unit: string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <View style={styles.rowsWrap} accessibilityRole="list">
      {rows.map((r, i) => (
        <View key={`${r.label}-${i}`} style={styles.row}
              accessibilityLabel={`${r.label}: ${r.value} ${unit}`}>
          <Text style={styles.rowLabel} numberOfLines={1}>{r.label}</Text>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${Math.round((r.value / max) * 100)}%` }]} />
          </View>
          <Text style={styles.rowValue}>{r.value}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  columnRow: {
    flexDirection: "row", alignItems: "flex-end", justifyContent: "center",
    gap: 6, paddingTop: 4,
  },
  column: { alignItems: "center", gap: 2, minWidth: 26, maxWidth: 44, flex: 1 },
  value: { fontSize: 11, fontWeight: "700", color: colors.text, minHeight: 14 },
  barSlot: {
    height: BAR_MAX_HEIGHT, width: "100%", justifyContent: "flex-end",
    alignItems: "center", borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  bar: {
    width: 18, backgroundColor: colors.primary,
    borderTopLeftRadius: 4, borderTopRightRadius: 4,
  },
  axisLabel: { fontSize: 10, color: colors.muted },
  rowsWrap: { gap: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  rowLabel: { flex: 1, fontSize: 13, color: colors.text },
  track: {
    flex: 2, height: 8, borderRadius: 4, backgroundColor: "#EFECFA",
    overflow: "hidden",
  },
  fill: { height: "100%", borderRadius: 4, backgroundColor: colors.primary },
  rowValue: { fontSize: 12, fontWeight: "700", color: colors.text, minWidth: 18, textAlign: "right" },
});
