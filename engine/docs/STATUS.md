# Technical status (15 Nov 2026, before the GitHub handover)

**Engineering: complete for the hackathon release.** Human validation is open and delegated (the internal human-review protocol). Every accuracy figure is provisional AI agreement until then.

## What works, with evidence

| Area | Status | Evidence |
|---|---|---|
| Start-up | works | `python -m citypulse.check` prints "ready for the demo" (bundle, cached scores, model weights with checksum, embedder, LLM, frontend) |
| Automated tests | **129 passed, 1 skipped** with `make test-live` (real model, bge-m3, Claude Haiku). 127 passed, 3 skipped with `make test` (no network/GPU). The skipped one is the opt-in lab benchmark test, which passes with `CITYPULSE_TEST_BENCHMARK=1` (9 of 9) | run on 15 Nov, 04:20 IST |
| Frontend | `tsc --noEmit` and `eslint` clean; all 7 screens load with no console errors | browser check 15 Nov |
| Frontend ↔ backend | all API endpoints answer 200 for Heilbronn; review queues load (120 / 167 / 55 / 48) | curl + browser |
| Argument matching | v2 matcher loaded on Apple MPS; live scores reproduce the cached GPU scores within 0.0001 (3 claims × 20 candidates) | `/api/replay/live-check` |
| Historical replay | cut-off 1 Jul 2026: 75 later claims arrive in order. 28 match known arguments, 11 open new concerns, 9 join them, 27 need review; 3 concerns reach 2+ independent voices. No look-ahead (asserted on every call and in tests). Cut-offs before 1 Jul 2026 are refused | browser + `tests/test_engine_core.py` |
| Emerging concerns | five states, evidence drawer, score against both cut-offs, nearby events, other-city cases labelled "historical case, not a forecast" | browser |
| New-batch workflow | upload of `samples/demo_batch_synthetic.json` through the API: validate → clean → dedupe → relevance → classify (Haiku) → extract → match (live v2 model) → novelty → store, in about 15 s; 1 bad record rejected with its reason; duplicate upload answered with 409 and the earlier run id; results visible in all screens | API + browser |
| Check a new argument | German and English free text matched live against Heilbronn history | `POST /api/match` |
| Human review | queues, append-only labels, evaluation against human labels (runs the v2 benchmark in a shadow copy of the lab, lab untouched), export for retraining | `tests/test_review_*.py` |

## ML issues from the research phase: what changed (details: `docs/EVALUATION.md`)

| Issue | Result |
|---|---|
| D. Leakage | **Found and fixed:** in v1, TRAIN overlapped CAL in time. v2 uses a strict TRAIN < CAL < TEST split; all audit checks pass (no future candidates, disjoint queries, no shared text pairs, no syndicated copies of test queries in training). |
| A. Contradictions (F1 0.13) | Disabled in the product; documented as future work. |
| B. Under-grouping | Depth 10 instead of 5; a separate "related concern" tier (precision 0.93, recall 0.66) that is never counted as the same argument; the hospital paraphrase that v1 missed is now grouped (0.88). Optional two-stage check with Qwen: recall 0.70 → 0.88, measured but not switched on (needs the GPU box). |
| C. Novelty false alarms (target 10%, v1 15%) | Cause: the overlapping calibration period. v2: 2.8% of familiar claims flagged. Trade-off: recall at the single cut-off fell to 0.32. The three-state display brings 82% of truly new claims to the user as "new" or "needs review", and nothing shown as "new" was familiar (19 of 19). |
| Matcher quality | Pair F1 0.65 [0.57–0.71] vs cosine 0.37 on later months. v1's 0.71 came from the leaky split; v2 at v1's depth: 0.68. LLM judges reach about 0.71 but are about 170 times slower. |
| E. GPU / model availability | Weights (558 MB, sha256 `2b7c277e…`) copied from the GPU box and verified. App runs without them on cached scores and says so. Retrain recipe in `models/MODEL_CARD.md`. |

Bugs fixed during integration: fp16 base checkpoint made training diverge to NaN under transformers 5 (now loads float32; the engine refuses non-finite weights); the live matcher fed the v2 combiner the wrong column names (uploads ended "unscored"); batch runs lacked the replay's frozen-family columns; the replay feed called variants of known arguments "emerging" (now "flagged for review"); `.venv` symlink and private SSH helpers would have gone into git; a personal path in the review config.

## Known limitations

- **No human validation yet.** All metrics are agreement with Claude Opus labels; Opus and Sonnet agree only at kappa 0.68 on "same or not".
- **Small numbers.** Heilbronn has 167 unique posts; 33 take a side. Intervals are wide and shown everywhere.
- **The replay's 3 flagged concerns are all "needs review",** not established new arguments: each first claim scored between the cut-offs against an older argument.
- **18% of truly new claims are shown as familiar** (16 of 90 on TEST). Missed concerns are possible.
- **Novelty cut-offs assume later months look like the calibration months.** No guaranteed false-alarm rate.
- **Contradiction detection is off.**
- **The AI reference labels are noisy** (an internal stability study of the AI reference labels): a blind, isolated re-read by Opus flips "same or not" on about 6% of test pairs (interval 2.5–11%), on a task where about 10% of pairs are "same". With these labels, an F1 above roughly 0.71 cannot be told apart from label noise. Fable 5.2 agrees with the stored Opus labels about as well as Opus agrees with itself. No relabelling and no retraining were done.
- **Known matcher error types** (independent of the reference): it merges the same kind of event in two places (two maintenance closures), follows the cheaper models on "preference vs finding" pairs, and misses one fact told from two angles with few shared words.
- **German or French free text is untested.** All training and test pairs are English one-line summaries; the live "check a new argument" box accepts German.
- **Codebook v1 has five known gaps** (two-part claims, observations, width of a sub-issue, shared attitude, cross-city "opposing"). These are for codebook v2, after the human review.
- **The one human-referenced number** will come from the untouched 180-pair final test set (the internal human-review protocol, steps 2 to 4). Nothing may be tuned on it.
- **Uploads need** Ollama with bge-m3 (embeddings) and the Claude Code CLI or a local Ollama LLM (classification). Without them the run ends with clear errors, and the rest of the app keeps working.
- **The two-stage LLM check** is measured but not used in the app.
- **Stance labels are AI labels** (Haiku, codebook v1), checked only against other AI models.
- **No licence file yet** for the code. Decide before the repository goes public.

## Not in git (by design)

`app_data/` (about 20 MB, derived from the challenge data), `models/` weights (558 MB), `runs/` (uploads), the research lab. How to get or rebuild each: README "Data" and `models/MODEL_CARD.md`.
