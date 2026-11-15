# Data contract v1 (pipeline -> app, eval)

Owner: the technical workflow session (`pipeline/`). Frontend (`app/`) and evaluation (`eval/`) build against this file. Change it only by adding columns or by bumping the version line below, and say so in the shared notes folder.

Version: **contract v1.1, 14 Nov 2026 evening** (v1 plus additive changes, listed in section 4).

## 0. Where things live

| What | Path | Format |
|---|---|---|
| Database | `pipeline/data/stadt.duckdb` | DuckDB, one file, all tables below |
| Same tables as files | `pipeline/data/parquet/<table>.parquet` | One parquet per table, rewritten on every run |
| Dashboard export | `pipeline/data/export/data.json` | Section 3. The app reads only this file |
| Label run files (input) | `pipeline/data/label_runs/<run_id>.jsonl` | One JSON object per post, section 2 |
| Human labels (input) | `eval/gold/labels_<name>.csv` (owned by eval) | Read by the pipeline, never written |

Rules for every table:
- `post_id` is the original `mention_id` from the export, as a string. It is the join key everywhere.
- **No author names, handles or e-mails in any table or export.** The raw `authors` field is dropped at ingest. We keep only `has_author` (true/false).
- Times are UTC, ISO 8601 strings in JSON, `TIMESTAMP` in DuckDB. `week` is the Monday of the ISO week (`YYYY-MM-DD`).
- Labels are never overwritten. A new run gets a new `run_id`.

## 1. Tables

### posts (one row per record; 39,361 from the dataset plus live items)
| Column | Type | Meaning |
|---|---|---|
| post_id | str | `mention_id` |
| published_at | timestamp | UTC |
| day, week | date | day; Monday of the week |
| media_type | str | vendor `media_type_name` (News, Other, YouTube Comments, ...) |
| platform | str | from the URL domain: `youtube`, `instagram`, `facebook`, `reddit`, `linkedin`, `tiktok`, `mastodon`, `web` |
| source | str | normalised domain (`www.` removed) |
| url | str | link to the original |
| language | str | `de`, `fr`, other |
| country_code | str or null | country of the source, not of the speaker |
| title | str | headline |
| text | str | content, HTML entities fixed, whitespace collapsed |
| text_len | int | characters of `text` |
| is_paywall_stub | bool | only the headline is real |
| is_truncated | bool | text ends with an ellipsis |
| vendor_sentiment | int or null | 1, 0, -1; null where the vendor gave -99 |
| engagements | int | vendor count (only meaningful for YouTube, Instagram, Facebook) |
| reach | float or null | outlet size, not article reach |
| has_author | bool | an author string existed (the string itself is dropped) |
| origin | str | `dataset` or `live` |
| new_since_dataset | bool | true when published after 2026-10-27 12:29 UTC |
| ingested_at | timestamp | when this row was loaded |

### clusters (near-duplicates; one row per post)
| Column | Type | Meaning |
|---|---|---|
| post_id | str | |
| cluster_id | str | id of the cluster (= `post_id` of its earliest member) |
| cluster_size | int | posts in the cluster |
| n_outlets | int | distinct `source` in the cluster |
| is_representative | bool | true for exactly one post per cluster (earliest). Count stories with `WHERE is_representative` |

### candidates (only posts that passed the wide net)
| Column | Type | Meaning |
|---|---|---|
| post_id | str | |
| project_hint | str | `heilbronn_cablecar`, `bonn_cablecar`, `paris_c1`, `ipai`, `other_cablecar` (rule guess, not a label) |
| rule_hits | str | `;`-joined rule names that fired |
| by_rule | bool | |
| by_embedding | bool | nearest-neighbour hit to seed posts |
| emb_score | float or null | cosine to the nearest seed |
| snippet | str | title + up to 600 characters around the project mention(s). This is what labellers read |
| n_mentions | int | mentions of the cable or project word in the text |

### label_runs (one row per labelling run)
| Column | Type | Meaning |
|---|---|---|
| run_id | str | e.g. `2026-11-14_sonnet_a_cb1` |
| created_at | timestamp | |
| labeller | str | model id (`claude-sonnet-5-5`), local model id, or `student_mmbert_v1` |
| kind | str | `llm_cloud`, `llm_local`, `student`, `rules`, `vendor` |
| runs_where | str | `cloud_eu`, `cloud_us`, `local_laptop`, `local_hamburg`, `city_server` |
| task | str | `project`, `stance_voice_args`, or `all` |
| prompt_version | str | e.g. `p1` |
| codebook_version | str | `v1` |
| codebook_sha | str | first 12 chars of SHA-256 of `scripts/pilot/codebook.md` |
| params | str (JSON) | temperature, shots, seed, max tokens |
| n_items | int | |

### labels (one row per post per run)
| Column | Type | Meaning |
|---|---|---|
| run_id | str | |
| post_id | str | |
| project | str | codebook values: `heilbronn_cablecar`, `bonn_cablecar`, `paris_c1`, `ipai`, `other_cablecar`, `irrelevant` |
| project_prob | float or null | model probability for `project` (students only; LLMs leave null) |
| stance | str or null | `support`, `oppose`, `neutral_informative`, `mixed`, `unclear` |
| stance_probs | str (JSON) or null | `{"support":0.1,...}` when the labeller gives probabilities |
| voice | str or null | `news_institutional`, `politician_official`, `citizen`, `company_vendor`, `unclear` |
| arguments | str (JSON list) | codebook argument codes, `[]` if none |
| evidence | str or null | quote up to 15 words, verbatim |
| abstain | bool | the labeller refused or output was invalid |

### labels_final (one row per candidate; the vote of all runs, used by the export)
| Column | Type | Meaning |
|---|---|---|
| post_id | str | |
| project, stance, voice | str | majority value; human label wins when one exists |
| arguments | str (JSON list) | codes chosen by at least half of the runs |
| n_runs | int | runs that labelled this post |
| agreement_project, agreement_stance | float | share of runs that chose the final value (1.0 = unanimous) |
| confidence | str | `high` (unanimous, 3+ runs), `medium` (majority; or curated rule and student agree), `low` (split, abstain, or wide net only) |
| abstain | bool | true when no majority on stance or no stance label at all: shown as "uncertain" / "not labelled", never counted as a side |
| label_source | str | `human` > `vote` (LLM runs) > `rules_curated` (frozen research rules, project only) > `wide_net` (rule hint only, NOT counted as relevant) |
| student_project, student_prob | str, float | the small student model's guess, a second opinion only |

### human_labels
Read from `eval/gold/labels_<name>.csv` (columns `pid,labeller,project,stance,voice,arguments,note,saved_at`). Stored in DuckDB with `pid` renamed to `post_id`. Annotators are pseudonyms (`A`, `B`), never names.

### faq (official facts) and faq_matches
`faq` is loaded from `pipeline/reference/faq_heilbronn.json`: `faq_id, project, question, answer_summary, topic, argument_code, official_figures (JSON), source_url, date_seen`.

| faq_matches column | Type | Meaning |
|---|---|---|
| post_id | str | |
| faq_id | str | |
| match_type | str | `concern_answered` (post raises a concern the FAQ already answers) or `figure_differs` (post states a number that differs from the official one) |
| score | float | rule/embedding score, 0 to 1 |
| post_value, official_value | str or null | for `figure_differs` |
| matched_text | str | up to 200 characters around the match |
| method | str | `rules_v1` or `embedding_v1` |
| checked | bool or null | a human confirmed it (null = not checked) |
| figure_id | str or null | which official figure (for `figure_differs`) |

### events
| Column | Type | Meaning |
|---|---|---|
| event_id | str | |
| date | date | |
| project | str | |
| type | str | `decision`, `money`, `participation`, `construction`, `opening`, `incident`, `other` |
| title | str | short, plain |
| source_url | str or null | link of the matching post in the dataset, or a page we opened; null = not linked |
| evidence_post_id | str or null | the dataset post that documents the event |
| after_dataset | bool | event after 27 Oct 2026 (live strip only) |

### peaks
| Column | Type | Meaning |
|---|---|---|
| project | str | |
| week | date | |
| stories | int | representative posts that week (syndication removed) |
| baseline | float | expected stories from surrounding weeks (excluding this week) |
| p_value, q_value | float | Poisson exceedance, Benjamini-Hochberg q |
| is_peak | bool | q < 0.05 and stories >= 3 |
| weak | bool | stories < 10 |
| linked_event_id | str or null | documented event within -3 to +7 days |

### metrics (every number the dashboard shows with a badge)
| Column | Type | Meaning |
|---|---|---|
| metric_id | str | e.g. `stance_share.heilbronn_cablecar.citizen.oppose` |
| project, voice, name | str | scope and name |
| value | float | |
| ci_low, ci_high | float or null | 95% interval |
| n | int | items behind the number |
| method | str | `count`, `cc`, `acc`, `ppi`, `kappa`, `bootstrap` |
| source_run_ids | str | `;`-joined |
| computed_at | timestamp | |

## 2. Label run file (input from any labeller, including the team's Hamburg runs)

`pipeline/data/label_runs/<run_id>.jsonl`, first line is the run header, then one line per post:

```json
{"_run": {"run_id":"2026-11-15_qwen9b_cb1","labeller":"Qwen/Qwen3.5-9B-Instruct","kind":"llm_local","runs_where":"local_hamburg","task":"all","prompt_version":"p1","codebook_version":"v1","codebook_sha":"<12 chars>","params":{"temperature":0}}}
{"post_id":"123","project":"heilbronn_cablecar","stance":"oppose","voice":"citizen","arguments":["cost"],"evidence":"...","project_prob":null,"stance_probs":null,"abstain":false}
```
`pid` is accepted instead of `post_id` (pilot format). Unknown fields are ignored.

## 3. `data.json` (the only file the app reads)

```json
{
  "meta": {"generated_at":"...","contract":"v1","dataset_end":"2026-10-27T12:29:00Z",
           "codebook_version":"v1","codebook_sha":"...","label_runs":["..."],
           "status":{"labels":"rules_only|llm_vote|human_checked"}},
  "funnel": [{"step":"all records","n":39361},{"step":"wide net","n":0},{"step":"candidates","n":0},
             {"step":"relevant (labelled)","n":0},{"step":"unique stories","n":0}],
  "projects": [{"id":"heilbronn_cablecar","name":"Heilbronn cable car","records":0,"stories":0,
                "by_voice":{"news_institutional":0,"politician_official":0,"citizen":0,"company_vendor":0,"unclear":0}}],
  "weekly": [{"project":"heilbronn_cablecar","week":"2025-03-31","records":0,"stories":0,"live":0}],
  "stance": [{"project":"heilbronn_cablecar","voice":"all","n":0,
              "counts":{"support":0,"oppose":0,"neutral_informative":0,"mixed":0,"unclear":0,"uncertain":0},
              "share_corrected":{"support":null,"oppose":null},"ci":{"support":[null,null],"oppose":[null,null]},
              "method":"count|acc|ppi","low_sample":true}],
  "arguments": [{"project":"heilbronn_cablecar","code":"cost","n":0,"share":0.0,"support":0,"oppose":0}],
  "events": [{"event_id":"...","date":"...","project":"...","type":"...","title":"...","source_url":"..."}],
  "peaks": [{"project":"...","week":"...","stories":0,"baseline":0.0,"q_value":0.0,"weak":true,"linked_event_id":null}],
  "faq": [{"faq_id":"hn_cost","project":"heilbronn_cablecar","question":"...","answer_summary":"...","topic":"...",
           "source_url":"...","n_concern_posts":0,"n_figure_differs":0,"example_post_ids":["..."]}],
  "reliability": [{"metric_id":"...","name":"...","value":0.0,"ci":[null,null],"n":0,"method":"..."}],
  "posts": [{"id":"...","date":"2025-03-31","project":"heilbronn_cablecar","source":"stimme.de","platform":"web",
             "media_type":"News","language":"de","url":"...","title":"...","snippet":"...",
             "stance":"oppose","voice":"citizen","arguments":["cost"],"confidence":"high",
             "vendor_sentiment":0,"cluster_id":"...","cluster_size":1,"is_paywall_stub":false,
             "new_since_dataset":false,"faq_ids":["hn_cost"],"label_source":"vote"}],
  "placebo": [{"project":"heilbronn_cablecar","n_events":6,"n_peaks":5,"peaks_linked":3,"placebo_mean_linked":0.43,"placebo_p":0.0}],
  "faq_figure_differs": [{"post_id":"...","figure_id":"travel_time_min","post_value":"14 minuten","official_value":"15 minutes","matched_text":"...","checked":null}],
  "live": [{"id":"live:...","date":"2026-11-10","source":"...","url":"...","title":"...","project_hint":"paris_c1",
            "student_project":"paris_c1","student_prob":0.8,"in_wide_net":true,"verified":false}]
}
```

Rules for the export:
- `posts` holds only candidates with a relevant project label (or the rule hint while no labels exist), never authors.
- Every count can be rebuilt from `posts` (the app can filter client side). `stories` = posts with distinct `cluster_id`.
- When `meta.status.labels` is `rules_only`, stance fields are null and the app must say "not labelled yet".
- `low_sample` is true when `n < 30`. The app shows the n on every bar.
- `stance[].method` is `count` (raw share, Wilson interval) until a human gold set exists; then `acc` (corrected, bootstrap interval). The key is still called `share_corrected`; read `method` to know which.
- `posts[].stance` is null for posts with `label_source` `rules_curated`: project is known, stance is not labelled yet. Show "not labelled", never "neutral".
- `live` items are titles only (no article text) and are never counted in `posts`, `weekly` or `stance`.

## 4. Changes since v1 (all additive)

- `labels_final`: `label_source` values are now `human`, `vote`, `rules_curated`, `wide_net`; new columns `student_project`, `student_prob`.
- `faq_matches.figure_id`; `events.evidence_post_id`, `events.after_dataset`; `events.source_url` may be null.
- `data.json`: new keys `placebo`, `faq_figure_differs`, `live`; `posts[].label_source`; `meta.status.stance_coverage`.
- Extra tables (not needed by the app): `placebo`, `faq`, and `data/parquet/student_oof.parquet`.
