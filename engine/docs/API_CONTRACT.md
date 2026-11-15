# CityPulse build contract (API, data, file ownership)

One source of truth for everyone building in parallel. If you need to deviate, write the deviation at the bottom under "Changes".

## Repo layout and owners

| Path | What | Owner |
|---|---|---|
| `pipeline/` | research + processing scripts (numbered), prompts | integrator |
| `citypulse/engine/` | data store, matcher, retrieval, replay, concerns | integrator |
| `citypulse/api/` | FastAPI app (`citypulse.api.main:app`), routers | API builder |
| `citypulse/batch/` | upload → process workflow | batch builder |
| `citypulse/review/` + `review/` | human verification tools and stored annotations | review builder |
| `web/` | Next.js app | web builder |
| `tests/` | pytest; each builder adds `tests/test_<area>_*.py` | each builder |
| `app_data/`, `runs/`, `models/` | data bundle, batch runs, model weights: **never in git** | integrator |
| `README.md`, `docs/ARCHITECTURE.md`, `Makefile`, `.gitignore`, `requirements.txt` | shared | integrator only |

Python: `.venv/bin/python` (3.14; fastapi, uvicorn, duckdb, pandas, pyarrow, numpy, scikit-learn, torch, transformers, pytest, httpx are installed). Do not install other Python packages without writing it under "Changes". API runs on `http://127.0.0.1:8000`, web on `http://127.0.0.1:3000`.

## Words used in the product (keep them consistent)

- **post / document**: one collected item (news article, comment, blog). `doc_id` is its stable id.
- **claim**: one argument or fact extracted from a post, a one-line English sentence. `cid`.
- **argument family**: claims grouped in the argument map. `family_id`.
- **equivalent** (matcher says "same argument") vs **related** (same sub-issue, different point). Never merge the two.
- **voice**: one independent source: an author (salted hash) or a publishing domain; re-published copies of one article count once. Never show author handles; only `voice` (6-character hash).
- Concern states: `new_emerging` (new argument, 2+ independent voices), `new_single` (new argument, one voice so far: candidate), `ambiguous` (score between the two cut-offs: needs review), `gaining` (known argument, significantly more frequent than its own past), `recurring` (known argument seen again).
- All accuracy numbers are **provisional: agreement with an AI reference, not human-validated**. The UI says so wherever a metric is shown.
- This is observable online debate, **not a representative poll**. Sample sizes (n) are shown next to every share.
- Contradiction / "opposing" detection is **disabled** in this release (not reliable). No UI for it.

## Common shapes

```jsonc
// ClaimCard
{"cid":"c3148","claim":"Money for cable car while Löwenstein hospital faces closure","project":"heilbronn_cablecar","project_name":"Heilbronn",
 "date":"2026-07-26","channel":"social","domain":"youtube.com","url":"https://…","topic":"social_priorities","polarity":"contra",
 "doc_id":"123,456","voice":"a1b2c3","family_id":"fam112","family_name":"Cable car is a wasteful project using public money"}
// Match (a ClaimCard plus)
{"relation":"equivalent|related|unrelated","p_same":0.93,"p_related":0.05,"cos":0.71,"score_source":"cached|live|baseline-cosine"}
// PostCard
{"doc_id":"123,456","date":"2026-07-26","channel":"social","media_type":"YouTube Comments","domain":"youtube.com","source_name":"…","url":"…",
 "lang":"de","title":"…","excerpt":"first 400 characters, boilerplate removed","project":"heilbronn_cablecar","stance":"oppose","tone":"negative",
 "passing":false,"label_source":"haiku","voice":"a1b2c3","dup_count":1,"n_claims":2,"run_id":"base"}
// Share with uncertainty
{"value":0.52,"lo":0.35,"hi":0.67,"n":33}
```
Filters accepted by list/statistics endpoints (all optional, query string): `project`, `from`, `to` (YYYY-MM-DD), `channel` (news|social|other_web), `topic`, `stance` (support|oppose|neutral|mixed), `run_id`.
Errors: HTTP 4xx/5xx with `{"error":{"code":"…","message":"human readable"}}`.

## Endpoints

| Method + path | Returns |
|---|---|
| `GET /api/health` | `{status, data_version, n_posts, n_claims, matcher:{available, mode:"local-model"\|"cached-only", version}, embedder:{available, backend}, llm:{backend, available}}` |
| `GET /api/meta` | `{projects:[{id,name,has_arguments,n_posts,n_claims,first_date,last_date}], topics:[], channels:[], stances:[], limitations:[str], metrics:{…provisional benchmark numbers, with "provisional":true}, model:{name,version,trained_until,checksum}}` |
| `GET /api/overview` (+filters) | `{n_posts,n_unique_posts,n_voices,n_with_stance,stance_counts:{},opposition_share:Share,channel_counts:{},top_sources:[{domain,n}],topic_shares:[{topic,n,pro,contra,neutral}],top_arguments:[{family_id,name,n,pro,contra,by_project:{}}],monthly:[{month,n,support,oppose,neutral,mixed}],notes:[str]}` |
| `GET /api/trends?granularity=week\|month` (+filters) | `{series:[{period,n,support,oppose,neutral,mixed}],peaks:[{period,n,expected,p_value,headline,event}],events:[{date,title,event_type,verified,source_url,project}]}` |
| `GET /api/posts?q=&limit=&offset=` (+filters) | `{total, items:[PostCard]}` |
| `GET /api/posts/{doc_id}` | PostCard + `{claims:[ClaimCard], classifications:{project,stance,tone,passing,label_source,codebook:"codebook_v1"}, duplicates:int}` |
| `GET /api/arguments/families?q=` (+project, topic) | `{items:[{family_id,name,n,main_topic,pro,contra,by_project:{},first_seen,last_seen}]}` |
| `GET /api/arguments/families/{family_id}` | family + `{claims:[ClaimCard]}` |
| `GET /api/claims/{cid}` | `{claim:ClaimCard, post:PostCard, equivalent:[Match], related:[Match], elsewhere:[CrossCase], mode}` |
| `GET /api/search?q=&project=&topic=&k=20` | `{mode:"semantic"\|"keyword-fallback", matcher_mode, results:[Match]}` |
| `POST /api/match` body `{text, project?}` | `{novelty:{state:"familiar"\|"ambiguous"\|"new", score, cutoffs:{new,familiar}}, matches:[Match], elsewhere:[CrossCase], mode}` |
| `GET /api/emerging?project=&cutoff=&state=` | `{cutoff, mode, concerns:[Concern]}` |
| `GET /api/emerging/{concern_id}?project=&cutoff=` | Concern with full evidence |
| `GET /api/replay?project=&cutoff=` | Replay (below) |
| `GET /api/replay/cutoffs` | `{cutoffs:["2026-07-01","2026-08-01","2026-09-01"], earliest_allowed:"2026-07-01", reason:"the matcher was trained on data before this date"}` |
| `POST /api/replay/live-check` body `{cid}` | `{available, cached:[{cand,p_same}], live:[{cand,p_same}], max_abs_diff}` |
| `GET /api/crosscity` (+topic) | `{projects:[{id,name,n_posts,n_with_stance,opposition_share:Share,topic_shares:[…]}], shared_arguments:[{family_id,name,by_project:{},pro,contra}], notes:[str]}` |
| `GET /api/crosscity/similar?cid=` or `POST` `{text, project?}` | `{cases:[CrossCase], mode}` |
| `POST /api/batches` multipart `file` | `{run_id, status:"queued"}`; 409 `{error:{code:"duplicate_upload", run_id}}` if the same file was processed |
| `GET /api/batches` | `{runs:[Run]}` newest first |
| `GET /api/batches/{run_id}` | Run with `steps`, `errors`, `findings` |
| `GET /api/batches/template` | example file + field list |
| `GET /api/export/briefing?project=&cutoff=&format=md\|json` | briefing built from current data (no hard-coded conclusions) |
| `GET /api/review/…`, `POST /api/review/annotations` | owned by the review builder; documented in `docs/REVIEW_API.md` |

```jsonc
// Concern
{"concern_id":"g:c3148","state":"new_emerging","label":"Money for cable car while Löwenstein hospital faces closure","project":"heilbronn_cablecar",
 "first_seen":"2026-07-26","flagged_at":"2026-07-31","n_claims":2,"n_voices":2,"polarity":{"contra":2},
 "uncertainty":{"novelty_score":0.03,"cutoffs":{"new":0.2,"familiar":0.74},"note":"no equivalent among 20 older candidates"},
 "new_anywhere":true,"claims":[Match…],"related_new_claims":[Match…],"closest_older":[Match…],"elsewhere":[CrossCase…],
 "events_nearby":[{"date":"2026-07-22","title":"First cost estimate: EUR 157 million","verified":"yes"}]}
// CrossCase: a similar historical claim in another project. Historical case, NOT a forecast.
{"claim":ClaimCard,"relation":"equivalent|related","p_same":0.95,"stage":{"date":"2025-06-01","title":"…","verified":"no","source":"https://…"},
 "after":[{"date":"2025-08-01","title":"…","verified":"yes","source":"…"}]}
// Replay
{"project":"heilbronn_cablecar","cutoff":"2026-07-01","mode":"cached-scores","model_version":"…","simulation":true,
 "known_before":{"n_claims":251,"n_posts":120,"top_families":[{family_id,name,n}]},
 "steps":[{"i":0,"ts":"2026-07-04T08:10:00Z","claim":ClaimCard,"decision":"familiar|joins_new|opens_new|ambiguous",
           "matched":Match|null,"concern_id":"g:c3049"|null,"raised":["g:c3148"],"novelty_score":0.97}],
 "concerns":[Concern],"activity":[{"week":"2026-07-06","n":12,"new":5,"familiar":7}]}
// Run
{"run_id":"r20261115-0131-ab12","filename":"new_posts.json","sha256":"…","created_at":"…","status":"queued|running|done|failed|done_with_errors",
 "steps":[{"name":"validate|clean|relevance|classify|extract|embed|match|novelty|store","status":"…","n_in":0,"n_out":0,"secs":0.0,"message":""}],
 "counts":{"records":0,"valid":0,"duplicates_in_file":0,"already_known":0,"relevant":0,"claims":0,"familiar":0,"ambiguous":0,"new":0},
 "errors":[{"record":"id or row","step":"…","message":"…"}],"findings":{"concerns":[Concern]},"models":{"classifier":"…","matcher":"…","embedder":"…"}}
```

## Engine functions the API and batch code call (do not re-implement these)

```python
from citypulse.engine import store, search, replay, matcher, crosscity
S = store.get()                 # S.posts, S.claims, S.events, S.families, S.pair_scores (pandas), S.emb (numpy), S.meta (dict), S.con (duckdb connection with views posts, claims, events, families, pair_scores)
store.reload()                  # after a batch run finished
search.semantic(text, project=None, topic=None, k=20) -> dict            # /api/search
search.match_text(text, project=None) -> dict                            # /api/match
search.claim_matches(cid) -> dict                                        # /api/claims/{cid}
replay.run(project, cutoff="2026-07-01") -> dict                         # /api/replay
replay.concerns(project=None, cutoff="2026-07-01", state=None) -> list  # /api/emerging
replay.live_check(cid) -> dict
crosscity.similar(cid=None, text=None, project=None) -> dict
matcher.status() -> dict                                                 # for /api/health
# batch only:
from citypulse.engine import ingest
ingest.match_new_claims(claims_df) -> (claims_df_with_states, pair_scores_df)   # embeds, retrieves older claims, scores, assigns novelty state
```
DuckDB views have exactly the columns of the PostCard / ClaimCard shapes above plus: posts(`published_at, month, week, is_first_copy, dup_key, tool_sentiment`), claims(`ts, norm, stance, cluster_all`), events(`date, date_precision, project, event_type, title_en, detail, source_url, source_name, verified`).

## Batch input format

JSON array or CSV. Required per record: `text` (or `content`) and `published_at` (ISO date). Optional: `id`, `title`, `url`, `source_name`, `media_type`, `language`, `author` (hashed with a salt on ingest and then dropped). The original challenge export format (`mention_id, title, content, url, published_at, media_type_name, source_name, language_code, authors`) must also be accepted.

## Changes

(none yet)

### API builder (citypulse/api), 2026-11-15

Clarifications and additions; no field of the contract was removed or renamed.

- **pro / contra / neutral are numbers of claims** in `topic_shares`, `top_arguments`, `/api/arguments/families`, `shared_arguments` (recomputed from the claims inside the filters). Shares are extra fields: `pro_share`, `contra_share` (0..1), and `share` in `topic_shares`. (The stored `families` table holds shares; the API does not pass those through.)
- **Share** has an extra `k` (the numerator). With `n = 0` the value, lo and hi are `null`.
- **Weeks** are named by their Monday, computed from the post date. The stored `posts.week` column is Tuesday-based and is not used.
- `/api/overview`: extra `n_counted` (unique posts that are not passing mentions: the base of the stance figures), `support_share`, `n_claims`, `has_arguments`, `projects_without_arguments`, `filters`. `monthly` rows also carry `n_unique`, `n_counted`. `n` is all collected posts (copies included); stance columns are unique, non-passing posts.
- `/api/trends`: `series` rows carry `n_unique`, `n_counted`. `peaks[].event` is an event object or `null`; peaks also carry `headline_doc_id`, `headline_url`, `project`, `episode_start`, `episode_end`, `episode_n`. Extra `peak_method` (test and parameters) and `notes`. The peak baseline uses history before `from`.
- Events (in `/api/trends.events`, `peaks[].event`): `{date,title,event_type,verified,source_url,source_name,project,project_name,detail,date_precision}`.
- `/api/posts`: extra `limit`, `offset`, `filters`; optional `unique=true` leaves out re-published copies; `q` = all words must appear in title or excerpt. `@handles` in titles and excerpts are masked as `@[account]`.
- `/api/posts/{doc_id}`: accepts the id raw or URL-encoded. Extra `has_arguments`, `notes`, `duplicate_doc_ids`, `is_first_copy`, `published_at`. `duplicates` = other stored posts with the same text.
- `/api/arguments/families`: accepts all common filters; `n`, `pro`, `contra`, `first_seen`, `last_seen` describe the claims inside the filters, `by_project` always shows all projects. Extra `n_voices`, `n_posts`, `total`, `has_arguments`, `notes`. `/api/arguments/families/{family_id}` also resolves single claims (`solo:c0000`, `is_family:false`).
- `/api/crosscity`: accepts all common filters except `project` (ignored, said in `notes`); project rows carry `has_arguments`, `stance_counts`, `support_share`, `n_claims`, `n_voices`.
- `/api/claims/{cid}`: `post` (PostCard) is added by the API. `/api/emerging`: extra `project`, `state`, `counts` (per state), `model_version`, `simulation`, `notes`. Every Concern gets `evidence:[{cid,doc_id,url,date}]`.
- `/api/meta`: extra `side_stances`, `stance_labels_in_data`, `data_version`, `date_min`, `date_max`, `runs`. `metrics.references.<opus|sonnet>` holds the numbers of each `eval_*.json`; `model.trained_until` falls back to the day before `config.EARLIEST_REPLAY_CUTOFF` (see `trained_until_source`).
- `/api/export/briefing?format=json` returns the structured briefing plus `markdown`; `format=md` returns `text/markdown`.
- `GET /api` lists the endpoints. Local file paths in engine messages are replaced by `<repo>`.
- **Error codes**: `invalid_parameter` (422, bad filter value, unknown project / topic / run_id), `invalid_request` (422, body or query validation, with `fields`), `invalid_cutoff` (422, with `earliest_allowed`), `no_arguments` (422, replay / emerging / match for a project without claims, e.g. `ipai`, with `has_arguments:false`), `unknown_post`, `unknown_claim`, `unknown_family`, `unknown_concern`, `unknown_run`, `not_found` (404), `duplicate_upload` (409, with `run_id`), `empty_file` (422), `file_too_large` (413), `engine_unavailable`, `batch_unavailable`, `data_unavailable` (503), `internal_error` (500).
- **Batch (`citypulse.batch`)**: Run `steps` are `validate, clean, dedupe, relevance, classify, extract, match, novelty, store` (`dedupe` added; embedding happens inside `match`); step `status` is `pending|running|done|skipped|failed`. Extra Run fields: `finished_at`, `message` (why a run failed), `counts.{rejected,candidates,not_relevant,unclassified,unscored}`, `models.{llm_backend,llm_model,prompt,prompt_hash,matcher_available}`, `findings.note`. Run ids use local time, `created_at` is UTC. `DuplicateUpload` is also raised while the same file is still being processed. Each run folder also holds `novelty.parquet` (`cid, novelty_state, novelty_score, best_match_cid`), because `claims.parquet` keeps exactly the store's columns. A claim the matcher calls `familiar` takes the `family_id` of its best match; every other new claim is `solo:<cid>`. If the matcher weights are missing the run ends `done_with_errors` with all claims `unscored`. Batch input also accepts `date` for `published_at` and `lang` for `language`; `python -m citypulse.batch <file>` runs one file in the foreground.
- The API reloads the store by itself (`store.reload()`) when the files in `app_data/` changed on disk and have been stable for about 5 seconds, so a rebuilt bundle shows up without a restart. `/api/health.data_version` tells which bundle is served.
