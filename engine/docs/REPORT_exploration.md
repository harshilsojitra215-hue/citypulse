# Cable car challenge: exploration report

Sat 14 Nov 2026, about 14:00 German time. Everything below was run on the real dataset. Each number says what it was measured on, and "n" means number of posts.

## Bottom line

1. **The data is mostly noise, and the core project is small.** Of 39,361 mentions, 167 unique posts are about the Heilbronn cable car. Only 33 of them take a side. The rest are news reports, ski lifts, alpine huts, tourist cable cars, ads and paywall text.
2. **The provided `sentiment` field is useless for opinion.** Its agreement with real stance is κ = 0.09, close to chance. It misses 94% of opposing posts, and it is −99 for every YouTube post.
3. **Claude can do the reading reliably.** Against an Opus 5.5 reference with a written codebook, Haiku agrees on which project a post is about 96% of the time (κ 0.94). On Heilbronn stance it agrees 91% of the time (κ 0.78), roughly as well as two careful humans would.
4. **A local model on Hamburg comes close, at €0.** Qwen 3.8 27B on the RTX 5090 reaches κ 0.90 on relevance and κ 0.68 on Heilbronn stance, at about 2 s per post. The city could rerun it on its own machine.
5. **Unsupervised topic modelling (BERTopic) groups posts by city, not by concern.** What works is having the model extract each argument (topic, pro/contra, one-line claim) and then clustering those claims. That gives an argument map with real sentences as labels.
6. **There are five candidate insights for Heilbronn** (section 5). The strongest: the cable car is the most contested project in the data, and support comes from officials while criticism comes from citizens. Critics attack priorities and who benefits, not the technology. Opinion turned when the first cost figure came out. Paris shows opinion improves once the system runs.

## 1. What the data really is

| Step | Posts |
|---|---|
| Raw mentions | 39,361 |
| Unique texts (3,504 are syndicated copies) | 35,857 |
| Unique texts sent to an LLM after keyword rules | 7,439 |
| → Heilbronn cable car | 167 unique (201 with copies) |
| → Bonn cable car | 116 |
| → Paris Câble C1 | 560 |
| → IPAI | 1,037 |
| → other urban cable cars (Trier, Koblenz, Hamburg, La Paz, Toulouse…) | 1,846 |
| → leisure / ski / tourist cable cars | 2,576 |
| → unrelated or Heilbronn but neither project | 1,136 |

Heilbronn in detail, leaving out posts that only mention it in passing:
- 146 posts, of which 40 are social media.
- 72 distinct (pseudonymised) authors across all 201 Heilbronn mentions.
- Only 33 posts take a side.
- The five most active authors write 33% of Heilbronn's social posts.

Cleaning findings worth telling the jury:
- 15% of all text is boilerplate: paywall banners, cookie notices, photo licence lines and newsletter blurbs. That is 5,460 sentences repeated across 15 or more posts. We strip it, because otherwise every topic model finds "Testabo freischalten".
- The keyword rule for the Heilbronn cable car is right only 61% of the time. The noise is mostly the "Heilbronner Hütte", the "Heilbronner Kreuz" on the Dachstein and Alpine trails. For Bonn the rule is right 37% of the time, because "Bonn" appears in leisure posts.
- **Recall check:** a classifier scored 3,000 random posts the rules had skipped, and Haiku verified the 1,275 flagged ones.
  - No missed Heilbronn, Bonn or IPAI posts.
  - About 38 missed Paris posts across the whole set, all German "Stadtseilbahn in Paris" wording. That is about 94% recall.
  - About 2,700 missed "other urban cable car" posts. This only matters if we compare against all cable cars.

## 2. Methods tested

**Reference set.** We drew 851 unique posts:
- all 251 Heilbronn candidates
- 60–110 from each other keyword bucket
- 150 random leftovers

Opus 5.5 labelled each post with the codebook in `prompts/codebook_v1.md`: project, passing mention, stance, tone, and up to 4 arguments. I read a sample of the cases where models disagreed. Most were press releases that one model called neutral and another called supportive. That is real ambiguity, not a mistake by Opus.

**Which project is a post about?** (6 classes, κ against Opus)

| Method | n | Accuracy | κ |
|---|---|---|---|
| Claude Haiku 5.5 | 850 | 0.96 | 0.94 |
| Claude Sonnet 5.5 | 850 | 0.95 | 0.93 |
| Qwen 3.8 27B, local on Hamburg | 700 | 0.92 | 0.90 |
| Qwen 3.5 9B, local on the Mac | 125 | 0.90 | 0.87 |
| XLM-RoBERTa fine-tuned on Haiku labels (Hamburg, 2 of 5 folds finished) | 341 | 0.90–0.91 | – |
| bge-m3 embeddings + logistic regression | 851 | 0.87 | 0.83 |
| Keyword rules only | 851 | 0.62 | 0.53 |

**Stance towards the project** (support / oppose / neutral / mixed, on posts that are really about a project)

| Method | n | Accuracy | κ (all projects) | κ (Heilbronn only) |
|---|---|---|---|---|
| Claude Haiku | 345 | 0.88 | 0.72 | 0.78 |
| Claude Sonnet | 346 | 0.88 | 0.71 | 0.84 |
| Qwen 3.8 27B, local | 292 | 0.81 | 0.60 | 0.68 |
| bge-m3 + logistic regression | 346 | 0.74 | 0.40 | – |
| Qwen 3.5 9B, Mac (too few to judge) | 46 | 0.52 | 0.25 | – |
| German sentiment BERT, used as stance | 277 | 0.74 | 0.15 | – |
| **Provided `sentiment` field** | 310 | 0.43 | **0.09** | – |

**Why tone is not stance.** In the reference set, 27 of 42 negative-sounding posts are not opposition: they are news about problems, or angry supporters. Across all relevant posts, 94% of opposing posts are not marked negative by the provided field.

**Speed and cost as measured today:**
- **Haiku:** 6,588 posts in roughly 35–40 minutes with 8 parallel calls, on the subscription, €0 extra.
- **Qwen 27B on the 5090:** about 2 s per post with one worker; slower while the GPU was shared.
- **Qwen 9B on the M5 Mac:** about 11 s per post. Too slow, and too weak on stance.
- **bge-m3 embeddings:** about 25 posts/s on the Mac.

## 3. Topics: what worked

| Approach | Result | Use it? |
|---|---|---|
| **BERTopic** (bge-m3, UMAP, HDBSCAN) on 1,705 cable-car posts | 49 topics, almost all **places** (Mexico, Ajaccio, Bonn, Heilbronn, Grenoble…). Its overlap with the argument codes is only NMI 0.23. | Only to discover unexpected themes |
| **LLM argument codes** (13 fixed topics, pro/contra per argument) | Comparable across cities and languages; every code traces back to its posts | **Yes, as the main topic layer** |
| **Argument map**: 3,500 extracted claims, embedded and clustered into 137 clusters, each named by its most central real claim | Readable clusters such as "Cable car is a wasteful project using public money" (137 claims, 86% contra, all cities), "Money should go to schools instead" (97% contra), "Proposal of women-only cabins" (Paris only), "VCD prefers extending the Stadtbahn" (Heilbronn only) | **Yes, as the drill-down** |
| **Keyness** (log-odds, Heilbronn vs other German cities) | Heilbronn's vocabulary is official: Mergel, Absichtserklärung, Planungskosten, Verkehrsminister, Bildungscampus. The social-vs-news comparison is swamped by platform UI words. | Supporting evidence only |

Share of posts raising each argument (unique posts about the project):

| Topic | Heilbronn | Bonn | Paris | Other urban |
|---|---|---|---|---|
| politics / process | 52% | 59% | 5% | 24% |
| transport benefit | 42% | 44% | 52% | 59% |
| cost / financing | 31% | 16% | 7% | 17% |
| connecting new districts / campus | 21% | 3% | 5% | 6% |
| safety / operations | 1% | 9% | 19% | 10% |
| residents / overflight | 1% | 9% | 2% | 1% |

This answers the brief's question about stages. **Projects still being planned (Heilbronn, Bonn) are debated as politics and money. A running system (Paris) is debated as transport and safety.**

## 4. Peaks and events

Method (in `src/07_peaks.py`):
- A Poisson surprise test against the previous weeks.
- Weekly counts for small projects (Heilbronn, Bonn), daily counts for large ones.
- For each peak: the most syndicated headline in that window and the nearest event from the timeline.

A subagent built the timeline: 55 sourced events (Heilbronn 23, Paris 14, Bonn 11, IPAI 7), 8 of them re-verified.

Heilbronn (weekly):

| Week | Posts | Stance in that window | Linked event | Weekly level before → after |
|---|---|---|---|---|
| 24 Mar 2025 | 31 | 6% support / 12% oppose | plans first reported; council vote 3 Apr | 0 → 3 (the debate starts and stays) |
| 12 May 2025 | 50 | 8% / 4% | state letter of intent, €4M planning money | 3 → 2 |
| 29 Jun 2026 | 5 | 14% / 0% | city names a possible opening date | 0 → 2 |
| **20 Jul 2026** | 10+ | **15% / 38%** | **first cost figure, €157M**; Löwenstein hospital closure video; council 27 Jul | 1 → 1 |

Other projects:
- **Paris opening** (week of 8 Dec 2025): the biggest spike in the data, 190 posts. Attention halves within a week, and the level afterwards is the same as before (7 per week).
- **IPAI groundbreaking with Merz** (Oct 2025): 139 posts, and the weekly level rises for good (4 → 12).

The data's own answer to "does the debate return to normal?": spikes fade within a week. A launch (Heilbronn 2025, IPAI groundbreaking) raises the level for good; an opening does not.

## 5. Candidate insights for Heilbronn

These are preliminary. Heilbronn's sample is small, so every share comes with its 95% interval.

1. **Heilbronn's cable car is the most contested project in the data.**
   - Heilbronn: 52% of posts with an opinion oppose it [35–67%, n=33].
   - Paris: 14% [7–27%, n=43]; Bonn: 33% [17–55%, n=21]; IPAI: 5% [3–10%, n=157].
   - The unusual transport system draws ten times the opposition share of the AI park it serves.
2. **Support and criticism come from different places.**
   - News is 93% neutral.
   - The supportive posts are mostly official or institutional: city, state minister, council, MPs, trade press, "Germany's first".
   - The opposing posts are citizens on YouTube, blogs and forums. Social posts with an opinion are 59% against [36–78%].
   - Heilbronn is talking past its critics.
3. **Critics attack priorities and who benefits, not the technology.** Heilbronn's top contra arguments:
   - the Stadtbahn or a bus station first (VCD, blogs)
   - a prestige project or "a monument for the mayor"
   - €157M while the Löwenstein hospital closes
   - an IPAI shuttle rather than transport for residents

   "Money should go elsewhere" (social priorities) is 2–3× more common in Heilbronn than in the other cities. Safety, noise and visual impact barely come up (1% each), although those are the classic cable-car fears.
4. **The first cost figure was the turning point, and Bonn shows what comes next.**
   - The week of 20 Jul 2026 is the only Heilbronn episode with more opposition than support (38% vs 15%).
   - Bonn shows the same pattern further along:
     - cost rose from about €66M to €155M
     - a landowner objected (DHL, Aug 2025)
     - delays to 2032
     - since a budget retreat in Jul 2026 and a budget freeze in Sep 2026 the project has effectively been on hold
   - Lesson: announce costs together with benefits and funding shares, and settle land and stakeholders early.
5. **Paris shows opinion improves once people ride it.**
   - Among posts with an opinion, support rose from 70% before opening (n=10, wide interval) to 85% after (n=33).
   - Talk moved from safety (23% → 12% of arguments, for example the "women-only cabins" row) to usefulness (37% → 50%, "18 instead of 40 minutes", "10,000 passengers a day").
   - For Heilbronn: show concrete trip times, stations and Deutschlandticket integration, not "AI city" symbolism.

## 6. What to build, and what makes it different (not the UI)

```
raw JSON ─► clean (dedupe, boilerplate, pseudonymise authors) ─► keyword rules (recall)
        ─► LLM codebook labels (project, stance, tone, arguments) ─► checked against the reference set
        ─► argument map + peaks/events + comparisons ─► dashboard where every number opens its posts
```

Differentiators that a Claude-generated UI from another team won't have:

1. **Measured accuracy, shown in the product.** For example: "Stance agrees with a reference model in 91 of 100 Heilbronn posts; relevance in 99 of 100." Better still, have you and Harshil hand-check 100 Heilbronn posts tonight. That turns it into "agrees with our human check".
2. **Proof that sentiment is wrong for this job.** The provided field scores κ 0.09 against stance. One slide, and it answers the brief's own warning.
3. **An evidence trail.** Every bar, peak and argument opens the posts behind it: short excerpt, date, source link, no handles. Authors are a salted hash, used only to count voices.
4. **Honest uncertainty.** n and a 95% interval on every share. Say plainly "only 33 Heilbronn posts take a side". Juries trust that.
5. **It runs at €0 on the city's own machine.** The local Qwen 27B pipeline has a measured gap: κ 0.68 vs Haiku's 0.78 on Heilbronn stance. Claude is the teacher that built the reference set, and one command reruns everything.
6. **Vision (20% of the score).** Rerun weekly and raise an "early warning" when the opposition share jumps, as it did in the €157M week. Plan communication around the next planned announcements (planning approval, cost update), using the Bonn and Paris lessons.

**Decision for you:** which labels the demo shows.
- **My recommendation:** ship the Haiku labels. They are complete, best measured, and done.
- Present the local Qwen 27B run as "the city can rerun this for free", with its measured gap.
- The phone-session plan on Hamburg said "bulk on local, Claude as teacher". Today you allowed the subscription, so both are possible.

## 7. Suggested plan until Sunday 10:00

- **Today:** book the preselection slot with Eva Deuchert (Ferdinand-Steinbeis-Institut). Ask her the open questions in `~/future_city_hackathon/CABLE_CAR_CLOSE_READ.md` on Hamburg, especially whether the dashboard may show short excerpts.
- **Tonight:**
  - Person 1: the dashboard from `data/labelled.parquet` with these views:
    - overview
    - project comparison
    - timeline with peaks and events
    - argument map
    - posts
  - Person 2: hand-check 100 Heilbronn posts and fix the codebook if needed.
  - Person 3: pitch story around the five insights.
- **Optional quality work:**
  - add few-shot examples for Qwen 27B (should narrow the stance gap)
  - ~~label the remaining 22 posts~~ done 14 Nov evening (Haiku); `labelled.parquet` rebuilt, insight numbers unchanged
  - finish the distillation run
  - add the Paris "Stadtseilbahn" rule

## 8. Files and how to rerun

Everything is in `6 Cable car lab/`, using the Python venv at `.venv`.

| Step | Script | Output |
|---|---|---|
| Clean, dedupe, pseudonymise | `src/01_build_base.py` | `data/base.parquet` |
| Keyword rules, boilerplate removal, snippets | `src/02_candidates.py` | `data/candidates.parquet` |
| Reference sample | `src/03_gold_sample.py` | `data/gold_items.parquet` |
| LLM labels (Claude CLI or Ollama) | `src/llm_label.py` | `labels/*.jsonl` |
| Non-LLM baselines | `src/05_encoder_baselines.py` | `labels/enc_preds.parquet` |
| Benchmark | `src/06_eval.py` | `out/eval_summary.json` |
| Peaks and events | `src/07_peaks.py … W` | `out/peaks_project_W.csv` |
| Topics (BERTopic, codes, keyness) | `src/08_topics.py` | `out/topics_*.csv`, `out/keyness_*.csv` |
| One labelled table | `src/09_assemble.py` | `data/labelled.parquet` |
| Argument map | `src/10_argument_map.py` | `out/argument_clusters.csv` |
| Recall audit | `src/11_recall.py` | `data/recall_items.parquet` |
| Insight numbers | `src/12_insights.py` | printed |
| Demo dashboard (4 screens, one HTML file, offline) and the detailed one it links to | `src/13_dashboard.py` + `dashboard/template_simple.html`, `dashboard/template.html` | `dashboard/cable_car_dashboard.html`, `dashboard/cable_car_details.html` |

Other files:
- **Event timeline:** `data/events_timeline.csv`, with notes in `data/events_timeline_NOTES.md`.
- **Codebook:** `prompts/codebook_v1.md`. Its hash is stored in every label row.

## 9. Limits and open items

- **The reference is Opus, not humans.** The 100-post human check is the fix.
- **Heilbronn is small (n=33 with an opinion).** Insights 1–2 hold in direction, but the exact percentages are soft.
- **Qwen 9B** was measured on only 46 stance posts.
- **Distillation** finished only 2 of 5 folds before the Hamburg VPN dropped. Results are in `~/future_city_hackathon/distill/` on Hamburg.
- **Hamburg changes:** I added `bge-m3` to Hamburg's Ollama (1.2 GB) and ran Qwen 27B plus one training job on the GPU. Nothing else was changed.
- **The Mac is on your phone hotspot.** I downloaded about 9–10 GB over it: Python packages, Qwen 3.5 9B, bge-m3, German sentiment BERT and part of XLM-R sentiment, which was never used.
