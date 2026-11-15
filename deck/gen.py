"""Build the CityPulse pitch deck v10: deck/deck.html (9 slides, 1280x720) and deck/SPEAKER_NOTES.md.

v10 (15 Nov, "a middle vibe"): v9's type and spacing (two-line headline, bold then light grey; 72px left edge), but
each slide carries its point fully: a headline plus 2 to 4 short supporting elements with real numbers, set in
columns or rows with hairline dividers, never boxes. No website screenshots (Harshil shows the website live).
Slides 1 and 8 unchanged; slide 6 keeps its v5 layout; slide 9 shows the survey QR (assets/survey_qr.png).

Run:    python -I -X utf8 deck/gen.py
Render: bash deck/render.sh CityPulse_deck.pdf   (headless Chrome, as in hackathon/deck_build_v10)

Slides 4 and 5 read the website's own History numbers from the History export (pipeline/data/export/data.json, meta.release
"final"), so the deck says what the History tab says; the build stops if that export is not final.
Slide 6 draws from the collector's receipt (live/out/update/latest.json) at build time.

Harshil's direction (15 Nov): no footers, no kickers, no page numbers. Slide 1 = "A problem that felt familiar" on a
full real photo. After it: warm white, deep ink, one orange accent, little text. A small cable car in the top-right
corner moves a bit further on every slide (a small touch, not the main thing). Slide 8 = link to the prototype,
slide 9 = the survey QR hook and "a reproducible, reusable intelligence".

Evidence rules: every number has a file behind it (in the speaker notes, knowledge/EVIDENCE_LEDGER.md).
"""
import argparse
import json
import pathlib
from collections import Counter
from datetime import date, datetime, timedelta, timezone

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
LATEST = ROOT / "live" / "out" / "update" / "latest.json"
EXPORT = ROOT / "pipeline" / "data" / "export" / "data.json"
ap = argparse.ArgumentParser()
ap.add_argument("--history", choices=["auto", "pilot"], default="auto",
                help="auto: charts only if the History export is final. pilot: test the chart code on the pilot export (never ship)")
ap.add_argument("--out", default=str(HERE / "deck.html"))
ARGS = ap.parse_args()
# The room survey (live 15 Nov). Slide 9 shows deck/assets/survey_qr.png when it exists, with SURVEY_LABEL under it
# (nobody types the long URL); without the PNG a placeholder. The form must store no name, e-mail, login or IP
# (knowledge/PITCH_IDEAS.md).
SURVEY_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdcIEPZVge20k8Y02RuAH2e0fLEccyaQVI-tPixxDp3sdYyeA/viewform"
SURVEY_LABEL = "Google Form · anonymous"
QR_PNG = HERE / "assets" / "survey_qr.png"
# The prototype he demos from slide 8 (app/serve.py must be running on his laptop). Change here if it moves.
DEMO_URL = "https://citypulse-bay.vercel.app"   # Harshil, 15 Nov: present from the hosted link

INK = "#0f172a"; ACC = "#ff5b1f"; LINE = "#d9d2c9"
TOTAL = 9   # Harshil, 15 Nov: slide 8 = link to the prototype for the demo, slide 9 = survey QR

# ── live numbers (since 27 Oct) ─────────────────────────────────────────────
upd = json.loads(LATEST.read_text(encoding="utf-8"))
items = upd["items"]
when = datetime.fromisoformat(upd["meta"]["generated_at"]).strftime("%d %b %Y, %H:%M UTC")
def dates(project):
    c = Counter(i["date_class"] for i in items if i["radar_project"] == project)
    return c.get("after", 0), c.get("late", 0), c.get("unknown", 0)
HN = dates("heilbronn_cablecar"); PA = dates("paris_c1"); IP = dates("ipai"); BO = dates("bonn_cablecar")
CORE = ("heilbronn_cablecar", "ipai", "bonn_cablecar", "paris_c1")
EDGE = datetime(2026, 10, 27, 12, 29, tzinfo=timezone.utc)          # the city's export ends here
SCAN = datetime.strptime(upd["meta"]["collect_run_id"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
DAYS = (SCAN - EDGE).days                                             # 18 for the 14 Nov scan
NEW4 = [i for i in items if i["radar_project"] in CORE and i["date_class"] == "after"]
FOUND4 = sum(1 for i in items if i["radar_project"] in CORE)
ALLFOUND = len(items); NPROJ = len({i["radar_project"] for i in items})
def find(pred):
    hit = [i for i in items if pred(i)]
    assert hit, "an item named on slide 6 is missing from latest.json"
    return hit[0]
PAPER = find(lambda i: "061/2025" in (i["title"] or ""))
TENDER = find(lambda i: "TenderMap" in (i["title"] or "") and i["date_class"] == "late")
OUTAGE = [i for i in items if i["radar_project"] == "paris_c1" and i["date_class"] == "after"
          and any(w in (i["title"] or "") for w in ("interrompu", "cavité", "interruption"))]
assert OUTAGE, "Paris outage items missing from latest.json"

# ── history (the History export) ──────────────────────────────────────────────────
exp = json.loads(EXPORT.read_text(encoding="utf-8")) if EXPORT.exists() else {}
FINAL = exp.get("meta", {}).get("release") == "final"
SHOW = FINAL or ARGS.history == "pilot"                                # pilot = local test render only
HEVENTS = sorted((e for e in exp.get("events", []) if e["project"] == "heilbronn_cablecar" and not e["after_dataset"]),
                 key=lambda e: e["date"])
EV_SHORT = {  # the six documented city events, in short English (titles and sources: pipeline export "events")
    "hn_2025_03_27_plans": "Plans go public", "hn_2025_04_03_council": "Council: start planning",
    "hn_2025_05_12_state": "State: 4 M EUR", "hn_2025_07_17_critics": "Critics: tram instead",
    "hn_2026_07_22_cost": "Cost: 157 M EUR", "hn_2026_07_27_council": "Council: hire planners"}
ARG = {"cost": "Cost", "traffic_mobility": "Traffic and mobility", "tourism_image": "Tourism and image",
       "climate_environment": "Climate and environment", "ipai_who_benefits": "Who benefits",
       "noise_privacy_overflight": "Noise, flying over homes", "cityscape_design": "Cityscape and design",
       "process_participation": "Process and participation", "safety_technology": "Safety and technology", "other": "Other"}

PHOTO = "assets/paris_c1_cabins.jpg"
CREDIT = "Paris Câble C1 · Michiel Hendryckx, CC BY 4.0, Wikimedia Commons"

# ── the small corner cable car (slides 2 to 8) ──────────────────────────────
X0, Y0, X1, Y1, CX, CY = 990, 22, 1300, 40, 1140, 46
def on_cable(t):
    return ((1 - t) ** 2 * X0 + 2 * (1 - t) * t * CX + t * t * X1,
            (1 - t) ** 2 * Y0 + 2 * (1 - t) * t * CY + t * t * Y1)
def cabin(x, y):
    """A small three-quarter view cabin: grip, hanger, accent body with a lit side face and a window band."""
    return f'''<g transform="translate({x:.1f},{y:.1f}) scale(.62)">
  <rect x="-8" y="-5" width="16" height="8" rx="3" fill="{INK}"/>
  <path d="M0,3 L0,20 Q0,24 4,24 L10,24" stroke="{INK}" stroke-width="2.6" fill="none" stroke-linecap="round"/>
  <path d="M-26,30 Q-26,24 -20,24 L22,24 Q30,24 32,31 L34,62 Q34,70 26,70 L-20,70 Q-26,70 -26,64 Z" fill="{ACC}"/>
  <path d="M22,24 Q30,24 32,31 L34,62 Q34,70 26,70 L22,70 Z" fill="#d94a14"/>
  <rect x="-20" y="31" width="38" height="17" rx="5" fill="#fff"/>
  <rect x="-17" y="34" width="13" height="11" rx="3" fill="#cfe0ff"/>
  <rect x="0" y="34" width="14" height="11" rx="3" fill="#cfe0ff"/>
  <path d="M24,33 L30,34 L31,47 L24,47 Z" fill="#fff" opacity=".85"/>
</g>'''
def corner(n):
    t = 0.10 + (min(n, TOTAL) - 2) * (0.70 / (TOTAL - 2))   # the Q&A backup slide keeps slide 9's position
    x, y = on_cable(t)
    return f'''<svg class="corner" width="1280" height="720" viewBox="0 0 1280 720">
  <path d="M{X0},{Y0} Q{CX},{CY} {X1},{Y1}" stroke="{LINE}" stroke-width="1.6" fill="none"/>
  {cabin(x, y)}
</svg>'''

MARK = '<div class="mark"><i></i>CITYPULSE</div>'
slides, notes = [], []
def add(html, note, source="", cls=""):
    n = len(slides) + 1
    slides.append(f'<section class="slide {cls}">\n{(corner(n) if n > 1 else "")}{MARK}\n{html}\n</section>')
    notes.append(note + (f"\n\n*Source:* {source}" if source else ""))

# 1 · A problem that felt familiar ───────────────────────────────────────────
add(f'''<div class="photo" style="background-image:url('{PHOTO}')"></div><div class="shade"></div>{MARK}
<div class="hero">
  <div class="kick">STADT HEILBRONN · RIDING THE SENTIMENT</div>
  <h1>A problem that<br>felt familiar.</h1>
  <div class="rule"></div>
  <p>Every big decision needs clarity.<br><b>So first, let's read the gossip.</b></p>
</div>
<div class="names">Harshil Sojitra</div>
<div class="credit">{CREDIT}</div>''',
"Before I chose my country and my university, I spent hours on Reddit reading debates, arguments and real opinions. That is how I got clarity. Today I work at a company in Stuttgart that builds a story map, so citizens can see a project before it is built. People react to how a plan touches their own life. Heilbronn is planning a cable car, and the city needs the same clarity: what are people really saying?",
"Photo: Paris Câble C1, one of the projects we compare (Wikimedia Commons, CC BY 4.0).", "s1")

# 2 · 39,361 posts, 201 about Heilbronn's cable car ─────────────────────────
# v11 (Harshil, 15 Nov: "i feel no need of this 0.5"): the big 0.5% is gone; the funnel is the slide's anchor.
# v10 (Harshil, 15 Nov: "u made over simple and minimal ... i want a middle vibe"): v9's big 0.5% stays, the funnel comes
# back as three labelled steps in one row (no record-card grid). The headline wall stays in the notes (WALL).
WALL = ["Schilthorn und Piz Gloria: Panorama-Gipfel über dem Lauterbrunnental (ad-hoc-news.de)",
        "Investor verzweifelt gesucht: Davoser Kult-Seilbahn stellt Betrieb ein (blick.ch)",
        "Hors-piste et freeride : les spots mythiques des Pyrénées (skiinfo.fr)",
        "Seilbahn auf Spielplatz in Euskirchener City (radioeuskirchen.de)",
        "Chamonix : Le nouveau forfait à 40 euros la journée fait débat (mon-sejour-en-montagne.com)",
        "Heilbronner Seilbahn soll 157 Millionen Euro kosten (stimme.de, 22 Jul 2026, the one about Heilbronn)"]
# Engine numbers (knowledge/EVIDENCE_LEDGER.md, 15 Nov): engine/app_data/posts.parquet, /api/overview.
# 4,020 = posts the engine's AI labeller (Claude Haiku for most posts; Claude Opus for the 534-post reference sample, which holds 189 of the 201 Heilbronn posts; codebook v1) put on an urban cable car or IPAI;
# 201 = Heilbronn cable car posts, copies included. Rechecked against posts.parquet on 15 Nov.
N_ALL, N_REL, N_HN = 39361, 4020, 201
pc = lambda n: f"{100 * n / N_ALL:.1f}%"
ARR = '<div class="arr"></div>'
add(f'''<h2>{N_ALL:,} posts.<br><span class="lt">Only {N_HN} are about Heilbronn's cable car.</span></h2>
<div class="fun2">
  <div><b>{N_ALL:,}</b><p>city posts in two years</p></div>{ARR}
  <div><b>{N_REL:,}</b><p>found about urban cable cars or IPAI</p></div>{ARR}
  <div class="me"><b>{N_HN}</b><p>about Heilbronn's cable car</p><span class="lab">{pc(N_HN)} of all</span></div>
</div>''',
f"The city gave us {N_ALL:,} records from two years of media monitoring. Most are noise: ski passes, holiday tips, a cable car on a playground. The engine found {N_REL:,} posts about urban cable cars or IPAI. For Heilbronn the count is complete as far as we checked: a recall test on 3,000 skipped posts found no missed Heilbronn post. {N_HN} are about Heilbronn's cable car, {pc(N_HN)} of everything. So the first job is simply finding the right ones.\n\nExamples of the noise, if asked (headlines from the sample file): " + "; ".join(WALL) + ".",
f"The city's export (materials/Stadt Heilbronn/FSI_*.json), 1 Oct 2024 to 27 Oct 2026; headlines from the sample file. {N_REL:,} relevant and {N_HN} Heilbronn come from the engine's AI labeller (Claude Haiku for most posts; Claude Opus for the 534-post reference sample, which holds 189 of the 201 Heilbronn posts; codebook v1): engine/app_data/posts.parquet and /api/overview (relevant split: other cities 2,026, IPAI 1,080, Paris 581, Heilbronn 201, Bonn 132). Shares computed from these counts: {N_ALL - N_REL:,} = {pc(N_ALL - N_REL)}, {N_REL:,} = {pc(N_REL)}, {N_HN} = {pc(N_HN)}, each of all 39,361. Ledger: knowledge/EVIDENCE_LEDGER.md. Limit: relevance is an AI reading, not checked by people; these are posts and articles, not people, and the 201 include re-published copies (167 unique).")

# 3 · Not just the words. The opinion behind them. ─────────────────────────
# v10: the full idea again, clean: comment -> five positions (Oppose highlighted) -> result, plus the doubt line.
POS = ["Support", "Oppose", "Neutral or informative", "Mixed", "Unclear"]
plist = "".join(f'<li class="{"on" if p == "Oppose" else ""}">{p}</li>' for p in POS)
# v11 (Harshil, 15 Nov: "the hook is to say that it understands it"): a REAL post replaces the illustrative comment;
# bottom line in his words: "When the position is unclear, the AI does not guess."
add(f'''<h2>Not just the words.<br><span class="lt">The <em>opinion</em> behind them.</span></h2>
<div class="cmt3"><div class="lab">Real post · Instagram · 15 Mar 2026 · translated</div>
  <p>“Business trip to Paris. Other cities build cable cars to relieve traffic. So of course I had a look in person. After all, you need to know <u>what you will argue against later in the city council</u>.”</p>
  <div class="tool3">City's monitoring tool: <b>positive</b></div></div>
<div class="arr a3a"></div>
<div class="pos3"><div class="lab">Five positions</div><ul>{plist}</ul></div>
<div class="arr a3b"></div>
<div class="res3"><div class="lab">CityPulse reads</div><div class="v">Oppose</div><div class="ll">Friendly words, but the writer will argue against it</div></div>
<div class="doubt3">When the position is unclear, the AI does not guess.</div>''',
"Most tools read the mood of the words. This is a real post from the city's own data. It sounds friendly, and the city's monitoring tool scored it positive. But read it to the end: the writer went to see a cable car so they know what to argue against in the city council. CityPulse reads the whole context and picks one of five positions: support, oppose, neutral or informative, mixed, or unclear. Here: oppose. And when the position is unclear, the AI does not guess: it says unclear and keeps it out of the for and against counts.",
"Real post: Instagram, 15 Mar 2026, doc_id 17712358,286826 in engine/app_data/posts.parquet (the city's export). German original, first sentences: 'Dienstreise nach Paris. Andere Städte bauen Seilbahnen, um den Verkehr zu entlasten. Also habe ich mir das selbstverständlich einmal persönlich angesehen – schließlich muss man wissen, wogegen man später im Stadtrat argumentiert.' The post continues as satire (a satirical party proposes zeppelins over the Neckar); no author name is shown. The vendor's tool_sentiment for it is 1 (positive); CityPulse's label: stance oppose, tone positive (read by Claude Opus as the reference sample of the engine's labelling). It is the only Heilbronn post in the data where tone is positive and stance is oppose. If asked about the party: say it is a public post from a political account, shown without the name. Five positions = the codebook (engine/pipeline/prompts/codebook_v1.md: support, oppose, neutral, mixed, unclear). Each relevant post has one engine label (Claude Haiku, or Claude Opus for the 534-post reference sample, which includes almost all Heilbronn posts); for the 240 pilot posts three earlier readings (Sonnet twice, Haiku) also vote, majority wins, a tie is 'uncertain'. Do not say 'read three times' about the final numbers. Backup for Q&A only: in the pilot, vendor mood matched stance in 46 of 127 relevant posts (36%, knowledge/STADT_EVAL_PLAN.md); on the final run it is 39% of 1,774 (slide 5). That is a comparison, not model accuracy.")

# History numbers (the final export; the website's History tab uses the same rows) ─────────────
# pipeline/data/export/data.json, release final, stance heilbronn_cablecar voice all:
# n 194, support 18, oppose 22, neutral_informative 148, unclear 6.
EXP_ST = next((s for s in exp.get("stance", []) if s["project"] == "heilbronn_cablecar" and s["voice"] == "all"), None)
assert FINAL and EXP_ST, "slides 4 and 5 need the final export's Heilbronn stance row"
S_N, S_FOR, S_AG = EXP_ST["n"], EXP_ST["counts"]["support"], EXP_ST["counts"]["oppose"]
S_REP, S_UNC = EXP_ST["counts"]["neutral_informative"], EXP_ST["counts"].get("unclear", 0) + EXP_ST["counts"].get("mixed", 0)
assert S_FOR + S_AG + S_REP + S_UNC == S_N, "stance counts do not add up to n"
PLACEBO = next(p for p in exp["placebo"] if p["project"] == "heilbronn_cablecar")      # 4 of 5 peaks on an event
TONE = next(r for r in exp["reliability"] if r["metric_id"] == "vendor_vs_stance.match")  # 0.39 of 1,774
TONE_PCT = f"{round(100 * TONE['value'])}%"
# Minutes for one live click: the last update that really scanned (an offline --no-collect rebuild takes seconds and would
# say "0 min"); fall back to the runbook's measured quick click (237 s).
_secs = [json.load(open(p, encoding="utf-8"))["meta"] for p in sorted((ROOT / "live" / "out" / "update").glob("live_update_*.json"))]
_scan = [m["seconds"] for m in _secs if m.get("collect_note") is None and m.get("seconds", 0) > 60]
CLICK_MIN = round((_scan[-1] if _scan else 237) / 60)

# Since 27 Oct, end of the pipeline: the engine's confirmed posts (used on slides 4 and 6). See slide 6 comment.
_ej = (ROOT / "app" / "data" / "engine.js").read_text(encoding="utf-8")
SINCE = json.loads(_ej[_ej.index("=") + 1:].rstrip().rstrip(";"))["since_engine"]
SC = SINCE["counts"]
SN_HN, SN_PA, SN_IP, SN_BO, SN_OT, SN_ALL = (SC["heilbronn_cablecar"], SC["paris_c1"], SC["ipai"], SC["bonn_cablecar"],
                                            SC["other_urban_cablecar"], SINCE["total"])

# 4 · One website, three questions ──────────────────────────────────────────
# v10 (Harshil: "the pictures u used are of no use as i am gonna show the ui"): no screenshot. Each tab: its question,
# what it shows, one real number. The fourth tab (Human review) in one quiet line.
# v11 (Harshil, 15 Nov: "keep one interface, three experience ... the visual is quite boring, the earlier deck had better
# boxes to make it lively"): v3's three cards come back in today's palette; Today is the filled orange card.
add(f'''<h2>One interface.<br><span class="lt">Three experiences.</span></h2>
<div class="cards4">
  <div class="c"><div class="k">01 · History</div><div class="q">What happened?</div><p>Two years of the city's posts, read for or against.</p><div class="n"><b>{S_N}</b><span>labelled Heilbronn posts</span></div></div>
  <div class="c"><div class="k">02 · So far</div><div class="q">What is happening?</div><p>Everything found since 27 Oct, with its real date.</p><div class="n"><b>{SN_ALL}</b><span>new posts, read and confirmed</span></div></div>
  <div class="c on"><div class="k">03 · Today</div><div class="q">What is new today?</div><p>One click checks every source again, with a receipt.</p><div class="n"><b>{CLICK_MIN} min</b><span>for one click</span></div></div>
</div>
<div class="quiet4"><i></i><span><b>Human review</b> needed: new or unclear arguments go to a person.</span></div>''',
f"CityPulse is one interface with three experiences, and each answers one question. History: what happened in two years of the city's posts, read for or against: {S_N} labelled Heilbronn posts. So far: what was published after that data ends on 27 October, from the sources we can check, read and confirmed by our engine: {SN_ALL} new posts. Older finds and undated ones are shown apart. Today: one click checks the sources again and writes a receipt of every step, about {CLICK_MIN} minutes. And a fourth tab, Human review: new or unclear arguments go to a person (slide 7). I will show all of it live in a moment.",
f"Tab names and questions are the website's own (app/: History, So far, Today, Human review). History {S_N}: pipeline/data/export/data.json, stance heilbronn_cablecar voice all, n. So far {SN_ALL}: app/data/engine.js since_engine, engine-confirmed posts published from 27 Oct (Heilbronn {SN_HN}, Paris {SN_PA}, IPAI {SN_IP}, Bonn {SN_BO}, other cable car cities {SN_OT}). The collector's own report before reading (live/out/update/latest.json, update {when}) counts {len(NEW4)} dated items for the four core projects by search match, a different base. Today: the last update that really scanned took {(_scan[-1] if _scan else 237):.0f} s end to end (knowledge/DEMO_RUNBOOK_LIVE.md: the --quick click measured 237 s).")

# 5 · Result of history ──────────────────────────────────────────────────────
# Same numbers and words as the website's History tab (Harshil: the deck uses the UI's words).
dots = []
for k in range(S_N):
    c, r = divmod(k, 5)
    cls = "f" if k < S_FOR else ("a" if k < S_FOR + S_AG else "")
    dots.append(f'<circle cx="{c * 29.1 + 10.5:.1f}" cy="{r * 29.1 + 10.5:.1f}" r="10.5" class="{cls}"/>')
add(f'''<h2>{S_FOR + S_AG} of {S_N} Heilbronn posts take a side.<br><span class="lt">{S_FOR} for, {S_AG} against. The rest is mostly neutral.</span></h2>
<svg class="dots5" width="1136" height="138" viewBox="0 0 1136 138">{"".join(dots)}</svg>
<div class="key5"><span><i class="f"></i>For</span><span><i class="a"></i>Against</span></div>
<div class="ba5">
  <div class="side"><div class="lab">Before CityPulse</div><h3>Tone</h3><p>Does it sound positive or negative?</p></div><!-- same length as the right box -->
  <div class="mid"><b>{TONE_PCT}</b><p>of {TONE['n']:,} posts, all four projects: tone matched the position</p></div>
  <div class="side on"><div class="lab">With CityPulse</div><h3>Position</h3><p>For, against, or just reporting?</p></div>
</div>''',
# v11 (Harshil, 15 Nov): "Read by AI" pill removed; "4 of 5 attention peaks" dropped from the slide (kept in notes);
# the 39% becomes a before/after strip. His spoken words are the note below.
"Here's something interesting we found. The original tool measures whether an article sounds positive or negative. But that doesn't necessarily tell us whether someone supports the cable car. In our historical comparison, if you read the tool's tone score as a position, it matched the position our AI read, across all four projects, in only about " + TONE_PCT + " of records. That's why CityPulse goes beyond sentiment and tries to understand the position behind the words.\n\n"
f"Two years of posts, read by our engine. Most Heilbronn coverage only reports. Of {S_N} labelled Heilbronn posts, {S_FOR + S_AG} take a side: {S_FOR} for, {S_AG} against. Every dot is one post. That is posts, not people, and {S_FOR + S_AG} is too few to say the city is split. Two more things the website shows. Attention rises around city decisions: {PLACEBO['peaks_linked']} of {PLACEBO['n_peaks']} weeks with unusual attention fall on a documented city event, like the council vote or the 157 million euro cost. That is a match in time, not proof of a cause; the event list was partly built by reading the data, so the random-date comparison flatters it. And the tone score of the city's monitoring tool is not opinion: it matched the position in only {TONE_PCT} of posts.\n\nIf there is time or a question, three more results from the engine: (1) We froze the system on 1 July 2026 and replayed what came next, in order. Of 75 later claims, 28 matched an argument it already knew, and 27 it would not decide alone, so they go to a person. A replay of the past, not a live detection. (2) It flagged a concern that three different authors raised, all under one YouTube video: money for the cable car while the Löwenstein hospital faces closure, first seen on 26 July 2026 (slide 7). It needs review; it is not a confirmed new issue. (3) The small model that spots the same argument in other words scores 0.65, against 0.37 for plain text similarity, measured against an AI reference, not against people.",
f"Slide numbers = the website's History tab (same words as the UI): pipeline/data/export/data.json, meta.release final, stance heilbronn_cablecar voice all: n {S_N} labelled Heilbronn posts incl. copies; {S_FOR} support, {S_AG} oppose, {S_REP} only report, {S_UNC} unclear (hence 'the rest mostly report'). Peaks: same file, placebo heilbronn_cablecar: {PLACEBO['peaks_linked']} of {PLACEBO['n_peaks']} significant weekly peaks link to one of {PLACEBO['n_events']} documented events; random dates link about {PLACEBO['placebo_mean_linked']:.1f} on average (placebo test). A date match does not prove a cause. Tone: same file, reliability vendor_vs_stance.match = {TONE['value']:.3f} (interval {TONE['ci'][0]:.2f} to {TONE['ci'][1]:.2f}), n {TONE['n']:,} labelled posts across all four projects, not only Heilbronn; website words 'Tone matched position in only {TONE_PCT} of posts'. The pilot figure 46 of 127 (36%) is the older, smaller check. The engine's own overview counts differently: only unique posts where Heilbronn is the main topic, 146, of which 16 support, 17 oppose, 109 only report, 4 unclear, on the city data alone (/api/overview, offline_pack/key_results.json); with collector items merged in, the engine now shows a few more (engine.js overview_hn); the deck follows the website. Replay: /api/replay?project=heilbronn_cablecar&cutoff=2026-07-01: 75 claims, 1 Jul to 26 Oct 2026; 28 matched a known argument, 20 started or joined new groups, 27 sent to review. Matcher: engine/app_data/matcher.json, pair F1 0.65 (interval 0.57 to 0.71) against 0.37 for plain cosine similarity, 3,239 test pairs Jul to Oct 2026, reference labels by Claude Opus. Ledger: knowledge/EVIDENCE_LEDGER.md findings 1, 3, 4, 5, 6, 9. Limit: every label and score here is an AI reading or agreement with an AI reference, not checked by people; never call 0.65 accuracy, and never say a share of Heilbronn is against (posts, not people; small n).")

# 6 · Since the city's data ended (v5 layout, restored by Harshil) ──────────────────────────────────────────
# v11 (Harshil, 15 Nov: "quiet in heilbronn does not make sense ... results have to come after the end to end pipeline"):
# numbers are now the ENGINE's: posts published from 27 Oct on that the engine read and kept as relevant
# (app/data/engine.js since_engine, from /api/posts?from=2026-10-27), after the 15 Nov date fix (three LinkedIn pages
# had been dated by the search crawl, not by their activity). Older finds and undated items are never in these counts.
add(f'''<h2>Since 27 Oct,<br><span class="lt">we <em>kept listening.</em></span></h2>
<div class="s6">
<div class="big3 two">{SN_ALL}</div>
<div class="t6 two"><h4>new posts, read and confirmed since the city's data ended.</h4><p>Older finds and undated items are never counted as new.</p></div>
<div class="others five">
  <div class="me"><span>Heilbronn cable car</span><b>{SN_HN}</b></div>
  <div><span>Paris Câble C1</span><b>{SN_PA}</b></div>
  <div><span>IPAI Heilbronn</span><b>{SN_IP}</b></div>
  <div><span>Bonn cable car</span><b>{SN_BO}</b></div>
  <div><span>Other cable car cities</span><b>{SN_OT}</b></div>
</div></div>''',
f"The city's data stops on 27 October. Our system kept listening. Since then it found and read {SN_ALL} new posts and confirmed them as relevant. Heilbronn itself had {SN_HN} new cable car posts in the sources we checked, which is a result too. Paris had {SN_PA}, among them reports on a service interruption from 6 to 11 November, and Bonn had {SN_BO}, about 4 different items (one article also appears on two archive pages), including a motion to drop its cable car. Anything published earlier and only found now, or without a clear date, is shown apart and never counted as new.",
f"app/data/engine.js since_engine (written by live/engine_bridge/snapshot.py from the engine API /api/posts?from=2026-10-27, per project), engine run fed by live/engine_bridge/feed_engine.py from live/out/raw_live.json; dated items only. 15 Nov fixes: three LinkedIn profile pages had the search crawl date (28 Oct, 28 Oct, 4 Nov) though their own text says 19 Aug, 6 Oct, 12 Oct (live/collector/dates.py fix_activity_dates); a news list page (Zukunftsnetzwerk ÖPNV) dated 3 Nov whose cable car teaser is 20.05.2025, and a static municipality page (Klimaschutz-Kommune) dated 8 Nov whose cable car sentence has no date (live/tools/fix_known_dates.py). None of them is counted as new. Paris: of its dated posts only a few are about the 6 to 11 Nov interruption; do not say all of them are. The collector's own report (live/out/update/latest.json, the website's So far tab) counts what the search found per project before reading: different base.")

# 7 · From conversations to clarity ─────────────────────────────────────────
# v10 (Harshil: "remove that evidence boring picture"): no screenshot. The four steps, one line each, and one real
# example traced in one line.
# v11 (Harshil, 15 Nov, in his words): "like i have 5 person team": the collector, the reader, the investigator, the
# analyst, the presenter, each with what it does and, below, the method. Wording kept true to the code: the collector
# keeps link, real date and the text it may keep (not always the whole article); Ask is RAG-style (results are
# computed from the data first, the model only reads the question), not a model writing answers.
# v11b (Harshil: "too much information ... a bit minimal, not too much minimal ... remove that one click line ... keep
# these 5 boxes and like 5-person picture ... from conversation to clarity, I want some better spice or hook"):
# one short line + one method tag per box, a drawn person per role, headline "Meet the team. One of them we trained ourselves."
def person(role, on=False):
    """Faceless editorial line portraits, one per role (Harshil, 15 Nov: the icon people "look very AI generated ... I want
    more humanized ... premium, decent, elegant"). Fine ink lines, solid hair, a soft round backdrop, one prop each.
    Drawn here as SVG, no stock photo and no AI image."""
    ink, bg, acc, paper = ("#fff", "rgba(255,255,255,.18)", "#fff", "rgba(255,255,255,.0)") if on else (INK, "#fbe7da", ACC, "#fff")
    sw = 'fill="none" stroke="{i}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"'.format(i=ink)
    body = (f'<path d="M24,100 C25,82 35,73 50,73 C65,73 75,82 76,100" {sw}/>'
            f'<path d="M45,63 L45,72 M55,63 L55,72" {sw}/>'
            f'<ellipse cx="50" cy="49" rx="12.5" ry="15" {sw}/>')
    hair = {
        # short, side part
        "collect": f'<path d="M37.5,47 C36,33 45,29 52,30 C60,30 65,36 62.8,47 C61,40 55,37 47,39 C42,40 39,43 37.5,47 Z" fill="{ink}"/>',
        # long hair to the shoulders
        "read": f'<path d="M37.6,50 C35,32 45,29 51,29.5 C59,30 66,35 63.2,50 L64,66 C61,64 61.5,56 61,50 C58,42 50,40 43,42 C40,44 39.5,50 39.8,56 C39,62 37,65 35,66 C37.5,61 37.8,55 37.6,50 Z" fill="{ink}"/>',
        # curly
        "investigate": "".join(f'<circle cx="{x}" cy="{y}" r="4.6" fill="{ink}"/>' for x, y in
                               ((39, 42), (42.5, 36), (48, 33), (54, 33), (59, 36), (62, 42), (45, 37.5), (56, 38))),
        # bun
        "analyse": f'<path d="M37.6,47 C36.5,34 45,30.5 50,30.5 C56,30.5 64,34 62.5,47 C60,40 54,38 50,38 C46,38 40,40 37.6,47 Z" fill="{ink}"/><circle cx="50" cy="26.5" r="5.6" fill="{ink}"/>',
        # short, swept
        "present": f'<path d="M37.6,46 C37,33 46,30 53,30.5 C59,31 64,35 62.6,45 C59,39 52,36.5 45,38.5 C41.5,40 39,42.5 37.6,46 Z" fill="{ink}"/>'}
    prop = {
        "collect": f'<g transform="translate(64,79) rotate(-8)"><rect x="0" y="0" width="17" height="13" rx="1.5" fill="{paper}" {sw}/><path d="M3,4 h11 M3,7.5 h8" {sw}/></g>',
        "read": f'<circle cx="45" cy="50" r="3.6" {sw}/><circle cx="55" cy="50" r="3.6" {sw}/><path d="M48.6,50 h2.8" {sw}/>'
                f'<g transform="translate(37,80)"><rect x="0" y="0" width="26" height="15" rx="1.5" fill="{paper}" {sw}/><path d="M4,4.5 h18 M4,8.5 h14" {sw}/></g>',
        "investigate": f'<circle cx="69" cy="57" r="7.5" fill="{paper}" {sw}/><path d="M74.5,62.5 L81,70" stroke="{acc}" stroke-width="3" stroke-linecap="round"/>',
        "analyse": f'<path d="M72,40 v-7 M77,40 v-12 M82,40 v-5" stroke="{acc}" stroke-width="3" stroke-linecap="round"/><path d="M69,42.5 h16" {sw}/>',
        "present": f'<path d="M74,28 h14 q3,0 3,3 v6 q0,3 -3,3 h-8 l-4,4 v-4 h-2 q-3,0 -3,-3 v-6 q0,-3 3,-3 z" fill="{paper}" {sw}/>'}
    return f'''<svg class="av" width="92" height="92" viewBox="0 0 100 100"><defs><clipPath id="cp-{role}"><circle cx="50" cy="50" r="46"/></clipPath></defs>
  <circle cx="50" cy="50" r="46" fill="{bg}"/>
  <g clip-path="url(#cp-{role})">{body}{hair[role]}</g>{prop[role]}
</svg>'''
TEAM = [("The collector", "collect", "Brings in posts from the sources it checks, with their real date.", "Exa · Tavily · RSS · YouTube"),
        ("The reader", "read", "About the cable car? For or against? On what?", "Claude Haiku · claim extraction"),
        ("The investigator", "investigate", "Said before, repeated, or new?", "Our fine-tuned matcher"),
        ("The analyst", "analyse", "Counts, compares, checks the evidence.", "Statistics · tests"),
        ("The presenter", "present", "Answers staff questions in plain words.", "Ask CityPulse · checked answers")]
rows = "".join(f'<div class="c{" on" if r == "The investigator" else ""}">{person(p, r == "The investigator")}<h3>{r}</h3><p>{d}</p><div class="m">{m}</div></div>'
               for r, p, d, m in TEAM)
# v11c (Harshil: remove "one of them we trained ourselves", keep "Meet the team" with something better)
add(f'''<h2>Meet the team.<br><span class="lt">Five specialists behind <em>every discussion.</em></span></h2>
<div class="team7">{rows}</div>''',
f"Think of CityPulse as a team of five. The collector searches news, city pages, council papers and video comments, and brings every item in with its link and its real date. The reader reads it and asks: is this about the cable car, does someone take a side, and what is it about? That is classification and claim extraction, done by a language model, Claude Haiku. The investigator is our own trained model: it compares each argument with everything said before and tells us whether it was said before, is being repeated, or is new, so we see what is emerging. The analyst counts, compares time periods, checks the evidence, and writes a result anyone can understand. And the presenter shows it to city staff: they can simply ask, and it finds the right results and explains them in plain language. One click runs the whole team again, in about {CLICK_MIN} minutes.\n\nOne real example, if asked: money for the cable car while the Löwenstein hospital faces closure. Three different authors raised it, all under one YouTube video, it was flagged on 26 July 2026, and it waits in Human review for a person. This comes from a replay of the past, not a live detection.\n\nIf asked for one real record end to end: the city's cable car tender. Found on 14 November, but its own page says 20 September, so it counts as older, found late, not as new. Read as neutral, a notice, not a vote. It opens as evidence on the website. And a check against the city's own tool: of 19 Heilbronn articles it found, ours found 11. Let me show you.",
"Concern: /api/replay?project=heilbronn_cablecar&cutoff=2026-07-01 concerns[]: 3 claims, 3 voices (all YouTube items on the same video), flagged 26 Jul 2026, needs review; the rule is two or more independent voices, this one had three. A voice is an author or a site (hashed), not a resident. On the website: the Human review tab, the concern 'Money for cable car while Löwenstein hospital faces closure'. Order in the code: collect, store and check, classify, evaluate, count, display. Tender: live/out/update/latest.json and app/data/live.js (Exa, discovered 14 Nov 16:41 UTC; date 20 Sep from its item card; neutral_informative, voice company_vendor, 3 of 3 runs agree; provisional bridge reading, knowledge/LIVE_PART_EXPLAINED.md). 11 of 19: backtest vs the city's tool on the same days, not tuned on misses, overlap not full recall (knowledge/STADT_LIVE_EXPERIMENTS.md). Names hidden = tested best-effort masking. Understand = the engine in engine: claims.parquet (3,500 claims pulled out, Heilbronn 326), families.parquet (137 argument families), app_data/matcher.json (citypulse-matcher-v2, a fine-tuned mDeBERTa model on CPU). Ledger: knowledge/EVIDENCE_LEDGER.md. Limit: the matcher agrees with an AI reference (Claude Opus), not with people; spotting contradicting claims is switched off because it was not reliable. New collector items do run through the whole engine on this laptop (Update now, step 5; verified 15 Nov). Ask CityPulse: app/ask.js, frozen suite app/tests/ask_suite.js.")

# 8 · Your turn: the survey, the end of the pitch (Harshil, 15 Nov: "slide 8 is the end") ───────────────────────────────────────────────────────────────
# v10: the real QR (assets/survey_qr.png) in a hairline frame with a short label under it; nobody types the URL.
# Without the PNG the placeholder stays.
if QR_PNG.exists():
    qr = f'<div class="qrimg"><img src="assets/{QR_PNG.name}" alt="QR code to the survey"></div><div class="qrlab">{SURVEY_LABEL}</div>'
else:
    qr = '<div class="qrbox empty">QR code to the survey<br>(appears when the form link is set)</div>'
add(f'''<div class="ask">
  <div class="kick">YOUR TURN</div>
  <h1>Want to contribute to the cable car project?</h1>
  <div class="how">Scan. <b>Four questions, one minute.</b><br>No name, no e-mail.</div>
</div>
<div class="reuse"><i></i>A reproducible, reusable intelligence.</div>
{qr}''',
"Want to contribute to the cable car project? Scan this: four questions, one minute, and we don't ask your name or e-mail. Your answers stay their own layer, never mixed with the online posts. That is CityPulse: a reproducible, reusable intelligence. The same rules on every run, new voices like yours, any new project. Thank you.\n\nThe four questions, if asked: (1) What do you think of Heilbronn's planned cable car? For it / Against it / Mixed / Not sure yet. (2) What matters most to you about it? Pick any: Cost and public money / Traffic and getting around / Link to the IPAI and Bildungscampus / Environment and the look of the city / Something else. (3) Would you use it? Yes, often / Sometimes / No / I don't live or work near Heilbronn. (4) One thing the city should know? Optional, please no names.\n\nAnswers from the room are their own layer, never mixed into the post counts. The people in this room are not a sample of Heilbronn, so never present their answers as what Heilbronn thinks.",
f"Survey: Google Form ({SURVEY_URL}), QR in deck/assets/survey_qr.png. Wording and privacy limits: knowledge/PITCH_IDEAS.md. Plan for before, during and after the pitch, and the report script: survey/README.md. Only claim what the form really stores.")

# 9 · Optional: the live link (Harshil, 15 Nov: "optional slide should be where the live working link should be") ─────────────────────────────────
add(f'''<div class="demo">
  <div class="kick">LIVE DEMO · OPTIONAL</div>
  <h1>Let's see how close Heilbronn is to its <em>cable car.</em></h1>
  <a class="go" href="{DEMO_URL}">Open CityPulse <span>&#8594;</span></a>
  <div class="url">{DEMO_URL}</div>
</div>''',
"Click Open CityPulse (the website opens in the browser). Show History, then So far, then Today. Then Ask CityPulse, in order: 'What changed after 27 October?', then 'and Bonn?', then 'What sources support that?'. Call it guided questions over the checked data, not an open chatbot: a small model only reads the question into a query; every number is counted from the data and checked before it is shown. Slide 8 was the end; this slide is only for opening the live site.",
"The link is the hosted copy on Vercel (deployed by the website chat from app/). It is a static copy: Ask CityPulse uses its keyword reader there and Update now does not run; the full live system (model reader, Update now, engine) runs on the laptop: START_CITYPULSE.cmd, then http://127.0.0.1:8790/ . Guided demo: add ?demo=long or ?demo=short (app/DEMO.md).")

# 10 · Q&A backup: the technical pipeline ─────────────────────────────────────
# Harshil, 15 Nov: an optional slide for questions, "the tag architecture, the pipeline", in his order and words:
# in -> clean and select -> understand the text -> find similar arguments -> decide whether arguments match ->
# decide potentially emerging concerns -> calculate and verify -> dashboard. Each step: what it does, and a tag with
# the real tool underneath. Kept true to the code (engine, live/, pipeline/, app/).
PIPE = [("Information enters", "Historical city data, plus our live collector.", "39,361 city posts · live since 27 Oct"),
        ("Clean and select", "Checks relevance, removes duplicates, knows which project it is about.", "Python rules · Claude Haiku"),
        ("Understand the text", "Reads the stance, extracts the claims, identifies the argument.", "Claude Haiku · one codebook"),
        ("Find similar arguments", "Turns raw text into numerical vectors, so meaning can be compared.", "bge-m3 embedding model"),
        ("Decide whether arguments match", "Compares claim pairs: same argument or not?", "Fine-tuned mDeBERTa model"),
        ("Decide emerging concerns", "New, familiar or uncertain. Flagged when 2+ voices raise it.", "Novelty cut-offs · voice count"),
        ("Calculate and verify", "Counts trends, runs tests, keeps the original evidence and the method.", "Statistics · evidence links"),
        ("Dashboard", "Historical replay, Ask CityPulse and live updates, every number opens its posts.", "History · So far · Today · Human review · Ask")]
cells = "".join(f'<div class="p{" on" if i == 5 else ""}"><div class="k">{i:02d}</div><h3>{t}</h3><p>{d}</p><div class="tag">{g}</div></div>'
                for i, (t, d, g) in enumerate(PIPE, 1))
add(f'''<div class="qa10">Q&amp;A backup</div>
<h2>Under the hood.<br><span class="lt">From a raw post to a <em>finding</em>.</span></h2>
<div class="pipe10">{cells}</div>''',
"Backup slide, open only if someone asks how it works technically. Walk it left to right, top row then bottom row. Information enters from two places: the city's two years of data and our live collector. First we clean and select: Python rules and Claude Haiku check relevance, remove duplicates and decide which project a post is about. Then Haiku understands the text: the stance, the claims, the argument. To find similar arguments, an embedding model called bge-m3 turns the text into numbers that capture its meaning. Then our own fine-tuned model compares claim pairs and decides whether two claims make the same argument. From that we decide whether a concern is new, familiar or uncertain, and we flag it when two or more independent voices raise it. Then we calculate and verify: counts, trends, tests, always with the original evidence and the method. And it all ends on the dashboard: the historical replay, Ask CityPulse and the live updates.",
"Clean and select: pipeline/01_build_base.py, 02_candidates.py (keyword rules), dedupe by text, Haiku project label (engine/citypulse/batch/steps.py). Understand: one Haiku call per 20 posts with codebook_v1 returns project, stance and arguments. Embeddings: bge-m3 through Ollama on the laptop's graphics card (same vectors as the engine's stored ones, cosine 1.0). Matcher: citypulse-matcher-v2, mDeBERTa base fine-tuned on claim pairs, F1 0.65 vs 0.37 for plain similarity against an AI reference (Claude Opus), not human-checked; contradiction spotting is switched off. Emerging: familiar above 0.80, new below 0.29, in between = uncertain, needs review (app_data/matcher.json). Statistics: Wilson intervals on shares, peak weeks against a placebo test, exact tests in Ask. Dashboard: app/ (History, So far, Today, Human review, Ask CityPulse).", cls="backup")

# ── write ─────────────────────────────────────────────────────────────────────
assert len(slides) <= TOTAL + 1, "Harshil: 9 slides plus one Q&A backup slide"
head = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CityPulse pitch deck</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=block" rel="stylesheet">
<link rel="stylesheet" href="deck.css"></head><body>'''
pathlib.Path(ARGS.out).write_text(head + "\n".join(slides) + "</body></html>", encoding="utf-8")
md = [f"# CityPulse pitch: speaker notes\n\nGenerated by `deck/gen.py`. Live numbers from the update of {when}. Say it in your own words; the source under each slide is for questions.\n"]
for i, n in enumerate(notes, 1):
    md.append(f"## Slide {i}\n{n}\n")
if ARGS.history == "auto":  # a pilot test render never touches the real notes
    (HERE / "SPEAKER_NOTES.md").write_text("\n".join(md), encoding="utf-8")
print(f"{len(slides)} slides; history {'final' if FINAL else ('PILOT TEST' if SHOW else 'awaiting')}; "
      f"{len(NEW4)} new in {DAYS} days; survey QR {'image' if QR_PNG.exists() else 'placeholder'}")
