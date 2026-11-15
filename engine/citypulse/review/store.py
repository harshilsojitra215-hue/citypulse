"""Append-only annotation store.

One file per queue: review/annotations/<queue>.jsonl. Every action is one JSON line
{ts, queue, item_id, labeller, label, note, rev}. Nothing is ever rewritten or deleted:
a correction is a new line, and the newest line per (labeller, item) is the current label.
A line with "label": null retracts that labeller's label. The files hold no post text.
"""
try:
    import fcntl          # macOS / Linux: lock the file across processes
except ImportError:       # Windows (Harshil's laptop, 15 Nov): one API process, the thread lock below is enough
    fcntl = None
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config

LABELLER_RE = re.compile(r"^[a-z0-9_.-]{1,40}$")
_lock = threading.Lock()


class LabellerError(ValueError):
    pass


def normalise_labeller(name) -> str:
    if not isinstance(name, str) or not LABELLER_RE.match(name.strip().lower()):
        raise LabellerError("labeller must be 1-40 characters: letters, digits, '_', '.', '-' (example: harshil)")
    return name.strip().lower()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def path(queue: str) -> Path:
    return config.annotations_dir() / f"{queue}.jsonl"


def read(queue: str) -> list:
    """Every stored line of a queue, oldest first. Broken lines are skipped (they are never produced by append)."""
    f = path(queue)
    if not f.exists():
        return []
    rows = []
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(r, dict) and "item_id" in r and "labeller" in r:
                r["item_id"] = str(r["item_id"])
                rows.append(r)
    return rows


def append(queue: str, item_id: str, labeller: str, label, note: str = "") -> dict:
    """Add one line. `label` is an already validated object, or None to retract. Returns the stored record."""
    f = path(queue)
    f.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(f, "a+", encoding="utf-8") as fh:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.seek(0)
            rev = 1
            tail = ""
            for line in fh:
                tail = line
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(r.get("item_id")) == item_id and r.get("labeller") == labeller:
                    rev += 1
            rec = {"ts": now(), "queue": queue, "item_id": item_id, "labeller": labeller, "label": label,
                   "note": note or "", "rev": rev}
            fh.seek(0, os.SEEK_END)
            if tail and not tail.endswith("\n"):
                fh.write("\n")
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        finally:
            if fcntl:
                fcntl.flock(fh, fcntl.LOCK_UN)
    return rec


def current(queue: str, rows=None) -> dict:
    """{(labeller, item_id): newest record}. Retracted labels (label null) are left out."""
    latest = {}
    for r in (read(queue) if rows is None else rows):
        latest[(r["labeller"], r["item_id"])] = r
    return {k: r for k, r in latest.items() if r.get("label") is not None}


def by_labeller(queue: str, labeller: str, rows=None) -> dict:
    """{item_id: newest record} of one labeller."""
    return {i: r for (l, i), r in current(queue, rows).items() if l == labeller}


def history(queue: str, labeller: str, item_id: str, rows=None) -> list:
    return [r for r in (read(queue) if rows is None else rows) if r["labeller"] == labeller and r["item_id"] == item_id]


def labellers(queue: str, rows=None) -> list:
    return sorted({l for (l, _i) in current(queue, rows)})
