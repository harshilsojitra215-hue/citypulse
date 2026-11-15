# Architecture

CityPulse reads public online discussion about an infrastructure project and answers: which arguments exist, which are new, which come back, and where the same argument appeared in another city. It analyses the observable online debate. It is not a poll.

## One picture

```
                       ┌──────────────────────────── research pipeline (pipeline/, run once) ────────────────────────────┐
 challenge dataset ──► │ 01 clean, dedupe, hash authors ─► 02 keyword rules ─► llm_label (codebook) ─► 09 labelled table │
 (39,361 mentions)     │ 10 argument map ─► 20/26/29/31 pair sets ─► 21 model labels ─► 27 fine-tune (GPU) ─► 32 benchmark │
                       └───────────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                                                   │ 30_build_app_data.py
                                                                   ▼
                                               app_data/  (posts, claims, embeddings, events,
                                                           cached matcher scores, thresholds, review queues)
                                                                   │
 new posts (upload) ──► citypulse/batch ──► runs/<run_id>/ ────────┤
   validate, clean, dedupe, rules,                                 ▼
   LLM labels, claims, match              citypulse/engine  store · matcher · search · replay · crosscity · ingest
                                                                   │
                                               citypulse/api (FastAPI)  +  citypulse/review (human labels, append-only)
                                                                   │  JSON
                                                                   ▼
                                               web/ (Next.js): Overview · Emerging Concerns · Historical Replay ·
                                                               Argument Explorer · Cross-City · Evidence & Review · New Data
```

## Parts

| Part | Folder | What it does |
|---|---|---|
| Research pipeline | `pipeline/` | The numbered scripts that produced every stored result. Run from a lab directory that holds the raw data. Kept so every number can be regenerated. |
| Data bundle | `app_data/` (not in git) | Compact copy of what the app needs: about 4,000 relevant posts with a 400-character excerpt, 3,500 claims with bge-m3 embeddings, 55 sourced events, cached matcher scores for every claim's 20 nearest older claims, thresholds, benchmark files, review queues. |
| Engine | `citypulse/engine/` | `store` loads the bundle and finished batch runs into pandas and DuckDB. `matcher` runs the fine-tuned cross-encoder. `search` embeds and retrieves. `replay` does the historical replay and concern detection. `crosscity` attaches project stage and later events to similar claims elsewhere. `ingest` matches new claims. |
| Batch workflow | `citypulse/batch/` | Upload to findings. Reuses the pipeline's cleaning rules, codebook prompt and LLM caller. One folder per run with status, counts, errors. |
| API | `citypulse/api/` | FastAPI. Contract in `docs/API_CONTRACT.md`. |
| Review | `citypulse/review/`, `review/annotations/` | Blind human labelling queues, append-only corrections, evaluation against human labels. |
| Web app | `web/` | Next.js, TypeScript, Tailwind. Talks only to the API. |

## How a claim is judged

1. **Extract.** An LLM reads each relevant post with a written codebook and returns up to four arguments, each as a one-line English claim with a topic and pro/contra. English claims make German and French posts comparable.
2. **Retrieve.** bge-m3 embeds the claim. The 10 nearest older claims in the same project and the 10 nearest in other projects become candidates. "Older" means published earlier, from another post, one row per distinct text.
3. **Match.** The fine-tuned matcher (mDeBERTa-v3-base, 279M parameters) reads each pair in both orders and gives probabilities for same / related / opposing / unrelated. A small logistic combiner adds the similarity and whether topic and polarity agree, and outputs `p_same`.
4. **Decide.** Best same-project `p_same` at or above the "familiar" cut-off: the claim counts on a known argument. Below the "new" cut-off: it opens a new concern. In between: "ambiguous", shown for human review.
5. **Group and count voices.** New claims that match each other form one concern. A concern is "emerging" once it has claims from two independent voices. One author, one domain, one post, or re-published copies of one article each count once.
6. **Context.** Each concern lists its evidence, the nearest sourced events, and equivalent or related claims in other projects with that project's stage at the time and what happened afterwards.

Relations shown in the product: **equivalent** (`p_same` above the pair threshold) and **related** (model's same + related probability above the related threshold). They are never merged. **Opposing is switched off**: the model cannot detect it reliably (see `docs/EVALUATION.md`).

## No look-ahead

- The candidate index only pairs a claim with claims published before it. The replay re-checks this on every call, and a test asserts it.
- The matcher was trained on pairs whose query claim was published before 2026-01-01, and calibrated on queries from January to June 2026. Replay cutoffs before 2026-07-01 are refused, because the model would know the future.
- Argument families used for "gaining visibility" in the replay are refitted on claims before 2026-07-01.

## Cached and live scores

Model scores for the stored history were computed once on a GPU and are cached in `app_data/pair_scores.parquet`. The UI labels them "cached". When the model weights are on the machine (`models/citypulse-matcher-v2`), free-text matching, uploads and the replay's "re-run live" button run the model locally (Apple MPS or CPU) and are labelled "live". Without the weights the app keeps working from the cache and says so; it never presents plain similarity as the matcher.

## Design choices

- **DuckDB and Parquet, no database server.** The data is small and read-mostly.
- **Thresholds in a JSON file** (`matcher.json`), fitted on the calibration period only, so they can be audited and replaced without code changes.
- **Append-only human labels.** Corrections never overwrite model labels; evaluation reads the latest human label per item.
- **Privacy.** Author names are hashed with a salt on ingest and dropped. The app stores a 400-character excerpt and a link, not the full text. Nothing derived from the dataset is in git.
