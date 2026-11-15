# CityPulse website: data map and the swap after the final run

Written 15 Nov 2026 (about 03:00 IST). Every number on the site comes from a file. This page says which file and field fills each place, which places wait for the final run, and the exact steps to swap them in.

## How data reaches the page

```
live/out/update/latest.json        (Harshil's collector: the last "Update now" receipt)
pipeline/data/export/data.json     (the pipeline export, contract: pipeline/CONTRACT.md)
pipeline/reference/faq_heilbronn.json   (the city's official figures)
        |
        v   python -I -X utf8 app/build_data.py   (reads only; never writes live/ or pipeline/)
app/data/live.js  history.js  facts.js  config.js
        |
        v   app/adapter.js   (the only reader of these fields; typed view models; a renamed field is fixed here)
app/index.html + app.js   (works from file:// too; Update needs app/serve.py)
```

`app/data/config.js` holds `history_mode`:

| history_mode | What part 01 shows | When |
|---|---|---|
| `awaiting` (now) | The five questions, quiet "Awaiting final run" tags, empty rows. Real: 39,361 records, the period, the documented events list. | Until the final export is in |
| `pilot` | The v1 export of 14 Nov, every block tagged "Pilot run, provisional" | Preview only: add `?history=pilot` to the URL, or build with `--history pilot` |
| `final` | The final export as the result | After the final run and our review |

**"Final run" needs a flag from the pipeline export, not only our config.** The page shows "Final run" only when `data.json` has `meta.release = "final"`. Without that field, even `--history final` shows "Pilot run, provisional". Set it when the run is final; it is one extra key in `meta`.

**Privacy in the snapshots (`build_data.py`):** links that name an account are withheld (`url` empty, `link_withheld`), `@handles` in titles are masked, and titles of social posts, photos, comments and forum posts are not shown (`title_withheld`); the drawer then shows "Social Network on facebook.com" and, where needed, "Link withheld: it names the account". News, video and web titles stay.

## The swap (minutes, after the pipeline pushes)

1. `git pull --rebase`
2. Check the export has the contract keys (one line): `python -I -X utf8 -c "import json;d=json.load(open('pipeline/data/export/data.json',encoding='utf-8'));print(d['meta']['generated_at'],d['meta']['status'],[k for k in ('funnel','projects','weekly','stance','arguments','events','peaks','placebo','reliability','posts') if k not in d])"` (the last list must be empty)
3. Preview without locking anything: `python -I -X utf8 app/build_data.py`, then open http://127.0.0.1:8790/?history=final and read every finding against the export.
4. Review the five finding sentences in `app/app.js` (`FINDINGS`). Each finding also has a "why it matters" and a "next question" line written for the placeholder stage; check them against the final numbers too. The numbers fill themselves; the sentence wording ("Most coverage only reports", "Citizens lean against") must still be true for the final numbers. Change the wording if not. This is the result review ChatGPT asked for.
5. Lock it: `python -I -X utf8 app/build_data.py --history final`, reload, commit `app/data/`.

If the export is late or broken, nothing breaks: the page stays in `awaiting`.

## Part 01: the story so far (the pipeline export)

| Place on the page | File and field | State now |
|---|---|---|
| Records in the export, 39,361 | constant (city export size, `funnel[0].n`) | real |
| Period, Oct 2024 to 27 Oct 2026, 12:29 UTC | constant (`meta.dataset_end`) | real |
| About the four projects | `funnel[step = "relevant to the 4 projects"].n` | awaiting |
| Read for stance | `funnel[step = "with a stance label (vote or human)"].n` | awaiting |
| Finding 1: who takes a side | `stance[project=heilbronn_cablecar, voice=all].counts` (support, oppose, neutral_informative) and `.n` | awaiting |
| Finding 2: what is raised most | `arguments[project=heilbronn_cablecar]` top by `n`: `code`, `n`, `base_n`, `share` | awaiting |
| Finding 3: when attention rises | `placebo[project=heilbronn_cablecar]`: `peaks_linked`, `n_peaks`, `placebo_mean_linked` (a count of peaks, not a share) | awaiting |
| Finding 4: citizens vs news | `stance[voice=citizen]` and `stance[voice=news_institutional]`, with `low_sample` | awaiting |
| Finding 5: tone is not position | `reliability[metric_id=vendor_vs_stance.match]`: `value`, `n` | awaiting |
| Evidence behind each finding | `posts[]`: `date, source, media_type, url, title, stance, voice, arguments, confidence` (filtered per finding) | awaiting |
| Tab "Who takes a side" | `stance[project, voice=all]`: `share_corrected`, `ci`, `counts`, `n`, `low_sample` | awaiting |
| Tab "What is raised" | `arguments[project]`: `code, n, share, base_n` | awaiting |
| Tab "When": the line | `weekly[project]`: `week, stories` (quiet weeks filled with 0 by the page) | awaiting |
| Tab "When": blue dots | `peaks[project, weak=false]`: `week, stories` | awaiting |
| Tab "When": numbered events and list | `events[project, after_dataset=false]`: `date, type, title, source_url` | real (documented events with sources) |
| Tab "Compared" | `projects[]`: `id, stories`; `stance[voice=all]` per project | awaiting |

Argument names on the page come from codebook v1 codes (`ARG` in `app.js`). A new code in codebook v2 shows as its raw code until a name is added there.

## Part 02: since 27 October (Harshil's collector, real now)

| Place | File and field |
|---|---|
| Found for the four projects | sum of `meta.per_project[id].found` for heilbronn_cablecar, ipai, bonn_cablecar, paris_c1 |
| Published after 27 Oct / older, found late / date unknown | `meta.per_project[id].d_after`, `d_late`, `d_unknown` |
| Project cards: "the model agrees N are about it" | `meta.per_project[id].about` |
| Comparator row | the other 7 `meta.per_project` entries, `found` |
| Evidence drawer | `items[]`: `date, date_class, kind, source, url, title, label_state, stance, voice, confidence, radar_project, counted_project, llm_project` |
| Coverage callout (11 of 19, 39 of 273) | constant `BACKTEST` in `app.js`, from `live/experiments/exp10_recall_vs_city_tool.py` as quoted in `latest.md` |

Readings in the drawer are the bridge's provisional labels. When the analysis pipeline labels live items itself, they arrive through the same receipt; nothing changes on the page.

## Part 03: today (Harshil's collector, real now)

| Place | File and field |
|---|---|
| Last check time, hero badge | `meta.generated_at` (shown in Heilbronn time) |
| Step 1, sources | `meta.sources_clean`, `meta.sources_problems`, `meta.coverage_gaps` |
| Step 2, search | `meta.collect_run_id` (scan time), `meta.collect_note`, `meta.counts.strong` |
| Step 3, new and dated | `meta.counts.new_this_update`, `items[].date_known` |
| Step 4, readings | `meta.counts.with_label`, `labelled_this_update`, `meta.usage.calls`, `usd`, `meta.labeller`, `meta.runs` |
| Step 6, report | `meta.update_id` |
| What we cannot see | `meta.coverage_gaps` lines starting "NOT COVERED BY DESIGN" |
| Update now button | `POST /api/update?mode=quick` in `app/serve.py`, which runs `live/update_now.py --quick`, streams its `[1/4]` to `[4/4]` lines into the steps, then rebuilds `app/data/` and reloads |

## Part 04: Human review (the pipeline's argument engine, real now; tab `#review`, the old `#arguments` link still opens it)

`app/data/engine.js` (`window.CP_ENGINE`) is written by `live/engine_bridge/snapshot.py` from the engine API (port 8000) after the engine has its data and after each collector feed. The page never calls the engine; it reads this snapshot through `CPAdapter.engine` (`app/adapter.js`, `engineModel`), which tolerates any missing block, drops links that name an account, masks @handles and never passes on the engine's author hash (`voice`).

| Place | File and field |
|---|---|
| Status chips (snapshot time, matcher, embedder) | `taken_at`, `health.matcher.mode`, `health.embedder.available` |
| Replay strip (frozen on 1 Jul 2026, 75 claims: 28 / 9 / 11 / 27, 3 flagged) | `replay_hn.cutoff`, `replay_hn.counts`: `n_claims, familiar, joins_new, opens_new, ambiguous, concerns_flagged`; label from `replay_hn.mode` |
| Concern cards, flagged first; "All 49" list | `replay_hn.concerns[]`: `label, state, first_seen, flagged_at, n_claims, n_voices, polarity, uncertainty.note` |
| Concern drawer | `concerns[].claims[]`: `date, channel, domain, url, claim, relation, polarity`; `closest_older[0]` |
| Main arguments before the cut-off | `replay_hn.known_before.top_families[]` (`name, n`), `n_claims`, `n_posts` |
| Since 27 Oct | `batches.runs[]` (runs fed from the collector): `status, created_at, counts, findings.concerns`. None yet: says so, no numbers |
| How reliable | `matcher.metrics`: `pair_f1, pair_f1_interval, baseline_pair_f1, n_test_pairs, familiar_claims_wrongly_flagged, reference` |
| "How it was tested" drawer | `leakage_audit`: split dates, look-ahead checks, `known_soft_spots` |
| Ask CityPulse: four engine questions | same fields, through the same adapter (`arg_new, arg_concern, arg_main, arg_rel` in `app/ask.js`) |

The matcher score is agreement with an AI reference (Claude Opus), not accuracy, and is labelled that way everywhere.

## Hero

| Place | File and field |
|---|---|
| Route 4,7 km, 6 stations, 15 min | `facts.js` from `pipeline/reference/faq_heilbronn.json` `official_figures`: `length_km`, `stations`, `travel_time_min` |
| Cost 157 Mio EUR, up to 90% | `cost_invest`, `funding_share` |
| Station names in the scene (Bildungscampus, IPAI Campus) and the route | city route graphic, heilbronn.de, 27 Jul 2026 (an illustration, distances compressed) |

## Run

```
python -I -X utf8 app/serve.py            (http://127.0.0.1:8790, preview config "citypulse-site")
python -I -X utf8 app/build_data.py       (after any new receipt or export)
```
