# Guided demo mode: rehearsal sheet

Run `python -I -X utf8 app/serve.py` (or `START_CITYPULSE.cmd`), then open one of:
- Preselection (long, 7 steps): http://127.0.0.1:8790/?demo=long
- Final (short, 6 steps, about 60 to 90 seconds of screen): http://127.0.0.1:8790/?demo=short

Keys: right arrow, Page Down, Space or a presenter clicker = next; left arrow or Page Up = back; Esc = leave the demo (if a drawer or the Ask panel is open, Esc closes that first). Add `&scene=3` to start at step 3.

**One click = one main screen.** The demo only switches the real tabs; it opens no evidence drawers, posts or sub-panels. The site stays fully clickable, so you can still open any drawer yourself.

**What makes it a demo, not just clicking the tabs:** in demo mode every screen makes an entrance (about 1.1 s): the sheet rises in, its panels follow one after another, the big numbers count up from 0 to the value already on the page, bars and charts grow from zero, and the caption fades in. The photo and the cable cars keep moving behind. Clicking the tabs yourself shows the plain fade. With "reduce motion" switched on in Windows, nothing moves and the numbers are shown straight away.

## Short route (final, 6 steps)
1. **Heilbronn, live**: home, the hook and the four ways in.
2. **Two years of debate**: History.
3. **Since the city's data ended**: So far (new items, new per day, where from, by project, latest).
4. **Human review needed**: the Human review tab (replay strip, flagged concerns, main arguments, since 27 Oct, how reliable).
5. **Today's check, step by step**: Today, the last check's steps and sources. Live option by hand: "Run it now" (about 4 minutes).
6. **Keep listening**: back home.

## Long route (preselection, 7 steps)
The same as the short route, with one Ask step after Human review:

5. **Ask, get the proof**: the Ask panel opens over Human review, the question types itself in, and the real answer appears with its proof (no drawer is opened). Before the final run the question is "What changed after 27 October?"; after it, "Are citizens actually opposing the cable car, or is this mostly news?". The answer can take about 2 seconds. The clicker keeps working while the panel is open.

How it works is a drawer (the "i" button), not a main screen, so it is not a step. Open it by hand if they ask.

Old links to `#arguments` still open the Human review tab (it now lives at `#review`).

Rule from the runbook: show the completed check first; run the quick live check only if there is time and the network is good.
