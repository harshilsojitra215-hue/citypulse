# Evaluation: argument matcher v2, novelty detector, leakage audit

All numbers in this file are **provisional AI agreement**. The reference labels come from Claude Opus, not from people. Human labels are being collected (see the internal human-review protocol); `make review-eval` recomputes the pair table against them.

Reproduce: `CITYPULSE_LAB=<lab folder> make eval` (runs `pipeline/32_eval_v2.py`, about 40 s on a laptop once the GPU score files exist). Full output of the run behind this file: `lab/out/citypulse/eval_v2_stdout.txt`; machine-readable: `app_data/eval_v2.json`, `app_data/leakage_audit.json`.

## Setup

- **Unit:** every extracted claim is a query at its real publication date. Its candidates are the 10 most similar *older* claims of the same project plus the 10 most similar older claims of other projects (bge-m3 cosine). Candidates from the same post are excluded.
- **Strict time split (new in v2):** TRAIN queries 2025-01-04..2025-12-31 (602 queries), CAL queries 2026-01-01..2026-06-26 (179 queries, 3,580 pairs), TEST queries 2026-07-02..2026-10-26 (162 queries, 3,239 pairs, 9.0% "same").
- **Labels:** Opus labelled every pair as same / related / opposing / unrelated (`pipeline/prompts/pair_codebook_v1.md`). Sonnet, Haiku and local Qwen 27B labelled the same pairs independently. Opus vs Sonnet on TEST: kappa 0.68 for "same or not", 0.59 on all four labels. That disagreement is the ceiling any model can be measured against.
- **Model:** `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` (MIT licence) fine-tuned as a 4-class cross-encoder on TRAIN pairs, both text orders, class-weighted loss, 4 epochs, epoch chosen on a DEV split of TRAIN queries. Three seeds on an RTX 5090, 210 s each. Dev F1 ("same") per seed: 0.66, 0.70, 0.73.
- **Product scorer:** the seed-0 model plus a small logistic combiner with the topic/polarity/project features the pipeline already has. Combiner, thresholds, novelty cut-offs and the second-stage band are fitted on CAL only. TEST is only scored.

## 1. Same argument? (TEST pairs, 10 candidates per side)

| Method | Precision | Recall | F1 [95% interval] | Gain over cosine [95%] |
|---|---|---|---|---|
| bge-m3 cosine + CAL threshold (baseline) | 0.39 | 0.36 | 0.37 [0.28–0.46] | |
| cosine + topic/polarity | 0.38 | 0.50 | 0.43 [0.35–0.51] | −0.00 to +0.12 |
| fine-tuned matcher, text only | 0.52 | 0.74 | 0.61 [0.54–0.68] | +0.16 to +0.34 |
| **fine-tuned matcher + topic/polarity (PRODUCT)** | **0.60** | **0.70** | **0.65 [0.57–0.71]** | **+0.19 to +0.35** |
| same, average of 3 training runs | 0.55 | 0.79 | 0.65 [0.58–0.71] | +0.20 to +0.36 |
| LLM judge on every pair: Haiku | 0.56 | 0.90 | 0.69 [0.62–0.75] | +0.22 to +0.41 |
| LLM judge on every pair: Qwen 27B (local) | 0.66 | 0.78 | 0.71 [0.65–0.77] | +0.25 to +0.43 |
| LLM judge on every pair: Sonnet | 0.64 | 0.80 | 0.71 [0.65–0.76] | +0.25 to +0.43 |
| two-stage: PRODUCT, Qwen re-reads the uncertain band (0.30–0.85) | 0.57 | 0.88 | 0.69 [0.63–0.74] | +0.24 to +0.41 |

Intervals: bootstrap over whole queries (1,000 resamples). Single training runs, text only: F1 0.61, 0.65, 0.68.

Reading:
- The fine-tuned matcher is clearly better than embedding similarity: the gain interval excludes zero.
- LLM judges are a little better (about +0.05 F1) but are about 150 ms per pair against 0.86 ms for the matcher on the 5090. The product uses the matcher and keeps the LLM for an optional second look.
- **Compared with v1 (F1 0.71 at 5 candidates per side):** v2 at the same depth reaches 0.68. The drop is the price of the stricter split (TRAIN no longer overlaps CAL in time, see the leakage section). The v2 number is the honest one.

## 2. Under-grouping of loose paraphrases (issue B)

Three changes, each measured on TEST, none of them a blanket lower threshold:

1. **Depth 10 instead of 5.** More candidates are labelled and scored per claim, so a paraphrase ranked 6th to 10th by cosine is no longer invisible. All tables above use depth 10.
2. **Separate "related concern" tier.** "Same or related" is scored as its own relation with its own cut-off (0.98 on p(same)+p(related), the lowest cut-off with precision >= 0.90 on CAL). On TEST: precision 0.93, recall 0.66 (base rate 0.75). The UI shows these as *related*, never as *the same argument*, and they are never counted as extra evidence for a concern.
3. **Optional second stage.** Sending only the uncertain band to Qwen 27B raises recall from 0.70 to 0.88 at precision 0.57 (F1 0.65 to 0.69), with 30% of TEST pairs going to the LLM (the band was chosen on CAL with a 25% budget). Haiku could not meet the budget on CAL. This is measured but not switched on in the app, because it needs the GPU box.

**Hospital regression example** (Heilbronn, July 2026; best older match per claim):

| New claim | Best older match | p(same) | p(same or related) |
|---|---|---|---|
| Money goes to cable car while lung clinic closes | Money for cable car while Löwenstein hospital faces closure | 0.98 | 1.00 |
| Building cable car while closing hospital is absurd | Money for cable car while Löwenstein hospital faces closure | 0.88 | 1.00 |
| Money for cable car while Löwenstein hospital faces closure | Money available for cable car but not for family doctors | 0.49 | 0.99 |
| Luxury construction projects instead of good medical care | Cable car called a prestige project | 0.30 | 1.00 |

In v1, "Building cable car while closing hospital is absurd" scored 0.40 and stayed outside the group. In v2 it joins (0.88 >= 0.85). The other two are linked as related concerns, which is what a careful human would say too.

## 3. Is this claim new? (TEST, 162 claims)

Truth: a claim is new when Opus found no equivalent among all 10+10 older candidates.

Single cut-off fitted on CAL so that about 10% of familiar claims would be flagged:

| Scope | Method | Precision | Recall | Familiar claims wrongly flagged |
|---|---|---|---|---|
| same project (90 new / 72 familiar) | cosine | 0.91 | 0.21 | 2 of 72 (2.8%) |
| same project | **PRODUCT** | **0.94** | **0.32** | **2 of 72 (2.8%)** |
| anywhere (77 new / 85 familiar) | cosine | 0.83 | 0.26 | 4 of 85 (4.7%) |
| anywhere | PRODUCT | 0.91 | 0.27 | 2 of 85 (2.4%) |

**What the product actually shows: three states.** "New" only below the 5% quantile of familiar CAL scores, "familiar" only above the 90% quantile of new CAL scores, "ambiguous / needs review" in between (same-project scope, TEST):

| | shown as new | needs review | shown as familiar |
|---|---|---|---|
| truly new (90) | 19 | 55 | 16 |
| truly familiar (72) | 0 | 11 | 61 |

- Every claim shown as *new* was really new (19 of 19).
- 74 of 90 truly new claims (82%) reach an official as *new* or *needs review*. 16 (18%) are wrongly shown as a familiar argument: this is the main remaining miss.
- 41% of claims land in *needs review*. That is the cost of not over-claiming, and it is why the Emerging Concerns screen shows evidence, scores and cut-offs for every card.

**False alarms (issue C).** v1 aimed at 10% and got 15% on TEST. The cause was the calibration period: in v1, TRAIN (Jan 2025–Jun 2026) overlapped CAL (Jul 2025–Jun 2026) in time, so CAL scores did not look like scores on unseen months. With the strict split, v2 flags 2.8%. That is below the target, which means the cut-off is conservative: recall at the single cut-off fell from 0.81 to 0.32. The three-state display recovers most of it as *needs review*. No guaranteed false-alarm rate is claimed: the cut-off holds only as long as the future looks like the calibration months.

## 4. Contradiction detection (issue A)

Not solved, and switched off. Only 0.6% of training pairs are "opposing" (v1: 43 of 7,647; v2 similar), and v1 measured F1 0.13 on that class. The model still outputs an "opposing" probability, but no screen, endpoint or count uses it (`contradiction_detection: "disabled"` in `/api/health`). Fixing it needs its own sampling of opposing pairs. That is future work, not a retrain of the same data.

## 5. Leakage audit (issue D)

Result of `pipeline/32_eval_v2.py` (all checks are asserts; the script stops if one fails):

| Check | Result |
|---|---|
| Every candidate is older than its query (all 20,140 labelled pairs) | yes |
| Query claims in TRAIN, CAL, TEST are disjoint | yes |
| Time order TRAIN < CAL < TEST | yes: TRAIN to 2025-12-31, CAL 2026-01-01..06-26, TEST from 2026-07-02 |
| Same text pair in training and evaluation | 0 (25 training pairs were removed for this) |
| TEST query texts that also occur in training (syndicated copies) | 0 |
| TEST pairs with identical text on both sides | 1 of 3,239; F1 without it: 0.646 vs 0.648 |
| What was fitted on what | combiner, pair threshold, related threshold, novelty cut-offs, second-stage band: CAL only. Epoch: DEV (12% of TRAIN queries). TEST: scoring only |
| Replay / historical retrieval | the replay only compares a claim with claims published before it (`tests/test_engine_core.py::test_replay_order_and_cutoff`, `test_later_claims_do_not_change_earlier_evidence`, `test_replay_rejects_cutoff_inside_training_period`); cut-offs before 2026-07-01 are refused because the model was calibrated on data up to then |
| Same argument counted twice as evidence | one post = one voice; re-published copies are collapsed (`is_first_copy`, `test_one_post_is_one_voice`) |

**Problem found and fixed:** the v1 date overlap between TRAIN and CAL (section 3). All v2 numbers come from the corrected split.

**Soft spots that remain:**
- The replay period (Jul–Oct 2026, Heilbronn) was read by hand in v1 while the grouping and voice rules were designed. Those rules have no fitted parameters, but they were not chosen blind.
- bge-m3 and the base mDeBERTa were pre-trained by others on data of unknown date.
- The reference labels (Opus) come from the same model family as the training labels. Scored against Sonnet in v1, the gain held (0.64 vs 0.34). Only human labels settle this.

## 6. Speed and footprint

- Matcher: 0.86 ms per pair, both orders, on an RTX 5090. On an Apple M-series laptop, live matching of an uploaded batch (a few hundred claims × 20 candidates) takes seconds to a minute.
- Weights: 558 MB in fp16, loaded as float32 for inference. The fp16 export changes probabilities by at most 0.0045 (3,000 pairs checked).
