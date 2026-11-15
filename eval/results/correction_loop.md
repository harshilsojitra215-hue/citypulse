# Correction loop: simulated staff corrections (feasibility)

**Simulation.** "Staff answer" = the 3-run AI consensus on the 240 pilot posts. No real staff were involved. 30 repeats; each holds out 30% of posts as a test set; seed of 10 corrections, then rounds of 5. Kappa vs consensus on the test set; mean with the 10th to 90th percentile across repeats.

## relevance (local model: e5-base + LR)

240 posts, pool 168, classes {'irrelevant': 85, 'relevant': 155}, AI runs split on 15. LLM level (each AI run vs the other two, same test posts): kappa 0.95.

| Corrections | random | least_confident | llm_disagreement |
|---|---|---|---|
| 10 | 0.23 (0.02 to 0.48) | 0.23 (0.02 to 0.48) | 0.23 (0.02 to 0.48) |
| 15 | 0.36 (0.14 to 0.52) | 0.35 (0.09 to 0.53) | 0.24 (0.05 to 0.42) |
| 20 | 0.44 (0.26 to 0.58) | 0.44 (0.18 to 0.62) | 0.29 (0.09 to 0.48) |
| 30 | 0.52 (0.32 to 0.68) | 0.53 (0.33 to 0.69) | 0.46 (0.31 to 0.62) |
| 40 | 0.56 (0.39 to 0.71) | 0.57 (0.42 to 0.73) | 0.55 (0.38 to 0.71) |
| 50 | 0.58 (0.41 to 0.73) | 0.59 (0.32 to 0.75) | 0.63 (0.53 to 0.71) |
| 60 | 0.60 (0.47 to 0.71) | 0.63 (0.46 to 0.75) | 0.64 (0.53 to 0.76) |
| 80 | 0.65 (0.54 to 0.81) | 0.72 (0.64 to 0.81) | 0.69 (0.57 to 0.78) |
| 100 | 0.67 (0.55 to 0.76) | 0.71 (0.61 to 0.79) | 0.72 (0.62 to 0.82) |
| 120 | 0.69 (0.60 to 0.82) | 0.71 (0.57 to 0.82) | 0.71 (0.60 to 0.82) |
| 140 | 0.71 (0.59 to 0.81) | 0.71 (0.60 to 0.81) | 0.72 (0.61 to 0.81) |
| 160 | 0.73 (0.62 to 0.82) | 0.73 (0.61 to 0.82) | 0.72 (0.61 to 0.82) |
| 168 | 0.72 (0.60 to 0.82) | 0.72 (0.60 to 0.82) | 0.72 (0.60 to 0.82) |

Corrections needed to reach a share of the LLM level (mean curve): random: 80% at None, 90% at None, 100% at None; least_confident: 80% at None, 90% at None, 100% at None; llm_disagreement: 80% at None, 90% at None, 100% at None. "None" = not reached with the whole pool.

How wrong the local model looks on the posts staff are shown (mean accuracy on the shown batch, at 20 and 60 corrections): random: 0.75 / 0.81; least_confident: 0.49 / 0.67; llm_disagreement: 0.44 / 0.61. Actively chosen posts are the hard ones, so their error rate is NOT the model's accuracy; only randomly chosen checks estimate accuracy.

## stance (local model: TF-IDF + LR)

147 posts, pool 103, classes {'neutral_informative': 108, 'oppose': 13, 'support': 26}, AI runs split on 32. LLM level (each AI run vs the other two, same test posts): kappa 0.83.

| Corrections | random | least_confident | llm_disagreement |
|---|---|---|---|
| 10 | 0.04 (-0.04 to 0.16) | 0.04 (-0.04 to 0.16) | 0.04 (-0.04 to 0.16) |
| 15 | 0.06 (-0.04 to 0.21) | 0.07 (-0.01 to 0.21) | 0.05 (-0.07 to 0.23) |
| 20 | 0.07 (-0.04 to 0.21) | 0.13 (0.00 to 0.35) | 0.04 (-0.10 to 0.24) |
| 30 | 0.08 (-0.02 to 0.24) | 0.21 (0.08 to 0.38) | 0.03 (-0.13 to 0.24) |
| 40 | 0.11 (0.00 to 0.24) | 0.28 (0.12 to 0.47) | 0.12 (-0.04 to 0.28) |
| 50 | 0.15 (0.00 to 0.32) | 0.31 (0.13 to 0.45) | 0.19 (0.06 to 0.35) |
| 60 | 0.17 (0.00 to 0.36) | 0.31 (0.13 to 0.45) | 0.24 (0.05 to 0.44) |
| 80 | 0.23 (0.09 to 0.35) | 0.33 (0.13 to 0.49) | 0.31 (0.13 to 0.47) |
| 100 | 0.31 (0.13 to 0.48) | 0.32 (0.19 to 0.53) | 0.32 (0.13 to 0.53) |
| 102 | 0.32 (0.19 to 0.53) | 0.32 (0.19 to 0.53) | 0.32 (0.19 to 0.53) |

Corrections needed to reach a share of the LLM level (mean curve): random: 80% at None, 90% at None, 100% at None; least_confident: 80% at None, 90% at None, 100% at None; llm_disagreement: 80% at None, 90% at None, 100% at None. "None" = not reached with the whole pool.

How wrong the local model looks on the posts staff are shown (mean accuracy on the shown batch, at 20 and 60 corrections): random: 0.73 / 0.73; least_confident: 0.54 / 0.75; llm_disagreement: 0.72 / 0.67. Actively chosen posts are the hard ones, so their error rate is NOT the model's accuracy; only randomly chosen checks estimate accuracy.

## Accuracy estimate from random checks (Wilson 95%, if the system is right 85% of the time)

| Random checks | Interval | Visits at 1 random check per visit |
|---|---|---|
| 10 | 49% to 94% (+/- 23%) | 10 |
| 20 | 64% to 95% (+/- 15%) | 20 |
| 30 | 70% to 95% (+/- 12%) | 30 |
| 50 | 71% to 92% (+/- 10%) | 50 |
| 80 | 76% to 91% (+/- 8%) | 80 |
| 100 | 77% to 91% (+/- 7%) | 100 |
| 150 | 79% to 90% (+/- 6%) | 150 |
