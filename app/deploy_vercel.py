"""Publish the CityPulse website as a hosted copy on Vercel (the same link every time).

Run:  python -I -X utf8 app/deploy_vercel.py
First time only: `npx vercel login` (Harshil signs in to his own Vercel account in the browser).

What goes up: only the static page (index.html, the scripts and styles, app/data/*.js, the photo).
What stays on the laptop: app/serve.py ("Run it now"), app/ask_model.py (the AI reading of Ask questions),
the engine and its analyst console, every key in live/.env. On the hosted copy the page says so itself:
"Run it now" shows "Runs on the presentation laptop", Replay works, and Ask answers with its keyword reader.

The copy is rebuilt from app/ on every run, so the link always shows the current website after a redeploy.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
OUT = APP.parent / "_run" / "citypulse"          # _run/ is gitignored; the folder name becomes the Vercel project name
FILES = ["index.html", "style.css", "app.js", "adapter.js", "ask.js", "ask.css", "demo.js", "scenephoto.js"]
DIRS = ["data", "photo"]

VERCEL_JSON = {
    "cleanUrls": True,
    # always fetch the newest page and data after a redeploy (no stale copy in the browser)
    "headers": [{"source": "/(.*)", "headers": [{"key": "Cache-Control", "value": "no-cache, must-revalidate"}]}],
}


def build():
    if OUT.exists():
        for p in OUT.iterdir():
            if p.name == ".vercel":                  # keeps the link to the same Vercel project
                continue
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    OUT.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        shutil.copy2(APP / f, OUT / f)
    for d in DIRS:
        shutil.copytree(APP / d, OUT / d, ignore=shutil.ignore_patterns("*.py", "__pycache__"))
    (OUT / "vercel.json").write_text(json.dumps(VERCEL_JSON, indent=2), encoding="utf-8")
    n = sum(1 for _ in OUT.rglob("*") if _.is_file())
    print(f"built {OUT} ({n} files)")


def deploy():
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        sys.exit("npx not found (Node.js is needed)")
    cmd = [npx, "--yes", "vercel@latest", "deploy", "--prod", "--yes"]
    print("deploying:", " ".join(cmd[1:]), flush=True)
    r = subprocess.run(cmd, cwd=str(OUT), text=True, encoding="utf-8", errors="replace")
    sys.exit(r.returncode)


if __name__ == "__main__":
    build()
    if "--build-only" not in sys.argv:
        deploy()
