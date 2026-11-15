"""Feed the collector's new items into the CityPulse argument engine (engine), end to end.

    python -I -X utf8 live/engine_bridge/feed_engine.py            # export new items, upload, wait, print the result
    python -I -X utf8 live/engine_bridge/feed_engine.py --dry-run  # only write the export file and print counts
    python -I -X utf8 live/engine_bridge/feed_engine.py --all      # resend everything (ignore the sent ledger)

One real item: the collector writes live/out/raw_live.json (482 records). This script keeps the ones with a real
publication date (date_known) that the radar marked strong or weak, normalises the date, keeps only the fields the
engine's batch format reads, drops records already sent in an earlier run (ledger live/engine_bridge/sent.json),
and writes live/out/batch_for_engine.json. It then POSTs that file to the engine API (http://127.0.0.1:8000/api/batches),
which labels each item (project, stance, arguments) with Haiku, embeds the claims with bge-m3, scores them against the
3,500 known claims with the fine-tuned matcher, sorts them into familiar / new / emerging, and reloads its store.
The result is written to live/out/engine_feed_receipt.json, and the ids are added to the ledger only when the run finished.

Why drop undated items: the engine's novelty logic is time-based. An item whose publication date is unknown would get
the day the collector found it, which is a guessed date. We never guess dates (decision 15 Nov).
"""
import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "live" / "out" / "raw_live.json"
OUT = ROOT / "live" / "out" / "batch_for_engine.json"
RECEIPT = ROOT / "live" / "out" / "engine_feed_receipt.json"
LEDGER = Path(__file__).resolve().parent / "sent.json"
API = "http://127.0.0.1:8000"
FIELDS = ["mention_id", "title", "content", "url", "published_at", "media_type_name", "source_name", "language_code", "authors"]


def norm_date(s):
    d = dt.datetime.fromisoformat(s.replace("+0000", "+00:00").replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build(resend_all=False):
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    sent = set() if resend_all or not LEDGER.exists() else set(json.loads(LEDGER.read_text(encoding="utf-8")))
    c = dict(total=len(raw), undated=0, radar_none=0, already_sent=0, no_text=0, bad_date=0, kept=0)
    rows = []
    for r in raw:
        if not r.get("date_known"):
            c["undated"] += 1
            continue
        if r.get("radar_match") not in ("strong", "weak"):
            c["radar_none"] += 1
            continue
        if r["mention_id"] in sent:
            c["already_sent"] += 1
            continue
        if not (r.get("content") or r.get("title") or "").strip():
            c["no_text"] += 1
            continue
        try:
            pub = norm_date(r["published_at"])
        except Exception:
            c["bad_date"] += 1
            continue
        o = {k: r.get(k) for k in FIELDS}
        o["published_at"] = pub
        o["content"] = (r.get("content") or r.get("title") or "").strip()
        o["authors"] = r.get("authors") or []          # collector stores hashes only, never names
        rows.append(o)
    c["kept"] = len(rows)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows, c


def api_up():
    try:
        with urllib.request.urlopen(API + "/api/health", timeout=60) as r:
            return json.load(r)
    except Exception:
        return None


def upload(path):
    boundary = uuid.uuid4().hex
    data = path.read_bytes()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: application/json\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(API + "/api/batches", data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "detail": json.loads(e.read() or b"{}")}


def wait(run_id, timeout_s=1800):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        with urllib.request.urlopen(f"{API}/api/batches/{run_id}", timeout=60) as r:
            run = json.load(r)
        st = run.get("status")
        step = run.get("current_step") or run.get("step")
        if (st, step) != last:
            print(f"  engine: {st} {step or ''}".rstrip(), flush=True)
            last = (st, step)
        if st not in ("queued", "running"):
            return run
        time.sleep(2)
    return {"status": "timeout", "run_id": run_id}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true", help="ignore the ledger and resend every dated item")
    a = ap.parse_args()

    rows, c = build(a.all)
    print(f"collector export: {c['total']} records; kept {c['kept']} new dated items "
          f"(dropped: {c['undated']} date unknown, {c['radar_none']} off-topic by radar, {c['already_sent']} already in the engine, "
          f"{c['no_text']} empty, {c['bad_date']} unreadable date)")
    receipt = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "counts": c, "status": None}
    if a.dry_run:
        print(f"dry run: wrote {OUT.relative_to(ROOT)}")
        return 0
    if not rows:
        receipt["status"] = "nothing_new"
        RECEIPT.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
        print("engine: nothing new to send (all dated items are already in the engine)")
        return 0
    h = api_up()
    if not h:
        receipt["status"] = "engine_offline"
        RECEIPT.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
        print("engine: API on port 8000 is not running. Start it with START_CITYPULSE.cmd, then run this again.")
        return 2
    print(f"engine: matcher {h['matcher'].get('mode')}, embedder {'on' if h['embedder'].get('available') else 'OFF'}, "
          f"llm {h['llm'].get('backend')} {'on' if h['llm'].get('available') else 'OFF'}")
    up = upload(OUT)
    if "http_error" in up:
        receipt.update(status="upload_refused", detail=up)
        RECEIPT.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
        print(f"engine refused the upload: {up}")
        return 2
    run_id = up.get("run_id") or (up.get("run") or {}).get("run_id")
    print(f"engine: run {run_id} queued")
    run = wait(run_id)
    receipt.update(status=run.get("status"), run_id=run_id, run=run)
    RECEIPT.write_text(json.dumps(receipt, indent=1, ensure_ascii=False), encoding="utf-8")
    if run.get("status") in ("done", "done_with_errors"):
        sent = set() if a.all or not LEDGER.exists() else set(json.loads(LEDGER.read_text(encoding="utf-8")))
        LEDGER.write_text(json.dumps(sorted(sent | {r["mention_id"] for r in rows}), indent=0), encoding="utf-8")
    s = run.get("summary") or {}
    print(f"engine: {run.get('status')}. " + (", ".join(f"{k} {v}" for k, v in s.items() if not isinstance(v, (dict, list))) if s else ""))
    for e in (run.get("errors") or [])[:5]:
        print("  note:", e if isinstance(e, str) else e.get("message"))
    return 0 if run.get("status") in ("done", "done_with_errors") else 1


if __name__ == "__main__":
    sys.exit(main())
