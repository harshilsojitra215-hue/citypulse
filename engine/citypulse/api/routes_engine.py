"""Endpoints that delegate to the engine (citypulse.engine.search / replay / crosscity / matcher).

No matching, retrieval or replay logic lives here. The engine modules are imported inside each handler; if one cannot be
imported or a call fails, the answer is HTTP 503 {"error": {"code": "engine_unavailable", ...}}.
Every claim returned carries doc_id and url (filled from the claims table if the engine left them out).
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .. import config
from .common import ApiError, S, check_date, check_project, claim_cards, clean, engine, engine_call, post_cards

router = APIRouter(prefix="/api")

CONCERN_STATES = ["new_emerging", "new_single", "ambiguous", "gaining", "recurring"]


class MatchBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    project: str | None = None


class CidBody(BaseModel):
    cid: str = Field(..., min_length=1)


class SimilarBody(BaseModel):
    text: str | None = Field(None, max_length=5000)
    cid: str | None = None
    project: str | None = None


def check_cid(st, cid: str) -> str:
    if cid not in st.cidx:
        raise ApiError(404, "unknown_claim", f"No claim with cid '{cid}'.")
    return cid


def check_cutoff(st, cutoff: str | None) -> str:
    cutoff = check_date(cutoff, "cutoff") or config.EARLIEST_REPLAY_CUTOFF
    if cutoff < config.EARLIEST_REPLAY_CUTOFF:
        raise ApiError(422, "invalid_cutoff", f"'cutoff' must be {config.EARLIEST_REPLAY_CUTOFF} or later: the matcher was trained on data "
                                              f"before this date, so an earlier replay would use knowledge from the future.",
                       earliest_allowed=config.EARLIEST_REPLAY_CUTOFF)
    if cutoff > st.posts.date.max():
        raise ApiError(422, "invalid_cutoff", f"'cutoff' {cutoff} is after the last stored post ({st.posts.date.max()}).",
                       earliest_allowed=config.EARLIEST_REPLAY_CUTOFF)
    return cutoff


def check_argument_project(st, project):
    """Projects without extracted arguments cannot be matched or replayed; say so instead of returning nothing."""
    project = check_project(st, project)
    if project and not (st.claims.project == project).any():
        raise ApiError(422, "no_arguments", f"No arguments have been extracted for project '{project}', so there is nothing to match or replay.",
                       has_arguments=False)
    return project


# ---------------------------------------------------------------- claims, search, match

@router.get("/claims/{cid}", tags=["arguments"])
def claim(cid: str):
    st = S()
    check_cid(st, cid)
    out = clean(engine_call("search", "claim_matches", cid), st)
    row = st.claims[st.claims.cid == cid]
    out.setdefault("claim", claim_cards(row)[0])
    p = st.posts[st.posts.doc_id == row.iloc[0].doc_id].head(1)
    if not out.get("post"):
        out["post"] = post_cards(p)[0] if len(p) else None
    for k in ("equivalent", "related", "elsewhere"):
        out.setdefault(k, [])
    out.setdefault("mode", None)
    return out


@router.get("/search", tags=["arguments"])
def search(q: str = Query(..., min_length=1, max_length=2000), project: str | None = None, topic: str | None = None,
           k: int = Query(20, ge=1, le=100)):
    st = S()
    if not q.strip():
        raise ApiError(422, "invalid_parameter", "'q' must not be empty.")
    project = check_project(st, project or None)
    topic = topic or None
    if topic and topic not in set(st.claims.topic.unique()):
        raise ApiError(422, "invalid_parameter", f"Unknown topic '{topic}'.")
    out = clean(engine_call("search", "semantic", q.strip(), project=project, topic=topic, k=k), st)
    out.setdefault("results", [])
    if project and not (st.claims.project == project).any():
        out["has_arguments"] = False
        out["notes"] = [f"No arguments have been extracted for project '{project}'."]
    return out


@router.post("/match", tags=["arguments"])
def match(body: MatchBody):
    st = S()
    if not body.text.strip():
        raise ApiError(422, "invalid_request", "'text' must not be empty.")
    project = check_argument_project(st, body.project or None)
    out = clean(engine_call("search", "match_text", body.text.strip(), project=project), st)
    for k in ("matches", "elsewhere"):
        out.setdefault(k, [])
    return out


# ---------------------------------------------------------------- emerging concerns and replay

def _concerns(st, project, cutoff, state=None) -> tuple:
    replay = engine("replay")
    items = clean(engine_call("replay", "concerns", project=project, cutoff=cutoff, state=state), st)
    mode = model_version = None
    try:                                        # replay.run is cached by the engine, so this only reads the mode it used
        first = project or next(iter(st.meta.get("arguments_available_for", [])), None)
        r = replay.run(first, cutoff)
        mode, model_version = r.get("mode"), r.get("model_version")
    except Exception:
        pass
    return items, mode, model_version


@router.get("/emerging", tags=["emerging"])
def emerging(project: str | None = None, cutoff: str | None = None, state: str | None = None):
    st = S()
    project = check_argument_project(st, project or None)
    cutoff = check_cutoff(st, cutoff)
    state = state or None
    if state and state not in CONCERN_STATES:
        raise ApiError(422, "invalid_parameter", f"'state' must be one of {', '.join(CONCERN_STATES)}; got '{state}'.")
    items, mode, model_version = _concerns(st, project, cutoff, state)
    counts = {s: sum(1 for c in items if c.get("state") == s) for s in CONCERN_STATES}
    return {"cutoff": cutoff, "project": project, "state": state, "mode": mode, "model_version": model_version, "simulation": True,
            "counts": counts, "concerns": items,
            "notes": ["Concerns come from a historical replay: the system is frozen at the cutoff and later claims arrive in their real order.",
                      "new_single is a candidate (one voice so far); ambiguous needs review. Neither is an established finding.",
                      "Scores are provisional: agreement with AI reference labels, not human-validated."]}


@router.get("/emerging/{concern_id:path}", tags=["emerging"])
def concern(concern_id: str, project: str | None = None, cutoff: str | None = None):
    st = S()
    project = check_argument_project(st, project or None)
    cutoff = check_cutoff(st, cutoff)
    items, mode, model_version = _concerns(st, project, cutoff)
    for c in items:
        if c.get("concern_id") == concern_id:
            return {**c, "cutoff": cutoff, "mode": mode, "model_version": model_version}
    raise ApiError(404, "unknown_concern", f"No concern '{concern_id}' for cutoff {cutoff}" + (f" in project {project}." if project else "."))


@router.get("/replay/cutoffs", tags=["replay"])
def replay_cutoffs():
    st = S()
    out = clean(engine_call("replay", "cutoffs"))
    out.setdefault("earliest_allowed", config.EARLIEST_REPLAY_CUTOFF)
    out["last_post_date"] = st.posts.date.max()
    return out


@router.get("/replay", tags=["replay"])
def replay(project: str | None = None, cutoff: str | None = None):
    st = S()
    project = check_argument_project(st, project or None)
    cutoff = check_cutoff(st, cutoff)
    return clean(engine_call("replay", "run", project, cutoff), st)


@router.post("/replay/live-check", tags=["replay"])
def live_check(body: CidBody):
    st = S()
    check_cid(st, body.cid)
    return clean(engine_call("replay", "live_check", body.cid), st)


# ---------------------------------------------------------------- cross-city cases

def _similar(st, cid, text, project):
    project = check_project(st, project or None)
    if cid:
        check_cid(st, cid)
        out = engine_call("crosscity", "similar", cid=cid)
    elif text and text.strip():
        out = engine_call("crosscity", "similar", text=text.strip(), project=project)
    else:
        raise ApiError(422, "invalid_request", "Give either 'cid' (a stored claim) or 'text' (a free-text argument).")
    out = clean(out, st)
    out.setdefault("cases", [])
    out["note"] = "Historical cases from other projects. They are not forecasts."
    return out


@router.get("/crosscity/similar", tags=["cross-city"])
def crosscity_similar(cid: str | None = None, text: str | None = Query(None, max_length=5000), project: str | None = None):
    return _similar(S(), cid, text, project)


@router.post("/crosscity/similar", tags=["cross-city"])
def crosscity_similar_post(body: SimilarBody):
    return _similar(S(), body.cid, body.text, body.project)
