// Neutral age screen shown before any personal details (roadmap §7.1).
// Only birth month and year are requested, and only the age band is kept.

import { router } from "expo-router";
import React, { useMemo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { Body, Button, Card, FilterChip, Screen, Title } from "../../components/ui";
import { colors } from "../../lib/theme";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function AgeScreen() {
  const currentYear = new Date().getFullYear();
  const years = useMemo(
    () => Array.from({ length: 80 }, (_, index) => currentYear - index),
    [currentYear],
  );
  const [month, setMonth] = useState<number | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [blocked, setBlocked] = useState(false);

  const continueNext = () => {
    if (month === null || year === null) return;
    const now = new Date();
    const age = now.getFullYear() - year - (now.getMonth() + 1 < month ? 1 : 0);
    if (age < 13) {
      setBlocked(true);
      return;
    }
    router.push({ pathname: "/(auth)/register", params: { year: String(year), month: String(month) } });
  };

  if (blocked) {
    return (
      <Screen>
        <Title>Thanks for telling us</Title>
        <Card>
          <Body>
            a-mbl supports people aged 13 and above, so an account can’t be created
            right now. Nothing you entered was saved.
          </Body>
          <Body muted>
            If messages are worrying you, please talk to a parent, teacher, or another
            adult you trust — they can help.
          </Body>
        </Card>
        <Button label="Back to start" onPress={() => router.replace("/(auth)/welcome")} />
      </Screen>
    );
  }

  return (
    <Screen>
      <Title>When were you born?</Title>
      <Body muted>Only the month and year — we use this to set up the right kind of account.</Body>

      <Card>
        <Text style={styles.groupLabel}>Birth month</Text>
        <View style={styles.wrap}>
          {MONTHS.map((name, index) => (
            <FilterChip key={name} label={name} active={month === index + 1}
                        onPress={() => setMonth(index + 1)} />
          ))}
        </View>
      </Card>

      <Card>
        <Text style={styles.groupLabel}>Birth year</Text>
        <View style={styles.wrap}>
          {years.map((value) => (
            <FilterChip key={value} label={String(value)} active={year === value}
                        onPress={() => setYear(value)} />
          ))}
        </View>
      </Card>

      <Button label="Continue" onPress={continueNext}
              disabled={month === null || year === null} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  groupLabel: { fontSize: 14, fontWeight: "600", color: colors.text },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
});
