# live/ : live collector for the city's monthly or bi-weekly update

Prototype, 14 Nov 2026. Owner: Harshil (data collection). Classification stays in `pipeline/` (the team). Nothing in `pipeline/` or `app/` was changed.

## Run

```
pip install pyyaml
python run_collect.py --since 2026-10-27          # real run, writes data/live.db and out/raw_live.json
python run_collect.py --health                    # exit code 1 if a source looks broken
python replay.py --from 2026-10-06 --to 2026-10-27 --n 12   # labelled replay of held-out history (demo only, see below)
python run_collect.py --since 2026-09-15 --db data/volume_test.db --out out/volume_test_raw.json --examples 3
python run_collect.py --source rss --project paris_c1   # one source, one project
```

## What it does

1. Reads `projects.yaml`. A project has keywords (de/fr/en), place words, queries, hashtags, a start date and a comparison group. **A new project = a new block in the yaml, no code.**
2. For each enabled source adapter (`collector/adapters/*.py`, one file each, interface `fetch(project, since) -> list[Item]`): RSS (outlet and city feeds), OParl (council papers), GDELT, Bluesky, Mastodon, Google News RSS.
3. Keeps an item only if the text names the project: a specific phrase alone ("Câble C1", "Seilbahn Heilbronn"), or a generic word ("Seilbahn") together with a place word ("Heilbronn"). This is a pre-filter, not the label. The team's pipeline decides relevance and stance.
4. Stores in SQLite (`data/live.db`). Key is sha1 of the canonical URL (tracking parameters and `www.` removed). Same key and same content hash is "seen", changed content is "updated". Same headline from the same outlet through two sources is stored once and flagged `dup_of` (not exported).
5. Every item carries `retrieved_at` and `source_terms` (which terms apply to it).
6. Exports `out/raw_live.json` in the raw shape that `pipeline/stages/s01_ingest.py` accepts: `mention_id` (`live:<12 hex>`, same scheme as `s12_live.py`), `published_at`, `url`, `media_type_name`, `source_name`, `language_code`, `country_code`, `sentiment=-99`, `engagements`, `authors`, `title`, `content`. Extra audit fields are ignored by `normalise()`. Checked by running `normalise()` on the file (see report).
7. Writes one line per run to `out/run_log.jsonl`: per source and project, items, new, updated, seen, dup, error. Feed and endpoint status is logged too.

## Privacy

- News, council and RSS items: headline, summary, link, outlet, date. No author names.
- Social posts (Bluesky, Mastodon): text, date, platform, URL, **hashed author id** (sha256 with a local random salt, 16 hex). No handle, display name, avatar or profile text. @mentions in the text are replaced by `@[USER]`. Why: the brief says collect only what is needed and show no personal data. We need the debate and the count of distinct voices, not who they are. The salt is in `data/.author_salt` and is never exported, so the hash cannot be reversed by the city or by us.
- Known limit: a Mastodon URL contains the handle and a Bluesky URL contains the account DID. We keep the URL as the link to the original source. The dashboard should show it as a link icon, never as text.
- Pipeline: `authors` holds the hash only, so `has_author` becomes true and no name reaches any table.

## Good manners (all adapters)

- One generic user agent that says what we are. No fake browser agent, no proxies, no logins, no keys.
- robots.txt is checked for every page or feed we fetch from a news or city site. Official APIs (GDELT, Bluesky, Mastodon, OParl) are not HTML pages and are used as documented.
- Spacing between requests per host, back-off on 429 and 503, two failures and the source is skipped for the rest of the run.
- A gated page (Bonn OParl) is reported as "gated" and left alone. We never solve a challenge.
- Google News RSS: `news.google.com/robots.txt` disallows `/rss` for generic crawlers. The feed is meant for feed readers and the team's pipeline already uses it. We use it, flagged. Switch off with `enabled: false` in `projects.yaml`. GDELT is the clean primary news source.

## Scheduling for the city

- **Windows Task Scheduler** (monthly or every 14 days): action `python C:\path\live\run_collect.py --since <last run date>`; then a second task `python run_collect.py --health`. `--since` defaults to 27 Oct 2026; the store is idempotent, so a wider window never creates duplicates. Simplest rule: always use `--since` 45 days back.
- **Linux cron**: `0 6 1,15 * * cd /opt/live && python run_collect.py --since $(date -d '45 days ago' +\%F) && python run_collect.py --health || mail -s "collector health" team@city`.
- **Button**: `app/serve.py` already has an "Update now" button for the headline strip. The same button can call `run_collect.py` and then the pipeline stages.
- Then run the team's stages on `out/raw_live.json` (s01 normalise, s02 candidates, labels, export).

## What breaks over time (and how we see it)

| Break | Sign | Health check |
|---|---|---|
| Outlet changes or removes a feed (404, new URL) | feed status `error` | `--health` lists the feed |
| Outlet puts feed behind bot protection (403) | same | same |
| GDELT or Bluesky rate limits or changes fields | HTTP 429 or schema error | error per source in the log |
| Source returns 0 items where it had items before | silent failure | `--health` compares with the last 3 runs |
| Council system gates its API (Bonn already did, Feb 2026) | status `gated` | `--health` lists it |
| Project keywords drift (new project names) | counts drop to 0 | edit `projects.yaml`, check weekly counts |
| Google News feed format changes | parse error | error in the log |

Review the run log once per run. Review `projects.yaml` keywords every quarter and after every milestone (new route, new name).

## Update 14 Nov 2026 night (experiments, see `knowledge/STADT_LIVE_EXPERIMENTS.md`)

- **Run receipt.** Every run writes `out/receipt_<run_id>.json` and `.md`: sources attempted, clean, partial, failed (with reason), items seen, truly new, changed versions, duplicates, per project counts, official page changes, coverage gaps, and `"published": false` (publishing is the pipeline's job). Exit code: 0 all clean, 2 partial, 1 failed. A run is only "success" when every attempted source answered without error. Use `--out-dir` to write somewhere else.
- **Official page monitor** (`collector/adapters/pagewatch.py`, pages in `projects.yaml` under `sources.pagewatch`). First run stores a baseline (no item), later runs report `changed` with a short word-level diff and emit one item of kind `official_page_change` per change. Stored: normalised text and hash only.
- **Dates kept apart.** `published_at` (source date), `modified_at` (source says it changed; OParl papers), `discovered_at` (first seen by us, never changes), `retrieved_at` (last seen). `ingested_at` is set by the pipeline. An item is exported when published_at OR modified_at is inside the window (before this, council papers dated earlier were silently left out).
- **New export fields** (ignored by `s01_ingest`): `discovered_at`, `modified_at`, `kind` (`article`, `official_news`, `council_paper`, `social_post`, `official_page_change`), `replay` (always false here), `published` (always false here).
- **Store.** `item_versions` keeps the old text when an item changes. `page_snapshots` keeps page text for the monitor.
- **Matching.** `projects.yaml`: added `Heilbronner`, `IPAI` alone, `Ile-de-France`, `du C1` (measured in experiment 1: 6 relevant headlines missed before, 0 after; tuned on 60 headlines, so treat as unvalidated).
- **troet.cafe** removed from the Mastodon list (HTTP 422 on every hashtag timeline, tested).
- **Replay** (`replay.py`): builds clearly labelled replay records and a replay receipt from held-out history. Never `live:`, never "new".
- `experiments/` holds the experiment scripts and logs. Run them with `python -X utf8 expN_*.py` from inside that folder.

## Update 14 Nov 2026 late (radar)

- `python -I -X utf8 run_collect.py --radar --since <date>`: all enabled sources, receipt plus `out/radar_<run_id>.md`. New adapters: Exa, Tavily, YouTube (comments), Apify (off). Keys, accounts, cost: `RADAR_SETUP.md`. Missing key = source skipped, listed in the receipt (not a failure).
- Social platforms are discovery only (link, title, snippet from a search service, `kind: social_link`, `text_scope: snippet`). Seven comparator cities added to `projects.yaml` (negative_words supported).

## Radar gate, dates and privacy (14 Nov 2026)

- `radar_match` on every item and export record: `strong` = a project phrase, or a cable word and a place word in the same snippet fragment at most 100 characters apart; `weak` = only one of them, or both far apart; `none` = neither, or a negative word. Everything stays stored. The radar report headline and top titles use strong only; weak is a collapsed "possible, check"; none is "noise filtered".
- Items without a publish date (`date_known` false) are counted as "found today, date unknown", never as "new since <date>". Tavily news dates come as RFC 2822 and are parsed.
- Site-scoped queries are quoted and need the cable word (`"Seilbahn Heilbronn"`; Exa also gets `includeText`). Queries without a cable word are dropped.
- Reports and receipts print no social URL (`Instagram link`); the URL stays in the export. @handles become `[USER]` everywhere; person names (built-in first-name list, best effort) in resident-type text. Export title and content are masked the same way.

## Update now: radar into the team's pipeline (15 Nov 2026)

- One click: `live/UPDATE_NOW.cmd` (or `python -I -X utf8 live/update_now.py`). Offline stage demo: `--no-collect`.
- Steps: radar scan, strong matches only, a fresh scratch copy of `pipeline/` (`live/bridge/scratch/`, not in git) runs the team's stages s01, s02, s03, s05 (LLM labels), s04 (vote), s11 (export). `pipeline/` is never written (checked by `tests/test_update_now.py`).
- Labeller: Claude Sonnet 5.5, 3 runs, majority vote, through `ANTHROPIC_API_KEY` or the OpenRouter key in `live/.env` (the key owner's; he agreed to this use, see `debate/DECISIONS.md`). `--quick` scans only Heilbronn and IPAI with the fast sources (for the live demo). No key: labels show as "pending". Cost cap `--max-usd` (default 1 USD per update); the real cost comes from the API's token counts.
- Cache: `data/label_cache/*.jsonl` (the team's run-file format plus `content_hash`). An item is labelled once, again only when its text changes. The 4 core projects are labelled by default; comparators with `--include-comparators`.
- Output: `out/update/latest.md` (what changed, per project counts, new items with stance and a short quote, checks, cost, what is not covered) and `out/update/latest.json` (for the dashboard). Fields: the pipeline notes.
- YouTube: items not seen again for 30 days lose title and text at the start of every collector run (YouTube API terms). Link, dates, hash and labels stay.
- `data/.author_salt` is no longer tracked in git (it was committed before 15 Nov; the old copy stays in git history).
- PostgreSQL (15 Nov, scope closed: the database is the team's area): `live/sql/schema_postgres.sql` + `live/tools/to_postgres.py`. Tested once on PostgreSQL 16 (pgvector image, Docker): 466 items, 551 versions, 682 sightings, 5 page snapshots copied, counts equal, second run identical. The live store stays SQLite. No further PostgreSQL work in `live/`.
