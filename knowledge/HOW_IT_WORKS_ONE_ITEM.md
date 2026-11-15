# How CityPulse works: one real item, every step

15 Nov 2026. Checked against the code and the data on the laptop, not against plans. **Built** = it ran today. **Not built** = a plan or a file only.

The item: the City of Heilbronn's procurement office put the planning of the cable car technology out to EU-wide tender. ID `live:9fa954b230c4`. Page: TenderMap. The tender was published on 20 Sep 2026 (its own card says so). Correction 15 Nov: earlier this file said 11 Nov, which is the search service's date for the whole list page (another tender on it). A keyword search of the city's export finds the 27 Jul council decision but not this tender.

## The six steps, with this item

| # | Step | Whose | What happened to this item (real values) | Built? |
|---|---|---|---|---|
| 1 | **Find** | Harshil (`live/`) | Exa search `"Seilbahn" Heilbronn` found it on 14 Nov at 16:41 UTC. Radar gate: `strong` (cable word and place word close together). Stored in `live/data/live_radar_v2.db`: source exa, kind web, page date 11 Nov (from the search service; the tender itself is 20 Sep), first seen 14 Nov, content hash `ab4f869c7f67b9e9`, version 1, seen once. | Built |
| 2 | **Remember** | Harshil | Same link = same item (key = the cleaned link). If the text changes later, version 2 is stored next to version 1. The run receipt says which sources answered. Exported to `live/out/raw_live.json` without author names. | Built |
| 3 | **Clean and find candidates** | The team (`pipeline/` s01, s02) | s01 made a `posts` row: source tendermap.de, German, `new_since_dataset` true, no author. s02 keyword rules: `rule_hits = heilbronn_cablecar`, 5 cable-car mentions, plus a 600-character snippet around them. | Built (rules). The meaning-based net (E5 embeddings) exists but is **off** by default |
| 4 | **Merge copies** | The team (s03) | Compared with 3,390 historical posts and 254 other live items: no copy found, so it is its own story (cluster size 1). | Built (word-overlap, MinHash) |
| 5 | **Understand** (the AI thinks here) | The team (s05 + codebook) | The snippet plus the codebook went to Claude Sonnet 5.5 three times. All 3 runs: project Heilbronn cable car, stance `neutral_informative`, voice `company_vendor`, no arguments, quote "Europaweite Vergabe von Leistungen der Planung der Seilbahntechnik ...". | Built in the team's code; run tonight through the bridge, labels **provisional** |
| 6 | **Check** | The team (s04) | Vote: 3 of 3 agree, so confidence `high`, source `vote`. If the runs had split, it would show as "uncertain", never as a side. | Built |
| 7 | **Report** | Harshil (`live/update_now.py`) | One line in `live/out/update/latest.md`: date, project, stance, outlet, title, quote. Counted in the Heilbronn row only because the model agreed it is about the Heilbronn cable car. | Built |

The AI does not run in the background. It thinks only in step 5, once per item per run, when the bridge sends it the text and the codebook. Everything else is rules, counting and statistics.

## What ChatGPT's explainer got right, and what is different in the repo

| ChatGPT said | In the repo today |
|---|---|
| Five jobs: find, remember, understand, measure, explain | Right. |
| AI thinks only when given a task | Right (step 5 above). |
| Stance, not positive/negative; journalists reporting is not their own opinion | Right. Codebook has `neutral_informative` and a voice field. |
| PostgreSQL + pgvector store everything | **Not today.** Only a schema file (`pipeline/sql/schema_postgres.sql`, "production path"). It runs on parquet files + DuckDB on a laptop. |
| E5 finds similar meaning | Configured but **off** by default (slow on a laptop). Relevance today = keyword rules. |
| Fuzzy matching | **Not in the code.** Copies are found by link (collector) and word overlap (s03). |
| The system compares models | Today: 3 runs of the same model vote. The pilot compared 3 labellers (2 Sonnet, 1 Haiku). Qwen vs Claude is the team's planned experiment. |
| Student learns from the teacher | A simple word-count model (TF-IDF) today. The fine-tuned student needs the Hamburg GPU (planned). |
| "What changed vs last fortnight, new arguments" | **Not built.** The report shows new items per project; trend comparison is not built. |
| Update Now is only a proposal | **Out of date.** The bridge exists and ran tonight (101 items labelled). But it reruns only steps 3 to 7. The team's stance shares with intervals, FAQ matching and peak detection are **not** rerun on a click, and his dashboard does not read `latest.json` yet. |
| Survey as a separate evidence layer | Right as a decision. Not built. |
| Harshil's job is to find evidence | Also: say honestly what was **not** covered (receipt), measure the radar's precision (87%, Heilbronn 9 of 12), and act as the independent referee (X-Stance: right 92% when it names a side, says "no side" too often, 27%). |

## Your 30-second answer (no algorithm names)

"Every two weeks our collector searches the open web for the cable car and keeps only clear matches. It records where each one came from and what it could not see. Then the AI reads each new item three times with the same rulebook: which project, for or against or just reporting, who is speaking, and a short quote as proof. If the three readings disagree, we show it as uncertain instead of guessing. We also tested the reader against people who stated their own side: when it picks a side it is right about nine times in ten, but it is too careful about one time in four, so we say that next to every chart."

## The sentence to repeat

"I make sure the right evidence comes in and that we say honestly what we missed; the team makes sure it is read correctly; I check his reading from outside."
