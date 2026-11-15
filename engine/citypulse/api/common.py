"""Shared pieces of the API: error type, filters, card builders, Wilson interval, engine loading, output cleaning.

Everything here reads the store (citypulse.engine.store); nothing is hard-coded.
"""
import importlib, json, logging, math, re, threading, time
from datetime import date as _date

import numpy as np
import pandas as pd
from fastapi import Query

from .. import config
from ..engine import store

log = logging.getLogger("citypulse.api")

CHANNELS = ["news", "social", "other_web"]
STANCES = ["support", "oppose", "neutral", "mixed"]          # the stance vocabulary of the contract
SIDE = ["support", "oppose", "mixed"]                        # "takes a side"
CODEBOOK = "codebook_v1"
PROVISIONAL_NOTE = "agreement with AI reference labels, not human-validated"

POST_FIELDS = ["doc_id", "date", "channel", "media_type", "domain", "source_name", "url", "lang", "title", "excerpt", "project",
               "project_name", "stance", "tone", "passing", "label_source", "voice", "dup_count", "n_claims", "run_id"]
CLAIM_FIELDS = ["cid", "claim", "project", "project_name", "date", "channel", "domain", "url", "topic", "polarity", "doc_id", "voice",
                "family_id", "family_name", "run_id"]
AUTHOR_KEYS = {"author", "authors", "author_hash", "author_name", "author_handle", "username", "user_name", "handle"}


class ApiError(Exception):
    """Raised anywhere in a handler; rendered as {"error": {"code", "message", ...extra}}."""

    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, **self.extra}}


_bundle = {"loaded": None, "seen": None, "checked": 0.0}
_bundle_lock = threading.Lock()
BUNDLE_CHECK_SECS = 5


def _bundle_signature():
    """Names, sizes and change times of the data bundle files (not the batch runs: the batch processor reloads the store itself)."""
    try:
        return tuple(sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in config.DATA.iterdir()
                            if p.is_file() and p.suffix in (".parquet", ".json", ".npy")))
    except OSError:
        return None


def S():
    """The current store. Never cache the object: store.reload() replaces it after a batch run.

    If the data bundle on disk was replaced while the server runs (a rebuilt app_data/), the store is reloaded once the files
    have stopped changing, so the API never keeps serving numbers from a bundle that no longer exists.
    """
    try:
        st = store.get()
    except FileNotFoundError as e:
        raise ApiError(503, "data_unavailable", str(e))
    now = time.time()
    if now - _bundle["checked"] > BUNDLE_CHECK_SECS and _bundle_lock.acquire(blocking=False):
        try:
            _bundle["checked"] = now
            sig = _bundle_signature()
            if _bundle["loaded"] is None:
                _bundle["loaded"] = sig
            elif sig is not None and sig != _bundle["loaded"]:
                if sig == _bundle["seen"]:                 # unchanged for one check interval: the copy has finished
                    try:
                        st = store.reload()
                        _bundle["loaded"] = sig
                        log.info("data bundle changed on disk: store reloaded, data version %s", st.data_version)
                    except Exception:
                        log.exception("data bundle changed on disk but could not be loaded; still serving the previous data")
                _bundle["seen"] = sig
        finally:
            _bundle_lock.release()
    return st


# ---------------------------------------------------------------- filters

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_date(value, name):
    if value in (None, ""):
        return None
    if not _DATE.match(value):
        raise ApiError(422, "invalid_parameter", f"'{name}' must be a date in the form YYYY-MM-DD, got '{value}'.")
    try:
        _date.fromisoformat(value)
    except ValueError:
        raise ApiError(422, "invalid_parameter", f"'{name}' is not a real calendar date: '{value}'.")
    return value


def known_projects(st) -> list:
    seen = list(dict.fromkeys(list(config.PROJECT_NAMES) + list(st.meta.get("projects", {})) + sorted(st.posts.project.dropna().unique())))
    return seen


def project_name(st, pid) -> str:
    return st.meta.get("projects", {}).get(pid) or config.PROJECT_NAMES.get(pid) or pid


def check_project(st, project):
    if project in (None, ""):
        return None
    if project not in known_projects(st):
        raise ApiError(422, "invalid_parameter", f"Unknown project '{project}'. Known projects: {', '.join(known_projects(st))}.")
    return project


class Filters:
    """The filters every list / statistics endpoint accepts (all optional)."""

    def __init__(self,
                 project: str | None = Query(None, description="project id, e.g. heilbronn_cablecar"),
                 from_: str | None = Query(None, alias="from", description="first day, YYYY-MM-DD"),
                 to: str | None = Query(None, description="last day (inclusive), YYYY-MM-DD"),
                 channel: str | None = Query(None, description="news | social | other_web"),
                 topic: str | None = Query(None, description="argument topic, see /api/meta"),
                 stance: str | None = Query(None, description="support | oppose | neutral | mixed"),
                 run_id: str | None = Query(None, description="'base' or the id of a batch run")):
        self.project, self.from_, self.to = project or None, from_ or None, to or None
        self.channel, self.topic, self.stance, self.run_id = channel or None, topic or None, stance or None, run_id or None

    def validate(self, st):
        check_project(st, self.project)
        check_date(self.from_, "from")
        check_date(self.to, "to")
        if self.from_ and self.to and self.from_ > self.to:
            raise ApiError(422, "invalid_parameter", f"'from' ({self.from_}) is after 'to' ({self.to}).")
        if self.channel and self.channel not in CHANNELS:
            raise ApiError(422, "invalid_parameter", f"'channel' must be one of {', '.join(CHANNELS)}; got '{self.channel}'.")
        if self.stance and self.stance not in STANCES:
            raise ApiError(422, "invalid_parameter", f"'stance' must be one of {', '.join(STANCES)}; got '{self.stance}'.")
        if self.topic:
            topics = set(st.claims.topic.dropna().unique())
            if self.topic not in topics:
                raise ApiError(422, "invalid_parameter", f"Unknown topic '{self.topic}'. Known topics: {', '.join(sorted(topics))}.")
        if self.run_id and self.run_id not in st.run_ids and self.run_id not in set(st.posts.run_id.unique()):
            raise ApiError(422, "invalid_parameter", f"Unknown run_id '{self.run_id}'. Known: {', '.join(st.run_ids)}.")
        return self

    def active(self) -> dict:
        d = {"project": self.project, "from": self.from_, "to": self.to, "channel": self.channel, "topic": self.topic,
             "stance": self.stance, "run_id": self.run_id}
        return {k: v for k, v in d.items() if v}

    def without(self, *names):
        f = Filters.__new__(Filters)
        f.__dict__.update(self.__dict__)
        for n in names:
            setattr(f, n, None)
        return f


def filter_posts(st, f: Filters) -> pd.DataFrame:
    """Posts that pass the filters. `topic` keeps posts with at least one claim on that topic."""
    p = st.posts
    m = pd.Series(True, index=p.index)
    if f.project:
        m &= p.project == f.project
    if f.from_:
        m &= p.date >= f.from_
    if f.to:
        m &= p.date <= f.to
    if f.channel:
        m &= p.channel == f.channel
    if f.stance:
        m &= p.stance == f.stance
    if f.run_id:
        m &= p.run_id == f.run_id
    if f.topic:
        m &= p.doc_id.isin(st.claims.doc_id[st.claims.topic == f.topic])
    return p[m]


def filter_claims(st, f: Filters, posts: pd.DataFrame | None = None) -> pd.DataFrame:
    """Claims extracted from the posts that pass the filters (and, with `topic`, only claims on that topic)."""
    posts = filter_posts(st, f) if posts is None else posts
    c = st.claims
    m = c.doc_id.isin(posts.doc_id)
    if f.topic:
        m &= c.topic == f.topic
    return c[m]


# ---------------------------------------------------------------- numbers

def wilson(k: int, n: int, z: float = 1.959963984540054) -> dict:
    """Share k/n with a Wilson 95% score interval. n = 0 gives nulls, never a made-up value."""
    k, n = int(k), int(n)
    if n <= 0:
        return {"value": None, "lo": None, "hi": None, "n": 0, "k": 0}
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"value": round(p, 4), "lo": round(max(0.0, centre - half), 4), "hi": round(min(1.0, centre + half), 4), "n": n, "k": k}


# ---------------------------------------------------------------- cards

_HANDLE = re.compile(r"(?<![\w.@/])@[A-Za-z0-9_][A-Za-z0-9_.\-]{1,}")
_POST_BY = re.compile(r"^(Post|Comment|Reply|Tweet) by \S+", re.I)


def mask(text):
    """Remove account handles from displayed text (titles / excerpts). The product never shows who wrote a post."""
    if not isinstance(text, str):
        return text
    text = _POST_BY.sub(lambda m: f"{m.group(1)} by [account removed]", text)
    return _HANDLE.sub("@[account]", text)


def records(df: pd.DataFrame) -> list:
    """DataFrame -> list of JSON-safe dicts (NaN -> null, timestamps -> ISO)."""
    if df is None or len(df) == 0:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso"))


def post_cards(df: pd.DataFrame) -> list:
    out = records(df[[c for c in POST_FIELDS if c in df.columns]])
    for r in out:
        r["title"], r["excerpt"] = mask(r.get("title")), mask(r.get("excerpt"))
    return out


def claim_cards(df: pd.DataFrame) -> list:
    return records(df[[c for c in CLAIM_FIELDS if c in df.columns]])


def has_arguments(st, project) -> bool:
    return bool((st.claims.project == project).any())


def no_arguments_note(st, project) -> str:
    return (f"No arguments have been extracted for {project_name(st, project)} ({project}): its posts carry stance and tone labels "
            f"but no claims, so argument, topic and matching views are empty for this project.")


# ---------------------------------------------------------------- engine / batch modules (written by other builders)

def engine(name: str):
    """Import citypulse.engine.<name> lazily. Missing or broken module -> HTTP 503, never a crash at start-up."""
    try:
        return importlib.import_module(f"citypulse.engine.{name}")
    except Exception as e:
        log.warning("engine module %s not available: %r", name, e)
        raise ApiError(503, "engine_unavailable", f"The engine module '{name}' is not available on this server: {e}")


def engine_call(name: str, fn: str, *args, **kwargs):
    mod = engine(name)
    try:
        return getattr(mod, fn)(*args, **kwargs)
    except ApiError:
        raise
    except Exception as e:
        log.exception("engine call %s.%s failed", name, fn)
        raise ApiError(503, "engine_unavailable", f"The engine call {name}.{fn} failed: {type(e).__name__}: {e}")


def batch_module():
    try:
        return importlib.import_module("citypulse.batch")
    except Exception as e:
        log.warning("batch module not available: %r", e)
        raise ApiError(503, "batch_unavailable", f"The batch processor is not available on this server: {e}")


_ROOT = str(config.ROOT)


def _fill_claim(d: dict, st):
    cid = d.get("cid")
    if isinstance(cid, str) and cid in st.cidx and not (d.get("doc_id") and d.get("url")):
        row = st.claims_by_cid.loc[cid]
        for k in CLAIM_FIELDS:
            if d.get(k) is None and k in row.index:
                v = row[k]
                d[k] = None if (isinstance(v, float) and math.isnan(v)) else (v.item() if isinstance(v, np.generic) else v)


def clean(obj, st=None, drop=AUTHOR_KEYS):
    """Make engine / batch output safe to send: numpy -> python, NaN -> null, no author fields.

    With a store, every dict that carries a `cid` gets its `doc_id` and `url` filled in from the claims table if the engine
    left them out, and every concern gets an `evidence` list, so each statement can be traced to a stored post.
    """
    if isinstance(obj, dict):
        out = {str(k): clean(v, st, drop) for k, v in obj.items() if str(k) not in drop}
        if st is not None:
            _fill_claim(out, st)
            if "concern_id" in out and "evidence" not in out and isinstance(out.get("claims"), list):
                out["evidence"] = [{"cid": c.get("cid"), "doc_id": c.get("doc_id"), "url": c.get("url"), "date": c.get("date")}
                                   for c in out["claims"] if isinstance(c, dict)]
        return out
    if isinstance(obj, (list, tuple, set)):
        return [clean(v, st, drop) for v in obj]
    if isinstance(obj, np.ndarray):
        return [clean(v, st, drop) for v in obj.tolist()]
    if isinstance(obj, pd.DataFrame):
        return clean(records(obj), st, drop)
    if isinstance(obj, pd.Series):
        return clean(obj.to_dict(), st, drop)
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, (pd.Timestamp,)):
        return None if pd.isna(obj) else obj.isoformat()
    if obj is pd.NaT:
        return None
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, str):
        return obj.replace(_ROOT, "<repo>") if _ROOT in obj else obj      # no local file paths in answers
    if obj is None or isinstance(obj, (int, bool)):
        return obj
    return str(obj).replace(_ROOT, "<repo>")
