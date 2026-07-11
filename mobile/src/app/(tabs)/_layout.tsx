import { Redirect, Tabs } from "expo-router";
import React from "react";
import { Text, type ColorValue } from "react-native";

import { useAuth } from "../../lib/auth";
import { colors } from "../../lib/theme";

function TabIcon({ glyph, color }: { glyph: string; color: ColorValue }) {
  return <Text style={{ fontSize: 20, color }} accessibilityElementsHidden>{glyph}</Text>;
}

export default function TabsLayout() {
  const { user, ready } = useAuth();
  if (ready && !user) return <Redirect href="/(auth)/welcome" />;
  if (ready && user && user.status === "pending_guardian") return <Redirect href="/pending" />;

  const isGuardian = user?.role === "guardian";
  const isAdmin = user?.role === "school_admin";

  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.background },
        headerTitleStyle: { fontWeight: "700", color: colors.text },
        tabBarActiveTintColor: colors.primaryDark,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
        tabBarLabelStyle: { fontSize: 12, fontWeight: "600" },
        sceneStyle: { backgroundColor: colors.background },
      }}>
      <Tabs.Screen name="index" options={{
        title: isGuardian ? "Overview" : isAdmin ? "Overview" : "Home",
        tabBarIcon: ({ color }) => <TabIcon glyph="⌂" color={color} />,
      }} />
      <Tabs.Screen name="analyze" options={{
        title: "Analyze",
        tabBarIcon: ({ color }) => <TabIcon glyph="✎" color={color} />,
      }} />
      <Tabs.Screen name="cases" options={{
        title: isAdmin ? "Review" : "Cases",
        tabBarIcon: ({ color }) => <TabIcon glyph="▤" color={color} />,
      }} />
      <Tabs.Screen name="alerts" options={{
        title: "Alerts",
        tabBarIcon: ({ color }) => <TabIcon glyph="◉" color={color} />,
      }} />
      <Tabs.Screen name="profile" options={{
        title: "Profile",
        tabBarIcon: ({ color }) => <TabIcon glyph="◐" color={color} />,
      }} />
    </Tabs>
  );
}
