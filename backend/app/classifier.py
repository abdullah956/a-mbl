"""Deterministic lexicon classifier — model version ``lexicon-0.1.0``.

Returns the five primary labels plus the Body Shaming tag with a heuristic
confidence in [0, 1]. It is intentionally simple, CPU-free, and explainable:
every prediction can be traced to matched terms (also used for masking).
Optional platform/sender metadata is never an input, per roadmap §12.2.
"""

import json
import re
from dataclasses import dataclass, field

from . import lexicon
from .db import now_iso

MODEL_VERSION = "lexicon-0.1.0"
MODEL_KIND = "lexicon-baseline"

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})

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


def variants(text: str) -> list[str]:
    """Search forms for one text: the plain lowercase form (so punctuation like
    'kill you!' still matches), the leet-translated form (so '1d1ot' matches),
    and repeat-collapsed forms of each (so 'loooser' matches). Each variant is
    searched SEPARATELY — never concatenated — so a phrase can never match
    across variant boundaries."""
    lowered = text.lower()
    forms: list[str] = []
    for base in (lowered, lowered.translate(_LEET)):
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


def _confidence(label: str, hit_count: int, targeted: bool) -> float:
    value = _BASE_CONFIDENCE[label] + 0.13 * hit_count + (0.08 if targeted else 0.0)
    return round(min(value, 0.97), 2)


def classify(text: str) -> Prediction:
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
    return Prediction(label, _confidence(label, count, targeted), body_shaming, matched)


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


def mask_text(text: str, matched_terms: list[str], limit: int = 80) -> str:
    """Censor matched terms (including obfuscated spellings) and truncate —
    used for previews and PDF reports."""
    masked = text
    for term in sorted(matched_terms, key=len, reverse=True):
        masked = _tolerant_pattern(term).sub(
            lambda m: m.group(0)[0] + "•" * (len(m.group(0)) - 1), masked)
    masked = masked.replace("\n", " ").strip()
    return masked[: limit - 1] + "…" if len(masked) > limit else masked


def register_model_version(conn) -> None:
    """Record the active model and its thresholds (roadmap §6.3)."""
    from . import config

    thresholds = {
        "needsReviewBelow": config.NEEDS_REVIEW_BELOW,
        "alertConfidenceAtLeast": config.ALERT_CONFIDENCE_AT_LEAST,
    }
    conn.execute(
        "INSERT OR IGNORE INTO model_versions (version, kind, thresholds_json, created_at)"
        " VALUES (?, ?, ?, ?)",
        (MODEL_VERSION, MODEL_KIND, json.dumps(thresholds), now_iso()),
    )
