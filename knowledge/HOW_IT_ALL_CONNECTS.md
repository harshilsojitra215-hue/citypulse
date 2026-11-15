# How CityPulse works now, end to end (15 Nov 2026)

One laptop, one click (`START_CITYPULSE.cmd`), four parts running hidden:

```
city export (39,361)                      collector (live/)
        |                                       |
        v                                       v
  ENGINE (engine, port 8000)  <---  feed_engine.py  (new dated items only)
  read -> claims -> match -> new?               |
        |                                       |
        v                                       v
  snapshot.py -> app/data/engine.js     update_now.py report (Today)
  labels_to_pipeline.py -> pipeline -> data.json (History)
        |
        v
  WEBSITE (app/, port 8790): History · So far · Today · Human review · Ask
  ANALYST CONSOLE (port 3000): the engine's own screens
```

## One real item, all the way through

**The post.** A YouTube video, 26 Jul 2026. Title in English: "157 million euros for a cable car in Heilbronn, but a hospital in Löwenstein is to die". Its text says a large crowd demonstrated on 19 Jul 2026 and that 205 hospital beds cannot be replaced.

| Box | What happens to it | Real file or field | Result for this post |
|---|---|---|---|
| 1. Read | Claude Haiku reads the post with one rulebook (the codebook) and answers: which project, which position, which arguments | `engine/pipeline/prompts/codebook_v1.md`, `app_data/posts.parquet` | project Heilbronn, stance **oppose**, tone negative (this one was also read by Claude Opus as a reference) |
| 2. Pull out the argument | Each argument becomes one short English sentence, a "claim" | `app_data/claims.parquet`, claim `c3153` | "Money for cable car while Löwenstein hospital faces closure" |
| 3. Find look-alikes | bge-m3 turns every claim into numbers, so the 20 or so most similar older claims can be found fast | `app_data/claims_emb.npy` | candidates found, among them "Money available for cable car but not for family doctors" (stimme.de, May 2025) |
| 4. Same argument or not? | Our small trained model (279M parameters) reads two claims side by side and says how likely they make the same argument | `models/citypulse-matcher-v2/`, `pair_scores.parquet` | family doctors claim: 0.49 same, so **not sure** |
| 5. New, known, or review? | Above 0.80 = known argument. Below 0.29 = new. In between = a person should look | `app_data/matcher.json` thresholds | 0.49 is in between: **needs review** |
| 6. Is it spreading? | When two or more independent voices (different authors or sites) raise the same new point, it is flagged | `/api/emerging`, `concerns[]` | two other YouTube comments on the same video say it in other words ("Building cable car while closing hospital is absurd", 0.88 same; "Money goes to cable car while lung clinic closes", 0.98 same). 3 voices, flagged on 26 Jul 2026 |
| 7. Show it | The website's Human review tab and the console show the card; one click opens the three posts with date, source and link | `app/data/engine.js`, `http://127.0.0.1:3000/emerging` | card "Money for cable car while Löwenstein hospital faces closure", needs review |

**Honest limits on this example:** all three voices are comments on one video, so it is one place where people talked, not three places. It is flagged for a person to look at, not proven as a city-wide concern.

## The replay (why we trust "new" at all)
We froze the engine on 1 Jul 2026 and let the later 75 Heilbronn claims arrive in their real order. Each claim could only be compared with claims dated before it, so the engine could not peek at the future. Result: 28 matched an argument it already knew, 9 joined a new group, 11 opened a new group, 27 went to review, 3 groups were flagged. The hospital concern is one of the 3.

## A new item from the collector (what "Update now" adds)
1. `live/update_now.py` collects (Exa, Tavily, RSS, the city's pages) and writes `live/out/raw_live.json`.
2. `live/engine_bridge/feed_engine.py` keeps only items with a real publication date (never guessed), on topic, not sent before; posts them to the engine.
3. The engine does boxes 1 to 6 for them: reading with Haiku through OpenRouter (capped at 1 USD), bge-m3 in Ollama on the laptop's graphics card, the matcher on the processor.
4. `live/engine_bridge/snapshot.py` copies the engine's answers into `app/data/engine.js`, so the website shows them even if the engine is off.

## The numbers, and what each one counts
39,361 city records -> 4,020 relevant posts -> 201 about Heilbronn (167 without copies) -> 146 mainly about it -> 33 take a side (16 for, 17 against). That is the engine's own strict count. On stage and in the deck use the website's History count: 40 of 194 labelled posts take a side, 18 for, 22 against. 3,500 claims in 137 families. Full list with limits: `knowledge/EVIDENCE_LEDGER.md`.

## How good is the matcher?
On 3,239 test pairs from Jul to Oct 2026 it agreed with Claude Opus's judgement at F1 0.65 (0.57 to 0.71). Plain text similarity scored 0.37. That is agreement with an AI reference, not checked by people. Spotting contradictions is switched off because it was not reliable.

## Say it in one sentence
"CityPulse reads every post, pulls out the argument, uses a small model we trained to see when two people make the same point in different words, and flags a new concern only when several independent voices raise it, always with the posts behind it."
