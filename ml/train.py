"""Train the cyberbullying classifier that replaces ``lexicon-0.1.0``.

Input:  ml/data/train.csv  — the Jigsaw Toxic Comment training file.
Output: ml/artifacts/      — model.joblib + metrics.json + confusion_matrix.png

Run:
    .venv\\Scripts\\python.exe ml\\train.py

The saved pipeline is consumed by backend/app/classifier.py behind the existing
``classify() -> Prediction`` interface, so nothing else in the backend changes.
"""

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline, FeatureUnion

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "train.csv"
ARTIFACTS = ROOT / "artifacts"

MODEL_VERSION = "tfidf-logreg-0.2.0"
LABELS = ["normal", "offensive", "harassment", "hate_speech", "threat"]

# Jigsaw is multi-label: one comment can be toxic AND insulting AND a threat.
# The app needs a single primary label, so collapse by severity — most severe
# flag present wins. This ordering mirrors the app's own severity tiers.
SEVERITY_ORDER = [
    ("threat", ["threat"]),
    ("hate_speech", ["identity_hate"]),
    ("harassment", ["insult"]),
    ("offensive", ["toxic", "severe_toxic", "obscene"]),
]


def to_primary_label(row: pd.Series) -> str:
    for label, flags in SEVERITY_ORDER:
        if any(row.get(flag, 0) == 1 for flag in flags):
            return label
    return "normal"


def load() -> pd.DataFrame:
    if not DATA.exists():
        raise SystemExit(
            f"Missing {DATA}.\n"
            "Download Jigsaw 'train.csv' from Kaggle and place it there:\n"
            "  https://www.kaggle.com/datasets/julian3833/"
            "jigsaw-toxic-comment-classification-challenge"
        )

    frame = pd.read_csv(DATA)
    expected = {"comment_text", "toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"}
    missing = expected - set(frame.columns)
    if missing:
        raise SystemExit(f"{DATA} is missing expected columns: {sorted(missing)}")

    frame = frame.rename(columns={"comment_text": "text"})
    frame["text"] = frame["text"].astype(str).str.strip()
    frame = frame[frame["text"].str.len() > 0]
    # Identical comments across splits would inflate the score.
    frame = frame.drop_duplicates(subset="text")
    frame["label"] = frame.apply(to_primary_label, axis=1)
    return frame[["text", "label"]]


def build_pipeline() -> Pipeline:
    # Word n-grams catch phrasing; char n-grams survive obfuscation ("k*ll", "l0ser"),
    # which is exactly where the lexicon baseline failed.
    features = FeatureUnion(
        [
            ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=100_000, sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, max_features=100_000, sublinear_tf=True)),
        ]
    )
    # No CalibratedClassifierCV here. Sigmoid calibration re-fits probabilities
    # against the real-world prior (90% normal), which dragged every prediction
    # back toward 'normal' and undid class_weight — threat recall collapsed to
    # 0.37. LogisticRegression already emits probabilities via predict_proba.
    clf = LogisticRegression(max_iter=3000, class_weight="balanced", C=4.0)
    return Pipeline([("features", features), ("clf", clf)])


def rebalance(train: pd.DataFrame, ratio: float = 2.0) -> pd.DataFrame:
    """Downsample 'normal' in the TRAINING split only.

    'normal' outnumbers every harmful class ~90:1, so the model can score 90%
    accuracy by always guessing 'normal' — which is what the first run did.
    Capping it at `ratio` x the harmful total forces the model to actually
    learn the harmful classes.

    The validation and test splits are NEVER touched: they keep the real-world
    distribution, so the reported metrics stay honest.
    """
    harmful = train[train["label"] != "normal"]
    normal = train[train["label"] == "normal"]
    keep = min(len(normal), int(len(harmful) * ratio))
    normal = normal.sample(n=keep, random_state=42)
    balanced = pd.concat([harmful, normal]).sample(frac=1.0, random_state=42)
    print(f"Rebalanced train: {len(normal):,} normal + {len(harmful):,} harmful = {len(balanced):,}")
    return balanced


# Severity order, worst first. A text is judged against each class in turn and
# takes the first label whose probability clears that class's threshold.
SEVERITY = ["threat", "hate_speech", "harassment", "offensive"]


def apply_thresholds(probabilities, classes, thresholds: dict[str, float]) -> list[str]:
    """Turn a probability matrix into labels using per-class bars, worst first."""
    index = {label: i for i, label in enumerate(classes)}
    order = [(label, index[label], thresholds[label]) for label in SEVERITY]
    predictions = []
    for row in probabilities:
        for label, i, bar in order:
            if row[i] >= bar:
                predictions.append(label)
                break
        else:
            predictions.append("normal")
    return predictions


def predict_with_thresholds(pipeline: Pipeline, texts, thresholds: dict[str, float]) -> list[str]:
    return apply_thresholds(pipeline.predict_proba(texts), pipeline.classes_, thresholds)


def tune_thresholds(pipeline: Pipeline, val: pd.DataFrame) -> dict[str, float]:
    """Pick per-class thresholds on the VALIDATION split (never on test).

    Missing a threat is far costlier than a false alarm, so threat gets the
    lowest bar it can while the overall false-positive rate stays inside the
    10% budget. Argmax gives every class the same implicit bar, which is what
    left threat recall at 0.42.
    """
    truth = val["label"].tolist()
    grid = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60]

    # Inference once; the grid search then only re-thresholds this matrix.
    probabilities = pipeline.predict_proba(val["text"])
    classes = pipeline.classes_

    best = {label: 0.5 for label in SEVERITY}
    best_score = -1.0
    for threat in grid:
        for hate in grid:
            for harass in grid:
                for offensive in grid:
                    candidate = {
                        "threat": threat,
                        "hate_speech": hate,
                        "harassment": harass,
                        "offensive": offensive,
                    }
                    predicted = apply_thresholds(probabilities, classes, candidate)
                    if false_positive_rate(truth, predicted) >= 0.10:
                        continue  # blows the false-positive budget
                    scores = classification_report(
                        truth, predicted, labels=LABELS, zero_division=0, output_dict=True
                    )
                    # Threat recall is the binding constraint; break ties on macro F1.
                    combined = scores["threat"]["recall"] + scores["macro avg"]["f1-score"]
                    if combined > best_score:
                        best_score, best = combined, candidate

    print(f"Tuned thresholds (on validation): {best}")
    return best


def false_positive_rate(y_true: list[str], y_pred: list[str]) -> float:
    """Share of genuinely Normal texts wrongly flagged as harmful.

    This is the number the report commits to (< 10%) and the one that matters
    ethically: a false positive accuses someone who did nothing.
    """
    normal = [(t, p) for t, p in zip(y_true, y_pred) if t == "normal"]
    if not normal:
        return 0.0
    return sum(1 for _, p in normal if p != "normal") / len(normal)


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    frame = load()
    print(f"Loaded {len(frame):,} unique comments")
    print(frame["label"].value_counts().to_string(), "\n")

    # 70/15/15. Stratified so rare classes (threat) appear in every split.
    train, temp = train_test_split(frame, test_size=0.30, stratify=frame["label"], random_state=42)
    val, test = train_test_split(temp, test_size=0.50, stratify=temp["label"], random_state=42)
    print(f"train={len(train):,}  val={len(val):,}  test={len(test):,} (test keeps the real distribution)")

    train = rebalance(train)

    print("\nTraining…")
    pipeline = build_pipeline()
    pipeline.fit(train["text"], train["label"])

    thresholds = tune_thresholds(pipeline, val)

    # Score on the held-out test split only — data the model has never seen,
    # still at the real-world 90%-normal ratio. Thresholds came from val, so
    # test remains an untouched estimate of real performance.
    predicted = predict_with_thresholds(pipeline, test["text"], thresholds)
    truth = test["label"].tolist()

    report = classification_report(truth, predicted, labels=LABELS, zero_division=0, output_dict=True)
    accuracy = accuracy_score(truth, predicted)
    macro_f1 = f1_score(truth, predicted, average="macro", labels=LABELS, zero_division=0)
    fpr = false_positive_rate(truth, list(predicted))
    threat_recall = report["threat"]["recall"]

    print("\n" + classification_report(truth, predicted, labels=LABELS, zero_division=0))

    # Four gates from ml/README.md. Accuracy alone is not a pass: on data that is
    # 90% normal, always answering 'normal' scores 0.90 and detects nothing.
    gates = [
        ("accuracy", accuracy, 0.85, "ge"),
        ("macro F1", macro_f1, 0.75, "ge"),
        ("threat recall", threat_recall, 0.80, "ge"),
        ("false-pos rate", fpr, 0.10, "lt"),
    ]
    for name, value, target, kind in gates:
        ok = value >= target if kind == "ge" else value < target
        sign = ">=" if kind == "ge" else "<"
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<15} {value:.3f}  (target {sign} {target})")
    print()

    metrics = {
        "modelVersion": MODEL_VERSION,
        "testSize": len(test),
        "accuracy": round(accuracy, 4),
        "macroF1": round(macro_f1, 4),
        "threatRecall": round(threat_recall, 4),
        "falsePositiveRate": round(fpr, 4),
        "targets": {"accuracy": 0.85, "macroF1": 0.75, "threatRecall": 0.80, "falsePositiveRate": 0.10},
        "thresholds": thresholds,
        "perClass": report,
    }
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=2))

    display = ConfusionMatrixDisplay(
        confusion_matrix(truth, predicted, labels=LABELS), display_labels=LABELS
    )
    display.plot(xticks_rotation=45, colorbar=False)
    display.figure_.tight_layout()
    display.figure_.savefig(ARTIFACTS / "confusion_matrix.png", dpi=150)

    joblib.dump(
        {
            "pipeline": pipeline,
            "labels": LABELS,
            "severity": SEVERITY,
            "thresholds": thresholds,
            "modelVersion": MODEL_VERSION,
        },
        ARTIFACTS / "model.joblib",
    )

    print(f"Saved model.joblib, metrics.json, confusion_matrix.png -> {ARTIFACTS}")


if __name__ == "__main__":
    main()
