# Contract: what live/ delivers to the team's pipeline

15 Nov 2026. Owner of this side: Harshil (live/). The pipeline side is the team's; changes to this contract are agreed with him, never made in `pipeline/` from here. Longer background: `INTEGRATION_PROPOSAL.md`.

**Rule:** live/ delivers good evidence and says honestly what it could not see. The team's pipeline decides what the evidence means.

## 1. What is delivered, per refresh

| File | What it is |
|---|---|
| `live/out/raw_live.json` | All records first seen or changed in the window, one JSON object each (fields below). |
| `live/out/receipt_<run_id>.json` | What this refresh did: sources tried, answered, failed, skipped (with reason), new, changed, coverage gaps. |

**Did the handoff succeed?** `python -I -X utf8 live/tools/check_handoff.py` prints `HANDOFF OK` and exits 0. It checks the fields below, the receipt, and runs the team's own `s01_ingest.normalise()` on the file (read only). Tested in `live/tests/test_check_handoff.py`: it passes a good file and catches each kind of broken one.

**Was the refresh complete?** Read `status` in the receipt: `success` (every source answered), `partial` (some failed or were gated), `failed` (none answered). A `partial` or `failed` refresh must never look green on the dashboard.

## 2. Fields of each record

Required by `normalise()`: `mention_id` (`live:<12 hex>`, stable for the same link), `published_at` (UTC), `url`, `media_type_name`. Also always present: `source_name`, `language_code`, `country_code`, `sentiment` (-99, we never judge), `engagements`, `authors` (empty, or one 16-hex hash; never a name), `title`, `content`.

Provenance and information value (ignored by `normalise()` today; for the team's tables):

| Field | Meaning |
|---|---|
| `kind` | `news`, `web`, `official`, `council_paper`, `official_page_change`, `social_post`, `social_link`, `video`, `video_comment`, `forum`, `article`, `official_news` |
| `text_scope` | `full` (page text), `snippet` (only the search service's excerpt; social pages are never opened) |
| `collector_source` | the source that first found it (exa, tavily, youtube, rss, oparl, bluesky, mastodon, pagewatch) |
| `found_by_sources`, `n_sightings` | all our sources that found it, and how many times. Many sightings of one link are one record, not many opinions |
| `radar_match` | `strong`, `weak`, `none`: our pre-filter only. The relevance decision is the team's |
| `project_hint` | which project's search found it (a hint, not a label) |
| `date_known` | false when the source gave no publish date; then `published_at` is the day we found it |
| `discovered_at`, `retrieved_at`, `last_changed_at`, `version_no`, `content_hash` | first seen, last seen, last real change, version, hash of title + text |
| `late_discovered` | published before 27 Oct 2026, first found after it |
| `published`, `replay` | always false |

## 3. Promises (and their tests)

| Promise | Test |
|---|---|
| Same link = one record; same headline from the same outlet = flagged copy, not exported | `test_b_same_article_two_sources` |
| A real edit of a full page = version 2, same id | `test_d_edit_creates_version` |
| A different search snippet for the same link is NOT an edit | `test_snippet_from_another_query_is_not_a_new_version` |
| Old article found late = exported and marked `late_discovered` | `test_c_late_discovery` |
| A failing, empty or rate-limited source = reported in the receipt, never a silent success | `test_e_failing_and_empty_sources`, `test_quota_error_*`, `test_youtube_quota_exceeded_is_skip_not_crash` |
| A missing key = source skipped with a clear line | `test_missing_key_skips_with_clear_line`, `test_run_receipt_lists_skipped_sources` |
| Running twice gives the same store | `test_idempotent_rerun` |
| Undated items never count as "new since" | `test_undated_items_are_not_counted_as_new_since` |
| No names or handles in exported text | `test_masking_handles_names_and_kinds`, checker (authors) |
| YouTube text removed after 30 days unless seen again | `test_youtube_text_purged_after_30_days` |

## 4. What live/ never sends

Stance, sentiment or a final relevance decision. Author names or handles. Content of closed platforms (Instagram, Facebook, TikTok, X, LinkedIn): links and search snippets only. Paywalled full text. Deletions (not detectable from our sources; stated in the receipt).
