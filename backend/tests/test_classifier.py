"""Classifier behavior on the shared labeled fixtures (roadmap §18.3)."""

import json

from backend.app import classifier, policy

from .conftest import FIXTURES


def _samples():
    lines = (FIXTURES / "labeled_samples.jsonl").read_text().strip().splitlines()
    return [json.loads(line) for line in lines]


def test_fixture_samples_get_expected_labels():
    failures = []
    for sample in _samples():
        prediction = classifier.classify(sample["text"])
        if prediction.primary_label != sample["label"]:
            failures.append(f"{sample['text']!r}: expected {sample['label']}, got {prediction.primary_label}")
        if prediction.body_shaming != sample["bodyShaming"]:
            failures.append(f"{sample['text']!r}: body shaming flag wrong")
    assert not failures, "\n".join(failures)


def test_confidence_range_and_determinism():
    for sample in _samples():
        first = classifier.classify(sample["text"])
        second = classifier.classify(sample["text"])
        assert 0.0 <= first.confidence <= 1.0
        assert (first.primary_label, first.confidence) == (second.primary_label, second.confidence)


def test_severity_mapping_and_body_shaming_floor():
    threat = classifier.classify("i will kill you")
    assert policy.severity_for(threat) == "critical"

    body_only = classifier.classify("lose some weight fatty")
    assert body_only.body_shaming is True
    assert policy.severity_for(body_only) == "high"  # tag raises severity to at least High

    normal = classifier.classify("see you at practice tomorrow")
    assert policy.severity_for(normal) == "safe"


def test_low_confidence_sets_needs_review():
    single_mild = classifier.classify("idiot")
    assert single_mild.primary_label == "offensive"
    assert policy.needs_review(single_mild) is True

    confident = classifier.classify("i will kill you")
    assert policy.needs_review(confident) is False


def test_alert_eligibility_rules():
    threat = classifier.classify("i will kill you")
    assert policy.alert_eligible(threat, policy.severity_for(threat)) is True

    offensive = classifier.classify("you are an idiot")
    assert policy.alert_eligible(offensive, policy.severity_for(offensive)) is False

    # Body-shaming tag alone (offensive label) never alerts linked roles.
    body_only = classifier.classify("lose some weight fatty")
    assert policy.alert_eligible(body_only, policy.severity_for(body_only)) is False


def test_obfuscated_terms_are_caught():
    assert classifier.classify("you are a l00ser and an 1d1ot").primary_label != "normal"
    assert classifier.classify("you're a looooser").primary_label != "normal"


def test_obfuscation_raises_confidence():
    # Dodging a filter is evidence of intent: the masked spelling must score
    # HIGHER than the plain one and clear the needs-review threshold.
    plain = classifier.classify("loser")
    masked = classifier.classify("l0ser")
    assert plain.primary_label == masked.primary_label == "offensive"
    assert masked.confidence > plain.confidence
    assert policy.needs_review(masked) is False


def test_punctuation_does_not_defeat_detection():
    # Regression: the leet map ('!'->'i' etc.) used to glue punctuation onto
    # the preceding word and break every word-boundary match.
    assert classifier.classify("i will kill you!").primary_label == "threat"
    assert classifier.classify("kys!").primary_label == "threat"
    assert classifier.classify("you're dead!").primary_label == "threat"
    assert classifier.classify("nobody likes you!!").primary_label == "harassment"


def test_no_phantom_matches_across_normalization_variants():
    # Regression: variants were joined with "\n" that \s+ could traverse, so
    # "...hurt" + "you..." matched "hurt you" across the boundary.
    for text in ("you never got hurt",
                 "you okay? that looked like it hurt",
                 "you know what i hate"):
        assert classifier.classify(text).primary_label == "normal", text


def test_mask_text_hides_obfuscated_spellings():
    text = "you are a l0ser and an 1d1ot"
    prediction = classifier.classify(text)
    masked = classifier.mask_text(text, prediction.matched_terms)
    assert "l0ser" not in masked and "1d1ot" not in masked


def test_mask_text_censors_matched_terms():
    prediction = classifier.classify("you are an idiot and a loser")
    masked = classifier.mask_text("you are an idiot and a loser", prediction.matched_terms)
    assert "idiot" not in masked and "loser" not in masked
    assert "i••••" in masked and "l••••" in masked


def test_mask_text_truncates_long_content():
    text = "you are an idiot " * 30
    prediction = classifier.classify(text)
    masked = classifier.mask_text(text, prediction.matched_terms)
    assert len(masked) <= 80
