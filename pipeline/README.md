# pipeline/: the technical workflow

Turns the 210 MB export (39,361 posts) into `data/export/data.json` for the dashboard, with every number traceable to posts and to the label run that produced it. Explained for humans in `knowledge/STADT_WORKFLOW.md`. Data contract: `CONTRACT.md`.

## Run it

```bash
cd pipeline
python -m pip install -r requirements.txt
python -X utf8 run_all.py            # about 3 minutes on a laptop, no network, no paid calls
python -X utf8 run_all.py --live     # also pull new public news after 27 Oct 2026 (Google News RSS)
python -X utf8 run_all.py --from labels   # after adding a new label run file
```

Inspect any table with DuckDB: `python -c "from common import sql; print(sql('select project, count(*) from labels_final group by 1'))"`

## Stages

| # | File | What it does | Runs in run_all |
|---|---|---|---|
| 1 | `stages/s01_ingest.py` | Load and validate the JSON, normalise, drop authors | yes |
| 12 | `stages/s12_live.py` | New public news items after 27 Oct (title only), flagged `new_since_dataset` | with `--live` |
| 2 | `stages/s02_candidates.py` | Wide net: cable word near a place word, per project; snippet around the mention; optional embedding net | yes (`--embed` for the slow part) |
| 3 | `stages/s03_dedup.py` | MinHash near-duplicate clusters, one story per cluster | yes |
| 4 | `stages/s04_labels.py` | Collect all label runs, vote, abstain on disagreement, human labels win | yes (twice) |
| 5 | `stages/s05_llm_label.py` | LLM teacher with the frozen codebook: batches, cloud or local model, multi-run | **no** (costs money or needs a GPU) |
| 6 | `stages/s06_student.py` | Small local model for project: fine-tuned model if present, else TF-IDF baseline | yes |
| 7 | `stages/s07_calibrate.py` | Temperature scaling of the student, ECE before and after | yes |
| 8 | `stages/s08_measure.py` | Stance shares with intervals, ACC/PPI correction once human gold exists, agreement between runs | yes |
| 9 | `stages/s09_faq_match.py` | Posts raising a concern the city FAQ already answers; figures that differ from official ones | yes |
| 10 | `stages/s10_events.py` | Weekly Poisson peaks, BH correction, link to documented events, placebo test | yes |
| 11 | `stages/s11_export.py` | `data/export/data.json` | yes |

## Folders

- `reference/`: official FAQ facts (Heilbronn, Bonn, Paris), seed events, frozen curated project sets (`curated_v0.csv`).
- `data/`: generated. `parquet/` (one file per table), `stadt.duckdb`, `label_runs/`, `export/data.json`, `llm_batches/`.
- `hamburg/`: GPU recipe and scripts for the team (`README.md` there).
- `handover/`: model handover design for the city, `infer.py`, model card template.
- `sql/schema_postgres.sql`: the same tables for PostgreSQL + pgvector (the city's in-house option).

## Storage decision

**DuckDB + parquet tonight, PostgreSQL + pgvector for the city.** Reason: 39k rows need no server, a single file cannot break on stage, and parquet files are readable by anything. The city runs PostgreSQL in-house, so `sql/schema_postgres.sql` mirrors every table; moving is a load job, not a redesign. The pipeline only talks to storage through `common.write_table` / `read_table`, so swapping the backend touches one file.

## Labelling the remaining posts (stage 5)

Today only the 240 pilot posts have stance labels (3 AI runs). To label the rest:
1. `python -X utf8 stages/s05_llm_label.py batches --project heilbronn_cablecar` writes blind batches (126 Heilbronn posts in 4 batches tonight).
2. Label them with any of: Claude Code agents (same way as the pilot, then `s05_llm_label.py import ...`), a local model (`run --provider openai_compat`), or the Anthropic API (`run --provider anthropic`, needs a key and Harshil's yes for the cost).
3. Run at least 2, better 3 runs. `run_all.py --from labels`.

## Rules kept everywhere

No author names stored or exported. Labels never overwritten (new run = new `run_id`). Every label run records model, prompt version and codebook hash. Unknown is "not known", never a guess.
