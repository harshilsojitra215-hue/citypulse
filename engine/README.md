# CityPulse

Public-debate and argument intelligence for city projects. Built for the Stadt Heilbronn cable car challenge (Future City Hackathon 2026).

CityPulse reads what people write online about an infrastructure project and shows a city official:

- which arguments exist, and who raises them
- which arguments are **new**, which **come back**, and which are **getting louder**
- where the same argument already appeared in another city, and what happened there afterwards
- the original posts behind every number

It analyses the observable online debate. **It is not a representative opinion poll.** Every accuracy figure in this repository is agreement with AI reference labels until the human review in the internal human-review protocol is done.

What is different from a sentiment dashboard: a cross-encoder fine-tuned for this task decides whether two differently worded claims make the same argument, and a replay-tested detector flags arguments that have no equivalent in the history. Measured results and limits: [`docs/EVALUATION.md`](docs/EVALUATION.md).

## Quick start

You need the repository plus two things that are **not in git** because they are derived from the challenge dataset: the data bundle `app_data/` and, optionally, the matcher weights in `models/`.

```bash
cd citypulse                                   # the repository root (the folder with this README)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                           # defaults work on a laptop
(cd ~/citypulse_release && shasum -a 256 -c --ignore-missing SHA256SUMS.txt)   # every file you have says OK
unzip -q ~/citypulse_release/app_data.zip -d .                    # -> ./app_data/
unzip -q ~/citypulse_release/citypulse-matcher-v2.zip -d models/  # optional -> ./models/citypulse-matcher-v2/
unzip -q ~/citypulse_release/citypulse-labkit.zip -d .            # optional -> ./lab/
.venv/bin/python -m citypulse.check            # says "ready for the demo" or what is missing
make api                                       # backend  http://127.0.0.1:8000  (API docs at /docs)
make web                                       # frontend http://127.0.0.1:3000  (second terminal, also from the repo root)
make test                                      # automated tests
```

Run every `make` command from the repository root. Tested from a clean copy on macOS with Python 3.14 and 3.12, Node 24. Needs Python 3.11+ and Node 20+. For semantic search and for processing new uploads you also need [Ollama](https://ollama.com) with `ollama pull bge-m3` (1.2 GB). For classifying new uploads you need either the Claude Code CLI logged in (default, model `haiku`) or a local model in Ollama (`CITYPULSE_LLM_BACKEND=ollama`). If port 3000 is busy, Next.js picks another port; the API accepts any localhost port.

## Two operating modes

The app starts in the best mode the machine allows and shows it in the left sidebar (`matcher: local-model` or `matcher: cached-only`) and at `GET /api/health`.

| Feature | Cached mode (no model) | Live mode (model installed) |
|---|---|---|
| Overview, trends, posts, evidence drawer, briefing export | yes | yes |
| Historical replay and Emerging Concerns (from cached v2 scores) | yes | yes, plus "Re-run live" re-scores a claim with the model |
| Argument Explorer: browse families and claims | yes | yes |
| Explorer search | similarity ranking only, no "same argument" verdict; keyword fallback if Ollama is down | ranked and judged by the matcher |
| "Check a new argument" (free text) | similar claims only, state "unknown" | familiar / ambiguous / new with scores |
| Cross-City | yes (cached) | yes |
| Evidence & Review (human labelling, `make review-eval`) | yes | yes |
| New Data upload | runs, but claims are stored **unscored** (no familiar/new decision), with the reason in the run's errors | full workflow: classified, matched, new concerns flagged |

Other requirements of the upload workflow, in both modes: Ollama with bge-m3 (embeddings) and an LLM (Claude Code CLI or Ollama). Without the LLM, an upload ends `failed` at the classify step with a message that names the fix. Everything else keeps working. All three situations (live, cached, and no model + no Ollama + no LLM) were tested from a clean copy before release.

## Demo script (about 4 minutes)

1. **Overview**: Heilbronn. Posts, voices, stance with sample sizes, main arguments. Click any bar to see the posts.
2. **Historical Replay**: cutoff 1 July 2026. Press play. Later claims arrive in order; familiar ones are matched to known arguments, new ones open concerns. Watch concerns open, grow, and get flagged once a second independent voice repeats them. A flagged concern whose first claim was close to an older argument is shown as "needs review", not as a new argument. Open one: evidence, uncertainty, similar cases in other cities.
3. **Emerging Concerns**: the same result as a list, grouped by how certain it is.
4. **Argument Explorer**: search in German or English; open a claim to see equivalent and related claims side by side; paste a new sentence into "Check a new argument".
5. **New Data**: upload `samples/demo_batch_synthetic.json` (clearly marked synthetic). Follow the steps; open the findings.
6. **Evidence & Review**: where a human confirms or corrects the AI labels.

## Data

Nothing derived from the challenge dataset is in git (it contains third-party posts). The app needs the bundle `app_data/` (about 20 MB):

- **Get it:** `app_data.zip` from the team, unpacked in the repository root, or
- **Rebuild it** from the research lab (the folder holding the raw challenge data and the pipeline outputs): `CITYPULSE_LAB=/path/to/lab make bundle`.

`app_data/MANIFEST.json` records which model the cached scores came from (`citypulse-matcher-v2`, weights sha256 `2b7c277e…`) and a checksum of every bundle file. `python -m citypulse.check` compares it with `models/checksums.txt` and, when the model is installed, re-scores 16 cached pairs live to prove that bundle and model belong together.

The bundle holds about 4,000 relevant posts (400-character excerpt, link, date, source, labels; author names only as a salted hash), 3,500 extracted claims with embeddings, 55 sourced timeline events, cached model scores, thresholds, benchmark files and the review queues. To regenerate everything from the raw export, run the numbered scripts in `pipeline/` in order from the lab directory (each script's first lines say how).

## Model

The fine-tuned matcher is described in [`models/MODEL_CARD.md`](models/MODEL_CARD.md): where to get the weights, the checksum, and the exact command to retrain it (about 4 minutes on an RTX 5090, about 35 minutes on an Apple M-series laptop). Without the weights the app still runs on cached scores and says so in the header; live matching of new text and uploads is then off.

## Repository layout

| Path | Content |
|---|---|
| `citypulse/engine/` | data store, matcher, search, replay and concern detection, cross-city cases, ingest |
| `citypulse/api/` | FastAPI backend (`docs/API_CONTRACT.md`) |
| `citypulse/batch/` | upload to findings workflow |
| `citypulse/review/` | human verification: queues, append-only labels, evaluation (`docs/REVIEW_API.md`) |
| `web/` | Next.js application |
| `pipeline/` | research and processing scripts that produced the stored results |
| `samples/` | input format description and a synthetic demo batch |
| `tests/` | automated tests |
| `docs/` | architecture, evaluation and limits, API contract, exploration report |
| `app_data/`, `runs/`, `models/*` | data, uploads, weights: local only, ignored by git |

## Tests

```bash
make test         # everything that needs no network and no GPU
make test-live    # also: real embedder, real LLM, real model
```

Tests that need the model weights, the embedder or the LLM skip with a clear reason when those are not available.

## Documents

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): how the parts fit, how a claim is judged, why there is no look-ahead
- [`docs/EVALUATION.md`](docs/EVALUATION.md): benchmark, leakage audit, known limits
- [`docs/STATUS.md`](docs/STATUS.md): what works, what was tested, what is open
- [`docs/REPORT_exploration.md`](docs/REPORT_exploration.md): the first exploration of the dataset

## Licences and sources

- **Code in this repository: no licence granted yet.** All rights reserved by its authors until the team decides. Keep the repository private until then.
- Base model `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`: MIT (its author fine-tuned it on MNLI and XNLI; XNLI is CC BY-NC 4.0, so check before any commercial use). Embeddings `BAAI/bge-m3`: MIT. Python and npm dependencies: MIT, BSD or Apache-2.0, installed from their registries, not copied here.
- Challenge dataset: provided by Stadt Heilbronn / FSI for the hackathon, with no redistribution licence. Not in this repository, and nothing derived from it (bundle, lab kit, fine-tuned weights) may be published without permission.
- Event timeline: compiled from public sources, each row with its link; rows marked "verified: no" still need a human check.
