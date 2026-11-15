# Evidence ledger: every number we show, where it comes from, how to say it

Built 15 Nov 2026, about 07:00 IST, after the argument engine ran on Harshil's laptop (smoke test passed, numbers below re-read from the running API or the files). Verdicts: **safe** (say as is), **qualify** (say with the limit in the same sentence), **blocked** (do not say).

## The counts are different things. Never mix them.

| Object | Number | What it is | Source |
|---|---|---|---|
| Raw city mentions | 39,361 | everything the city's monitoring tool exported, 1 Oct 2024 to 27 Oct 2026, mostly ski lifts and noise | `materials/Stadt Heilbronn/FSI_*.json`, pipeline funnel |
| Relevant posts (engine) | 4,020 | posts the engine's AI labeller (Claude Haiku for most posts; Claude Opus for the 534-post reference sample, which holds 189 of the 201 Heilbronn posts; codebook v1) put on an urban cable car or IPAI: other cities 2,026, IPAI 1,080, Paris 581, Heilbronn 201, Bonn 132 | `engine/app_data/posts.parquet`, `/api/overview` |
| Heilbronn posts | 201 | posts about the Heilbronn cable car, copies included | `/api/overview?project=heilbronn_cablecar` |
| Heilbronn unique posts | 167 | after re-published copies are merged | same |
| Independent voices | 93 | distinct authors or sites (hashed). A news site counts as one voice. Not residents. | same |
| Counted for stance | 146 | unique posts where Heilbronn is the main topic (passing mentions left out) | same |
| Take a side | 33 | 16 support + 17 oppose; the other 113: 109 only report, 4 unclear | same, `offline_pack/key_results.json` |
| Extracted claims | 3,500 | one-sentence arguments the AI pulled out of posts (Heilbronn 326) | `claims.parquet` |
| Argument families | 137 | groups of claims that say the same thing | `families.parquet` |

## Findings

**One answer per question (decided 15 Nov, about 07:00 IST):** the website's History numbers are the ones we say, on slides and on stage: 40 of 194 labelled Heilbronn posts take a side, 18 support, 22 oppose. The engine's own overview (#1, #2 below: 33 of 146 unique main-topic posts) is the same labelling counted on a stricter base; use it only in Q&A if someone asks why two counts exist.

| # | Say this | Number, base, period | Source | Verdict |
|---|---|---|---|---|
| 1 | "Most Heilbronn coverage only reports. Of 146 Heilbronn posts, 33 take a side: 16 for, 17 against." | 33 of 146 unique posts, Oct 2024 to Oct 2026, city data alone (with collector items merged the engine shows a few more) | `/api/overview` | **safe** with "posts", never "people" |
| 2 | "Among the posts that take a side, it is about even." | 17 of 33 oppose, 51.5%, interval 35% to 68% | same | **qualify**: 33 posts is small; the interval is wide. **Blocked:** "51% of Heilbronn is against". |
| 3 | "Reading the posts as a whole: 9% support, 11% oppose, 76% only report." (History tab) | 194 relevant Heilbronn posts incl. copies; one engine label per post (Opus for 189 of the 201 engine Heilbronn posts, Haiku for the rest), and on 61 of the 194 three pilot readings from 14 Nov also vote (majority wins, a tie is uncertain) | `pipeline/data/export/data.json` | **qualify**: AI labels, not checked by people; different base from #1 (all relevant posts vs unique main-topic posts) |
| 4 | "We froze the system on 1 July 2026 and replayed what came next in order. Of 75 later Heilbronn claims, 28 matched an argument it already knew, 20 started or joined new groups, 27 needed a person." | 75 claims, 1 Jul to 26 Oct 2026 | `/api/replay?project=heilbronn_cablecar&cutoff=2026-07-01` | **safe** as "historical replay"; **blocked**: "it detected this live" |
| 5 | "Three concerns were flagged because two or more independent voices raised them: money for the cable car while the Löwenstein hospital faces closure (3 voices), the 157 million euro cost (2), Germany's first cable car fully in the transit network (3)." | first seen 22 to 27 Jul 2026 | same, `concerns[]` | **qualify**: all three are "needs review", not confirmed new issues; the third is a news fact, not a complaint |
| 6 | "Our small model learned to spot when two differently worded claims make the same argument: 0.65 F1 against 0.37 for plain text similarity." | 3,239 test pairs, Jul to Oct 2026, interval 0.57 to 0.71 | `app_data/matcher.json` | **qualify**: measured against Claude Opus as reference, not people. **Blocked:** "65% accurate", "understands 65% of opinions" |
| 7 | "When it says an argument is new, it is right about 94% of the time, but it is careful: it marks only about a third of the truly new ones as new; the rest go to review." | novelty precision 0.94, recall 0.32 | same | **qualify** (Opus reference) |
| 8 | "Spotting a claim that contradicts an earlier one is switched off: it was not reliable." | earlier F1 0.13 | `/api/health` "contradiction_detection disabled" | **safe**, good answer to "what can't it do" |
| 9 | "The city's tool says the post is negative; it is news about a yes." ("Heilbronn sagt Ja zur Seilbahn-Idee") | vendor sentiment matched stance 46 of 127 (36%) | `eval/`, 14 Nov pilot | **safe** (Q&A backup) |
| 10 | "Since the city's data ends (27 Oct), the collector found items in the sources it checks." | see `live/out/update/latest.json` of the last run; undated items are never counted as new | collector receipt | **qualify**: "in the sources checked"; **blocked**: "Heilbronn is quiet" as a fact about the city |

## What runs where (verified 15 Nov on this laptop)

| Part | State | Check |
|---|---|---|
| Engine API (port 8000) with the fine-tuned matcher on CPU | working | `/api/health`: matcher local-model, 3,500 claims, 68,874 cached pair scores |
| Analyst console (port 3000) | working, production build | build OK, 8 pages |
| Replay and concerns | cached model scores; first call 10 s, then 0.15 to 0.5 s | timed with the API |
| Labelling new items | Claude Haiku through OpenRouter (test call OK) | `steps.check_llm()` |
| Embedding new claims (bge-m3) | waiting for Ollama install | `/api/health` embedder |
| Website History | final run from the engine's labels | `data.json` meta.release final |

## Rules
- Posts are not people. A voice is an author or a site, not a resident.
- Replay is a simulation of the past, not a live detection.
- Every model number is agreement with an AI reference, not human-checked.
- Never show author names or handles. Never invent a number.
