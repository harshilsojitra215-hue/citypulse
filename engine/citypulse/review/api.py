"""FastAPI router for human verification. Mounted by the main app:

    from citypulse.review import router
    app.include_router(router)

Endpoints and shapes: docs/REVIEW_API.md.
"""
import csv
import io
import json

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse, Response

from . import config, queues, store

router = APIRouter(prefix="/api/review", tags=["review"])
PROVISIONAL_NOTE = "All current accuracy numbers are agreement with AI labels, not human-validated."


def err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.response = err(status, code, message)


def _queue(name: str) -> queues.Queue:
    if name not in queues.SPECS:
        raise ApiError(404, "unknown_queue", f"unknown queue {name!r}; one of {queues.ORDER}")
    try:
        return queues.load(name)
    except queues.QueueUnavailable as e:
        raise ApiError(503, "queue_unavailable", str(e))


def _labeller(name, required=False):
    if name is None or name == "":
        if required:
            raise ApiError(400, "invalid_labeller", "labeller is required")
        return None
    try:
        return store.normalise_labeller(name)
    except store.LabellerError as e:
        raise ApiError(400, "invalid_labeller", str(e))


def _public(rec: dict) -> dict:
    return {k: rec.get(k) for k in ("queue", "item_id", "labeller", "label", "note", "ts", "rev")}


def _item(q: queues.Queue, item_id: str, mine: dict) -> dict:
    """Item as sent to the client. Hidden fields of a blind queue are only attached when `mine` (this labeller's
    current annotations) contains the item."""
    ann = mine.get(item_id) if mine else None
    return {"queue": q.spec.name, "item_id": item_id, "position": q.rows[item_id]["_position"],
            "data": q.data(item_id),
            "my_annotation": _public(ann) if ann else None,
            "revealed": q.hidden(item_id) if (q.spec.blind and ann) else None}


def _progress(q: queues.Queue, labeller: str, mine: dict) -> dict:
    done = [r for i, r in mine.items() if i in q]
    return {"labeller": labeller, "done": len(done), "total": len(q),
            "last_ts": max((r["ts"] for r in done), default=None)}


def _next_id(q: queues.Queue, mine: dict, after: str = None):
    """First item without a label from this labeller; starts looking after `after`, then wraps around."""
    ids = q.ids
    start = ids.index(after) + 1 if after in q else 0
    for i in ids[start:] + ids[:start]:
        if i not in mine:
            return i
    return None


def guarded(fn):
    """Turn ApiError into the contract's error shape."""
    from functools import wraps

    @wraps(fn)
    def inner(*a, **k):
        try:
            return fn(*a, **k)
        except ApiError as e:
            return e.response
    return inner


@router.get("/queues")
@guarded
def list_queues(labeller: str = Query(None)):
    who = _labeller(labeller)
    out, everyone = [], set()
    for name in queues.ORDER:
        spec = queues.SPECS[name]
        entry = {"queue": name, "title": spec.title, "description": spec.description, "blind": spec.blind,
                 "available": False, "n_items": 0, "estimated_minutes": spec.estimated_minutes,
                 "label_schema": spec.schema, "guidelines": queues.guidelines(name), "progress": [],
                 "my_progress": None}
        try:
            q = queues.load(name)
        except queues.QueueUnavailable:
            out.append(entry)
            continue
        rows = store.read(name)
        entry.update(available=True, n_items=len(q))
        for l in store.labellers(name, rows):
            entry["progress"].append(_progress(q, l, store.by_labeller(name, l, rows)))
            everyone.add(l)
        if who:
            entry["my_progress"] = _progress(q, who, store.by_labeller(name, who, rows))
        out.append(entry)
    return {"queues": out, "labellers": sorted(everyone), "provisional_note": PROVISIONAL_NOTE}


@router.get("/queues/{queue}/items")
@guarded
def list_items(queue: str, labeller: str = Query(None), status: str = Query("all"),
               limit: int = Query(500, ge=1, le=5000), offset: int = Query(0, ge=0)):
    q = _queue(queue)
    who = _labeller(labeller)
    if status not in ("all", "todo", "done"):
        raise ApiError(400, "invalid_request", "status must be all, todo or done")
    if status != "all" and not who:
        raise ApiError(400, "invalid_labeller", f"status={status} needs a labeller")
    mine = store.by_labeller(queue, who) if who else {}
    ids = [i for i in q.ids if status == "all" or ((i in mine) == (status == "done"))]
    return {"queue": queue, "blind": q.spec.blind, "total": len(q), "n_done": sum(1 for i in mine if i in q),
            "n_matching": len(ids), "offset": offset, "limit": limit,
            "items": [_item(q, i, mine) for i in ids[offset:offset + limit]]}


@router.get("/queues/{queue}/next")
@guarded
def next_item(queue: str, labeller: str = Query(None)):
    q = _queue(queue)
    who = _labeller(labeller, required=True)
    mine = store.by_labeller(queue, who)
    nxt = _next_id(q, mine)
    return {"queue": queue, "blind": q.spec.blind, "progress": _progress(q, who, mine),
            "item": _item(q, nxt, mine) if nxt else None}


@router.get("/queues/{queue}/items/{item_id:path}")
@guarded
def get_item(queue: str, item_id: str, labeller: str = Query(None)):
    q = _queue(queue)
    who = _labeller(labeller)
    if item_id not in q:
        raise ApiError(404, "unknown_item", f"item {item_id!r} is not in queue {queue!r}")
    rows = store.read(queue) if who else []
    mine = store.by_labeller(queue, who, rows) if who else {}
    out = _item(q, item_id, mine)
    out["history"] = [_public(r) for r in store.history(queue, who, item_id, rows)] if who else []
    return out


@router.post("/annotations")
@guarded
def post_annotation(payload: dict = Body(...)):
    extra = [k for k in payload if k not in ("queue", "item_id", "label", "labeller", "note")]
    if extra:
        raise ApiError(400, "invalid_request", f"unknown field(s) {extra}; allowed: queue, item_id, label, labeller, note")
    if "label" not in payload:
        raise ApiError(400, "invalid_request", "label is required (an object, or null to retract)")
    q = _queue(str(payload.get("queue")))
    queue = q.spec.name
    who = _labeller(payload.get("labeller"), required=True)
    item_id = payload.get("item_id")
    if isinstance(item_id, int) and not isinstance(item_id, bool):
        item_id = str(item_id)
    if not isinstance(item_id, str) or item_id not in q:
        raise ApiError(404, "unknown_item", f"item {item_id!r} is not in queue {queue!r}")
    note = payload.get("note") or ""
    if not isinstance(note, str) or len(note) > queues.MAX_NOTE:
        raise ApiError(400, "invalid_request", f"note must be text of at most {queues.MAX_NOTE} characters")
    label = payload["label"]
    if label is not None:
        try:
            label = queues.validate_label(queue, label)
        except queues.LabelError as e:
            raise ApiError(400, "invalid_label", str(e))
    elif item_id not in store.by_labeller(queue, who):
        raise ApiError(400, "invalid_request", "nothing to retract: this labeller has no label for this item")
    rec = store.append(queue, item_id, who, label, note.strip())
    mine = store.by_labeller(queue, who)
    return {"ok": True, "annotation": _public(rec), "progress": _progress(q, who, mine),
            "item": _item(q, item_id, mine), "next_item_id": _next_id(q, mine, after=item_id)}


@router.get("/annotations")
@guarded
def list_annotations(queue: str = Query(None), labeller: str = Query(None), item_id: str = Query(None),
                     history: bool = Query(False)):
    if queue is not None and queue not in queues.SPECS:
        raise ApiError(404, "unknown_queue", f"unknown queue {queue!r}; one of {queues.ORDER}")
    who = _labeller(labeller)
    out = []
    for name in ([queue] if queue else queues.ORDER):
        rows = store.read(name)
        recs = rows if history else list(store.current(name, rows).values())
        for r in recs:
            if (who is None or r["labeller"] == who) and (item_id is None or r["item_id"] == item_id):
                out.append(_public({**r, "queue": name}))
    return {"n": len(out), "history": history, "annotations": out}


def export_rows(queue: str, labeller: str = None):
    """Current labels of one queue as flat rows, in queue order when the queue file is there."""
    keys = queues.LABEL_KEYS[queue]
    cols = ["item_id", "labeller"] + keys + ["note", "ts", "rev"]
    cur = store.current(queue)
    try:
        order = {i: n for n, i in enumerate(queues.load(queue).ids)}
    except queues.QueueUnavailable:
        order = {}
    recs = sorted(cur.values(), key=lambda r: (r["labeller"], order.get(r["item_id"], 10 ** 9), r["item_id"]))
    rows = []
    for r in recs:
        if labeller and r["labeller"] != labeller:
            continue
        row = {"item_id": r["item_id"], "labeller": r["labeller"], "note": r.get("note", ""), "ts": r.get("ts"),
               "rev": r.get("rev")}
        row.update({k: (r["label"] or {}).get(k) for k in keys})
        rows.append({c: row.get(c) for c in cols})
    return cols, rows


@router.get("/export")
@guarded
def export(queue: str = Query(None), format: str = Query("json"), labeller: str = Query(None)):
    if queue not in queues.SPECS:
        raise ApiError(404, "unknown_queue", f"queue is required; one of {queues.ORDER}")
    if format not in ("json", "csv"):
        raise ApiError(400, "invalid_request", "format must be json or csv")
    cols, rows = export_rows(queue, _labeller(labeller))
    if format == "json":
        return {"queue": queue, "n": len(rows), "columns": cols, "rows": rows}
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="review_{queue}.csv"'})


@router.get("/results")
@guarded
def results():
    f = config.results_dir() / "latest.json"
    if not f.exists():
        return {"available": False, "message": "no evaluation has been run yet"}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ApiError(500, "results_unreadable", f"{f} is not valid JSON; run the evaluation again")


@router.post("/evaluate")
@guarded
def run_evaluate():
    from . import evaluate  # imported late: pulls in pandas-heavy code only when asked for
    return evaluate.evaluate(run_benchmark=False)
