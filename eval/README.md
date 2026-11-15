# eval/: test and evaluation

The proof that our numbers are right. Protocol and plain explanation: `knowledge/STADT_EVAL_PLAN.md`.

## Run

```
python -I -X utf8 eval/run_eval.py                       # all metrics -> eval/results/metrics.json + tables.md
python -I -X utf8 eval/run_eval.py --preds pipeline/data/label_runs/<run_id>.jsonl --preds-name qwen   # add a model
python -X utf8 -m pytest eval/tests -q -p no:cacheprovider                 # 61 tests
EVAL_PREDS=<labels.jsonl> python -X utf8 -m pytest eval/tests/test_falsification.py   # any model vs the suite
```

Label tonight (pseudonyms a = Harshil, b = the team; port 8777 because the app uses 8765):
```
python -I -X utf8 eval/label_tool/server.py --labeller a --tasks eval/gold/tasks_tier1_both.csv --tasks eval/gold/tasks_tier2_both_hn_citizens.csv
```
Open http://127.0.0.1:8777. Saved to `eval/gold/labels_a.csv` after every post. Restart resumes.

## Scoring the team's push

One command, any label run file in the `pipeline/CONTRACT.md` section 2 format (`post_id` or `pid`, `project`, `stance`, `voice`, `arguments`, `abstain`; optional columns may be missing; common spellings such as `neutral` or `favor` are mapped; a missing id or label column stops with a one-line message):

```
python -I -X utf8 eval/score_run.py pipeline/data/label_runs/<run_id>.jsonl      # prints, and writes eval/results/run_<run_id>.md and .json
```

| Number | Plain meaning |
|---|---|
| Regression suite: pass / fail | Of the 33 real hard cases (ski lifts, council reports, accidents elsewhere, syndicated copies, IPAI), how many the run labels the way the codebook rule says. Cases the run does not contain are counted as "no label", not as passed |
| Agreement with the 3-AI majority (240 pilot posts) | How often the run says the same as the three AI labellers' majority: project, relevant yes/no, stance. It is agreement with other models, not accuracy |
| X-Stance side accuracy, "no side" rate | On 200 German and French comments where the author's own yes/no is the truth: how often the run gets the side, how often it refuses to pick one, and how many sides it swapped. Needs ids `X001..X200` in the run |
| Edited posts: kept / changed | After harmless edits (tone, figures, link list) the label must stay; after rule-forced edits it must change. Needs ids `E001..E179` in the run |

The team's run covers real `post_id`s, so parts 1 and 2 score at once. Parts 3 and 4 only appear after his labeller has also labelled `eval/xstance/batch_*_blind.jsonl` and `eval/robustness/batch_*_blind.jsonl` (ids `X###`, `E###`) and those lines are added to the run file. The report says so when they are missing.

What is NOT measured: accuracy against people (there is no human gold set). The regression cases, the edit answers and the pilot consensus were written or produced by Claude and other models, so those parts are model-judged and show rule-following and consistency. A run that was trained on the pilot vote (such as `student_tfidf_baseline`) agrees with the consensus almost perfectly because it saw it; that is not a result. The pilot sample is stratified, so shares are not population shares.

## Files

| Path | What |
|---|---|
| `score_run.py` | Scores one contract-format label run (see "Scoring the team's push"); reuses `evallib`, `run_eval.py`, `xstance/xstance.py`, `robustness/score_edits.py` |
| `run_eval.py` | One command: AI vs AI, leave one labeller out, keyword and vendor baselines, stance counts, vote calibration and abstention, prevalence correction (proxy now, real with `--preds` + human gold), human sections when labels exist, falsification suite, sample size table. Writes `results/metrics.json` (with `status`, `n_gold`, `stance`, `relevance`, `by_project` for `app/`, and `metrics_rows` in the `pipeline/CONTRACT.md` metrics shape) and `results/tables.md` |
| `evallib/metrics.py` | kappa, Krippendorff alpha, confusion, per-class P/R/F1, macro-F1, paired bootstrap, Wilson |
| `evallib/calibration.py` | reliability table, ECE, Brier, temperature scaling, vote share confidence |
| `evallib/prevalence.py` | classify and count, ACC (+ bootstrap), PPI |
| `evallib/regression.py` | checks any label set against `tests/regression_cases.jsonl` |
| `evallib/dedup.py` | reference near-duplicate clustering (5-word shingles, Jaccard 0.8) |
| `evallib/events_qa.py` | placebo test for event peaks; Q&A faithfulness scorer (quotes, numbers, refusals) |
| `evallib/io.py` | loads pilot JSONL, label tool CSV, contract run files; maps `post_id` (mention_id) to pilot `P###` |
| `build_gold_tasks.py` | writes `gold/tasks_*.csv` and `gold/task_key.csv` |
| `build_regression_cases.py` | writes `tests/regression_cases.jsonl` (33 real cases, masked text) |
| `label_tool/` | `server.py` (stdlib only, 127.0.0.1) + `index.html` + copy of the frozen codebook |
| `tests/` | synthetic-truth tests for every metric, label tool tests, falsification suite |

## Formats

- Human labels (`gold/labels_<a|b>.csv`): `pid,labeller,project,stance,voice,arguments,note,saved_at,ref`. `pid` = export `mention_id` (contract `post_id`), `ref` = short screen id. Arguments `;`-joined.
- Adjudicated labels: `gold/labels_adjudicated.csv`, same columns (at least `pid,project,stance,voice`).
- Model labels: pilot JSONL (`pid`) or contract run file (`post_id`, header line `_run`, `abstain`).
