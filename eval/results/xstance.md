# X-Stance check (truth = the author's own answer)

Swiss candidates' comments on "Infrastructure & Environment" questions, test split, 50 FAVOR + 50 AGAINST per language. Our labeller read "question + comment" and used the codebook stance definitions with the question's proposal as the target. Licence CC BY-NC 4.0, evaluation only. Intervals: bootstrap 95% (accuracy, kappa, macro-F1), Wilson (no-side rate).

| Model | Language | n | Accuracy | Kappa | Macro-F1 (favor/against) | Said "no side" | Swapped sides |
|---|---|---|---|---|---|---|---|
| haiku | de | 100 | 0.73 [0.64, 0.81] | 0.55 [0.43, 0.67] | 0.81 [0.74, 0.87] | 20 (20%) | 7 |
| haiku | fr | 100 | 0.58 [0.48, 0.68] | 0.38 [0.27, 0.49] | 0.70 [0.60, 0.79] | 35 (35%) | 7 |
| haiku | all | 200 | 0.66 [0.59, 0.72] | 0.46 [0.38, 0.54] | 0.76 [0.70, 0.81] | 55 (28%) | 14 |
| sonnetA | de | 100 | 0.69 [0.60, 0.78] | 0.51 [0.40, 0.62] | 0.80 [0.72, 0.86] | 27 (27%) | 4 |
| sonnetA | fr | 100 | 0.63 [0.53, 0.72] | 0.44 [0.32, 0.55] | 0.74 [0.65, 0.82] | 31 (31%) | 6 |
| sonnetA | all | 200 | 0.66 [0.59, 0.72] | 0.47 [0.40, 0.55] | 0.77 [0.72, 0.82] | 58 (29%) | 10 |
| sonnetB | de | 100 | 0.69 [0.60, 0.78] | 0.51 [0.40, 0.62] | 0.79 [0.71, 0.86] | 26 (26%) | 5 |
| sonnetB | fr | 100 | 0.65 [0.56, 0.74] | 0.45 [0.34, 0.57] | 0.76 [0.67, 0.83] | 28 (28%) | 7 |
| sonnetB | all | 200 | 0.67 [0.60, 0.73] | 0.48 [0.40, 0.56] | 0.77 [0.72, 0.82] | 54 (27%) | 12 |
| majority_3 | de | 98 | 0.71 [0.62, 0.80] | 0.54 [0.42, 0.65] | 0.81 [0.73, 0.87] | 23 (23%) | 5 |
| majority_3 | fr | 98 | 0.64 [0.55, 0.73] | 0.45 [0.34, 0.57] | 0.75 [0.67, 0.83] | 29 (30%) | 6 |
| majority_3 | all | 196 | 0.68 [0.61, 0.74] | 0.49 [0.41, 0.58] | 0.78 [0.73, 0.83] | 52 (27%) | 11 |

What this shows: whether the labeller reads the side an author really took, in German and French. What it does not show: the neutral class (X-Stance has none), cable car or news text, or how people read our posts. The models may have seen X-Stance during training.

