"""API tests for the endpoints that delegate to the engine (search, match, claims, emerging, replay, cross-city cases),
to the batch processor, and for the briefing export. Real data bundle, FastAPI TestClient.

Tests that need an engine or batch module are skipped, with the reason, while that module cannot be imported.
No test starts a real batch run or calls a paid model: uploads use a stand-in for batch.submit.
"""
import importlib
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from citypulse import config

pytestmark = pytest.mark.skipif(not (config.DATA / "posts.parquet").exists(), reason=f"data bundle missing in {config.DATA}")

HN = "heilbronn_cablecar"
CLAIM_KEYS = {"cid", "claim", "project", "date", "domain", "url", "topic", "polarity", "doc_id", "voice"}
STATES = {"new_emerging", "new_single", "ambiguous", "gaining", "recurring"}
BANNED = {"author", "authors", "author_hash", "author_name", "author_handle", "username", "user_name", "handle"}


def need(*names):
    """Skip the test when a module owned by another builder is not importable yet."""
    for n in names:
        try:
            importlib.import_module(n)
        except Exception as e:
            pytest.skip(f"{n} is not importable yet: {type(e).__name__}: {e}")


def need_engine(*mods):
    need(*[f"citypulse.engine.{m}" for m in mods])


@pytest.fixture(scope="module")
def client():
    from citypulse.api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def S():
    from citypulse.engine import store
    return store.get()


def ok(r):
    assert r.status_code == 200, f"{r.request.url}: {r.status_code} {r.text[:300]}"
    return r.json()


def is_error(r, status, code=None):
    assert r.status_code == status, r.text[:300]
    body = r.json()
    assert set(body) == {"error"} and isinstance(body["error"].get("code"), str) and body["error"].get("message"), body
    if code:
        assert body["error"]["code"] == code, body
    return body["error"]


def walk(obj):
    """Every dict inside a JSON answer."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def check_evidence(obj, S):
    """Every claim anywhere in the answer carries doc_id and url of a stored post; no author fields. Returns the doc_ids."""
    docs = set()
    for d in walk(obj):
        assert not set(d) & BANNED, set(d) & BANNED
        if "cid" in d and "claim" in d:
            assert d.get("doc_id") and d.get("url"), d
            assert d["doc_id"] in S.posts_by_id.index, d["doc_id"]
            docs.add(d["doc_id"])
    return docs


def resolve_all(client, doc_ids):
    for doc_id in doc_ids:
        r = client.get("/api/posts/" + quote(doc_id, safe=""))
        assert r.status_code == 200 and r.json()["doc_id"] == doc_id, doc_id


def a_scored_claim(S):
    P = S.pair_scores
    cid = P.qid.iloc[0] if len(P) else S.claims[S.claims.project == HN].cid.iloc[-1]
    return cid


# ---------------------------------------------------------------- the lazy-import rule (always runs)

def test_engine_unavailable_gives_503(client, monkeypatch):
    from citypulse.api import common
    real = importlib.import_module

    def broken(name, *a, **k):
        if name.startswith("citypulse.engine.") or name == "citypulse.batch":
            raise ImportError(f"{name} is not built yet")
        return real(name, *a, **k)
    monkeypatch.setattr(common.importlib, "import_module", broken)
    for r in [client.get("/api/search", params={"q": "too expensive"}), client.get("/api/replay", params={"project": HN}),
              client.get("/api/emerging"), client.get("/api/replay/cutoffs"), client.get("/api/crosscity/similar", params={"text": "noise"}),
              client.post("/api/match", json={"text": "too expensive"})]:
        is_error(r, 503, "engine_unavailable")
    for r in [client.get("/api/batches"), client.get("/api/batches/template"), client.get("/api/batches/r1"),
              client.post("/api/batches", files={"file": ("a.json", b"[]", "application/json")})]:
        is_error(r, 503, "batch_unavailable")
    # the briefing still comes, and says that the concerns are missing
    b = ok(client.get("/api/export/briefing", params={"project": HN, "format": "json"}))
    assert b["concerns"]["available"] is False and "not available" in b["concerns"]["message"]
    assert b["overview"]["n_posts"] > 0 and "not available" in b["markdown"]
    # endpoints that need no engine keep working
    h = client.get("/api/health")
    assert client.get("/api/overview").status_code == 200 and h.status_code == 200 and isinstance(h.json()["matcher"]["available"], bool)


def test_engine_call_failure_gives_503(client, monkeypatch):
    need_engine("search")
    from citypulse.engine import search
    monkeypatch.setattr(search, "semantic", lambda *a, **k: 1 / 0)
    e = is_error(client.get("/api/search", params={"q": "noise"}), 503, "engine_unavailable")
    assert "ZeroDivisionError" in e["message"]


# ---------------------------------------------------------------- claims, search, match

def test_claim_detail(client, S):
    need_engine("search", "crosscity")
    cid = a_scored_claim(S)
    d = ok(client.get(f"/api/claims/{cid}"))
    assert {"claim", "post", "equivalent", "related", "elsewhere", "mode"} <= set(d)
    assert d["claim"]["cid"] == cid and CLAIM_KEYS <= set(d["claim"])
    assert d["post"]["doc_id"] == d["claim"]["doc_id"] == S.claims_by_cid.loc[cid].doc_id
    for m in d["equivalent"] + d["related"]:
        assert CLAIM_KEYS <= set(m) and {"relation", "p_same", "score_source"} <= set(m)
    assert all(m["relation"] == "equivalent" for m in d["equivalent"]) and all(m["relation"] == "related" for m in d["related"])
    for c in d["elsewhere"]:
        assert {"claim", "relation", "p_same", "stage", "after"} <= set(c) and c["claim"]["project"] != d["claim"]["project"]
    resolve_all(client, check_evidence(d, S))
    is_error(client.get("/api/claims/c-does-not-exist"), 404, "unknown_claim")


def test_search(client, S):
    need_engine("search")
    r = ok(client.get("/api/search", params={"q": "the cable car is too expensive", "project": HN, "k": 5}))
    assert r["mode"] in ("semantic", "keyword-fallback") and "matcher_mode" in r
    assert 0 < len(r["results"]) <= 5
    for m in r["results"]:
        assert CLAIM_KEYS <= set(m) and m["project"] == HN and "score_source" in m
    resolve_all(client, check_evidence(r, S))
    t = ok(client.get("/api/search", params={"q": "cost", "topic": "cost_financing", "k": 3}))
    assert all(m["topic"] == "cost_financing" for m in t["results"])
    is_error(client.get("/api/search"), 422, "invalid_request")
    is_error(client.get("/api/search", params={"q": "x", "k": 0}), 422, "invalid_request")
    is_error(client.get("/api/search", params={"q": "x", "project": "atlantis"}), 422, "invalid_parameter")


def test_match(client, S):
    need_engine("search", "crosscity")
    r = ok(client.post("/api/match", json={"text": "Money for a cable car while the hospital is being closed", "project": HN}))
    assert {"novelty", "matches", "elsewhere", "mode"} <= set(r)
    assert "state" in r["novelty"]
    if r["mode"] == "live":
        assert r["novelty"]["state"] in ("familiar", "ambiguous", "new") and {"new", "familiar"} <= set(r["novelty"]["cutoffs"])
    else:                                   # no model or no embedder on this machine: the answer must say so, not guess
        assert r["novelty"]["state"] == "unknown" and r["novelty"]["note"]
    for m in r["matches"]:
        assert CLAIM_KEYS <= set(m) and m["project"] == HN
    resolve_all(client, check_evidence(r, S))
    is_error(client.post("/api/match", json={}), 422, "invalid_request")
    is_error(client.post("/api/match", json={"text": "   "}), 422, "invalid_request")
    is_error(client.post("/api/match", json={"text": "x", "project": "ipai"}), 422, "no_arguments")


# ---------------------------------------------------------------- emerging concerns and replay

def test_replay_cutoffs(client):
    need_engine("replay")
    c = ok(client.get("/api/replay/cutoffs"))
    assert c["earliest_allowed"] == config.EARLIEST_REPLAY_CUTOFF and c["reason"]
    assert c["cutoffs"] and all(x >= c["earliest_allowed"] for x in c["cutoffs"])


def test_replay(client, S):
    need_engine("replay")
    r = ok(client.get("/api/replay", params={"project": HN}))
    assert {"project", "cutoff", "mode", "model_version", "simulation", "known_before", "steps", "concerns", "activity"} <= set(r)
    assert r["project"] == HN and r["cutoff"] == config.EARLIEST_REPLAY_CUTOFF and r["simulation"] is True
    stream = S.claims[(S.claims.project == HN) & (S.claims.date >= r["cutoff"]) & (S.claims.run_id == "base")]
    assert len(r["steps"]) == len(stream) > 0
    before = S.claims[(S.claims.project == HN) & (S.claims.ts < r["cutoff"])]
    assert r["known_before"]["n_claims"] == len(before)
    for s in r["steps"]:
        assert {"i", "ts", "claim", "decision", "matched", "concern_id", "raised", "novelty_score"} <= set(s)
        assert s["decision"] in ("familiar", "joins_new", "opens_new", "ambiguous")
        assert s["ts"][:10] >= r["cutoff"] and s["claim"]["project"] == HN
        if s["matched"]:
            assert s["matched"]["date"] <= s["claim"]["date"], "a match must not come from the future"
    assert [s["i"] for s in r["steps"]] == list(range(len(r["steps"])))
    docs = check_evidence(r, S)
    assert {s["claim"]["doc_id"] for s in r["steps"]} <= docs
    resolve_all(client, docs)                       # every doc_id of every step and concern resolves
    later = ok(client.get("/api/replay", params={"project": HN, "cutoff": "2026-08-01"}))
    assert len(later["steps"]) < len(r["steps"]) and later["cutoff"] == "2026-08-01"


def test_replay_and_emerging_reject_bad_input(client):
    need_engine("replay")
    for path in ("/api/replay", "/api/emerging", "/api/emerging/g:c1"):
        e = is_error(client.get(path, params={"project": HN, "cutoff": "2026-01-01"}), 422, "invalid_cutoff")
        assert e["earliest_allowed"] == config.EARLIEST_REPLAY_CUTOFF
        is_error(client.get(path, params={"cutoff": "July"}), 422, "invalid_parameter")
        is_error(client.get(path, params={"project": "atlantis"}), 422, "invalid_parameter")
        e = is_error(client.get(path, params={"project": "ipai"}), 422, "no_arguments")
        assert e["has_arguments"] is False
    is_error(client.get("/api/emerging", params={"state": "scary"}), 422, "invalid_parameter")
    is_error(client.get("/api/replay", params={"cutoff": "2031-01-01"}), 422, "invalid_cutoff")


def test_emerging(client, S):
    need_engine("replay")
    e = ok(client.get("/api/emerging", params={"project": HN}))
    assert {"cutoff", "mode", "concerns"} <= set(e) and e["cutoff"] == config.EARLIEST_REPLAY_CUTOFF
    assert e["concerns"], "the Heilbronn replay produces concerns"
    replayed = ok(client.get("/api/replay", params={"project": HN}))
    assert [c["concern_id"] for c in e["concerns"]] == [c["concern_id"] for c in replayed["concerns"]]
    assert e["counts"] == {s: sum(c["state"] == s for c in e["concerns"]) for s in e["counts"]} and set(e["counts"]) == STATES
    for c in e["concerns"]:
        assert {"concern_id", "state", "label", "project", "first_seen", "n_claims", "n_voices", "polarity", "uncertainty", "claims",
                "related_new_claims", "closest_older", "elsewhere", "events_nearby", "evidence"} <= set(c), set(c)
        assert c["state"] in STATES and c["project"] == HN
        assert c["claims"] and len(c["evidence"]) == len(c["claims"])
        for ev in c["evidence"]:
            assert ev["doc_id"] in S.posts_by_id.index and ev["url"] and ev["cid"] in S.cidx
        if c["state"] == "new_emerging":
            assert c["n_voices"] >= 2
    docs = check_evidence(e, S)
    resolve_all(client, sorted(docs)[:150])
    only = ok(client.get("/api/emerging", params={"project": HN, "state": "recurring"}))
    assert [c["concern_id"] for c in only["concerns"]] == [c["concern_id"] for c in e["concerns"] if c["state"] == "recurring"]
    all_projects = ok(client.get("/api/emerging"))
    assert {c["project"] for c in all_projects["concerns"]} <= set(S.meta["arguments_available_for"])
    assert len(all_projects["concerns"]) >= len(e["concerns"])


def test_emerging_detail(client, S):
    need_engine("replay")
    e = ok(client.get("/api/emerging", params={"project": HN}))
    for c in e["concerns"][:5] + e["concerns"][-3:]:
        d = ok(client.get("/api/emerging/" + quote(c["concern_id"], safe=""), params={"project": HN}))
        assert d["concern_id"] == c["concern_id"] and d["state"] == c["state"] and d["claims"] == c["claims"] and d["cutoff"] == e["cutoff"]
        assert ok(client.get("/api/emerging/" + c["concern_id"]))["concern_id"] == c["concern_id"]     # raw colon, no project
    is_error(client.get("/api/emerging/g:c-nope", params={"project": HN}), 404, "unknown_concern")


def test_live_check(client, S):
    need_engine("replay", "matcher")
    cid = a_scored_claim(S)
    r = ok(client.post("/api/replay/live-check", json={"cid": cid}))
    assert {"available", "cached", "live", "max_abs_diff"} <= set(r) and isinstance(r["available"], bool)
    assert len(r["cached"]) == int((S.pair_scores.qid == cid).sum())
    assert all({"cand", "p_same"} <= set(x) and x["cand"] in S.cidx for x in r["cached"])
    if not r["available"]:
        assert r["live"] == [] and r["max_abs_diff"] is None and str(config.ROOT) not in str(r)
    is_error(client.post("/api/replay/live-check", json={"cid": "c-nope"}), 404, "unknown_claim")
    is_error(client.post("/api/replay/live-check", json={}), 422, "invalid_request")


def test_crosscity_similar(client, S):
    need_engine("crosscity", "search")
    P = S.pair_scores
    cid = P[~P.same_project.astype(bool)].sort_values("p_same", ascending=False).qid.iloc[0] if len(P) else a_scored_claim(S)
    r = ok(client.get("/api/crosscity/similar", params={"cid": cid}))
    assert {"cases", "mode"} <= set(r)
    home = S.claims_by_cid.loc[cid].project
    for c in r["cases"]:
        assert {"claim", "relation", "p_same", "stage", "after"} <= set(c)
        assert c["relation"] in ("equivalent", "related") and c["claim"]["project"] != home
        assert c["stage"] is None or {"date", "title", "verified"} <= set(c["stage"])
    resolve_all(client, check_evidence(r, S))
    t = ok(client.post("/api/crosscity/similar", json={"text": "residents fear noise and loss of privacy", "project": HN}))
    assert {"cases", "mode"} <= set(t)
    check_evidence(t, S)
    is_error(client.get("/api/crosscity/similar"), 422, "invalid_request")
    is_error(client.get("/api/crosscity/similar", params={"cid": "c-nope"}), 404, "unknown_claim")


# ---------------------------------------------------------------- briefing

def test_briefing_is_built_from_live_numbers(client, S):
    need_engine("replay")
    o = ok(client.get("/api/overview", params={"project": HN}))
    e = ok(client.get("/api/emerging", params={"project": HN}))
    b = ok(client.get("/api/export/briefing", params={"project": HN, "format": "json"}))
    assert b["overview"]["opposition_share"] == o["opposition_share"] and b["overview"]["n_posts"] == o["n_posts"]
    assert b["data_version"] == S.data_version and b["cutoff"] == e["cutoff"]
    assert b["concerns"]["available"] is True and b["concerns"]["counts"] == e["counts"]
    assert b["limitations"] == ok(client.get("/api/meta"))["limitations"]
    listed = [c for group in b["concerns"]["by_state"].values() for c in group]
    assert {c["concern_id"] for c in listed} == {c["concern_id"] for c in e["concerns"]}
    for c in listed:
        assert c["evidence"], c["concern_id"]
        for ev in c["evidence"]:
            assert ev["doc_id"] in S.posts_by_id.index and ev["url"] and ev["post"].endswith("/api/posts/" + quote(ev["doc_id"], safe=""))
    link = listed[0]["evidence"][0]["post"]
    assert ok(client.get(link[link.index("/api/"):]))["doc_id"] == listed[0]["evidence"][0]["doc_id"]

    r = client.get("/api/export/briefing", params={"project": HN})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    md = r.text
    s = o["opposition_share"]
    assert f"{s['value']:.0%} (95% interval {s['lo']:.0%} to {s['hi']:.0%}, n = {s['n']})" in md
    assert f"Posts collected: {o['n_posts']} ({o['n_unique_posts']} unique texts" in md
    assert "not a representative poll" in md and "## Limitations" in md and "## Current concerns" in md
    first = next(c for c in listed if c["state"] == next(s for s, n in e["counts"].items() if n))
    assert first["evidence"][0]["url"] in md or any(c["evidence"][0]["url"] in md for c in listed)
    assert all(lim in md for lim in b["limitations"])


def test_briefing_other_cases(client):
    b = ok(client.get("/api/export/briefing", params={"project": "ipai", "format": "json"}))
    assert b["concerns"]["available"] is False and "No arguments have been extracted" in b["concerns"]["message"]
    assert b["overview"]["has_arguments"] is False and "No arguments have been extracted" in b["markdown"]
    is_error(client.get("/api/export/briefing", params={"format": "pdf"}), 422, "invalid_parameter")
    is_error(client.get("/api/export/briefing", params={"cutoff": "2026-01-01"}), 422, "invalid_cutoff")
    is_error(client.get("/api/export/briefing", params={"project": "atlantis"}), 422, "invalid_parameter")


# ---------------------------------------------------------------- batches (wiring only: no real run is started)

def test_batches_list_template_unknown(client):
    need("citypulse.batch")
    from citypulse import batch
    runs = ok(client.get("/api/batches"))
    assert isinstance(runs["runs"], list) and [r["run_id"] for r in runs["runs"]] == [r["run_id"] for r in batch.list_runs()]
    for r in runs["runs"][:3]:
        d = ok(client.get(f"/api/batches/{r['run_id']}"))
        assert d["run_id"] == r["run_id"] and {"status", "steps", "errors"} <= set(d)
    t = ok(client.get("/api/batches/template"))
    assert isinstance(t, dict) and t == batch.template()
    is_error(client.get("/api/batches/r-does-not-exist"), 404, "unknown_run")


def test_batch_upload_is_passed_to_the_batch_module(client, monkeypatch):
    need("citypulse.batch")
    from citypulse import batch
    seen = {}

    def fake_submit(path, filename=None):
        seen.update(path=path, filename=filename, data=open(path, "rb").read())
        return {"run_id": "r20261115-0000-test", "filename": filename, "status": "queued", "steps": [], "errors": []}
    monkeypatch.setattr(batch, "submit", fake_submit)
    payload = b'[{"text": "Die Seilbahn ist zu teuer", "published_at": "2026-11-03"}]'
    r = ok(client.post("/api/batches", files={"file": ("new_posts.json", payload, "application/json")}))
    assert r["run_id"] == "r20261115-0000-test" and r["status"] == "queued"
    assert seen["filename"] == "new_posts.json" and seen["data"] == payload and seen["path"].endswith(".json")

    def dup_submit(path, filename=None):
        raise batch.DuplicateUpload("r20261114-2359-ab12")
    monkeypatch.setattr(batch, "submit", dup_submit)
    e = is_error(client.post("/api/batches", files={"file": ("new_posts.json", payload, "application/json")}), 409, "duplicate_upload")
    assert e["run_id"] == "r20261114-2359-ab12"
    is_error(client.post("/api/batches", files={"file": ("empty.json", b"", "application/json")}), 422, "empty_file")
    is_error(client.post("/api/batches"), 422, "invalid_request")

    def boom(path, filename=None):
        raise RuntimeError("disk full")
    monkeypatch.setattr(batch, "submit", boom)
    is_error(client.post("/api/batches", files={"file": ("x.json", payload, "application/json")}), 503, "batch_unavailable")
