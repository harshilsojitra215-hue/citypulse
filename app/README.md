# CityPulse website (app/)

The whole CityPulse prototype for Stadt Heilbronn (decision of 15 Nov 2026: the site reads the analysis pipeline's export and the argument engine's snapshot).

## Run

```
python -I -X utf8 app/serve.py
```
Open http://127.0.0.1:8790/ (preview config `citypulse-site`). Offline fallback: double-click `app/index.html`; everything works except "Update now" (Replay still works).

After a new collector receipt or a new pipeline export:
```
python -I -X utf8 app/build_data.py
```

## What is on the page

- **Background:** a real photo of Heilbronn from the Kilianskirche tower (Peter Schmelzle, CC BY-SA 4.0, credited on the page) with the cable car drawn in. Every part (cabin body, glazing, doors, hanger, grip, mast head, sheave trains) is a small 3D model in metres, projected through the photo's own camera and lit by the photo's own sun (behind the camera, to the right), so each cabin shows the faces the camera really sees and its glass catches the light as it passes. One mast, two ropes, a cabin every 24 s each way at 5 m/s, a swing after the mast, soft cloud shadows over the roofs, a few birds. An illustration of the plan, not its real position. Reduced motion keeps it still.
- **Home:** the photo with the cabins, one hook ("Let's see how close Heilbronn is to its cable car."), three ways in (each with one fact: 39,361 records, new since 27 Oct, last check time) and the Ask field.
- **Three reports, each one focused sheet with a dashboard grid (no scrolling on a laptop):**
  - **History** (the city's data, hash #history): before the final run, the six documented moments on a real time axis (Paris C1 below for comparison), their sources, and one quiet "Final analysis, pending" card with the four questions. After it: who takes a side, what is raised, who speaks, when attention rises, tone vs position, evidence. Each card opens its finding in the drawer.
  - **So far** (after 27 Oct, the collector, hash #since): new items, about Heilbronn's line, found late, undated; new per day; where from; by project; latest on-topic items.
  - **Today** (the live check, hash #today): Run it now, sources (answered or not run in this check), what stays out of reach, every step.
- **How it works:** the "i" button; method, rules, city FAQ figures, photo credit.
- **Ask CityPulse:** the "Ask" pill (every screen), the field on home, or the `/` key. With `app/serve.py` running, a language model (Haiku via OpenRouter, app title "studio") reads the question into a query only: which checked answer, project, period, speaker group. The answer itself is always computed from the data and every number is checked before it is shown ("Understood as" = read by the model, "Read as" = keyword reader, which also takes over if the model fails). It handles follow-ups and refuses resident shares, names, predictions and causes. Tests: `node app/tests/ask_suite.js`, `python -I -X utf8 app/tests/ask_model_eval.py` (real calls, about 0.004 USD), then `node app/tests/ask_e2e.js`.

## Files

| File | Role |
|---|---|
| `index.html`, `style.css`, `app.js` | The page. Plain JavaScript, no libraries |
| `scenephoto.js` | The background: photo plus the drawn mast, ropes and two gondolas (SVG in photo pixels) |
| `photo/` | The photo (CC BY-SA 4.0, Peter Schmelzle, Wikimedia Commons) |
| `adapter.js` | The only reader of the pipeline export and the collector receipt; typed view models for the screens |
| `ask.js`, `ask.css` | Ask CityPulse. `makeCore()` (no DOM): interpret, the read-only answers, validate. Then the panel, which opens evidence through `CP_APP` (end of `app.js`) |
| `ask_model.py` | Ask CityPulse question reader behind `POST /api/ask`: model call, strict check of its query, cost cap, rate limit |
| `tests/ask_suite.js`, `tests/ask_model_eval.py`, `tests/ask_e2e.js` | Ask CityPulse tests: offline suite, real model readings (results in `tests/results/`), readings through the answers |
| `demo.js` | Guided demo mode (`?demo=long`, `?demo=short`), see `DEMO.md` |
| `serve.py` | Static server plus `/api/status` and `/api/update` (streams `live/update_now.py`) |
| `build_data.py` | Builds `data/*.js` from `live/out/update/latest.json`, `pipeline/data/export/data.json`, the city FAQ |
| `DATA_MAP.md` | Every placeholder, which field fills it, and the swap after the final run |
| `DATA_SCHEMA_PROPOSAL.md` | Old proposal of 14 Nov, superseded by `pipeline/CONTRACT.md` and `DATA_MAP.md` |
| `shots/` | Screenshots for review |
