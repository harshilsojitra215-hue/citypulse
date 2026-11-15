# CityPulse: Heilbronn cable car debate monitor

Future City Hackathon 2026, Heilbronn University of Applied Sciences. Challenge: Stadt Heilbronn, "Riding the Sentiment".

CityPulse reads the public debate on Heilbronn's planned urban cable car, compares it with Bonn, Paris Câble C1, IPAI and other German cities, and keeps listening after the city's data ends. It reads **stance** (for or against the project), not only tone, and every number opens the posts behind it.

It is built on the city's export of 39,361 posts (Oct 2024 to 27 Oct 2026) plus our own live collector for newer public items.

- **Live website:** https://citypulse-bay.vercel.app (the online copy; the live check runs on the presentation laptop, Replay works online)
- **Pitch deck:** [`deck/CityPulse_deck.pptx`](deck/CityPulse_deck.pptx) and [`deck/CityPulse_deck.pdf`](deck/CityPulse_deck.pdf)

## How it works

| Box | What it does | Where |
|---|---|---|
| 1. History | Reads all 39,361 city posts: relevance, duplicates, project, stance, topics, attention peaks | `pipeline/` (`run_all.py`) |
| 2. Collector | Finds new public items since 27 Oct with their real date, versions and a receipt per run | `live/` (`run_collect.py`) |
| 3. Argument engine | Extracts claims, matches them to known arguments with a fine-tuned matcher, flags new ones | `engine/`, connected by `live/engine_bridge/` |
| 4. Website | History, So far, Today, Arguments, Ask CityPulse, an evidence drawer for every number | `app/` |
| 5. Referee | Independent tests of the labels: X-Stance benchmark, edited posts, known hard cases | `eval/` |

One real item followed through every box: [`knowledge/HOW_IT_ALL_CONNECTS.md`](knowledge/HOW_IT_ALL_CONNECTS.md). Every number with its source: [`knowledge/EVIDENCE_LEDGER.md`](knowledge/EVIDENCE_LEDGER.md).

## Challenge outcomes and where to find them

| The brief asks for | In CityPulse |
|---|---|
| Reproducible processing | `pipeline/run_all.py` (history), `live/UPDATE_NOW.cmd` (one click: collect, read, match, refresh) |
| Topics and arguments | Website tab Arguments; the engine's argument families |
| Sentiment and stance | Website History: stance per post, tone shown separately |
| Change over time, events and peaks | History attention chart with documented moments |
| Cities and projects compared | History project switch (Heilbronn, Bonn, Paris C1, IPAI); So far lists other cities |
| Interactive dashboard | `app/` (the live website above) |
| Key insights | The pitch deck |

## Run it

Windows, Python 3.12, Node 20. API keys go in `live/.env` (see `live/.env.example`); they are never in git.

```
START_CITYPULSE.cmd                      website :8790, analyst console :3000, engine API :8000, Ollama bge-m3
live\UPDATE_NOW.cmd --quick              live check, a few minutes (--no-collect works offline)
python -X utf8 pipeline/run_all.py       rebuild the history, about 3 to 4 minutes
python -I -X utf8 app/serve.py           the website alone, http://127.0.0.1:8790/
```

The website also opens without a server: `app/index.html` (everything except the live check).

Tests:

```
python -I -X utf8 -m pytest live/tests -q
python -X utf8 -m pytest eval/tests -q -p no:cacheprovider
python -I -X utf8 live/tools/check_handoff.py
node app/tests/ask_suite.js
```

One live test (`test_bridge_end_to_end`) needs the history files built from the city's export; run `pipeline/run_all.py` with the export in place first (see Data).

## Data

- **The city's export is not in this repository.** It contains third-party posts and belongs to the challenge. To rebuild the history, put it at `materials/Stadt Heilbronn/FSI_Heilbronn_Medienbeiträge (1).json` (path in `pipeline/config.toml`).
- What the website shows is already built and included (`app/data/`, `pipeline/data/export/`).
- The engine's data bundle (`engine/app_data/`) and the matcher weights (`engine/models/`) are not published; the model card and checksums are in `engine/models/`.

## Where the extra data comes from

The live collector uses only legal routes: search APIs (Exa, Tavily), public RSS feeds, official city and project pages, and the YouTube Data API. Social platforms are stored as links plus search snippets, never page downloads. No logins, bot checks or paywalls are bypassed; Google News is off because of its robots.txt. Details: `live/README.md`, `knowledge/STADT_LIVE_SOURCES.md`.

## Honest limits

- This is the observable online debate, not a representative opinion poll.
- Label quality is measured against AI reference labels and the X-Stance benchmark (Swiss comments). No Heilbronn post has been checked by a person yet.
- No author names, handles or e-mails are shown. Findings are labelled CONFIRMED, INTERPRETATION or UNKNOWN.

## Folder map

| Folder | What |
|---|---|
| `app/` | The CityPulse website (`app/README.md`, demo route `app/DEMO.md`) |
| `live/` | Collector, update button, engine bridge, tests |
| `engine/` | Argument engine (`README.md`, `docs/EVALUATION.md`, `models/MODEL_CARD.md`) |
| `pipeline/` | History pipeline over the city export (`CONTRACT.md`) |
| `eval/` | Independent referee |
| `scripts/pilot/` | Codebook and the 240-post reliability pilot |
| `deck/` | Pitch deck (PPTX, PDF, source) |
| `knowledge/` | How it connects, evidence ledger, workflow, sources, evaluation plan |
