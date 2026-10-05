// Organization member management for school administrators (roadmap §8.4).
// Members are existing school-administrator accounts; adding one grants
// access to cases shared with the organization, removing revokes it.

import { Redirect, useFocusEffect } from "expo-router";
import React, { useCallback, useState } from "react";
import { Alert, StyleSheet, View } from "react-native";

import {
  Banner, Body, Button, Card, ErrorNotice, Field, Loading, Screen, Subtitle,
} from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Member, Organization } from "../lib/types";

export default function Members() {
  const { user, ready } = useAuth();

  if (ready && !user) return <Redirect href="/(auth)/welcome" />;
  if (!user || user.role !== "school_admin") {
    return (
      <Screen>
        <Banner tone="warn" text="Only school administrator accounts manage members." />
      </Screen>
    );
  }

  return (
    <Screen>
      <Body muted>
        Members can open cases explicitly shared with the organization and receive
        its alerts. Removing a member revokes that access immediately.
      </Body>
      {user.organizations.map((org) => (
        <OrgMembers key={org.id} org={org} selfId={user.id} />
      ))}
      {!user.organizations.length ? (
        <Body muted>Your account is not a member of any organization.</Body>
      ) : null}
    </Screen>
  );
}

function OrgMembers({ org, selfId }: { org: Organization; selfId: string }) {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await api<Member[]>(`/v1/organizations/${org.id}/members`);
      setError(null);
      setMembers(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load members.");
    }
  }, [org.id]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const add = async () => {
    setBusy(true);
    setAddError(null);
    try {
      await api(`/v1/organizations/${org.id}/members`, {
        method: "POST", body: { email: email.trim() },
      });
      setEmail("");
      await load();
    } catch (err) {
      setAddError(err instanceof ApiError ? err.message : "Could not add this member.");
    }
    setBusy(false);
  };

  const remove = (member: Member) => {
    Alert.alert(`Remove ${member.displayName}?`,
      "They immediately lose access to cases shared with this organization.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Remove", style: "destructive",
          onPress: async () => {
            try {
              await api(`/v1/organizations/${org.id}/members/${member.id}`, { method: "DELETE" });
              await load();
            } catch (err) {
              Alert.alert("Could not remove",
                          err instanceof ApiError ? err.message : "Please try again.");
            }
          },
        },
      ]);
  };

  return (
    <Card>
      <Subtitle>{org.name}</Subtitle>
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {members === null && !error ? <Loading label="Loading members…" /> : null}
      {members?.map((member) => (
        <View key={member.id} style={styles.memberRow}>
          <Body>{member.displayName} — {member.email}</Body>
          {member.id === selfId ? (
            <Body muted>This is you.</Body>
          ) : (
            <Button label={`Remove ${member.displayName}`} kind="danger"
                    onPress={() => remove(member)} />
          )}
        </View>
      ))}
      <Field label="Add an administrator by email" value={email} onChangeText={setEmail}
             autoCapitalize="none" keyboardType="email-address" autoCorrect={false}
             placeholder="admin@school.test" error={addError ?? undefined} />
      <Body muted>
        Only existing school administrator accounts (created on the server with
        create_admin) can be added.
      </Body>
      <Button label="Add member" onPress={add} loading={busy} disabled={!email.trim()} />
    </Card>
  );
}

const styles = StyleSheet.create({
  memberRow: { gap: 6, paddingVertical: 6 },
});
