# Review API (human verification)

Owner: review builder. Code: `citypulse/review/`. The main app includes `citypulse.review.router` (a FastAPI `APIRouter`, prefix `/api/review`).

Purpose: a human labels four queues. The labels are stored append-only and are later compared with the AI labels. Until that is done, every accuracy number in the product is provisional AI agreement.

Base URL: `http://127.0.0.1:8000`. All bodies are JSON (UTF-8). Errors use the contract shape:
`{"error":{"code":"unknown_queue","message":"human readable"}}`.

| Code | HTTP | When |
|---|---|---|
| `unknown_queue` | 404 | queue name is not one of the four |
| `unknown_item` | 404 | `item_id` is not in that queue |
| `queue_unavailable` | 503 | the queue file is missing in `app_data/review/` |
| `invalid_labeller` | 400 | labeller missing or not `[a-z0-9_.-]{1,40}` after lower-casing |
| `invalid_label` | 400 | label object does not match the queue's vocabulary |
| `invalid_request` | 400 | anything else wrong with the request |

## The four queues

| `queue` | Items | `item_id` is | Blind | What the human decides |
|---|---|---|---|---|
| `pairs` | 120 TEST claim pairs | `pid` | yes | relation of the two claims |
| `stance` | 167 Heilbronn posts | `doc_id` | yes | is it about the Heilbronn cable car, and the author's stance |
| `events` | 55 timeline events | `event_id` (as string) | no | does the source confirm the event |
| `disputes` | 48 posts where the models disagree | `doc_id` | no | the correct label (adjudication) |

Recommended order for the labeller: `pairs`, `stance`, `events`, `disputes`. The API returns them in this order.

**Blind** means: the item never contains a model label or the `why` field until *this labeller* has annotated *this item*. After that, the hidden fields appear under `revealed`. Do not show `revealed` before the labeller has pressed a label. Items of a blind queue requested without `labeller` are never revealed.

`doc_id` contains a comma (example `29174404,103553`). Use `encodeURIComponent` when it goes into a URL path.

## Label vocabularies (the `label` object)

| Queue | `label` object | Rules |
|---|---|---|
| `pairs` | `{"relation": "same" \| "related" \| "opposing" \| "unrelated"}` | required |
| `stance` | `{"about": "yes" \| "passing" \| "no", "stance": "support" \| "oppose" \| "neutral" \| "mixed"}` | `about` required. `stance` required when `about` is `yes` or `passing`. When `about` is `no`, send `"stance": null` or leave it out. |
| `events` | `{"verdict": "confirmed" \| "wrong_date" \| "wrong_content" \| "source_dead", "correct_date": "YYYY-MM-DD"}` | `verdict` required. `correct_date` optional, only allowed with `wrong_date` (`YYYY-MM-DD` or `YYYY-MM`). |
| `disputes` | `{"about": "yes" \| "passing" \| "no", "stance": "support" \| "oppose" \| "neutral" \| "mixed", "project": "…"}` | `about` and `stance` as for `stance`. `project` optional: what the post is about instead, one of `heilbronn_cablecar`, `paris_c1`, `bonn_cablecar`, `other_urban_cablecar`, `ipai`, `heilbronn_other`, `leisure_cablecar`, `unrelated`. |

Unknown keys in `label` are rejected. `note` is free text (max 2000 characters), stored next to the label. For `wrong_content` and `source_dead` the UI should ask for a note (what is wrong, or a working link).

Meaning of the values (show these as help text):

- pairs: **same** = same argument or the same fact, an analyst would count them together. **related** = same sub-issue but a different point or a different fact. **opposing** = same specific point, opposite assertions. **unrelated** = different issue. If unsure between same and related, choose related. Full rules are returned in `guidelines` by `GET /api/review/queues`.
- stance: position of the *author* towards the Heilbronn cable car. **neutral** = reports facts without taking a side (typical news, even when it quotes critics). **mixed** = clearly both sides and no side taken, or an opinion whose direction cannot be told. Stance is not tone.
- about: **yes** = the post is about the Heilbronn cable car. **passing** = it is only mentioned in one line. **no** = not about it.
- events: **confirmed** = the source says this happened on this date. **wrong_date** = it happened, but the date is wrong. **wrong_content** = the source says something else. **source_dead** = the link does not open or no longer shows the content.

## Shapes

```jsonc
// Annotation (one stored line; the latest line per labeller + item is the current one)
{"queue":"pairs","item_id":"6e1136ebbe","labeller":"harshil","label":{"relation":"related"},"note":"","ts":"2026-11-15T09:12:03Z","rev":1}

// Item
{"queue":"pairs","item_id":"6e1136ebbe","position":0,
 "data":{ /* visible fields, see below */ },
 "my_annotation":null,            // or an Annotation by the labeller in the query
 "revealed":null}                 // blind queues: hidden fields, only after this labeller annotated this item. Always null for events and disputes.
```

`data` per queue:

```jsonc
// pairs      (revealed: {"why":"models disagree"|"random"})
{"pid":"6e1136ebbe","q_claim":"Popular curiosity and success with foreign tourists","q_project":"paris_c1",
 "c_claim":"Attraction that also draws tourists, seen as urban model","c_project":"paris_c1"}
// stance     (revealed: {"model_project":"heilbronn_cablecar","model_stance":"neutral","model_tone":"neutral","label_source":"opus"})
{"doc_id":"29174404,127945","date":"2025-03-27","channel":"news","domain":"stimme.de","url":"https://…","title":"…","excerpt":"up to 400 characters"}
// events
{"event_id":0,"date":"2025-03-28","date_precision":"day","project":"heilbronn_cablecar","event_type":"media",
 "title_en":"First detailed reports on cable car plan to IPAI","detail":"…","source_url":"https://…","source_name":"Heilbronner Stimme","verified":"no"}
// disputes   (not blind: model labels are shown; project/stance are null when that model has no label)
{"doc_id":"17712358,293461","date":"2026-08-21","domain":"instagram.com","url":"https://…","excerpt":"…",
 "models":[{"model":"opus","project":"heilbronn_cablecar","stance":"unclear"},{"model":"haiku","project":"heilbronn_cablecar","stance":"support"},
           {"model":"sonnet","project":"heilbronn_cablecar","stance":"unclear"},{"model":"qwen27","project":"heilbronn_cablecar","stance":"support"}]}
```

Model stance values can also be `unclear` and `na`; show them as they are.

## Endpoints

### `GET /api/review/queues?labeller=`

Lists the queues with progress. `labeller` is optional; with it, `my_progress` is filled.

```jsonc
// GET /api/review/queues?labeller=harshil
{"queues":[
  {"queue":"pairs","title":"Argument pairs","description":"Do these two claims make the same argument?","blind":true,
   "available":true,"n_items":120,"estimated_minutes":20,
   "label_schema":{"relation":{"required":true,"values":["same","related","opposing","unrelated"]}},
   "guidelines":"markdown text with the labelling rules",
   "progress":[{"labeller":"harshil","done":12,"total":120,"last_ts":"2026-11-15T09:20:11Z"}],
   "my_progress":{"labeller":"harshil","done":12,"total":120,"last_ts":"2026-11-15T09:20:11Z"}},
  {"queue":"stance", "…":"…"}, {"queue":"events", "…":"…"}, {"queue":"disputes", "…":"…"}],
 "labellers":["harshil"],
 "provisional_note":"All current accuracy numbers are agreement with AI labels, not human-validated."}
```

`label_schema` has one entry per key of the label object: `{"required":bool,"values":[…]}` or `{"required":false,"format":"date"}`. `my_progress` is `null` without `labeller`. If a queue file is missing: `"available":false,"n_items":0`.

### `GET /api/review/queues/{queue}/items?labeller=&status=all|todo|done&limit=&offset=`

All items of a queue in fixed order. `status` filters by this labeller's work (default `all`; `todo` and `done` need `labeller`). `limit` default 500, `offset` default 0.

```jsonc
// GET /api/review/queues/pairs/items?labeller=harshil&status=todo&limit=2
{"queue":"pairs","blind":true,"total":120,"n_done":12,"n_matching":108,"offset":0,"limit":2,
 "items":[{"queue":"pairs","item_id":"…","position":12,"data":{…},"my_annotation":null,"revealed":null}, {…}]}
```

`total` = items in the queue, `n_done` = annotated by this labeller, `n_matching` = items passing the `status` filter.

### `GET /api/review/queues/{queue}/next?labeller=`

The first item this labeller has not annotated yet. `labeller` is required.

```jsonc
// GET /api/review/queues/stance/next?labeller=harshil
{"queue":"stance","blind":true,"progress":{"labeller":"harshil","done":0,"total":167,"last_ts":null},
 "item":{"queue":"stance","item_id":"29174404,103553","position":0,"data":{…},"my_annotation":null,"revealed":null}}
```

`item` is `null` when the labeller has finished the queue.

### `GET /api/review/queues/{queue}/items/{item_id}?labeller=`

One item, plus the labeller's full history for it (oldest first). Use it for a "go back and correct" screen.

```jsonc
// GET /api/review/queues/pairs/items/6e1136ebbe?labeller=harshil
{"queue":"pairs","item_id":"6e1136ebbe","position":0,"data":{…},
 "my_annotation":{"queue":"pairs","item_id":"6e1136ebbe","labeller":"harshil","label":{"relation":"same"},"note":"changed my mind","ts":"…","rev":2},
 "revealed":{"why":"random"},
 "history":[{"…":"rev 1"},{"…":"rev 2"}]}
```

### `POST /api/review/annotations`

Stores one decision. Posting again for the same labeller and item is a correction: a new line is appended with `rev` + 1, the old line stays in the file, and the newest line is the current label. `"label": null` retracts the labeller's label for that item (also appended, also kept in history).

```jsonc
// request
{"queue":"pairs","item_id":"6e1136ebbe","label":{"relation":"related"},"labeller":"harshil","note":""}
// response 200
{"ok":true,
 "annotation":{"queue":"pairs","item_id":"6e1136ebbe","labeller":"harshil","label":{"relation":"related"},"note":"","ts":"2026-11-15T09:12:03Z","rev":1},
 "progress":{"labeller":"harshil","done":1,"total":120,"last_ts":"2026-11-15T09:12:03Z"},
 "item":{"queue":"pairs","item_id":"6e1136ebbe","position":0,"data":{…},"my_annotation":{…},"revealed":{"why":"random"}},
 "next_item_id":"6dfa18781b"}
```

`note` is optional (default `""`). `next_item_id` is the next item this labeller has not done (`null` when finished). More examples of valid bodies:

```jsonc
{"queue":"stance","item_id":"29174404,127945","label":{"about":"yes","stance":"neutral"},"labeller":"harshil"}
{"queue":"stance","item_id":"29174404,103553","label":{"about":"no"},"labeller":"harshil","note":"circus video, cable car only in a column teaser"}
{"queue":"events","item_id":"0","label":{"verdict":"wrong_date","correct_date":"2025-03-27"},"labeller":"harshil","note":"article is dated 27 March"}
{"queue":"disputes","item_id":"17712358,293461","label":{"about":"yes","stance":"support"},"labeller":"harshil"}
```

### `GET /api/review/annotations?queue=&labeller=&item_id=&history=false`

Stored annotations. All filters optional. Default: the current label per (queue, labeller, item), retracted ones left out. `history=true` returns every stored line, including corrections and retractions.

```jsonc
// GET /api/review/annotations?queue=pairs&labeller=harshil
{"n":1,"history":false,"annotations":[{"queue":"pairs","item_id":"6e1136ebbe","labeller":"harshil","label":{"relation":"related"},"note":"","ts":"…","rev":1}]}
```

### `GET /api/review/export?queue=&format=json|csv&labeller=`

Current labels of one queue (`queue` required), one row per (labeller, item), in queue order. `format=json` (default) returns `{"queue":"pairs","n":1,"columns":[…],"rows":[{…}]}`. `format=csv` returns `text/csv` as a download. Columns: `item_id, labeller, <label keys of the queue>, note, ts, rev`. The export never contains post text or model labels.

```
item_id,labeller,relation,note,ts,rev
6e1136ebbe,harshil,related,,2026-11-15T09:12:03Z,1
```

### `GET /api/review/results`

The last evaluation (`review/results/latest.json`). `{"available":false,"message":"no evaluation has been run yet"}` if there is none.

### `POST /api/review/evaluate`

Recomputes the evaluation from the stored annotations, writes `review/results/latest.json` and returns it. No body. This is the fast part only (about a second). The full matcher benchmark against human labels is a command-line step (`python -m citypulse.review.evaluate`, about 30 seconds); when it has run before, its last result is carried along under `pairs.benchmark` with `"carried_over": true`, and `"stale": true` if pair labels changed since.

```jsonc
// with no annotations stored (this is the real output today)
{"generated_at":"2026-11-14T20:00:52Z","provisional":true,"labeller_filter":null,
 "pairs":{"status":"no human labels yet","n_items":120,"n_labelled":0,"complete":false,"labellers":[]},
 "stance":{"status":"no human labels yet","n_items":167,"n_labelled":0,"complete":false,"labellers":[],
           "model_stance_counts":{"neutral":121,"support":20,"oppose":20,"unclear":6}},
 "events":{"status":"no human labels yet","n_items":55,"n_labelled":0,"complete":false,"labellers":[]},
 "disputes":{"status":"no human labels yet","n_items":48,"n_labelled":0,"complete":false,"labellers":[]},
 "n_labelled_total":0,"n_annotations":0,"labellers":[],"complete":false,
 "message":"no human labels yet",
 "provisional_note":"Every accuracy number elsewhere in CityPulse is agreement with AI labels. …"}
```

`message` is one of `no human labels yet`, `human review in progress; numbers below cover the labelled items only`, `all four queues are fully labelled`. Each section has `status` (`"no human labels yet"` or `"ok"`), `n_items`, `n_labelled`, `complete`, `labellers`. The keys below exist **only** when the section has labels. `X` stands for a number; this block shows the shape, it is not a result.

```jsonc
"pairs":{"status":"ok","n_items":120,"n_labelled":X,"complete":false,"labellers":["harshil"],
  "label_counts":{"same":X,"related":X,"opposing":X,"unrelated":X},
  "human_labels_csv":["…/review/results/human_labels.csv","…/out/citypulse/human_labels.csv"],
  "human_vs_model":[{"model":"opus","n":X,"agreement":X,"kappa_4way":X,"kappa_same":X}],   // also sonnet, qwen27 when the lab folder is there
  "by_why":[{"why":"models disagree","n":X,"agreement_with_opus":X},{"why":"random","n":X,"agreement_with_opus":X}],
  "benchmark":{"status":"ok","generated_at":"…","reference":"human","n_test_pairs":X,"test_same_rate":X,
               "selected_method":"fine-tuned mdeberta + meta (ours)",
               "selected":{"method":"…","precision":X,"recall":X,"f1":X,"f1_lo":X,"f1_hi":X,"auroc":X},
               "methods":[{"method":"cosine (current baseline)","precision":X,"recall":X,"f1":X,"f1_lo":X,"f1_hi":X,"ap":X,"auroc":X,"macro_f1_4way":X,"cal_cv_f1":X}],
               "notes":["…"],"n_labels_at_run":X}},
               // or {"status":"not run"|"skipped"|"failed","message":"…"}: then there are no benchmark numbers at all
"stance":{"status":"ok","n_items":167,"n_labelled":X,"complete":false,"labellers":["harshil"],
  "about_counts":{"yes":X,"passing":X,"no":X},"human_stance_counts":{"support":X,"oppose":X,"neutral":X,"mixed":X},
  "model_vs_human":[{"model":"pipeline label (all sources)","n":X,"accuracy":X,"kappa":X},
                    {"model":"pipeline label from opus","n":X,"accuracy":X,"kappa":X},
                    {"model":"sonnet","n":X,"accuracy":X,"kappa":X,"subset":"disputed posts only"}],
  "relevance":{"n":X,"model_said_about":X,"human_confirms_about":X,"share_confirmed":X},
  "stance_counts":{"model":{"neutral":121,"support":20,"oppose":20,"unclear":6},"corrected":{"neutral":X,"support":X,"oppose":X,"mixed":X},
                   "n_reviewed":X,"n_unreviewed":X,"n_changed":X,"n_not_about":X,"n_passing":X,
                   "opposition_share_of_sided":{"value":X,"n":X}}},
"events":{"status":"ok","n_items":55,"n_labelled":X,"complete":false,"labellers":["harshil"],
  "verdict_counts":{"confirmed":X,"wrong_date":X,"wrong_content":X,"source_dead":X},
  "by_previous_verified_flag":{"no":{"confirmed":X},"yes":{"confirmed":X}},
  "to_fix":[{"item_id":"3","date":"2025-04-04","project":"heilbronn_cablecar","verdict":"wrong_date","correct_date":"2025-04-03","note":"…"}]},
"disputes":{"status":"ok","n_items":48,"n_labelled":X,"complete":false,"labellers":["harshil"],
  "about_counts":{"yes":X,"passing":X,"no":X},"stance_counts":{"support":X,"oppose":X,"neutral":X,"mixed":X},
  "human_sided_with":[{"model":"opus","n_stance":X,"stance_agreement":X,"n_about":X,"about_agreement":X}],
  "n_no_model_had_the_stance":X}
```

When two or more labellers worked on a queue, the section also has
`"inter_labeller":[{"a":"harshil","b":"team","n":X,"relation":{"n":X,"agreement":X,"kappa":X}}]` (one object per label key: `relation`; `about` and `stance`; `verdict`). One label per item is then chosen by majority. Items where the labellers disagree without a majority are left out and listed: `"n_conflicts":X,"conflicts":["item_id",…]`.

Rules the UI can rely on:
- A metric that cannot be computed (no items, or only one label value on both sides) is `null`. Nothing is ever filled in.
- Every metric has its `n` next to it. Show both.
- Model label `unclear` is compared as `mixed`. Posts the human marked `"about":"no"` have no stance and are left out of stance comparisons.
- `corrected` stance counts = human label where reviewed, model label otherwise, posts marked "not about" removed.
- The 120 pairs are not a random sample (half were picked because the AI annotators disagreed). Benchmark scores on them are not comparable with the AI-reference table. `benchmark.notes` says this; show the notes.

## Storage (for information; the UI never touches files)

- `review/annotations/<queue>.jsonl`: one JSON line per action, append-only. Fields: `ts, queue, item_id, labeller, label, note, rev`. No post text, safe for git.
- The newest line per (labeller, item) is the current label. Older lines are the history. Model labels are never changed.
- Queue files are read from `app_data/review/` (`pair_queue.parquet`, `stance_queue.parquet`, `events_queue.parquet`, `disputes_queue.parquet`).

Environment variables (optional): `CITYPULSE_REVIEW_QUEUES` (queue folder; default `$CITYPULSE_DATA/review`, that is `app_data/review`), `CITYPULSE_REVIEW_DIR` (folder holding `annotations/` and `results/`; default `review/`), `CITYPULSE_LAB` (lab folder for the pair benchmark).

## Notes for the web builder

- Ask for the labeller's name once, keep it in `localStorage`, send it lower-case with every call.
- Flow per queue: `GET …/next` → show `item.data` → on key press `POST /annotations` → use `next_item_id` or call `…/next` again.
- Keyboard for pairs: 1 same, 2 related, 3 opposing, 4 unrelated, left arrow = back (load the previous item with `GET …/items/{item_id}`).
- Show progress from `progress.done` / `progress.total`.
- Wherever a metric from `/results` is shown, show its `n` and the word "provisional" until `n_labelled` equals `n_items`.

## Changes since the first version of this document

Only the result of `POST /api/review/evaluate` / `GET /api/review/results` was made more precise after the code was written. Queues, items, annotations and export are unchanged.

- Sections also carry `complete` and `labellers`. Top level also has `n_labelled_total`, `complete`, `labeller_filter`, `provisional_note`.
- `stance.model_vs_human[].model` names are `pipeline label (all sources)`, `pipeline label from <source>`, and one row per model for the disputed posts (`"subset":"disputed posts only"`).
- `disputes.human_sided_with[]` has `n_stance` and `n_about` instead of one `n`.
- `inter_labeller[]` has one object per label key (`{"n","agreement","kappa"}`) instead of flat fields.
- `pairs.benchmark` has `selected`, `notes`, `n_labels_at_run`, and `carried_over` / `stale` when it was not recomputed.
