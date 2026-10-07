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

The model is trained and active on the development Mac: `ml/artifacts/`
holds `model.joblib`, `metrics.json` and `confusion_matrix.png`, and
`/v1/health` there reports `"modelVersion": "tfidf-logreg-0.2.0"`. Without
`ml/artifacts/model.joblib` on disk (fresh clone or any other machine —
artifacts stay out of Git), the API falls back to the lexicon baseline
(`lexicon-0.1.0`) automatically, and the test suite pins that baseline via
`A_MBL_FORCE_LEXICON=1` so its assertions stay deterministic.

## Measured results (held-out test set, real class distribution)

From `python ml/train.py` on the development Mac (training took a few
minutes). Test set: 23,936 comments, never seen in training or threshold
tuning, kept at the real class distribution.

| Metric | Deployed model | Gate |
| --- | --- | --- |
| Accuracy | **0.903** | ≥ 0.85 ✅ |
| False-positive rate | **0.053** | < 0.10 ✅ |
| Threat recall | **0.718** | ≥ 0.80 ❌ |
| Macro F1 | **0.558** | ≥ 0.75 ❌ |

Per class on the test set:

| Class | Precision | Recall | Test examples |
| --- | --- | --- | --- |
| Normal | 0.98 | 0.95 | 21,503 |
| Offensive | 0.30 | 0.42 | 1,191 |
| Harassment | 0.56 | 0.62 | 975 |
| Hate speech | 0.49 | 0.47 | 196 |
| Threat | 0.28 | 0.72 | 71 |

Accuracy alone is misleading here: the data is ~90% Normal, so a do-nothing
model that answers Normal every time scores about 0.90 while detecting
nothing. The deployed model trades headline accuracy for threat recall: the
training split is rebalanced and the per-class decision thresholds are tuned
on the validation split, with a deliberately low bar for Threat. Tuned
thresholds: threat 0.10, hate speech 0.45, harassment 0.40, offensive 0.50.
The two failed gates are honest limitations, driven mainly by class scarcity
(478 threat examples out of 159,571) and domain mismatch (Wikipedia
discussion comments vs. teen chat). Full numbers:
[`artifacts/metrics.json`](artifacts/); test-set confusion matrix:
`artifacts/confusion_matrix.png`.

An earlier run on another machine recorded accuracy 0.906, false-positive
rate 0.048, threat recall 0.66 and macro F1 0.57 (threat threshold 0.15);
small differences like these come from library versions.

### How the data is prepared

- Jigsaw's six binary flags collapse to one primary label, most severe flag
  first: `threat` → threat, `identity_hate` → hate speech, `insult` →
  harassment, `toxic` / `severe_toxic` / `obscene` → offensive, otherwise
  normal. After removing empty and duplicate comments: normal 143,346,
  offensive 7,940, harassment 6,500, hate speech 1,307, threat 478.
- Stratified 70/15/15 split: train 111,699, validation 23,936, test 23,936.
- Only the training split is rebalanced — Normal downsampled to twice the
  harmful total (22,716 normal + 11,358 harmful = 34,074). Validation and
  test keep the real distribution.
- Features: word 1–2-grams plus character 3–5-grams (TF-IDF); classifier:
  class-weighted logistic regression. Thresholds come from a grid search on
  validation that maximizes threat recall + macro F1 while keeping the
  false-positive rate under 10%.

## Retraining

1. Put the Jigsaw Toxic Comment `train.csv` in `ml/data/` (gitignored). Either
   source works — the file and its columns are identical:
   - Hugging Face mirror, no account needed (CC-BY-SA-3.0, 159,571 rows):
     <https://huggingface.co/datasets/thesofakillers/jigsaw-toxic-comment-classification-challenge>
     — download its `train.csv`. This is the copy used on the development Mac.
   - Kaggle (needs a Kaggle account):
     <https://www.kaggle.com/datasets/julian3833/jigsaw-toxic-comment-classification-challenge>
2. `pip install -r ml/requirements.txt` into the project environment (the
   `a-mbl` conda env on the Mac, or the `.venv` on Windows).
3. `python ml/train.py` — writes `model.joblib`, `metrics.json`, and
   `confusion_matrix.png` into `ml/artifacts/` and prints the gate report.
4. Restart the backend; `/v1/health` shows the active model version.

`model.joblib` (~15 MB) is deliberately not in Git — hand it to the next
machine separately, or retrain there with the steps above.

## Future work

A fine-tuned transformer compared against this baseline (the proposal's
TensorFlow/PyTorch intent), and a labeled body-shaming dataset so the tag can
graduate from the lexicon.
