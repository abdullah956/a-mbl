# ml/ — classification model workspace

## What exists today

Version 0.1 ships a deterministic **lexicon baseline** (`lexicon-0.1.0`) that
lives in [`backend/app/classifier.py`](../backend/app/classifier.py) with word
lists in [`backend/app/lexicon.py`](../backend/app/lexicon.py). It returns the
five primary labels, the Body Shaming tag, a heuristic confidence, and the
matched terms used for masking. It is CPU-free, explainable, and covered by
[`backend/tests/test_classifier.py`](../backend/tests/test_classifier.py)
against the shared fixtures in
[`tests/fixtures/labeled_samples.jsonl`](../tests/fixtures/labeled_samples.jsonl).

This is an honest placeholder, not a trained model. Its accuracy has **not**
been measured on a benchmark dataset and no such claim is made anywhere.

## What replaces it (roadmap §12, weeks 3–4)

1. **Data preparation** (`ml/data/`, kept out of Git): public datasets with
   clear licenses, a dataset card per source, label mapping to the five
   classes, manual review for Harassment and Body Shaming, deduplication, and
   a fixed 70/15/15 split by source group.
2. **Baseline training**: word + character TF-IDF, class-weighted Logistic
   Regression, calibrated probabilities, a separate one-vs-rest Body Shaming
   classifier, saved with joblib into `ml/artifacts/` (also ignored).
3. **Evaluation gates** (validation targets, not achievements): accuracy ≥ 85%,
   false-positive rate < 10%, macro-F1 ≥ 0.75, threat recall ≥ 0.80 — with the
   full metric report, confusion matrix, and error slices recorded here.
4. **Swap-in**: the trained pipeline replaces `classifier.classify()` behind
   the same `Prediction` interface and registers a new row in the
   `model_versions` table. Nothing else in the backend or app changes.

Until that work happens, the app displays results as uncertain estimates and
the model version string makes the lexicon baseline visible everywhere.
