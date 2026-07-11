"""Risk policy: severity mapping, review flags, alert eligibility, guidance.

Implements roadmap §6. The original model result is immutable; human reviews
are stored separately. Wording stays cautious — estimates, not judgments.
"""

from . import config
from .classifier import Prediction

_SEVERITY_ORDER = ["safe", "caution", "high", "critical"]

_BASE_SEVERITY = {
    "normal": "safe",
    "offensive": "caution",
    "harassment": "high",
    "hate_speech": "high",
    "threat": "critical",
}


def severity_for(prediction: Prediction) -> str:
    severity = _BASE_SEVERITY[prediction.primary_label]
    if prediction.body_shaming:  # Body Shaming raises severity to at least High
        if _SEVERITY_ORDER.index(severity) < _SEVERITY_ORDER.index("high"):
            severity = "high"
    return severity


def needs_review(prediction: Prediction) -> bool:
    return prediction.confidence < config.NEEDS_REVIEW_BELOW


def creates_case(severity: str) -> bool:
    """Anything above Safe becomes an encrypted, expiring case. Normal raw
    text is discarded immediately and never stored."""
    return severity != "safe"


def alert_eligible(prediction: Prediction, severity: str) -> bool:
    """Guardian/organization alerts require a High or Critical primary label
    with confident output. Offensive results and the Body Shaming tag alone
    never alert linked roles (roadmap §6.3, §14.1, §19)."""
    return (
        prediction.primary_label in ("harassment", "hate_speech", "threat")
        and severity in ("high", "critical")
        and prediction.confidence >= config.ALERT_CONFIDENCE_AT_LEAST
    )


_ADVICE = {
    "normal": [
        "No clear harmful-language signal was detected in the submitted text.",
        "If something still feels wrong, trust your judgment and talk to someone you trust.",
    ],
    "offensive": [
        "The submitted text may contain offensive language.",
        "You can keep this case, add context, or ask someone you trust to look at it.",
    ],
    "harassment": [
        "The submitted text may contain harassment signals.",
        "Consider keeping related messages together and sharing them with a trusted adult or your guardian.",
        "You do not have to respond to messages like this.",
    ],
    "hate_speech": [
        "The submitted text may contain hate-speech signals aimed at an identity or group.",
        "Consider reporting the content on the platform where it appeared and talking to someone you trust.",
    ],
    "threat": [
        "The submitted text may contain threatening language.",
        "If someone may be in immediate danger, contact a trusted person or an appropriate local service now.",
        "Consider keeping this evidence and involving a trusted adult as soon as possible.",
    ],
}

_UNCERTAIN = "This result is uncertain and should be reviewed by a person."
_ESTIMATE = "Classifications are automated estimates, not judgments about a person or incident."


def advice_for(prediction: Prediction, uncertain: bool) -> list[str]:
    lines = list(_ADVICE[prediction.primary_label])
    if prediction.body_shaming:
        lines.append("The text may also contain body-shaming language.")
    if uncertain:
        lines.insert(0, _UNCERTAIN)
    lines.append(_ESTIMATE)
    return lines
