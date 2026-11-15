# What changed: update Sun 15 Nov 2026, 09:42 Heilbronn time (08:42 UTC)

Note: no new scan in this update (--no-collect): items come from the last scan.
**Collection: success.** Scan 20261115T082738Z, window since 2026-10-27. Sources that answered: rss, pagewatch, exa, tavily, date_recovery.

**Labels:** 165 of 371 strong items have an LLM label (Claude Sonnet 5.5 via OpenRouter, 3 runs, majority vote); 0 were labelled in this update; 206 pending (comparator cities are not labelled by default).
Labels are provisional: they come from the team's pipeline code as it stands today (not final). The bridge reruns whatever pipeline/ holds at the click.

## Per project (strong radar matches found since 2026-10-27)

| Project | radar found | new now | model: about it | support | oppose | neutral | mixed | unclear or uncertain | label pending | model: not about it |
|---|---|---|---|---|---|---|---|---|---|---|
| Heilbronn cable car | 13 | 0 | 10 | 2 | 1 | 7 | 0 | 0 | 0 | 3 |
| IPAI Heilbronn | 84 | 0 | 77 (2 moved in) | 16 | 0 | 57 | 0 | 4 | 0 | 9 |
| Bonn cable car | 13 | 0 | 11 | 3 | 0 | 4 | 3 | 1 | 0 | 2 |
| Paris Câble C1 | 55 | 0 | 53 | 9 | 0 | 37 | 0 | 7 | 0 | 2 |
| Berlin | 25 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 25 | 0 |
| Hamburg | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 7 | 0 |
| Koblenz | 61 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 61 | 0 |
| Köln | 69 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 69 | 0 |
| München | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 |
| Stuttgart | 26 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 26 | 0 |
| Wuppertal | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 15 | 0 |

Counts are items, not people, and not a poll. "Model: about it" = the model read the text and agrees it is about this project; only those are counted for stance. "Moved in" = the radar filed it under a neighbour project (for example Heilbronn cable car versus IPAI). "Model: not about it" = radar hits the model put elsewhere or found irrelevant (radar precision check). "Uncertain" = the runs disagreed, never counted as a side.

## When were they published? (the city's data ends 2026-10-27, 12:29 UTC)

| Project | published after 2026-10-27 | published before, found late | date unknown |
|---|---|---|---|
| Heilbronn cable car | 0 | 5 | 8 |
| IPAI Heilbronn | 23 | 4 | 57 |
| Bonn cable car | 5 | 1 | 7 |
| Paris Câble C1 | 17 | 3 | 35 |
| Berlin | 7 | 0 | 18 |
| Hamburg | 2 | 0 | 5 |
| Koblenz | 17 | 3 | 41 |
| Köln | 24 | 3 | 42 |
| München | 1 | 1 | 1 |
| Stuttgart | 4 | 0 | 22 |
| Wuppertal | 6 | 1 | 8 |

Only the first column is new evidence for the period after the city's data. "Found late" = published before the edge but not in the city's data (our sources found it later). "Date unknown" = no service and no rule gave a date; such items are never counted as new. Where dates come from: from the search service 85, from the page's date tag 31, activity date in the text 3, from the text 3, from the link 3, teaser date of the cable car item on the list page ("20.05.2025 Startschuss für urbane Seilbahn in Heilbronn"), checked 15 Nov 1, item card on the page ("Veröffentlicht: 20. Sept. 2026"), checked 15 Nov 1.

**Coverage, measured:** this radar is an extra discovery layer, not a replacement for the city's monitoring service. Backtest on the same days against the city's own tool: Heilbronn cable car web articles 11 of 19, all projects and platforms 39 of 273 (`live/experiments/exp10_recall_vs_city_tool.py`).

## Since the last update (2026-11-15 08:33 UTC)

- Strong items stored: 371 then, 371 now (no change per project).
- With a label: 165 then, 165 now.
- Sources that answered: rss, pagewatch, exa, tavily, date_recovery.

## Checks

- The team's stage 2 rules also catch 168 of 371 strong items; 9 core-project items reach the labels only through the radar (input for codebook v2).
- Cost of this update: 0 model calls, 0 input tokens (0 read from cache), 0 output tokens, 0.00 USD at list price (cap 1.00). Failed calls: 0, refusals: 0, not called because of the cap: 0.
- Pipeline: pipeline stages exit code 0 (11s), log live\out\update\pipeline_20261115T084252Z.log. pipeline/ was not written; everything ran in live\bridge\scratch.
- Search cost: this scan no scan; this month so far exa 0.59 USD, tavily 336 credits (free tiers: Tavily 1,000 credits, Exa 10 USD, YouTube 10,000 units a day).

## Not covered

- NOT COVERED BY DESIGN: Instagram, Facebook, TikTok, LinkedIn, X: no legal open access (needs a vendor or research contract)
- NOT COVERED BY DESIGN: Reddit: official API needs approval, not set up. Reddit and the other social platforms appear only as search-result links (title, snippet), never opened
- NOT COVERED BY DESIGN: YouTube: only videos and comments the YouTube search returns for our queries (daily quota); texts older than 30 days are removed (API terms)
- NOT COVERED BY DESIGN: Heilbronner Stimme and echo24: paywall or no feed; only what Exa and Tavily index (Google News is off)
- NOT COVERED BY DESIGN: Citizen participation platforms (comments): no export, not collected
- NOT COVERED BY DESIGN: Local radio, TV, podcasts: not collected
- NOT COVERED BY DESIGN: GDELT (news index): switched off, rate limited (HTTP 429) from our network on 14 Nov, retest needed
- NOT COVERED BY DESIGN: Google News RSS: switched off, robots.txt disallows /rss. Without it and GDELT, news comes only from Exa and Tavily (what they index) and five outlet RSS feeds (a few days each), so news coverage is thinner than the city's monitoring tool
- The radar sees what search services index. Undated items count as "found now, date unknown", never as new posts.
- Labels are AI labels checked by agreement between runs, not by a person. Staff corrections go in the review queue.
