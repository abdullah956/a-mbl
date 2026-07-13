// Analyze: manual text entry, or screenshot → OCR → user-corrected text.
// Only user-confirmed text is ever classified (roadmap §7.2–7.3).

import * as ImagePicker from "expo-image-picker";
import { router } from "expo-router";
import React, { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import {
  Banner, Body, Button, Card, Field, FilterChip, Screen, SeverityChip, Subtitle,
} from "../../components/ui";
import { api, ApiError, getApiUrl, checkHealth } from "../../lib/api";
import { normalizeScreenshot } from "../../lib/images";
import { colors, confidencePercent, formatDate, labelText } from "../../lib/theme";
import type { AnalysisResult, OcrResult } from "../../lib/types";

const MAX_CHARS = 5000;

// "unreachable" also covers a failed health check: the scan flow only shows
// once the server has positively confirmed that OCR is available.
type OcrStatus = "checking" | "ready" | "unavailable" | "unreachable";

interface AnalysisPayload {
  text: string;
  sourceType: "text" | "screenshot";
  platformName?: string;
  senderAlias?: string;
}

export default function Analyze() {
  const [mode, setMode] = useState<"text" | "screenshot">("text");
  const [text, setText] = useState("");
  const [platformName, setPlatformName] = useState("");
  const [senderAlias, setSenderAlias] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const [ocrStatus, setOcrStatus] = useState<OcrStatus>("checking");
  const [ocrBusy, setOcrBusy] = useState(false);
  const [ocrInfo, setOcrInfo] = useState<OcrResult | null>(null);
  const [textFromScreenshot, setTextFromScreenshot] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const url = await getApiUrl();
        if (!url) {
          setOcrStatus("unreachable");
          return;
        }
        setOcrStatus((await checkHealth(url)).ocrReady ? "ready" : "unavailable");
      } catch {
        setOcrStatus("unreachable");
      }
    })();
  }, []);

  const [flagBusy, setFlagBusy] = useState(false);
  // The payload the visible result was produced from. Flagging must re-submit
  // exactly that text, never whatever is in the form now.
  const [analyzed, setAnalyzed] = useState<AnalysisPayload | null>(null);

  const buildPayload = (): AnalysisPayload => ({
    text: text.trim(),
    sourceType: textFromScreenshot ? "screenshot" : "text",
    platformName: platformName.trim() || undefined,
    senderAlias: senderAlias.trim() || undefined,
  });

  // Editing any input invalidates the result on screen, so a stale card can
  // never be flagged or misread as belonging to the new text.
  const clearResult = () => {
    setResult(null);
    setAnalyzed(null);
  };

  const runAnalysis = async () => {
    setBusy(true);
    setError(null);
    setFieldErrors({});
    clearResult();
    const payload = buildPayload();
    try {
      setResult(await api<AnalysisResult>("/v1/analyses", { method: "POST", body: payload }));
      setAnalyzed(payload);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFieldErrors(err.fieldErrors ?? {});
      } else {
        setError("Analysis failed. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  };

  // §6.3: any result — even a safe one — can be kept for human review.
  const flagForReview = async () => {
    if (!analyzed) return;
    setFlagBusy(true);
    setError(null);
    try {
      setResult(await api<AnalysisResult>("/v1/analyses", {
        method: "POST", body: { ...analyzed, flagForReview: true },
      }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not keep this result.");
    } finally {
      setFlagBusy(false);
    }
  };

  const pickImage = async (source: "camera" | "gallery") => {
    setError(null);
    setOcrInfo(null);
    try {
      if (source === "camera") {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!permission.granted) {
          setError("Camera access was declined. You can allow it in system settings, or pick from the gallery instead.");
          return;
        }
      }
      const picked = source === "camera"
        ? await ImagePicker.launchCameraAsync({ quality: 0.8, exif: false })
        : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.8, exif: false });
      if (picked.canceled || !picked.assets?.length) return;

      const asset = picked.assets[0];
      setOcrBusy(true);
      const upload = await normalizeScreenshot(asset);
      const form = new FormData();
      form.append("file", upload as unknown as Blob);
      const ocr = await api<OcrResult>("/v1/ocr", { formData: form, method: "POST", timeoutMs: 30000 });
      setOcrInfo(ocr);
      // OCR replaces the message text, so any earlier result no longer
      // describes what is on screen — drop it before it can be misread or flagged.
      clearResult();
      setText(ocr.text);
      setTextFromScreenshot(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not read the screenshot.");
    } finally {
      setOcrBusy(false);
    }
  };

  const remaining = MAX_CHARS - text.length;

  return (
    <Screen>
      <View style={styles.modeRow}>
        <FilterChip label="Enter text" active={mode === "text"}
                    onPress={() => { setMode("text"); setTextFromScreenshot(false); }} />
        <FilterChip label="Scan screenshot" active={mode === "screenshot"}
                    onPress={() => setMode("screenshot")} />
      </View>

      {mode === "screenshot" ? (
        <Card>
          <Subtitle>Screenshot → text</Subtitle>
          {ocrStatus === "ready" ? (
            <>
              <Body muted>
                Pick one screenshot. The server extracts the text, and you review and
                correct it before anything is analyzed. The image itself is not kept.
              </Body>
              <View style={styles.modeRow}>
                <Button label="Camera" kind="secondary" onPress={() => pickImage("camera")}
                        loading={ocrBusy} />
                <Button label="Gallery" kind="secondary" onPress={() => pickImage("gallery")}
                        loading={ocrBusy} />
              </View>
            </>
          ) : ocrStatus === "checking" ? (
            <Body muted>Checking whether the server can read screenshots…</Body>
          ) : (
            <Banner tone="warn"
                    text={ocrStatus === "unavailable"
                      ? "Screenshot text extraction is not installed on the server yet (Tesseract). You can still type the message text yourself."
                      : "Could not confirm screenshot text extraction with the server. Check the connection, or type the message text yourself."} />
          )}
          {ocrInfo ? (
            <Banner tone={ocrInfo.lowConfidence ? "warn" : "info"}
                    text={ocrInfo.lowConfidence
                      ? "The text reader was not confident. Please check and fix the text below before analyzing."
                      : `Text extracted (reader confidence ${confidencePercent(ocrInfo.meanConfidence)}). Review it below, then analyze.`} />
          ) : null}
        </Card>
      ) : null}

      <Card>
        <Field
          label={textFromScreenshot ? "Extracted text (review and correct)" : "Message text"}
          value={text}
          onChangeText={(value) => { setText(value.slice(0, MAX_CHARS)); clearResult(); }}
          multiline
          placeholder="Paste or type the message you want to check…"
          error={fieldErrors.text}
        />
        <Text style={styles.counter}>{remaining} characters left</Text>
        <Field label="Platform (optional, as you describe it)" value={platformName}
               onChangeText={(value) => { setPlatformName(value); clearResult(); }}
               placeholder="e.g. ChatApp"
               maxLength={60} error={fieldErrors.platformName} />
        <Field label="Sender nickname (optional, unverified)" value={senderAlias}
               onChangeText={(value) => { setSenderAlias(value); clearResult(); }}
               placeholder="e.g. anon_17"
               maxLength={60} error={fieldErrors.senderAlias} />
        <Button label="Analyze" onPress={runAnalysis} loading={busy} disabled={!text.trim()} />
      </Card>

      {error ? <Banner tone="error" text={error} /> : null}

      {result ? (
        <ResultCard result={result} onOpenCase={(id) => router.push(`/case/${id}`)}
                    onFlag={flagForReview} flagBusy={flagBusy} />
      ) : null}
    </Screen>
  );
}

function ResultCard({ result, onOpenCase, onFlag, flagBusy }: {
  result: AnalysisResult; onOpenCase: (id: string) => void;
  onFlag: () => void; flagBusy: boolean;
}) {
  return (
    <Card>
      <Subtitle>Result</Subtitle>
      <View style={styles.resultHead}>
        <SeverityChip severity={result.severity} />
        <Body>{labelText[result.primaryLabel]} · confidence {confidencePercent(result.confidence)}</Body>
      </View>
      {result.bodyShaming ? <Body>Also tagged: possible body-shaming language.</Body> : null}
      {result.needsReview ? (
        <Banner tone="warn" text="This result is uncertain and should be reviewed by a person." />
      ) : null}
      {result.advice.map((line) => <Body key={line} muted>• {line}</Body>)}
      {result.caseId ? (
        <>
          <Body muted>
            Saved as a private case until {formatDate(result.retainedUntil)} (30 days), then
            deleted automatically.
          </Body>
          <Button label="Open case" kind="secondary" onPress={() => onOpenCase(result.caseId!)} />
        </>
      ) : (
        <>
          <Body muted>Nothing was saved — ordinary messages are discarded right away.</Body>
          <Body muted>
            If this still feels wrong, you can keep it as a case and ask for a
            human review. Keeping it stores the message text for 30 days, and
            anyone who can already see your cases — a linked guardian, for
            example — will be able to open it.
          </Body>
          <Button label="Keep for human review anyway" kind="secondary"
                  onPress={onFlag} loading={flagBusy} />
        </>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  modeRow: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  counter: { alignSelf: "flex-end", color: colors.muted, fontSize: 12 },
  resultHead: { gap: 8 },
});
