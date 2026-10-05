// Reports: role-scoped summaries with date-range filters, a weekly trend,
// unverified sender-alias grouping, and masked PDF download (§15, §8.4).

import { File, Paths } from "expo-file-system";
import { Redirect, useFocusEffect } from "expo-router";
import * as Sharing from "expo-sharing";
import React, { useCallback, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import {
  Banner, Body, Button, Card, ErrorNotice, Field, FilterChip, Loading, Screen, Subtitle,
} from "../components/ui";
import { api, ApiError, apiBinary } from "../lib/api";
import { useAuth } from "../lib/auth";
import { colors, labelText, severityMeta } from "../lib/theme";
import type { PrimaryLabel, Severity, SummaryReport } from "../lib/types";

const PRESETS = [
  { key: "7", label: "Last 7 days", days: 7 },
  { key: "30", label: "Last 30 days", days: 30 },
  { key: "90", label: "Last 90 days", days: 90 },
] as const;

type PresetKey = (typeof PRESETS)[number]["key"] | "custom";

const isoDay = (date: Date) => date.toISOString().slice(0, 10);

export default function Reports() {
  const { user, ready } = useAuth();
  const [preset, setPreset] = useState<PresetKey>("30");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [summary, setSummary] = useState<SummaryReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfNotice, setPdfNotice] = useState<string | null>(null);

  const range = useCallback((): { rangeFrom?: string; rangeTo?: string } => {
    if (preset === "custom") {
      return {
        rangeFrom: customFrom.trim() || undefined,
        rangeTo: customTo.trim() || undefined,
      };
    }
    const days = PRESETS.find((entry) => entry.key === preset)?.days ?? 30;
    const from = new Date();
    from.setDate(from.getDate() - days);
    return { rangeFrom: isoDay(from), rangeTo: isoDay(new Date()) };
  }, [preset, customFrom, customTo]);

  const load = useCallback(async () => {
    try {
      const { rangeFrom, rangeTo } = range();
      const params = new URLSearchParams();
      if (rangeFrom) params.set("rangeFrom", rangeFrom);
      if (rangeTo) params.set("rangeTo", rangeTo);
      const query = params.toString();
      const next = await api<SummaryReport>(`/v1/reports/summary${query ? `?${query}` : ""}`);
      setError(null);
      setSummary(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the report.");
    }
  }, [range]);

  // Presets load immediately (and again on focus); custom dates apply via the
  // button so typing doesn't fire requests.
  useFocusEffect(useCallback(() => {
    if (preset !== "custom") load();
  }, [preset, load]));

  const downloadPdf = async () => {
    setPdfBusy(true);
    setPdfNotice(null);
    try {
      const { rangeFrom, rangeTo } = range();
      const buffer = await apiBinary("/v1/reports/pdf", {
        method: "POST",
        body: { rangeFrom: rangeFrom ?? null, rangeTo: rangeTo ?? null },
      });
      const file = new File(Paths.cache, `a-mbl-report-${isoDay(new Date())}.pdf`);
      if (file.exists) file.delete();
      file.write(new Uint8Array(buffer));
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(file.uri, {
          mimeType: "application/pdf", dialogTitle: "a-mbl masked report",
        });
      } else {
        setPdfNotice("PDF created, but sharing is not available on this device.");
      }
    } catch (err) {
      setPdfNotice(err instanceof ApiError ? err.message : "Could not create the PDF.");
    }
    setPdfBusy(false);
  };

  if (ready && !user) return <Redirect href="/(auth)/welcome" />;

  return (
    <Screen>
      <Card>
        <Subtitle>Date range</Subtitle>
        <View style={styles.chipsWrap}>
          {PRESETS.map((entry) => (
            <FilterChip key={entry.key} label={entry.label} active={preset === entry.key}
                        onPress={() => setPreset(entry.key)} />
          ))}
          <FilterChip label="Custom" active={preset === "custom"}
                      onPress={() => setPreset("custom")} />
        </View>
        {preset === "custom" ? (
          <>
            <Field label="From (YYYY-MM-DD)" value={customFrom} onChangeText={setCustomFrom}
                   autoCapitalize="none" autoCorrect={false} placeholder="2026-06-01" />
            <Field label="To (YYYY-MM-DD)" value={customTo} onChangeText={setCustomTo}
                   autoCapitalize="none" autoCorrect={false} placeholder="2026-07-12" />
            <Button label="Apply range" kind="secondary" onPress={load} />
          </>
        ) : null}
      </Card>

      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {!summary && !error ? <Loading label="Loading report…" /> : null}

      {summary ? (
        <>
          <Card>
            <Subtitle>{summary.rangeFrom} to {summary.rangeTo}</Subtitle>
            <Body>
              {summary.total} harmful case{summary.total === 1 ? "" : "s"} —{" "}
              {summary.reviewed} reviewed, {summary.pending} pending.
            </Body>
            {(Object.entries(summary.bySeverity) as [Severity, number][]).map(([key, count]) => (
              <Body key={key} muted>
                {severityMeta[key].icon} {severityMeta[key].label}: {count}
              </Body>
            ))}
            {(Object.entries(summary.byLabel) as [PrimaryLabel, number][]).map(([key, count]) => (
              <Body key={key} muted>• {labelText[key]}: {count}</Body>
            ))}
          </Card>

          <Card>
            <Subtitle>Weekly trend</Subtitle>
            <WeeklyTrend weekly={summary.weekly} />
          </Card>

          <Card>
            <Subtitle>By sender alias</Subtitle>
            <Body muted>
              Aliases are entered by the person submitting the message and are not
              verified — treat them as context, not identification.
            </Body>
            {Object.keys(summary.bySender).length ? (
              Object.entries(summary.bySender)
                .sort(([, a], [, b]) => b - a)
                .map(([alias, count]) => (
                  <Body key={alias}>“{alias}”: {count} case{count === 1 ? "" : "s"}</Body>
                ))
            ) : (
              <Body muted>No cases in this range carry a sender alias.</Body>
            )}
          </Card>

          <Card>
            <Subtitle>Masked PDF report</Subtitle>
            <Body muted>
              The PDF contains masked previews and review notes for the cases your
              role can already see — never raw message content.
            </Body>
            {pdfNotice ? <Banner tone="warn" text={pdfNotice} /> : null}
            <Button label="Download and share PDF" onPress={downloadPdf} loading={pdfBusy} />
          </Card>
        </>
      ) : null}
    </Screen>
  );
}

function WeeklyTrend({ weekly }: { weekly: { weekStart: string; count: number }[] }) {
  if (!weekly.length) return <Body muted>No activity in this range.</Body>;
  const max = Math.max(...weekly.map((week) => week.count));
  const description = weekly
    .map((week) => `week of ${week.weekStart}: ${week.count}`)
    .join(", ");
  return (
    <View accessible accessibilityLabel={`Weekly trend. ${description}`}>
      <View style={styles.chartRow}>
        {weekly.map((week) => (
          <View key={week.weekStart} style={styles.chartCol}>
            <Text style={styles.chartCount} maxFontSizeMultiplier={1.4}>{week.count}</Text>
            <View style={[styles.chartBar,
                          { height: 8 + Math.round(72 * (week.count / max)) }]} />
            <Text style={styles.chartLabel} maxFontSizeMultiplier={1.4}>
              {week.weekStart.slice(5)}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  chipsWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chartRow: { flexDirection: "row", alignItems: "flex-end", gap: 8, minHeight: 110 },
  chartCol: { flex: 1, alignItems: "center", gap: 4 },
  chartBar: { width: "70%", borderRadius: 6, backgroundColor: colors.primary },
  chartCount: { fontSize: 12, fontWeight: "700", color: colors.primaryDark },
  chartLabel: { fontSize: 11, color: colors.muted },
});
