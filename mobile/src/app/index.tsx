import { Redirect } from "expo-router";

import { Loading, Screen } from "../components/ui";
import { useAuth } from "../lib/auth";

export default function Boot() {
  const { ready, hasServer, user } = useAuth();

  if (!ready) {
    return <Screen scroll={false}><Loading label="Starting a-mbl…" /></Screen>;
  }
  if (!hasServer) return <Redirect href="/connect" />;
  if (!user) return <Redirect href="/(auth)/welcome" />;
  if (user.status === "pending_guardian") return <Redirect href="/pending" />;
  return <Redirect href="/(tabs)" />;
}
