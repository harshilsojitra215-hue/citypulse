# CityPulse argument engine in the team repository

Branch `engine-engine`, folder `engine/` (the team's folder under `COLLAB.md`). Prepared 15 Nov 2026, 05:50 IST, from `origin/main` at `1e096a9`. Nothing outside `team/` is changed.

## Where things stand

| Area | Team repo (keep as is) | This folder (added) | Decision |
|---|---|---|---|
| Product website | `app/` (Harshil): the CityPulse website for the pitch, three parts, Ask CityPulse, guided demo | `web/`: Next.js analyst console for the engine | **`app/` is the main interface** (team decision, 15 Nov). `web/` stays here as the engine's own console and is not merged into `app/` |
| Live collection | `live/` (Harshil): collector, Update now, receipts | none | keep |
| Referee and human labels | `eval/` (Harshil): `score_run.py`, regression suite, label tool (8777), staff correction loop | `citypulse/review/`: 120 pairs, 167 stance, 55 events, 48 disputes; Fable 180-pair final test (an internal stability study of the AI reference labels) | both kept. The human-review protocol in the internal human-review protocol is unchanged. **Conflict to settle with Harshil:** `debate/DECISIONS.md` (14 Nov) says "no human labelling sessions" and prefers staff corrections, while the engine's evaluation needs one blind labelling session |
| Labelling and stance pipeline | `pipeline/` (the team, from Harshil's machine): stages `s01`–`s12`, DuckDB, `data.json` (pilot, 14 Nov) | `pipeline/`: the research lab's numbered scripts `01`–`33` (Haiku labels of all relevant posts, claims, matcher, replay) | duplicated in purpose, different code. Not merged tonight |
| Unique to this folder | | argument extraction and claim families; fine-tuned matcher (`citypulse-matcher-v2`) and its leak-free benchmark; novelty detector with three states; historical replay without look-ahead; cross-city cases; batch upload; v2 evaluation and leakage audit; Fable label-noise study | added, isolated |

## API and data differences

- The team app reads `pipeline/data/export/data.json` (contract v1.1, `pipeline/CONTRACT.md`): `post_id` is the vendor `mention_id`, weeks start on Monday.
- The engine reads `app_data/` (Parquet, `docs/API_CONTRACT.md`): `doc_id` is the lab's id (vendor ids, comma-joined for re-published copies). It serves its own FastAPI on port 8000.
- Ports: team app 8790, label tool 8777, reference dashboard 8765; engine API 8000, engine web 3000. No clash.
- Data policy: the team repo commits the city export (LFS) and pipeline tables. This folder keeps its bundle, model and keys out of git (nested `.gitignore`) and ships them as private zips (the internal release notes).

## Connection work left (not done tonight)

1. **Fill part 01 of the website with final results** (`app/DATA_MAP.md`): write the lab's Haiku labels as a label run (`pipeline/data/label_runs/<run_id>.jsonl`, `pipeline/CONTRACT.md` section 2), run `pipeline/run_all.py`, set `meta.release = "final"`. Owner: the team. Then Harshil reviews the five finding sentences and builds with `--history final`.
2. **Show the engine from the website:** a link or tab in `app/` to the engine console (http://127.0.0.1:3000), or an `app/` panel fed by the engine API (`/api/emerging`, `/api/replay`). Owner: Harshil (his folder).
3. **Settle the human-review protocol conflict** (row above).
4. **Windows:** the engine was tested on macOS only. the internal presentation notes has the PowerShell setup and the smoke test.

## Checks run on this branch

- `scripts/release_check.sh` in `engine/`: 152 files, no credentials, personal paths, SSH helpers, data, weights or archives.
- Engine tests in the branch: 53 passed, 80 skipped (no data bundle in git, as intended). With the bundle (macOS): 130 passed, 3 skipped; 132 with the live tests.
- Harshil's tests on this Mac: `live/tests` 58 of 59, `eval/tests` 64 of 65 (3 skipped). The same two fail without `team/` too: this Mac has no git-lfs, so the city export files are pointers. Not caused by this branch.
