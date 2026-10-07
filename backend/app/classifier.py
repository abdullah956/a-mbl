"""Text classifier: trained model with the lexicon baseline as a safety net.

The trained TF-IDF pipeline (ml/train.py -> ml/artifacts/model.joblib) decides
the primary label and confidence when the artifact is present; the lexicon
below keeps the two jobs it is structurally better at — ``matched_terms``
(mask_text needs literal spans to censor) and the Body Shaming tag (no public
dataset labels it). Verdicts merge severity-max, so a lexicon catch is never
downgraded: the model only ever ADDS detections. Without the artifact (fresh
clone, tests) everything falls back to the deterministic lexicon baseline.
Optional platform/sender metadata is never an input, per roadmap §12.2.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import lexicon
from .db import now_iso

MODEL_VERSION = "lexicon-0.1.0"
MODEL_KIND = "lexicon-baseline"

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})

# Symbol "letters" that end a word are punctuation, not leet ("k1ll you!").
_TRAILING_SYMBOLS = re.compile(r"[!@$]+(?!\w)")

_TARGETING = re.compile(r"\b(you|your|youre|you're|yourself|u|ur|urself)\b")


def _compile(phrases: list[str]) -> list[tuple[str, re.Pattern]]:
    compiled = []
    for phrase in phrases:
        pattern = r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b"
        compiled.append((phrase, re.compile(pattern)))
    return compiled


_THREAT = _compile(lexicon.THREAT_PHRASES)
_HATE = _compile(lexicon.HATE_PHRASES)
_IDENTITY = _compile(lexicon.IDENTITY_TERMS)
_IDENTITY_ATTACK = _compile(lexicon.IDENTITY_ATTACK_TERMS)
_HARASSMENT = _compile(lexicon.HARASSMENT_PHRASES)
_OFFENSIVE = _compile(lexicon.OFFENSIVE_TERMS)
_BODY = _compile(lexicon.BODY_SHAMING_TERMS)

# phrase -> pattern across every list, to test a matched term against the
# plain lowercase form (same phrase always compiles to the same pattern).
_ALL_PATTERNS = dict(_THREAT + _HATE + _IDENTITY + _IDENTITY_ATTACK + _HARASSMENT + _OFFENSIVE + _BODY)


def variants(text: str) -> list[str]:
    """Search forms for one text: the plain lowercase form (so punctuation like
    'kill you!' still matches), the leet-translated form (so '1d1ot' matches),
    a leet form with word-final '!@$' dropped first (so 'k1ll you!' matches —
    translating that '!' to 'i' would glue it onto the word), and
    repeat-collapsed forms of each (so 'loooser' matches). Each variant is
    searched SEPARATELY — never concatenated — so a phrase can never match
    across variant boundaries."""
    lowered = text.lower()
    forms: list[str] = []
    for base in (lowered, lowered.translate(_LEET),
                 _TRAILING_SYMBOLS.sub("", lowered).translate(_LEET)):
        for form in (base,
                     re.sub(r"(.)\1{2,}", r"\1\1", base),   # loooser -> looser
                     re.sub(r"(.)\1{1,}", r"\1", base)):    # looser  -> loser
            if form not in forms:
                forms.append(form)
    return forms


def _hits(forms: list[str], compiled: list[tuple[str, re.Pattern]]) -> list[str]:
    return [phrase for phrase, pattern in compiled
            if any(pattern.search(form) for form in forms)]


@dataclass
class Prediction:
    primary_label: str
    confidence: float
    body_shaming: bool
    matched_terms: list[str] = field(default_factory=list)
    model_version: str = MODEL_VERSION


_BASE_CONFIDENCE = {"threat": 0.62, "hate_speech": 0.60, "harassment": 0.58, "offensive": 0.55}


def _confidence(label: str, hit_count: int, targeted: bool, obfuscated: bool = False) -> float:
    # Deliberate masking (l0ser, loooser) is evidence of intent — someone
    # dodging a filter knows the word is harmful — so it raises confidence.
    value = (_BASE_CONFIDENCE[label] + 0.13 * hit_count + (0.08 if targeted else 0.0)
             + (0.10 if obfuscated else 0.0))
    return round(min(value, 0.97), 2)


def _lexicon_classify(text: str) -> Prediction:
    forms = variants(text)
    targeted = any(_TARGETING.search(form) for form in forms)

    threat = _hits(forms, _THREAT)
    hate = _hits(forms, _HATE)
    identity = _hits(forms, _IDENTITY)
    identity_attack = _hits(forms, _IDENTITY_ATTACK)
    harassment = _hits(forms, _HARASSMENT)
    offensive = _hits(forms, _OFFENSIVE)
    body = _hits(forms, _BODY)

    body_shaming = len(body) > 0

    # An identity term plus an attack term is a strong hate-speech signal.
    identity_combo = identity and identity_attack
    hate_all = hate + (identity + identity_attack if identity_combo else [])

    if threat:
        label, hits = "threat", threat
        count = len(threat)
    elif hate_all:
        label, hits = "hate_speech", hate_all
        count = len(hate) + (2 if identity_combo else 0)
    elif harassment or (targeted and len(offensive) >= 2) or (targeted and body):
        label = "harassment"
        hits = harassment + offensive + body
        count = len(harassment) + max(len(offensive) - 1, 0) + len(body)
        count = max(count, 1)
    elif offensive or body:
        label, hits = "offensive", offensive + body
        count = len(offensive) + len(body)
    else:
        return Prediction("normal", 0.92, False, [])

    matched = sorted(set(hits + body))
    # Obfuscated = at least one matched term is absent from the plain lowercase
    # text, i.e. it only surfaced after leet translation or repeat collapsing.
    obfuscated = any(
        term in _ALL_PATTERNS and not _ALL_PATTERNS[term].search(forms[0])
        for term in matched
    )
    return Prediction(label, _confidence(label, count, targeted, obfuscated), body_shaming, matched)


_SEVERITY_RANK = {"normal": 0, "offensive": 1, "harassment": 2, "hate_speech": 3, "threat": 4}

_ML = None


def _load_trained_model() -> None:
    """Load ml/artifacts/model.joblib if present; otherwise stay on the lexicon.

    A_MBL_FORCE_LEXICON=1 pins the lexicon (the test suite asserts its exact
    outputs); A_MBL_MODEL_PATH overrides the artifact location.
    """
    global _ML, MODEL_VERSION, MODEL_KIND
    if os.environ.get("A_MBL_FORCE_LEXICON") == "1":
        return
    path = Path(
        os.environ.get("A_MBL_MODEL_PATH")
        or Path(__file__).resolve().parents[2] / "ml" / "artifacts" / "model.joblib"
    )
    if not path.exists():
        return
    try:
        import joblib

        bundle = joblib.load(path)
        pipeline = bundle["pipeline"]
        _ML = {
            "pipeline": pipeline,
            "index": {label: i for i, label in enumerate(pipeline.classes_)},
            "severity": bundle["severity"],
            "thresholds": bundle["thresholds"],
        }
        MODEL_VERSION = bundle["modelVersion"]
        MODEL_KIND = "tfidf-logreg"
    except Exception as exc:  # a broken artifact must not take the API down
        print(f"[classifier] could not load {path}: {exc} — using lexicon baseline")


def classify(text: str) -> Prediction:
    lexicon_prediction = _lexicon_classify(text)
    if _ML is None:
        return lexicon_prediction

    row = _ML["pipeline"].predict_proba([text])[0]
    label = "normal"
    for candidate in _ML["severity"]:  # worst first, per-class bars from validation
        if row[_ML["index"][candidate]] >= _ML["thresholds"][candidate]:
            label = candidate
            break
    confidence = float(row[_ML["index"][label]])

    # Severity-max merge: whichever detector saw more danger wins; when they
    # agree, the agreement strengthens the verdict, so keep the higher score.
    if _SEVERITY_RANK[lexicon_prediction.primary_label] > _SEVERITY_RANK[label]:
        label = lexicon_prediction.primary_label
        confidence = lexicon_prediction.confidence
    elif _SEVERITY_RANK[lexicon_prediction.primary_label] == _SEVERITY_RANK[label]:
        confidence = max(confidence, lexicon_prediction.confidence)

    return Prediction(
        label,
        round(confidence, 2),
        lexicon_prediction.body_shaming,
        lexicon_prediction.matched_terms,
        model_version=MODEL_VERSION,
    )


_load_trained_model()


# Reverse of _LEET, so masking also catches the obfuscated spellings that the
# matcher normalized away (l0ser, st!upid, …).
_REVERSE_LEET = {"a": "a4@", "e": "e3", "i": "i1!", "o": "o0", "s": "s5$", "t": "t7"}


def _tolerant_pattern(term: str) -> re.Pattern:
    """A pattern that finds the term in the ORIGINAL text even when it was
    written with leet substitutions or repeated letters. Deliberately has no
    word boundaries: over-masking is safer than leaking."""
    parts = []
    for char in term:
        if char == " ":
            parts.append(r"\s+")
        elif char in _REVERSE_LEET:
            parts.append("[" + re.escape(_REVERSE_LEET[char]) + "]+")
        elif char.isalnum():
            parts.append(re.escape(char) + "+")
        else:
            parts.append(re.escape(char))
    return re.compile("".join(parts), re.IGNORECASE)


def _censor_word(match: re.Match) -> str:
    word = match.group(0)
    return word[0] + "•" * (len(word) - 1)


def mask_text(text: str, matched_terms: list[str], limit: int = 80) -> str:
    """Censor the text down to its shape and truncate — used for previews and
    PDF reports, which must never carry a readable raw message (§15.2).

    Matched terms go first, as whole phrases, because their obfuscated
    spellings contain symbols a word pattern would split on ('$hit', 'st!upid').
    Every remaining word is then reduced to its first letter as well:
    censoring only the harmful terms left the rest of the message — names,
    places, times — readable in the preview and the PDF.
    """
    masked = text
    for term in sorted(matched_terms, key=len, reverse=True):
        masked = _tolerant_pattern(term).sub(_censor_word, masked)
    masked = re.sub(r"\w+", _censor_word, masked)
    masked = masked.replace("\n", " ").strip()
    return masked[: limit - 1] + "…" if len(masked) > limit else masked


def register_model_version(conn) -> None:
    """Record the active model and its thresholds (roadmap §6.3)."""
    from . import config

    thresholds = {
        "needsReviewBelow": config.NEEDS_REVIEW_BELOW,
        "alertConfidenceAtLeast": config.ALERT_CONFIDENCE_AT_LEAST,
    }
    if _ML is not None:
        thresholds["classThresholds"] = _ML["thresholds"]
    conn.execute(
        "INSERT OR IGNORE INTO model_versions (version, kind, thresholds_json, created_at)"
        " VALUES (?, ?, ?, ?)",
        (MODEL_VERSION, MODEL_KIND, json.dumps(thresholds), now_iso()),
    )
