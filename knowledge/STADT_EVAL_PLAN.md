# Evaluation plan: the proof that our numbers are right

Written Sat 14 Nov 2026, evening, by Claude (test and evaluation session). Code: `eval/`. Results: `eval/results/tables.md` and `metrics.json`. Labels in this file: **MEASURED** (we ran it today), **PENDING** (needs human labels or another session's output), **INTERPRETATION**, **UNKNOWN**.

## 0. The answer in six lines

1. Every number we show on stage gets three things: the **n** behind it, a **95% interval**, and a **reference** (what it was checked against). MEASURED numbers today are all AI vs AI; the human check is PENDING.
2. **Correction to earlier files.** The stance kappa of 0.73 to 0.81 we quoted includes irrelevant posts, where stance is "unclear" by rule, which makes agreement easy. On posts both models call relevant it is **0.63 to 0.80** (haiku vs sonnet_a 0.63 [0.50, 0.74]; sonnet_a vs sonnet_b 0.80 [0.69, 0.90]). MEASURED.
3. **The models never swap sides.** In all three leave-one-out checks, zero posts went support to oppose or oppose to support. All stance errors are between "takes a side" and "just reports". Haiku over-reads support (13 neutral reports called support). MEASURED, AI vs AI.
4. **Voting helps.** When two models agree, the third matches 92% on stance; when they split, 53%. The 3-model majority passes all 31 checkable falsification cases; single models fail 0 to 2. MEASURED, AI vs AI.
5. **Decision 14 Nov, late evening: no 60-post human labelling** (Harshil: no time to read 60 posts). It is replaced by three checks that need no human time: edited posts with answers fixed by code, the 33-case regression suite, and X-Stance (comments whose author stated their own side; waits for Harshil's yes to download). Verdict in section 9. Human tiers in section 3 stay available as optional.
6. With about 22 citizen voices, a stance share has an interval of about **plus or minus 20 points**. We can say "most citizen posts in the data oppose" only if the interval stays above 50%; we cannot say "Heilbronn residents oppose".

---

## 1. Claims, data, metric, pass line

"Pass line" = the value at which we show the number on stage as a strength. Below it we still show it, but as a limit.

| # | Claim | Data | Labelled by | Metric and interval | Pass line | Status |
|---|---|---|---|---|---|---|
| C1 | Relevance: we find the right posts | Tier 1 gold (60) now; plus 100 random keyword hits from the full file (to do) | Humans a, b | Precision and recall of the AI vote vs human, bootstrap 95% CI; keyword baseline on the same posts | AI precision >= 0.90 and clearly above keyword (keyword today 0.79 [0.73, 0.85] on the sample) | AI vs AI MEASURED; human PENDING |
| C2 | Project: we sort posts into the right project | Tier 1 gold | Humans | Accuracy and kappa, bootstrap | kappa >= 0.80 | AI vs AI 0.90 to 0.94 MEASURED; human PENDING |
| C3 | Stance: we read the side a post takes | Tier 1 + Tier 2 gold, relevant posts only | Humans | Macro-F1 over 4 classes (support, oppose, neutral, other) with bootstrap CI; confusion matrix; share of human support/oppose posts the AI labels the same | macro-F1 >= 0.70 and **zero support/oppose flips**; human vs human kappa >= 0.60 first | AI leave-one-out macro-F1 0.78 to 0.99, flips 0 MEASURED; human PENDING |
| C4 | Order of checks | Tier 1 | Humans | (a) human vs human kappa, (b) AI vs human, (c) vendor sentiment vs human | (a) >= 0.60 on stance or we simplify stance to 3 classes; (b) close to (a); (c) shown as the weak baseline | PENDING |
| C5 | Calibration: confidence means what it says | Tier 1 gold; later the small local model's probabilities | Humans | Reliability table and ECE. For the 3-model vote, one bin per vote share (1/3, 2/3, 1). For the student, 10 bins plus temperature scaling fitted on held-out data | ECE <= 0.05; unanimous posts right >= 90% | AI proxy: ECE 0.074 stance MEASURED; human PENDING; student PENDING (the team) |
| C6 | Abstention: "uncertain" when models split | Tier 1 gold | Humans | Coverage (share auto-labelled) and accuracy on covered vs all posts | Accuracy on covered >= 90% with coverage >= 70% | Stance coverage 118/155 = 0.76 [0.69, 0.82] MEASURED; accuracy PENDING |
| C7 | Corrected stance shares | Pipeline labels for all relevant posts + human gold | Humans for M | Raw count (CC) next to ACC with bootstrap CI, PPI as cross-check | Show only with interval; flag `low_sample` when n < 30 | Code tested on synthetic truth; real-data proxy MEASURED; real run PENDING pipeline labels |
| C8 | Syndicated copies count once | 50 merged pairs from `pipeline` clusters | One human | Merge precision = share of merged pairs that are the same story (Wilson CI) | >= 0.90 | Reference dedup passes 4/4 suite cases MEASURED; pipeline clusters PENDING |
| C9 | FAQ claim matching | 40 matches from `faq_matches`, stratified by `match_type` | One human | Precision (Wilson CI) per match type | >= 0.80 for `figure_differs`, >= 0.70 for `concern_answered` | PENDING (workflow session builds it) |
| C10 | Event detection | `peaks` per project + documented events | Code | Placebo test: real event windows vs random dates (`evallib/events_qa.placebo_test`) | p < 0.05 for the claim "peaks follow decisions" | Code tested on synthetic data MEASURED; real run PENDING peaks table |
| C11 | "Ask the debate" faithfulness | 30 questions: 20 answerable, 10 unanswerable (e.g. "how many residents support it?") | Code + one human for the question list | Quote accuracy (verbatim in cited post), number accuracy (numbers in the answer exist in the SQL facts), refusal accuracy (`evallib/events_qa.score_qa`) | Quotes 100%, numbers 100%, refusals >= 9/10 | Code tested on synthetic data MEASURED; real run PENDING Q&A |

Rules that apply to every claim:
- **Bootstrap** = resample posts with replacement 2,000 times, recompute the metric, take the 2.5th and 97.5th percentiles. **Wilson** interval for simple proportions.
- **Stratified sample warning.** The pilot and Tier 1 over-sample Heilbronn and hard negatives, and Tier 1 puts non-news posts first. So accuracy on Tier 1 is "accuracy on this mix", not on the whole file. ACC handles a different mix (it only needs P(predicted | true) to stay the same, tested in `test_acc_survives_prior_shift`). PPI does not: use PPI only with a random gold sample.
- **Gold = humans who agree.** Until the humans adjudicate their disagreements, the gold set drops the hard posts, so AI vs human looks better than it is. `run_eval.py` prints this warning. Adjudicate before quoting.
- **AI vs AI is consistency, not accuracy.** Models can share a blind spot.

## 2. Sample size: what n buys

Normal-approximation half-width of a 95% interval, `1.96 x sqrt(p(1-p)/n)` (Wilson intervals in `eval/results/tables.md` section 10):

| n | share near 50% | share near 80% | share near 90% |
|---|---|---|---|
| 12 | +/- 28 points | +/- 23 | +/- 17 |
| 22 | +/- 21 | +/- 17 | +/- 12 |
| 60 | +/- 13 | +/- 10 | +/- 8 |
| 166 | +/- 8 | +/- 6 | +/- 5 |
| 300 | +/- 6 | +/- 4 | +/- 3 |

**What we can honestly claim with about 22 citizen voices** (INTERPRETATION built on the table):
- We can show counts ("8 of 12 citizen posts in the sample oppose") with an interval (Wilson 0.39 to 0.86). Both ends matter: the lower end is under 50%, so even "most citizen posts oppose" is **not** proven on 12. On 22 posts, "most oppose" holds only if at least 16 of 22 oppose (Wilson lower bound 0.52).
- We cannot say anything about **residents**: 22 self-selected online posts are not a sample of residents. The right sentence is "what the online debate says", never "what Heilbronn thinks".
- We can say the citizen share of the debate is small: about 22 of 166 records (MEASURED in STADT_EMPIRICAL), which is itself the insight.
- The 60-row Tier 1 is a smoke test for accuracy (+/- 10 points at 80%), not a final result. With Tier 3 the Heilbronn set becomes a **census**: no sampling error, only labelling error, which human vs human kappa measures.

## 3. Gold set (OPTIONAL since the 14 Nov decision; section 9 replaces it)

Smallest optional human step: `eval/gold/tasks_spotcheck10.csv`, the 10 Heilbronn posts where the AI runs split on stance, about 5 minutes for one person. It shows who is right where the models fight; it is not an accuracy figure.

### Original plan (kept for reference)

Pseudonyms (pipeline contract rule): **a = Harshil, b = the team**. Labels are saved to `eval/gold/labels_a.csv` and `labels_b.csv` after every post.

| Tier | File | Who | Posts | Time (about 40 s per post) | What it unlocks |
|---|---|---|---|---|---|
| 1 (must) | `eval/gold/tasks_tier1_both.csv` | a and b, separately, no talking | 60 | 40 min each | Human vs human kappa; AI vs human for project, relevance, stance, voice; vendor vs human; vote calibration; abstention accuracy; suite check |
| 2 (should) | `tasks_tier2_both_hn_citizens.csv` | a and b | 15 | 10 min each | All 20 Heilbronn records our earlier work tagged as citizen voice (15 here + 5 in Tier 1), double-labelled: the "what citizens say" number as a human census |
| 3 (if time) | `tasks_tier3A.csv` (a), `tasks_tier3B.csv` (b) | split | 65 each | 45 min each | Human census of all 166 Heilbronn records (2 syndicated copies inherit their original's label); bigger M for ACC |
| Adjudicate | `eval/results/human_disagreements.csv` | a and b together | rows where you disagree | 10 min | Removes the "easy posts only" bias; save as `eval/gold/labels_adjudicated.csv` |

Commands (one person at a time per laptop; both tiers in one session is fine):

```
python -I -X utf8 eval/label_tool/server.py --labeller a --tasks eval/gold/tasks_tier1_both.csv --tasks eval/gold/tasks_tier2_both_hn_citizens.csv
```
Open http://127.0.0.1:8777. Keys: project 1 to 6, stance q w e r t, voice a s d f g, arguments z x c v b n m , . - (optional, tick "hide arguments" to go faster), Enter saves and moves on, Left/Right to move, ? opens the frozen codebook. Then:
```
python -I -X utf8 eval/run_eval.py
```
Do not label with the AI labels or `disagreements.csv` open. The tool shows only date, media type and the same masked text the models saw.

## 4. Results today (MEASURED on the 240-post pilot, all AI vs AI)

From `eval/results/tables.md`, B = 2,000 bootstrap resamples.

| What | Value [95% CI] |
|---|---|
| Project kappa, 3 pairs | 0.90 [0.85, 0.94], 0.94 [0.91, 0.97], 0.92 [0.87, 0.95] |
| Stance kappa, posts both call relevant | 0.63 [0.50, 0.74] (haiku vs sonnet_a), 0.70 [0.59, 0.80] (haiku vs sonnet_b), 0.80 [0.69, 0.90] (sonnet_a vs sonnet_b) |
| Krippendorff alpha, 3 labellers | project 0.92 [0.88, 0.95], stance 0.77 [0.71, 0.82], voice 0.73 [0.68, 0.79] |
| Leave one out, stance macro-F1 | haiku 0.78 [0.68, 0.89], sonnet_a 0.84 [0.74, 0.94], sonnet_b 0.99 [0.97, 1.00] (sonnet_b is the "middle" model, so the other two's agreement looks like it; not a sign it is right) |
| Support/oppose flips | 0 in all three |
| Keyword baseline vs consensus | precision 0.79 [0.73, 0.85], recall 0.98 [0.96, 1.00] |
| Vendor sentiment read as stance | matches 46/127 = 0.36 [0.28, 0.45] (Wilson); 62 "positive" posts are neutral reports |
| Abstain unless all 3 agree | project coverage 0.90 [0.86, 0.94]; stance coverage 0.76 [0.69, 0.82] |
| Vote share as confidence (stance) | two agree: third matches 0.92 (n 386); two split: 0.53 (n 79); ECE 0.074 |
| Prevalence correction, proxy truth (haiku as model, sonnet_a as truth, 200 random half splits) | mean absolute error per class share: raw count 0.073, ACC 0.059, PPI 0.040; PPI intervals covered the proxy truth 98% of the time |
| Heilbronn stance in the sample (consensus) | n 62: support 9, oppose 9, neutral 43, other 1 |
| Heilbronn citizen voice in the sample | n 12: oppose 8, support 2, neutral 1, other 1 (oppose share Wilson 0.39 to 0.86) |
| Falsification suite (31 checkable: 27 single posts + 4 copy groups; 2 full-file posts have no labels yet) | majority 31/31; sonnet_b 31/31; sonnet_a 30/31 (P049 IPAI paywall stub called cable car); haiku 29/31 (P161 ski-area lift, P183 council report called support); keyword baseline 22/23 checkable, fails P063 (playground "Seilbahn" in Neckarsulm). Reference dedup 4/4 |

Not done here: anything with human labels; the full-file keyword precision; the local model (no probability file from the team yet; `run_eval.py --preds <file>` takes it in contract format).

## 5. The falsification suite (`eval/tests/regression_cases.jsonl`)

33 real posts, no author names, texts masked the same way as the pilot. Any model must pass them: `EVAL_PREDS=<labels.jsonl> python -X utf8 -m pytest eval/tests/test_falsification.py`.

| Rule | Cases | Example |
|---|---|---|
| R1 ski, tourist and toy lifts are irrelevant | 10 | Zugspitze sights; a playground "Seilbahn" in Neckarsulm reported by the Heilbronn paper |
| R2 a news report of a council decision is neutral, not support | 6 | "Heilbronn sagt Ja zur Seilbahn-Idee" |
| R3 an accident elsewhere is not opposition to Heilbronn | 5 | Monte Faito accident (2 copies); the 1954 Dachstein disaster of a Heilbronn school class (from the full file, says "Heilbronn", not the cable car) |
| R4 syndicated copies count once and get the same label | 4 | 3 outlets running "Stadt plant Baden-Württembergs erste Nahverkehrs-Seilbahn" |
| R5 an IPAI post without a cable car claim gets no cable car project | 8 | "Brückenschlag zwischen der Innenstadt und dem Ipai muss gelingen" (paywall stub, no cable car word) |

Limits: Claude picked these while seeing the AI labels, so they are known hard spots, not a random sample. A pass rate here is not an accuracy. One candidate was dropped (heilbronn.de "Gemeinderat beschließt Vorplanung") because the city quotes its mayor in favour, so "neutral" is not the only defensible label. `run_eval.py` also checks the suite against each human's labels, which tells us whether the humans agree with the expected answers.

## 6. The trust slide: 5 measurements

| # | Measurement | Value now | Sentence Harshil says |
|---|---|---|---|
| 1 | Edited-post test: does the label change when it must, and only then? (section 9) | 3-run majority: stays the same under 97 of 98 harmless edits; follows 51 of 52 rule-forced changes (all 14 for/against flips); fails on opinions quoted inside news reports (6 of 29), a codebook gap | "We changed real posts in ways where our rules fix the right answer. The system kept its answer when only tone, numbers or links changed, and flipped it when the side flipped. The one place it fails is opinions quoted inside news reports, and we show that." |
| 2 | Relevance vs keyword search | Keyword precision 0.79 on our sample, AI PENDING vs human | "A keyword search for Seilbahn is wrong about one post in five. Ski lifts and playgrounds. Our filter is checked against posts we read by hand." |
| 3 | Vendor sentiment vs stance | 36% match (46 of 127), 62 positive-scored posts are neutral reports | "The sentiment score in the dataset agrees with the actual stance only about a third of the time. 'Heilbronn sagt Ja' is scored positive, but it is a news report." |
| 4 | Uncertain is a label | Models all agree on 76% of relevant posts; when two agree the third matches 92%, when they split 53% | "When our models disagree, we show the post as uncertain instead of guessing. They never confused support with opposition." |
| 5 | Stance share with an interval, and the n behind it | Heilbronn citizen posts: 12 in the sample, 8 oppose, interval 39% to 86%; full census PENDING | "Only about 22 posts in two years come from citizens. That is too few to say what Heilbronn thinks, so every bar shows its n and its range." |

If X-Stance is run, add its line to measurement 1: "On comments where the authors told us their own side, our labeller read it right in X% of German and Y% of French cases."

## 7. The evaluation in plain words (with one real example each)

**Kappa: agreement after removing luck.** Two labellers read the same posts. Raw agreement is the share of posts where they pick the same label. But if 70% of posts are neutral news, two people who always say "neutral" agree 70% of the time without reading anything. Kappa subtracts that luck: `kappa = (observed agreement - agreement expected by chance) / (1 - agreement expected by chance)`. 0 = no better than luck, 1 = perfect. Real example: haiku and sonnet_a gave the same stance on 82% of all 240 posts, but kappa is 0.73, and only 0.63 on the posts both call relevant, because the "irrelevant = unclear" posts were free agreement. Code: `metrics.cohen_kappa`, checked against scikit-learn in `test_kappa_matches_sklearn`.

**F1: how good one class is, then the average.** For "oppose": precision = of the posts the model calls oppose, how many really are; recall = of the posts that really oppose, how many the model found. F1 is the balance of the two. Macro-F1 averages F1 over the classes, so the rare "oppose" class counts as much as the common "neutral" class. Real example: haiku vs the other two's agreed label, class "support": recall 1.00 (found all 17), precision 0.57 (also called 13 neutral reports support), F1 0.72. That is the "over-reads support" problem in one number. Code: `metrics.per_class`, `metrics.macro_f1`.

**Calibration: does "sure" mean right?** A system is calibrated if, of all posts where it says "90% sure", about 90% are right. ECE (expected calibration error) is the average gap between "how sure" and "how often right", weighted by how many posts sit at that level. Real example: our confidence is the vote share. When the other two models agree (confidence 1.0) the third matches 92% of the time; when they split (0.5) it matches 53%. The gap at 1.0 is 8 points, so ECE is 0.074. Temperature scaling fixes an over-confident small model by dividing its scores by one number T before turning them into probabilities; the test makes a model 3 times too confident and recovers T = 3. Code: `calibration.ece`, `fit_temperature`.

**Prevalence correction: fixing the count, not the posts.** If the model wrongly calls 15% of neutral posts "support", simply counting its labels overstates support. ACC (adjusted classify and count) measures on the gold set how often each true class gets each predicted label (a table M), then solves "which true shares would produce the counts we see?" PPI (prediction-powered inference) takes the model's share and adds the average correction it needed on the gold set, with an interval. Real example: on the pilot, with haiku as the model and sonnet_a as stand-in truth, raw counting said support is 23% when the stand-in truth was 12%; ACC said 0% [0, 16] and PPI said 6% [0, 20]. Over 200 random splits ACC and PPI were closer on average than raw counting (error 0.059 and 0.040 vs 0.073). On synthetic data with a known answer, raw counting nearly doubles support (0.12 becomes about 0.22) and ACC lands within 2.5 points with a large gold set. Code: `prevalence.acc`, `prevalence.ppi`.

**One sentence to repeat:** "Every number has its n, its range and what it was checked against, and the hard cases are a test suite any model must pass."

## 8. Not covered or not verified

- No human labels exist yet: every AI vs human line is PENDING.
- Full-file keyword precision is UNKNOWN (the pilot over-samples real candidates). Needs 100 random keyword hits labelled.
- C8 to C11 code exists only as scorers tested on synthetic data; they need the pipeline's clusters, faq_matches, peaks and Q&A answers.
- The local student model has not been evaluated (no prediction file yet).
- Calibration of LLM vote shares against humans is PENDING; against AI it is a proxy.

## 9. How reliable are we without human labels (verdict, 14 Nov 2026, late evening)

Decision (eval session, on the main session's instruction after Harshil said he cannot read 60 posts): the human gold set is replaced by three checks that need no human time. Reason: they are the only checks where the right answer does not come from the same AI that is being tested.

| Check | Where the right answer comes from | Result for the system (3-run majority) | Status |
|---|---|---|---|
| A. Edited posts (179: real posts edited by code, plus written templates) | A codebook rule applied by code; for real posts relative to the model's own label on the original | Harmless edits (tone, figures, link list, city swap): label kept 97/98 = 99% [94, 100]. Rule-forced changes, excluding the quoted-opinion family: 51/52 = 98% [90, 100]; all 14 one-phrase for/against flips right. Opinion quoted inside a news report: 6/29 turned neutral | MEASURED (`eval/results/robustness.md`) |
| B. Regression suite (33 real hard cases) | Codebook rules on real posts, picked by Claude | 31/31 checkable; single runs fail 0 to 2 | MEASURED (`eval/results/tables.md` section 9) |
| C. X-Stance (200 German and French comments) | The comment's author (their own yes/no answer) | Not run | PENDING Harshil's yes to download 6.4 MB (CC BY-NC 4.0, evaluation only). Runner ready: `eval/xstance/xstance.py` |

**Verdict.** Without human labels we can honestly claim that the labeller **follows our written rules and is stable**. Changing tone, figures, a link list or the city name almost never moves its answer, and when one phrase flips the side, the label flips with it. Combined with zero support/oppose swaps between models (section 4), the sides it reports are not noise. We **cannot** claim that our rules match how Heilbronn readers would read these posts, or give an accuracy percentage on real posts. Every expected answer here was written by Claude from the codebook, so these checks show rule-following, not agreement with people.

The tests also found one real weak spot. When a news item quotes a citizen's opinion at length, two of three runs label the quoted opinion's side instead of "neutral report". The codebook only covers quotes of politicians (stance rule 1). On real data this would push neutral news toward support or oppose. Fix: add one rule to the next codebook version, or a separate "quoted stance" field. The workflow session owns that choice.

Stage wording: "We tested the labeller on posts where the right answer is fixed by our rules, and on hard real cases. It is stable and follows the rules; the one gap we found is quoted opinions, and we show it. We did not check it against people reading these posts, so stance shares are validated model output, not measured accuracy."

## 10. Human review without a labelling session (correction loop), feasibility, 14 Nov 2026

Idea (main chat): city staff correct a few labels while they use the tool ("this one is wrong"). Each correction fixes the published label, counts toward an accuracy estimate and becomes training data for the local model. No separate labelling session.

**Design we tested.** Each visit shows 2 to 5 posts chosen by the system. Measured below: the posts the local model is least sure about work best. Add **one random post per visit**, because only random checks give an honest accuracy number. Staff click "right" or pick the correct label.

**Measured (SIMULATION, `eval/correction_loop/simulate.py`, results `eval/results/correction_loop.md`).**
- Staff answers were simulated with the 3-run AI consensus on the 240 pilot posts. No real staff were involved.
- The local models are the best ones from the local benchmark: e5-base + logistic regression for relevance, TF-IDF + logistic regression for stance.
- 30 repeats, 30% of posts held out for testing, a start of 10 corrections, then rounds of 5.

| Task | AI level (kappa) | Local model with all corrections | Corrections to reach most of that ceiling: random picks | Same, model picks posts it is least sure about |
|---|---|---|---|---|
| Relevance | 0.95 | 0.72 (168 corrections) | kappa 0.70 at about 125 | kappa 0.70 at about 80 |
| Stance (support / oppose / neutral) | 0.83 | 0.32 (102 corrections) | kappa 0.30 at about 100 | kappa 0.30 at about 50 |

**What this means.**
1. **Letting the system choose roughly halves the work.** With 4 model-chosen posts per visit, the relevance model reaches its ceiling after about 20 visits, and the stance model after about 13. Random choice needs about 30 and 25 visits.
2. **On this data the local model never reaches the AI level**, however many corrections it gets. The limit is the small model and the small data (147 stance posts, only 13 "oppose"), not the number of corrections.
   - So, today: corrections should mainly **fix and measure the AI's labels**, and corrected posts can be added to the AI prompt as worked examples.
   - Training the local model to the AI's level needs the team's stronger model (a fine-tuned encoder or small local LLM) trained on thousands of AI-labelled posts, with staff corrections on top. This simulation did not test that set-up.
3. **Choosing posts where the AI runs disagree** helps less than "least sure" early on (only 15 such posts for relevance, and they are genuinely ambiguous). It is still the right queue for fixing published labels.
4. **Accuracy needs the random checks, not the chosen ones.**
   - On chosen posts the model looks much worse (relevance, 20 corrections: 44% to 49% right on chosen posts vs 75% on random ones). That is because those are the hard posts, not because the model is worse.
   - With one random check per visit and a system that is right about 85% of the time: 30 visits give a range of about 70% to 95%, 50 visits about 71% to 92%, and 100 visits about 77% to 91% (Wilson 95%).

**Important caveat about the ceiling.** The 0.72 and 0.32 ceilings belong to the old benchmark models (TF-IDF and e5-base with logistic regression, trained only on corrections). The team's stack (better local models, specialised embeddings, fuzzy and typo matching, full-text search) is built to read the text better, so fewer posts should land in the review queue. The ceiling numbers say nothing about his models. Re-run the same simulation on his model's outputs: it scores any label file and trains nothing of his.

**Honest limit.** Corrections from staff measure agreement with **staff**, not with "the public". For a city tool that is the right target: the tool should read posts the way the people who use it would. Staff may also correct mostly what looks wrong to them, so only the random check per visit counts toward the accuracy number.

## 11. Who does what (eval vs the team), 14 Nov 2026, night

Sources: `COLLAB.md` (eval/ = Harshil), `debate/DECISIONS.md` (the team = models, pipeline, dashboard), ChatGPT handoff `debate/chatgpt/2026-11-14_2100_citypulse_handoff.md` lines 23 to 28 (lists "evaluation of model outputs" under the team). The two overlap. Line confirmed by the main chat on 14 Nov 2026, night (Harshil delegated technical calls to it; logged in `debate/DECISIONS.md`):

| The team (builds and improves the reader) | eval/ (independent referee, Harshil's folder) |
|---|---|
| Local models, embeddings, fuzzy and typo matching, full-text and vector search, the student model, the codebook | Fixed test sets the models never train on: regression suite, edited posts, X-Stance (if allowed), staff corrections when they exist |
| His own benchmarks while developing, to pick his best model | One scoring command for any label run in contract format (`run_eval.py --preds`, `EVAL_PREDS=... pytest`, `robustness/score_edits.py`) |
| Confidence scores and the abstain rule | Measures what the city cares about: accuracy with intervals, the size of the review queue at a given accuracy, and the trust numbers for the jury |
| | Never trains or tunes his models, never edits `pipeline/` |

Why split it this way: an exam written by someone other than the student is more credible to the jury, and the team gets a ready score for every model he tries. Corrections: the correction-loop simulation (section 10) trained small benchmark models only to size the review design. It is not a model choice, and its ceiling does not describe the team's models.
