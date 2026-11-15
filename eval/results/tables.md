# Evaluation results

Generated 2026-11-14T20:09:06 by `eval/run_eval.py`. 95% intervals: paired bootstrap over posts (B = 2000) unless marked Wilson. Pilot sample = 240 stratified posts, so shares are within-sample.

AI labellers: ['haiku', 'sonnet_a', 'sonnet_b']. Human labellers: none yet. Extra models: none.

## 1. AI vs AI agreement (consistency, not accuracy)

| Pair | n | Project kappa | Relevant kappa | Stance kappa (all) | Stance kappa (both say relevant) | Voice kappa |
|---|---|---|---|---|---|---|
| haiku vs sonnet_a | 240 | 0.90 [0.85, 0.94] | 0.89 [0.83, 0.95] | 0.73 [0.66, 0.80] | 0.63 [0.50, 0.74] (n 147) | 0.72 [0.64, 0.78] |
| haiku vs sonnet_b | 240 | 0.94 [0.91, 0.97] | 0.93 [0.87, 0.97] | 0.77 [0.70, 0.83] | 0.70 [0.59, 0.80] (n 153) | 0.67 [0.59, 0.74] |
| sonnet_a vs sonnet_b | 240 | 0.92 [0.87, 0.95] | 0.91 [0.85, 0.96] | 0.81 [0.74, 0.88] | 0.80 [0.69, 0.90] (n 149) | 0.82 [0.75, 0.88] |

Krippendorff alpha, all 3: project 0.92 [0.88, 0.95], stance 0.77 [0.71, 0.82], voice 0.73 [0.68, 0.79]

Note: the stance kappa "all" includes irrelevant posts where stance is unclear by rule, which inflates it. The "both say relevant" column is the honest stance number.

## 2. Leave one labeller out (each AI vs the agreed label of the other two)

Reference = label where the other two AI labellers agree; posts where they split are dropped from the reference. This tells us whether one model is an outlier. It is still AI vs AI.

**haiku vs agreed label of the other two** (n = 224; stance on 134 relevant posts)

| Metric | Value [95% CI] |
|---|---|
| Project accuracy | 0.97 [0.95, 0.99] |
| Project kappa | 0.96 [0.93, 0.99] |
| Relevance precision | 0.99 [0.97, 1.00] |
| Relevance recall | 0.99 [0.97, 1.00] |
| Stance accuracy (4 classes) | 0.87 [0.81, 0.93] |
| Stance kappa | 0.73 [0.61, 0.84] |
| Stance macro-F1 | 0.78 [0.68, 0.89] |
| Support/oppose posts labelled the same (Wilson) | 0.97 [0.83, 0.99] (29/30), support<->oppose flips: 0 |
| Voice kappa | 0.75 [0.67, 0.82] |

Stance confusion (rows = reference, columns = prediction):

| ref \ pred | support | oppose | neutral_informative | other |
|---|---|---|---|---|
| support | 17 | 0 | 0 | 0 |
| oppose | 0 | 12 | 0 | 1 |
| neutral_informative | 13 | 0 | 84 | 4 |
| other | 0 | 0 | 0 | 3 |

Per class: support P 0.57 R 1.00 F1 0.72 (n 17); oppose P 1.00 R 0.92 F1 0.96 (n 13); neutral_informative P 1.00 R 0.83 F1 0.91 (n 101); other P 0.38 R 1.00 F1 0.55 (n 3)

**sonnet_a vs agreed label of the other two** (n = 229; stance on 127 relevant posts)

| Metric | Value [95% CI] |
|---|---|
| Project accuracy | 0.95 [0.92, 0.97] |
| Project kappa | 0.94 [0.90, 0.97] |
| Relevance precision | 0.99 [0.98, 1.00] |
| Relevance recall | 0.96 [0.92, 0.99] |
| Stance accuracy (4 classes) | 0.91 [0.85, 0.95] |
| Stance kappa | 0.80 [0.68, 0.90] |
| Stance macro-F1 | 0.84 [0.74, 0.94] |
| Support/oppose posts labelled the same (Wilson) | 0.81 [0.65, 0.90] (29/36), support<->oppose flips: 0 |
| Voice kappa | 0.93 [0.87, 0.98] |

Stance confusion (rows = reference, columns = prediction):

| ref \ pred | support | oppose | neutral_informative | other |
|---|---|---|---|---|
| support | 17 | 0 | 7 | 0 |
| oppose | 0 | 12 | 0 | 0 |
| neutral_informative | 1 | 1 | 83 | 3 |
| other | 0 | 0 | 0 | 3 |

Per class: support P 0.94 R 0.71 F1 0.81 (n 24); oppose P 0.92 R 1.00 F1 0.96 (n 12); neutral_informative P 0.92 R 0.94 F1 0.93 (n 88); other P 0.50 R 1.00 F1 0.67 (n 3)

**sonnet_b vs agreed label of the other two** (n = 220; stance on 115 relevant posts)

| Metric | Value [95% CI] |
|---|---|
| Project accuracy | 0.99 [0.97, 1.00] |
| Project kappa | 0.98 [0.96, 1.00] |
| Relevance precision | 0.98 [0.95, 1.00] |
| Relevance recall | 1.00 [1.00, 1.00] |
| Stance accuracy (4 classes) | 0.99 [0.97, 1.00] |
| Stance kappa | 0.98 [0.93, 1.00] |
| Stance macro-F1 | 0.99 [0.97, 1.00] |
| Support/oppose posts labelled the same (Wilson) | 0.97 [0.83, 0.99] (29/30), support<->oppose flips: 0 |
| Voice kappa | 0.91 [0.85, 0.96] |

Stance confusion (rows = reference, columns = prediction):

| ref \ pred | support | oppose | neutral_informative | other |
|---|---|---|---|---|
| support | 17 | 0 | 1 | 0 |
| oppose | 0 | 12 | 0 | 0 |
| neutral_informative | 0 | 0 | 82 | 0 |
| other | 0 | 0 | 0 | 3 |

Per class: support P 1.00 R 0.94 F1 0.97 (n 18); oppose P 1.00 R 1.00 F1 1.00 (n 12); neutral_informative P 0.99 R 1.00 F1 0.99 (n 82); other P 1.00 R 1.00 F1 1.00 (n 3)

## 3. Keyword baseline vs 3-AI consensus (relevance)

n = 239: precision 0.79 [0.73, 0.85], recall 0.98 [0.96, 1.00], project accuracy 0.73 [0.67, 0.78]. Counts: {'tp': 152, 'fp': 40, 'fn': 3, 'tn': 44, 'precision': 0.7916666666666666, 'recall': 0.9806451612903225, 'f1': 0.8760806916426512}.

The sample over-represents real candidates (200 of 240 are from candidate sets), so on the full 39,361 records keyword precision will be lower. Measure it on a random sample of keyword hits before quoting a full-data number.

## 4. Vendor sentiment vs 3-AI consensus stance (relevant posts)

Vendor score read as stance (1 = support, 0 = neutral, -1 = oppose) matches the consensus in 46/127 = 0.36 [0.28, 0.45] (Wilson). 62 posts scored positive are neutral reports. 23/150 relevant posts have no score.

## 5. Stance counts per project (3-AI consensus, within the stratified sample)

| Project | n | Support | Oppose | Neutral | Mixed/unclear | Oppose share (Wilson) |
|---|---|---|---|---|---|---|
| bonn_cablecar | 26 | 8 | 3 | 15 | 0 | 0.12 [0.04, 0.29] |
| heilbronn_cablecar | 62 | 9 | 9 | 43 | 1 | 0.15 [0.08, 0.25] |
| ipai | 27 | 3 | 1 | 22 | 1 | 0.04 [0.01, 0.18] |
| paris_c1 | 35 | 6 | 0 | 28 | 1 | 0.00 [0.00, 0.10] |

Heilbronn posts with consensus voice = citizen in this sample: n = 12, {'other': 1, 'oppose': 8, 'neutral_informative': 1, 'support': 2}. With n this small every share has an interval of roughly plus or minus 20 to 35 points (see section 10).

## 6. Voting with abstention and vote-share calibration (AI proxy, leave one out)

For each held-out AI labeller: the other two vote. Confidence = share of the two votes for the chosen label (1.0 = they agree, 0.5 = split). "Correct" = the held-out labeller gives the same label. This is AI vs AI; the human version is in section 8.

- project: when the two split (n 47) the third matches 0.51; when the two agree (n 673) the third matches 0.97. ECE 0.031.
- stance: when the two split (n 79) the third matches 0.53; when the two agree (n 386) the third matches 0.92. ECE 0.074.
- Abstain unless all 3 agree, project: coverage 217/240 = 0.90 [0.86, 0.94]. Accuracy on the covered posts needs human labels (section 8).
- Abstain unless all 3 agree, stance: coverage 118/155 = 0.76 [0.69, 0.82]. Accuracy on the covered posts needs human labels (section 8).

## 7. Prevalence correction on real pilot data (proxy truth)

Set-up with a known answer: pretend haiku is the deployed model and sonnet_a is the truth. Split the relevant posts at random: half is the "gold set" (both labels known), half is "unlabelled" (only haiku used). We know sonnet_a on the unlabelled half, so we can see which estimate lands closer. Repeated over 200 random splits.

| Class | Proxy truth | Raw count (CC) | ACC [95% CI] | PPI [95% CI] |
|---|---|---|---|---|
| support | 0.12 | 0.23 | 0.00 [0.00, 0.16] | 0.06 [0.00, 0.20] |
| oppose | 0.09 | 0.08 | 0.08 [0.00, 0.15] | 0.08 [0.01, 0.15] |
| neutral_informative | 0.73 | 0.65 | 0.92 [0.75, 0.99] | 0.85 [0.71, 0.99] |
| other | 0.06 | 0.04 | 0.00 [0.00, 0.07] | 0.01 [0.00, 0.08] |

Over 200 splits, mean absolute error per class share: CC 0.073, ACC 0.059, PPI 0.040. PPI 95% intervals contained the proxy truth 98% of the time.

Read this carefully: the two models disagree little, so the correction has little to fix here. It shows the code runs on real data and that the intervals are honest; the real test is with human gold.

## 8. Human labels

**Pending.** No human labels in `eval/gold/` yet. Start the label tool (see `eval/README.md`).

## 9. Falsification regression suite (`eval/tests/regression_cases.jsonl`)

| Model | R1_ski_lift_irrelevant | R2_council_report_neutral | R3_accident_elsewhere_not_hn | R4_syndicated_count_once | R5_ipai_without_cablecar | failures |
|---|---|---|---|---|---|---|
| haiku | 9/10 | 5/6 | 3/3 (+2 not checkable) | 4/4 | 8/8 | R1_ski_lift_irrelevant:P161: project=other_cablecar, expected one of ['irrelevant']; R2_council_report_neutral:P183: stance=support, expected one of ['neutral_informative'] |
| sonnet_a | 10/10 | 6/6 | 3/3 (+2 not checkable) | 4/4 | 7/8 | R5_ipai_without_cablecar:P049: project=heilbronn_cablecar, must not be ['heilbronn_cablecar'] |
| sonnet_b | 10/10 | 6/6 | 3/3 (+2 not checkable) | 4/4 | 8/8 | none |
| ai_majority_3 | 10/10 | 6/6 | 3/3 (+2 not checkable) | 4/4 | 8/8 | none |
| keyword_baseline | 9/10 | 0/0 (+6 not checkable) | 3/3 (+2 not checkable) | 2/2 (+2 not checkable) | 8/8 | R1_ski_lift_irrelevant:P063: project=heilbronn_cablecar, expected one of ['irrelevant'] |

Reference dedup (5-word shingles, Jaccard 0.8): 4/4 cases pass.

Cases were picked by Claude from the data while seeing the AI labels, so they are known hard spots, not a random sample. A pass rate here is not an accuracy. Humans confirm the expected labels via section 8.

## 10. Sample size: what n gives what interval

| n | p = 0.5: half-width / Wilson | p = 0.8 | p = 0.9 |
|---|---|---|---|
| 10 | +/-0.31 / [0.24, 0.76] | +/-0.25 / [0.49, 0.94] | +/-0.19 / [0.60, 0.98] |
| 22 | +/-0.21 / [0.31, 0.69] | +/-0.17 / [0.61, 0.93] | +/-0.12 / [0.72, 0.97] |
| 30 | +/-0.18 / [0.33, 0.67] | +/-0.14 / [0.63, 0.91] | +/-0.11 / [0.74, 0.96] |
| 60 | +/-0.13 / [0.38, 0.62] | +/-0.10 / [0.68, 0.88] | +/-0.08 / [0.80, 0.95] |
| 100 | +/-0.10 / [0.40, 0.60] | +/-0.08 / [0.71, 0.87] | +/-0.06 / [0.83, 0.94] |
| 166 | +/-0.08 / [0.42, 0.57] | +/-0.06 / [0.73, 0.85] | +/-0.05 / [0.84, 0.94] |
| 300 | +/-0.06 / [0.44, 0.56] | +/-0.04 / [0.75, 0.84] | +/-0.03 / [0.86, 0.93] |
| 1000 | +/-0.03 / [0.47, 0.53] | +/-0.03 / [0.77, 0.82] | +/-0.02 / [0.88, 0.92] |

