"""Freeze the argument engine's results into the website: app/data/engine.js (window.CP_ENGINE).

    python -I -X utf8 live/engine_bridge/snapshot.py

The website (app/, port 8790) is static and must work even if the engine API is down during the demo. So after the
engine has its data (and after every collector feed), this script asks the running engine API (port 8000) for the
results the website shows and writes them into one file. Every block keeps the engine's own labels ("cached",
"simulation", "provisional"). Nothing is computed here: it is a copy of the API's answers plus the time it was taken.
"""
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "app" / "data" / "engine.js"
API = "http://127.0.0.1:8000/api"
HN = "heilbronn_cablecar"
CUTOFF = "2026-07-01"           # the replay cut-off used in the demo (engine's documented example)


# Links that name a person's account are withheld from report data (decision 15 Nov 03:35); same rule as app/adapter.js
# HANDLE_URL and app/build_data.py. The page already hid them; this keeps the names out of the data file itself.
import re
ACCOUNT_URL = re.compile(r"/@[^/?#]+|(?:^|//)(?:www\.)?(?:x|twitter)\.com/(?!i/|search)[^/?#]+|tiktok\.com/@|"
                         r"facebook\.com/(?!\d+/|groups/\d+|watch|share|events)[A-Za-z][^/?#]*|"
                         r"instagram\.com/(?!p/|reel/|tv/)[^/?#]+/?$|linkedin\.com/in/|threads\.net/@|bsky\.app/profile/")


def scrub(o):
    """Replace every url that names an account with None and mark it withheld. Returns how many were withheld."""
    n = 0
    if isinstance(o, dict):
        for k, v in list(o.items()):
            if k in ("url", "source_url") and isinstance(v, str) and ACCOUNT_URL.search(v):
                o[k] = None
                o["link_withheld"] = True
                n += 1
            else:
                n += scrub(v)
    elif isinstance(o, list):
        for v in o:
            n += scrub(v)
    return n


def get(path, **q):
    q = {k: v for k, v in q.items() if v is not None}
    url = API + path + ("?" + urllib.parse.urlencode(q) if q else "")
    with urllib.request.urlopen(url, timeout=300) as r:
        return json.load(r)


def main():
    try:
        health = get("/health")
    except Exception as e:
        print(f"engine API not reachable on port 8000 ({e!r}); website keeps its previous snapshot")
        return 2
    snap = {"taken_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "health": health}
    snap["meta"] = get("/meta")
    snap["overview_hn"] = get("/overview", project=HN)
    snap["overview_all"] = get("/overview")
    snap["replay_hn"] = get("/replay", project=HN, cutoff=CUTOFF)
    snap["emerging_hn"] = get("/emerging", project=HN, cutoff=CUTOFF)
    snap["emerging_now"] = get("/emerging", project=HN)               # default cut-off: includes collector-fed runs
    snap["families_hn"] = get("/arguments/families", project=HN)
    snap["crosscity"] = get("/crosscity")
    snap["batches"] = get("/batches")
    # Since the city's data ends: posts PUBLISHED from 27 Oct on that the engine read and kept as relevant, per project.
    # This is the end of the pipeline (collector -> dates checked -> engine reading), the number the deck and site should say
    # (Harshil, 15 Nov: "results have to come after the end to end pipeline").
    since = {"from": "2026-10-27", "counts": {}, "heilbronn_posts": []}
    for proj in ("heilbronn_cablecar", "paris_c1", "ipai", "bonn_cablecar", "other_urban_cablecar"):
        since["counts"][proj] = get("/posts", project=proj, **{"from": "2026-10-27"}, limit=1)["total"]
    since["heilbronn_posts"] = get("/posts", project=HN, **{"from": "2026-10-27"}, limit=20)["items"]
    since["total"] = sum(since["counts"].values())
    snap["since_engine"] = since
    bdir = ROOT / "engine" / "app_data"
    for name in ("matcher.json", "eval_v2.json", "leakage_audit.json"):
        p = bdir / name
        if p.exists():
            snap[name.replace(".json", "")] = json.loads(p.read_text(encoding="utf-8"))
    withheld = scrub(snap)
    OUT.write_text("// written by live/engine_bridge/snapshot.py from the engine API; do not edit by hand\n"
                   "window.CP_ENGINE = " + json.dumps(snap, ensure_ascii=False) + ";\n", encoding="utf-8")
    kb = OUT.stat().st_size // 1024
    c = snap["replay_hn"].get("counts", {})
    print(f"engine snapshot -> {OUT.relative_to(ROOT)} ({kb} KB): replay from {CUTOFF}: {c.get('familiar')} matched, "
          f"{c.get('opens_new')} opened, {c.get('concerns_flagged')} flagged; runs {health.get('runs')}; "
          f"{withheld} account links withheld")
    return 0


if __name__ == "__main__":
    sys.exit(main())
