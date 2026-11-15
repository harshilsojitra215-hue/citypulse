# CityPulse pitch deck (v8)

For the 10:00 preselection ("pitch deck and a working version", opening deck p.25) and the 14:00 final (5 min pitch + 3 min questions; idea and implementation 50%, pitch 30%, vision 20%).

- `gen.py` builds `deck.html` and `SPEAKER_NOTES.md`. Run: `python -I -X utf8 deck/gen.py`
- `render.sh` makes the PDF (headless Chrome, temp files on D:): `bash deck/render.sh CityPulse_deck.pdf`
- Style: Harshil's v10 deck tokens plus the navy panels and real photo opener of the Smart Industry pitch (`hackathon/VANTAGE Intelligence Pitch.pdf`, "A problem that felt familiar").
- Photo: `assets/paris_c1_cabins.jpg`, Paris Câble C1 by Michiel Hendryckx, CC BY 4.0, Wikimedia Commons (1920px copy). The city's own challenge image is AI-made, so it is not used.

## Storyline v8 (9 slides max since 15 Nov, no footers or kickers; Harshil, 15 Nov). Sources are in SPEAKER_NOTES.md under each slide.
Look: slide 1 is a full real photo. Slides 2 to 8 are warm white, deep ink, one orange accent, little text, real charts where they exist. A small orange cable car rides a short cable in the top-right corner and moves a bit further on every slide.
| Slide | What | State |
|---|---|---|
| 1 | "A problem that felt familiar." / "Every big decision needs clarity. So first, let's read the gossip." Harshil's name only | Real photo; Reddit and story map story in the notes |
| 2 | 39,361 records, most not about Heilbronn: 89.8% about something else (dark grey), 10.2% about urban cable cars or IPAI (black), inside those 0.5% Heilbronn (orange) | Engine counts 4,020 and 201 (posts.parquet, knowledge/EVIDENCE_LEDGER.md), fixed in gen.py |
| 3 | "Not just the words. The opinion behind them.": an illustrative comment, the five positions of the codebook, result Oppose with argument and quote, read three times and uncertain kept out of the counts (Harshil's 15 Nov brief; the 36% and the vendor headline are backup for Q&A only) | Comment marked ILLUSTRATIVE; mechanism real |
| 4 | One website, three questions: So far, Now, Today (the website's own tab names) | Real |
| 5 | "What two years of posts say." v5 boxes, now real: 33 of 146 take a side (16 for, 17 against); replay from 1 Jul 2026, 28 of 75 matched, 27 to review; flagged concern, 3 voices, Löwenstein hospital, needs review; matcher 0.65 vs 0.37, AI reference | Real, from the engine (ledger findings 1, 4, 5, 6); pill "Read by AI, not yet checked by people" |
| 6 | v5 as Harshil restored it: "Since 27 Oct, our sources are quiet on Heilbronn." 3 vs Paris 17, IPAI 20, Bonn 5 | Real, from `live/out/update/latest.json` at build time |
| 7 | "From conversations to clarity.": Find, Remember, Understand (our engine: pulls out arguments, matches different wordings with a small trained model, flags a concern at two or more independent voices), Explain; the tender traced; 11 of 19 | Real |
| 8 | Live demo: "Let's see how close Heilbronn is to its cable car." + Open CityPulse link (DEMO_URL) | Link to the local prototype |
| 9 | "Want to contribute to the cable car project?" survey QR + "A reproducible, reusable intelligence." | QR appears once `SURVEY_URL` in gen.py is set |
