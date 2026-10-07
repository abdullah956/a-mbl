# ml/ — classification model workspace

## What exists

The backend ships a **hybrid classifier**. A trained TF-IDF pipeline
(`tfidf-logreg-0.2.0`, word + character n-grams, class-weighted logistic
regression, per-class decision thresholds) decides the primary label and
confidence; the deterministic lexicon baseline in
[`backend/app/classifier.py`](../backend/app/classifier.py) remains as a
safety net and still owns two jobs the model cannot do: the matched terms used
to censor previews/PDFs, and the Body Shaming tag (no public dataset labels
it). Verdicts merge severity-max, so a lexicon catch is never downgraded.

Without `ml/artifacts/model.joblib` on disk (fresh clone — artifacts stay out
of Git), the API falls back to the lexicon baseline automatically, and the
test suite pins that baseline via `A_MBL_FORCE_LEXICON=1` so its assertions
stay deterministic.

## Measured results (held-out test set, real class distribution)

| Metric | Naive baseline | Deployed model | Gate |
| --- | --- | --- | --- |
| Accuracy | 0.934 | **0.906** | ≥ 0.85 ✅ |
| False-positive rate | 0.002 | **0.048** | < 0.10 ✅ |
| Threat recall | 0.37 | **0.66** | ≥ 0.80 ❌ |
| Macro F1 | 0.54 | **0.57** | ≥ 0.75 ❌ |

The naive run shows why accuracy alone is misleading here: the data is ~90%
Normal, so a do-nothing model scores 0.90. The deployed model trades a little
headline accuracy for nearly doubled threat recall (rebalanced training split;
validation-tuned thresholds with a deliberately low bar for Threat). The two
failed gates are honest limitations, driven mainly by class scarcity (478
threat examples out of 159,571) and domain mismatch (Wikipedia discussion
comments vs. teen chat). Full numbers: [`artifacts/metrics.json`](artifacts/)
and `metrics_naive_baseline.json`; test-set confusion matrix:
`confusion_matrix.png`.

## Retraining

1. Download the Jigsaw Toxic Comment `train.csv` from Kaggle
   (<https://www.kaggle.com/datasets/julian3833/jigsaw-toxic-comment-classification-challenge>)
   into `ml/data/` (gitignored).
2. `pip install -r ml/requirements.txt` into the project venv.
3. `python ml/train.py` — writes `model.joblib`, `metrics.json`, and
   `confusion_matrix.png` into `ml/artifacts/` and prints the gate report.
4. Restart the backend; `/v1/health` shows the active model version.

`model.joblib` (~15 MB) is deliberately not in Git — hand it to the next
machine separately, or retrain there with the steps above.

## Future work

A fine-tuned transformer compared against this baseline (the proposal's
TensorFlow/PyTorch intent), and a labeled body-shaming dataset so the tag can
graduate from the lexicon.
