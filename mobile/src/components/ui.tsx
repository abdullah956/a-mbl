// Small shared UI kit: screen scaffold, cards, buttons, fields, banners,
// severity chips. 44pt touch targets and screen-reader labels throughout.

import React, { useRef, useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet,
  Text, TextInput, View, type TextInputProps,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, severityMeta } from "../lib/theme";
import type { Severity } from "../lib/types";

// §8.5: dynamic type is supported but capped so enlarged text reflows inside
// minHeight containers instead of clipping. Headings cap lower than body text.
const SCALE_HEADING = 1.5;
const SCALE_CONTROL = 1.8;
const SCALE_BODY = 2;

// `safeTop` is only for screens without a navigation header (welcome, boot):
// a header already sits below the status bar, so adding the top inset again
// would leave an empty band above every titled screen.
export function Screen({ children, scroll = true, safeTop = false }: {
  children: React.ReactNode; scroll?: boolean; safeTop?: boolean;
}) {
  const content = scroll ? (
    <ScrollView contentContainerStyle={styles.scrollBody}
                keyboardShouldPersistTaps="handled"
                automaticallyAdjustKeyboardInsets>{children}</ScrollView>
  ) : (
    <View style={styles.scrollBody}>{children}</View>
  );
  return (
    <SafeAreaView style={styles.screen}
                  edges={safeTop ? ["top", "left", "right"] : ["left", "right"]}>
      <KeyboardAware>{content}</KeyboardAware>
    </SafeAreaView>
  );
}

// Android draws edge to edge, so the window no longer shrinks for the
// keyboard and a focused field low on the screen ends up underneath it.
// Padding the screen by the overlap shrinks the ScrollView, and Android then
// scrolls the focused field back into view. The keyboard is reported in
// window coordinates, so the offset is this screen's own top in the window
// (the height of any header above it). iOS uses the ScrollView's
// automaticallyAdjustKeyboardInsets instead.
function KeyboardAware({ children }: { children: React.ReactNode }) {
  const frame = useRef<View>(null);
  const [top, setTop] = useState(0);
  if (Platform.OS !== "android") return <>{children}</>;
  return (
    <View ref={frame} style={styles.fill}
          onLayout={() => frame.current?.measureInWindow((_x, y) => setTop(y))}>
      <KeyboardAvoidingView style={styles.fill} behavior="padding" keyboardVerticalOffset={top}>
        {children}
      </KeyboardAvoidingView>
    </View>
  );
}

export function Card({ children, tone }: {
  children: React.ReactNode; tone?: "danger" | "info";
}) {
  return (
    <View style={[styles.card,
                  tone === "danger" && { borderColor: "#F3C4C0" },
                  tone === "info" && { backgroundColor: "#EFECFA" }]}>
      {children}
    </View>
  );
}

export function Title({ children }: { children: React.ReactNode }) {
  return (
    <Text accessibilityRole="header" style={styles.title}
          maxFontSizeMultiplier={SCALE_HEADING}>{children}</Text>
  );
}

export function Subtitle({ children }: { children: React.ReactNode }) {
  return <Text style={styles.subtitle} maxFontSizeMultiplier={SCALE_CONTROL}>{children}</Text>;
}

export function Body({ children, muted }: { children: React.ReactNode; muted?: boolean }) {
  return (
    <Text style={[styles.body, muted && { color: colors.muted }]}
          maxFontSizeMultiplier={SCALE_BODY}>{children}</Text>
  );
}

export function Button({ label, onPress, kind = "primary", disabled, loading }: {
  label: string;
  onPress: () => void;
  kind?: "primary" | "secondary" | "danger" | "ghost";
  disabled?: boolean;
  loading?: boolean;
}) {
  const inactive = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: Boolean(inactive) }}
      onPress={inactive ? undefined : onPress}
      style={({ pressed }) => [
        styles.button,
        kind === "secondary" && styles.buttonSecondary,
        kind === "danger" && styles.buttonDanger,
        kind === "ghost" && styles.buttonGhost,
        pressed && !inactive && { opacity: 0.75 },
        inactive && { opacity: 0.45 },
      ]}>
      {loading ? (
        <ActivityIndicator color={kind === "primary" || kind === "danger" ? "#fff" : colors.primary} />
      ) : (
        <Text maxFontSizeMultiplier={SCALE_CONTROL} style={[
          styles.buttonLabel,
          (kind === "secondary" || kind === "ghost") && { color: colors.primaryDark },
        ]}>{label}</Text>
      )}
    </Pressable>
  );
}

export function Field({ label, error, ...inputProps }: TextInputProps & {
  label: string; error?: string;
}) {
  return (
    <View style={styles.fieldWrap}>
      <Text style={styles.fieldLabel} maxFontSizeMultiplier={SCALE_CONTROL}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor="#9B96B3"
        maxFontSizeMultiplier={SCALE_CONTROL}
        style={[styles.input, inputProps.multiline && styles.inputMultiline,
                error ? { borderColor: colors.danger } : null]}
        {...inputProps}
      />
      {error ? (
        <Text style={styles.fieldError} maxFontSizeMultiplier={SCALE_BODY}>{error}</Text>
      ) : null}
    </View>
  );
}

export function Banner({ text, tone = "info" }: { text: string; tone?: "info" | "warn" | "error" }) {
  const palette = {
    info: { bg: "#EFECFA", fg: colors.primaryDark, icon: "ℹ" },
    warn: { bg: "#FFF3D1", fg: "#7A5E00", icon: "!" },
    error: { bg: "#FCE1DF", fg: colors.danger, icon: "⚠" },
  }[tone];
  return (
    <View accessibilityRole="alert"
          style={[styles.banner, { backgroundColor: palette.bg }]}>
      <Text style={[styles.bannerIcon, { color: palette.fg }]}
            maxFontSizeMultiplier={SCALE_CONTROL}>{palette.icon}</Text>
      <Text style={[styles.bannerText, { color: palette.fg }]}
            maxFontSizeMultiplier={SCALE_BODY}>{text}</Text>
    </View>
  );
}

export function SeverityChip({ severity }: { severity: Severity }) {
  const meta = severityMeta[severity];
  return (
    <View accessibilityLabel={`Severity: ${meta.label}`}
          style={[styles.chip, { backgroundColor: meta.bg }]}>
      <Text style={[styles.chipText, { color: meta.fg }]}
            maxFontSizeMultiplier={SCALE_CONTROL}>{meta.icon} {meta.label}</Text>
    </View>
  );
}

export function FilterChip({ label, active, onPress }: {
  label: string; active: boolean; onPress: () => void;
}) {
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ selected: active }}
               onPress={onPress}
               style={[styles.filterChip, active && styles.filterChipActive]}>
      <Text style={[styles.filterChipText, active && { color: "#fff" }]}
            maxFontSizeMultiplier={SCALE_CONTROL}>{label}</Text>
    </Pressable>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <View style={styles.empty}>
      <Text style={styles.emptyTitle} maxFontSizeMultiplier={SCALE_BODY}>{title}</Text>
      {hint ? <Text style={styles.emptyHint} maxFontSizeMultiplier={SCALE_BODY}>{hint}</Text> : null}
    </View>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <View style={styles.empty} accessibilityLabel={label}>
      <ActivityIndicator color={colors.primary} size="large" />
      <Text style={styles.emptyHint} maxFontSizeMultiplier={SCALE_BODY}>{label}</Text>
    </View>
  );
}

export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Card tone="danger">
      <Banner tone="error" text={message} />
      {onRetry ? <Button label="Try again" kind="secondary" onPress={onRetry} /> : null}
    </Card>
  );
}

export function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel} maxFontSizeMultiplier={SCALE_CONTROL}>{label}</Text>
      <Text style={styles.rowValue} maxFontSizeMultiplier={SCALE_CONTROL}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  fill: { flex: 1 },
  scrollBody: { padding: 16, gap: 12, paddingBottom: 40 },
  card: {
    backgroundColor: colors.surface, borderRadius: 16, padding: 16, gap: 10,
    borderWidth: 1, borderColor: colors.border,
  },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 16, fontWeight: "600", color: colors.text },
  body: { fontSize: 15, lineHeight: 21, color: colors.text },
  button: {
    minHeight: 48, borderRadius: 12, backgroundColor: colors.primary,
    alignItems: "center", justifyContent: "center", paddingHorizontal: 16,
  },
  buttonSecondary: {
    backgroundColor: "#EFECFA", borderWidth: 1, borderColor: colors.border,
  },
  buttonDanger: { backgroundColor: colors.danger },
  buttonGhost: { backgroundColor: "transparent" },
  buttonLabel: { color: "#fff", fontSize: 16, fontWeight: "600" },
  fieldWrap: { gap: 6 },
  fieldLabel: { fontSize: 14, fontWeight: "600", color: colors.text },
  input: {
    minHeight: 48, borderWidth: 1, borderColor: colors.border, borderRadius: 12,
    paddingHorizontal: 14, paddingVertical: 12, fontSize: 16, color: colors.text,
    backgroundColor: colors.inputBg,
  },
  inputMultiline: { minHeight: 130, textAlignVertical: "top" },
  fieldError: { color: colors.danger, fontSize: 13 },
  banner: {
    flexDirection: "row", gap: 8, borderRadius: 12, padding: 12, alignItems: "flex-start",
  },
  bannerIcon: { fontSize: 16, fontWeight: "700" },
  bannerText: { flex: 1, fontSize: 14, lineHeight: 20 },
  chip: {
    alignSelf: "flex-start", borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6,
  },
  chipText: { fontSize: 14, fontWeight: "700" },
  filterChip: {
    minHeight: 44, paddingHorizontal: 14, borderRadius: 999, justifyContent: "center",
    backgroundColor: "#EFECFA", borderWidth: 1, borderColor: colors.border,
  },
  filterChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  filterChipText: { color: colors.primaryDark, fontWeight: "600" },
  empty: { alignItems: "center", gap: 8, paddingVertical: 40 },
  emptyTitle: { fontSize: 16, fontWeight: "600", color: colors.text },
  emptyHint: { fontSize: 14, color: colors.muted, textAlign: "center", paddingHorizontal: 24 },
  row: {
    flexDirection: "row", justifyContent: "space-between", gap: 12,
    paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  rowLabel: { color: colors.muted, fontSize: 14 },
  rowValue: { color: colors.text, fontSize: 14, fontWeight: "600", flexShrink: 1, textAlign: "right" },
});
