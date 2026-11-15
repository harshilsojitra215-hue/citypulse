# The technical workflow, explained (Stadt Heilbronn "Riding the Sentiment")

Written Sat 14 Nov 2026, evening, by the workflow session. Code: `pipeline/` (start with `pipeline/README.md`). Data contract for the app and eval: `pipeline/CONTRACT.md`.

Labels: **CONFIRMED** (we ran it on the real data tonight), **INTERPRETATION** (our reading), **UNKNOWN**, **PLANNED** (written, not run).

---

## 0. The whole thing in six lines

1. One command (`python -X utf8 run_all.py` in `pipeline/`) turns the 210 MB export into `data/export/data.json` in about 3 minutes on the laptop. CONFIRMED.
2. The chain: **ingest → wide net → near-duplicates → labels (rules, AI vote, humans) → measure → FAQ matching → peaks and events → export.** Each step writes a table you can open.
3. **Stance** (is the author for or against this project?) comes from an AI with a frozen rulebook (the codebook), run several times. If the runs disagree we say "uncertain", we do not guess.
4. **Relevance and project** (is this post about the Heilbronn cable car at all?) is the big, easy job. A small model we own can learn it and run inside the city. The team trains that model on the Hamburg GPU tonight.
5. Every number carries its **n**, a **95% interval**, and the **label run** (model, prompt and codebook version) that made it.
6. The city's own FAQ is used to **name the topics** and to **find where the city's answers are not reaching people**. It never decides who is for or against.

**The sentence for the jury:** "We do not show what an AI thinks; we show what a fixed rulebook says, how often independent runs agree, and where they do not."

---

## 1. Stance is not sentiment (three real posts from the data)

**Sentiment** = are the words happy or angry? (The vendor's column `sentiment`: 1, 0, -1.)
**Stance** = does the author want this project or not? (Our label: support, oppose, neutral_informative, mixed, unclear.)

They are different things. Three real posts from the export, no author names:

| # | Post (date, type) | Vendor sentiment | Our stance (3 of 3 AI runs agree) | Why they differ |
|---|---|---|---|---|
| A | tagesschau.de, 12 May 2025, news: "Land BW fördert Seilbahn-Projekt in Heilbronn mit Millionen" | **positive (+1)** | **neutral_informative** | Good news words, but the newsroom only reports a funding decision. Reporting is not supporting. |
| B | A comment on a transit forum, 20 Apr 2025: a resident proposes to extend the Heilbronn cable car to Bad Friedrichshall ("Ich schlage hiermit vor, die Strecke bis Bad Friedrichshall Hbf zu verlängern") | **negative (-1)** | **support** | The text talks about problems, but the author wants more cable car, not less. |
| C | Blog of a transport club, 17 Jul 2025: "Stadtbahn statt Seilbahn: VCD fordert Ausbau des Tram-Netzes" | **positive (+1)** | **oppose** | Calm, positive words about the tram; the author wants the cable car replaced. |

How often this happens: on the 127 relevant pilot posts that have both, vendor sentiment read as stance matches our stance in **46 of 127 (36%, interval 28% to 45%)**. CONFIRMED, recomputed by `pipeline/stages/s08_measure.py` (metric `vendor_vs_stance.match`).

**The sentence for the jury:** "Sentiment measures the mood of the words; stance measures the position on the project; on our data they agree only about a third of the time."

---

## 2. The chain, stage by stage

Real numbers from tonight's run (CONFIRMED unless marked).

```
39,361 records (+11 live items after 27 Oct)
   │ s01 ingest: validate, normalise, mask user names, drop the author field
   ▼
32,930 unique stories after near-duplicate merge (s03)
   │ s02 wide net: cable word near a place word, per project
   ▼
3,390 candidates  ──►  snippet = title + the sentences around the mention (≤ 600 chars)
   │ s04 labels: human > AI vote > curated rules > wide net only
   ▼
1,743 relevant posts (Heilbronn 155, Bonn 62, Paris C1 351, IPAI 1,175) = 1,580 stories
   │ of which 156 have a stance label today (the 240-post pilot vote)
   ▼
s08 measure ─ s09 FAQ matching ─ s10 peaks and events ─ s11 data.json
```

| Stage | What it does (plain) | How it is checked | Result tonight | One sentence for a technical jury |
|---|---|---|---|---|
| **s01 Ingest** (`s01_ingest.py`) | Reads the JSON, checks every record has id, date, URL, type; makes week, platform and domain columns; marks paywall stubs; replaces user names with `[USER]`; drops the author field | Row count in = row count out; ids unique; stops on any failure | 39,361 in, 39,361 out, 223 paywall stubs, 6,797 without vendor sentiment | "Every row keeps its id and link from the raw file to the chart, and no author name survives the first step." |
| **s02 Wide net** (`s02_candidates.py`) | Rules per project: a cable word (Seilbahn, Gondel, téléphérique, Câble C1 ...) within 400 characters of a place word (Heilbronn, IPAI, Venusberg, Créteil ...). Removes alpine noise. Cuts a snippet around the mention | Recall against the research team's curated sets | 3,390 candidates. Finds 165 of 166 curated Heilbronn posts (the missing one is an alpine hiking post about the "Heilbronner Rundweg" at Krippenstein that the curated set wrongly contains), 84 of 85 Bonn, 356 of 356 Paris, 1,238 of 1,238 IPAI | "We cast a wide net on purpose; deciding relevance is the next step's job, and we measure what the net misses." |
| **s03 Near-duplicates** (`s03_dedup.py`) | MinHash on 5-word pieces of text; two posts with estimated overlap of 80% or more are one story. Short comments merge only if identical on the same URL | Unit test; eval session hand-checks 50 merged pairs (PLANNED) | 39,361 records → 32,930 stories. Heilbronn: 196 hits → 158 stories (x1.24) | "A press release copied by ten outlets counts once, and we keep the list of outlets." |
| **s04 Labels** (`s04_labels.py`) | Collects every label run (pilot, LLM, local model, humans). Human wins. Otherwise majority of AI runs. No majority on stance = "uncertain" | Agreement between runs, stored per post | 240 pilot posts voted: 185 high, 49 medium, 6 low confidence; 5 stance abstentions | "Labels are never overwritten; each run has an id, a model name and the codebook hash." |
| **s05 LLM teacher** (`s05_llm_label.py`) | Sends each snippet with the codebook to an LLM, 3 runs in different order, JSON out, invalid = abstain | Kappa between runs; vs human gold (eval) | Not run tonight beyond the pilot. 126 unlabelled Heilbronn candidates are batched and ready | "The same frozen rulebook goes to every model, cloud or local, so we can compare them on the same posts." |
| **s06 Student** (`s06_student.py`) | Small model for "which project, or none". Uses the team's fine-tuned model if present; tonight a TF-IDF baseline trained on the 240 pilot votes | 5-fold cross-validation | Baseline: project 0.80, relevance 0.86 agreement with the AI vote. Weak on the wide net (it calls many Bonn posts Paris), so it is only a second opinion | "The small model is our own and runs offline; we only trust it where it beats the baseline on human labels." |
| **s07 Calibration** (`s07_calibrate.py`) | Temperature scaling so "80% sure" means about 80% right | Expected calibration error (ECE) before and after | Baseline student ECE 0.21 → 0.08 (against AI labels) | "When the tool says 90 percent, we measured how often that is true." |
| **s08 Measure** (`s08_measure.py`) | Stance shares per project and voice, with Wilson intervals; once human labels exist, corrected shares (ACC, PPI from the eval session's code) | Interval width, n on every number | Heilbronn (62 pilot posts): support 15% [8, 25], oppose 15% [8, 25], neutral 69% [57, 79]. AI vs AI stance kappa on relevant posts 0.63 to 0.80 | "Counting predicted labels is biased; we correct with measured error rates and always show the interval." |
| **s09 FAQ matching** (`s09_faq_match.py`) | Finds Heilbronn posts that raise a concern the city FAQ already answers, and numbers that differ from the official ones | Eval session checks 40 matches by hand (PLANNED) | Concern matches: cost 32, traffic and parking 20, comparison with other cities 18, masts 9 ... One figure flag ("14 Minuten" vs official 15) | "We show the city which questions it has already answered that people still ask." |
| **s10 Peaks** (`s10_events.py`) | Weekly stories per project; a week is a peak if the count is very unlikely under the surrounding weeks (Poisson test, corrected for testing many weeks); links peaks to documented events; placebo test with random dates | Placebo test, eval session's independent test (PLANNED) | Heilbronn: 5 peak weeks, 3 sit next to a documented event (council 3 Apr 2025, state funding 12 May 2025, cost figure 22 Jul 2026); random dates link 0.43 on average | "We test whether peaks line up with documented decisions more than random dates would." |
| **s11 Export** (`s11_export.py`) | Writes `data.json` for the dashboard: funnel, projects, weekly, stance with intervals, arguments, events, peaks, FAQ, reliability, posts, live, review queue | Shape follows CONTRACT.md; no author field exists to leak | 2.4 MB, 1,743 posts, 11 live items (kept apart from all totals), 55 posts in the review queue | "Every number on screen can be rebuilt from the posts in the file." |
| **s12 Live** (`s12_live.py`) | Google News RSS (public, no key) for items after 27 Oct; titles only; flagged "new since dataset" | Only after the city says yes (open question 5) | 11 new items, 4 about the Câble C1 outage of 5 to 11 Nov 2026 | "The dataset ends on 27 October; the same pipeline reads what came after, and labels it as new." |

---

## 3. What runs in the cloud, what runs locally, and why

| Job | Volume | Where | Why |
|---|---|---|---|
| Ingest, wide net, dedup, measure, peaks, export | 39,361 records | Laptop (later the city's server) | Plain code, no model needed |
| Relevance and project | Thousands of posts, plus every new one | **Local small model** (student), trained once on a GPU | Easy task with many examples. Small fine-tuned models do well here (Bucher and Martini 2024, in `STADT_TECH_DEEP.md`). Runs offline, costs nothing per post, the city owns it |
| Stance, voice, arguments | Hundreds of posts (Heilbronn 155) | **Cloud LLM for development** (Claude, with the codebook). **Local open LLM as the city's option** (`hamburg/label_with_vllm.py`) | Hard task with few examples. A small model cannot learn stance from 155 posts: on the pilot, small methods reach stance kappa 0.31 to 0.43 against the AI vote (CONFIRMED in `scripts/localbench/results.json`) |
| Human gold set | 60 to 166 posts | The team, eval label tool | The only way to turn "AI agrees with AI" into "AI agrees with people" |

The honest sentence: **our own labelling used a cloud model on public data the organisers gave us; the design for the city removes that dependency, and the Hamburg run measures how close the local models get.** We do not claim local equals Claude until the gold set says so. (Data protection detail and EU cloud options: `STADT_TECH_DEEP.md` 1.4. Handover: `pipeline/handover/MODEL_HANDOVER.md`.)

**The sentence for the jury:** "The hard, small job goes to the strongest reader with a fixed rulebook; the big, easy job goes to a small model the city owns."

---

## 4. The city FAQ as criteria: what we decided and why

What we found (CONFIRMED, page fetched 14 Nov 2026): heilbronn.de has a real FAQ on the cable car, "Häufig gestellte Fragen rund um die geplante Seilbahn", with 18 questions plus a status section. Key official figures: **157 million EUR** first cost estimate (price level 2026, to be validated), up to **90%** funded by state and federal government, **4.7 km** (the same page also says "about 5" and "almost 5"), **6 stations**, **15 minutes**, **1,500 passengers per hour and direction**, cabins for **10**, masts at most **55 m**, council decision on preliminary planning **27 Jul 2026**, operation "in the early years of the next decade". Stored in `pipeline/reference/faq_heilbronn.json`. Bonn and Paris have official FAQs too (`pipeline/reference/faq_bonn_paris.json`; Bonn about 155 million EUR net, opening planned 2032; Paris 138 million EUR, 4.5 km).

One small thing the FAQ itself gets wrong: it gives Câble C1 as **4.3 km**; Île-de-France Mobilités gives **4.5 km**. CONFIRMED from both pages.

**Decision: the FAQ never defines stance.** The FAQ is the city's own position. If "agrees with the FAQ" meant "support", we would be measuring loyalty to the city, not opinion, and every critic would look "wrong". So:

1. **It names the topics.** Each FAQ question is a concern the city already expects (cost, alternatives like the tram, masts, privacy, wind, noise, timeline, participation). Each one maps to an argument code in the codebook, so the dashboard can say "cost: 32 posts raise it, and here is the city's own answer".
2. **It finds where communication is not reaching people.** `concern_answered`: a post asks something the FAQ already answers ("why not the tram?" while the FAQ explains the comparison). `figure_differs`: a post states a number outside the official range, after the official number was public (an earlier estimate is not "wrong", so each figure has a `valid_from` date).

What it tells the city (INTERPRETATION, to be confirmed by the hand check): the FAQ answers many of the questions people raise, but the people raising them in the data may never see the FAQ page. That is a communication finding, not an opinion finding.

**The sentence for the jury:** "We use the city's FAQ as a map of known concerns and as a mirror for its communication, never as the answer key for who is right."

---

## 5. One real post, end to end

Post `29120189,22400`: a forum reply on alpinforum.com, 4 Apr 2025, thread "Heilbronn: Seilbahn für öffentlichen Nahverkehr". It quotes the city's press release and then says: "Das wird wieder nichts. Das ist wieder so ein Sinnlosprojekt und keine sinnvolle ÖV Planung." (The same sentence is the stance example in the codebook.)

| Stage | What happened to this post (CONFIRMED from the tables) |
|---|---|
| s01 Ingest | Kept as type `Forums`, platform `web`, source `alpinforum.com`, week 2025-03-31. 1,526 characters. Author field existed (`has_author = true`) and was removed; the user name is gone from the text. Vendor sentiment **+1 (positive)**. |
| s02 Wide net | Rule `heilbronn_cablecar` fired (6 mentions). Also the noise word list fired (it is an alpine forum), but the urban context kept it. Snippet: the title, the quoted press release, and the reply. |
| s03 Dedup | In a cluster of **6** posts from the same thread (the pages repeat the quoted press release). The earliest page represents the story. Note: this means 6 forum pages count as one story, which is right for "stories" but undercounts separate replies. INTERPRETATION. |
| s04 Labels | Three AI runs: all `heilbronn_cablecar`, all `oppose`, all `citizen`; evidence "Das wird wieder nichts. Das ist wieder so ein Sinnlosprojekt". Curated rules agree on the project. Student baseline: `heilbronn_cablecar`, 0.83. Final: **oppose, citizen, confidence high, label source vote**. |
| s08 Measure | One of the 9 "oppose" posts in the Heilbronn stance share (15%, interval 8% to 25%, n = 62). |
| s09 FAQ | **No match.** "Sinnlosprojekt" rejects the whole idea without a specific concern, so no FAQ answer applies. This is a limit of FAQ matching, and it is fine: not every post is a question. |
| s10 Peaks | Its week (31 Mar 2025) has 18 Heilbronn stories against a baseline of 2.9: a peak (q < 0.001), linked to the council decision of 3 Apr 2025 (`hn_2025_04_03_council`, city press release on heilbronn.de). |
| s11 Export | In `data.json` `posts` with stance oppose, voice citizen, confidence high, cluster size 6, no author. |

What the post teaches: vendor said **positive**, three independent runs said **oppose**, and a human reading it agrees with the runs. It also shows the limits: one forum thread, one voice.

---

## 6. Storage: DuckDB tonight, PostgreSQL for the city

- **Tonight: DuckDB + parquet.** 39k rows need no server; one file cannot crash on stage; parquet files open in anything (pandas, Excel via Power Query, R).
- **For the city: PostgreSQL + pgvector.** The city contact said they have in-house infrastructure; `pipeline/sql/schema_postgres.sql` has every table, plus an `embeddings` table for later search ("ask the debate").
- All reads and writes go through two functions in `pipeline/common.py`, so moving is a load job, not a rewrite.

**The sentence for the jury:** "We picked the storage that cannot fail on stage, and wrote the PostgreSQL schema the city would run in-house."

---

## 7. What is real by Sunday 13:00, and what is vision

| Real by Sunday 13:00 (built and run tonight, or a short step away) | Vision (designed, not done) |
|---|---|
| Whole pipeline runs in 3 minutes, `data.json` for the app (CONFIRMED) | A model the city runs itself, retrained on its own labels every quarter |
| Funnel, dedup, peaks with placebo, FAQ matching, live strip (CONFIRMED) | "Ask the debate": questions answered only from retrieved posts, numbers only from SQL |
| Stance for the 240 pilot posts, 3 AI runs, abstain rule (CONFIRMED) | Stance for all four projects with a large human gold set |
| Stance for the remaining 126 Heilbronn candidates, if we run the batches tonight (PLANNED, needs a decision) | Live monitoring of new items every day, with the same codebook |
| Human gold set: 60 posts each (about 40 minutes per person, eval plan) (PLANNED) | Corrected stance shares with tight intervals for Bonn and Paris |
| Hamburg results: student vs teacher, local LLM vs Claude, if the night works (PLANNED, the team) | Handover package: weights, model card, codebook, retraining guide (`pipeline/handover/`) |

---

## 8. Limits, said before anyone asks

1. **Only 156 posts have a stance label today.** Everything else has project only. The app must show "not labelled" for those, never "neutral".
2. **AI agreeing with AI is consistency, not accuracy.** The human gold set is still empty tonight.
3. **The curated project sets came from the research phase**, and they contain mistakes: at least one alpine hiking post sits in the curated Heilbronn 166. (rules plus hand additions). They are frozen as `reference/curated_v0.csv` and counted as "rules", below the AI vote. The pilot vote moved 11 of the 166 curated Heilbronn posts to other or irrelevant; they sit in the review queue.
4. **The placebo test is optimistic**: some seed events were found by reading the data around peaks. A clean test uses only an official calendar fixed beforehand.
5. **The student baseline is weak** (trained on 240 stratified posts). It calls many Bonn posts "Paris". It is a second opinion until the Hamburg model is measured on human labels.
6. **FAQ matching is rules.** Some matches will be topic mentions in news, not citizen concerns. The eval session measures precision by hand.
7. **User names are masked** where they appear as author strings or bylines ("verfasst von ..."). Side effect, and a good one: a forum post whose only cable car word was the user name ("Seilbahn...") no longer enters the wide net. Names of journalists or politicians inside news text are not masked; the export shows short snippets only.
8. **The near-duplicate merge treats forum thread pages as one story.** Right for counting stories, wrong for counting separate replies.

---

## 9. Files

| File | What |
|---|---|
| `pipeline/README.md` | How to run, stage list, storage decision |
| `pipeline/CONTRACT.md` | Tables and `data.json` shape (v1.1) |
| `pipeline/run_all.py`, `pipeline/stages/*.py` | The pipeline |
| `pipeline/reference/faq_heilbronn.json` | Official Heilbronn FAQ facts with concern patterns and figures |
| `pipeline/reference/faq_bonn_paris.json` | Official Bonn and Paris facts |
| `pipeline/reference/events_seed.json` | Documented events for peak linking |
| `pipeline/hamburg/README.md` | The team's GPU recipe, stop rules, what to bring back |
| `pipeline/handover/MODEL_HANDOVER.md` | What the city would get, licence and GDPR open questions |
| `pipeline/data/export/data.json` | The dashboard input (generated) |
