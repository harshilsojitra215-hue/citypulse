"""Engine tests on the real data bundle: schema, ids, no look-ahead, novelty states, evidence links, matching."""
import re
import numpy as np, pandas as pd, pytest
from citypulse import config
from citypulse.engine import store, replay, search, crosscity, matcher

pytestmark = pytest.mark.skipif(not (config.DATA / "posts.parquet").exists(), reason=f"data bundle missing in {config.DATA}")
PROJECT = "heilbronn_cablecar"


@pytest.fixture(scope="module")
def S():
    return store.get()


# ---------- data loading and schema ----------
def test_bundle_schema(S):
    for col in ["doc_id", "published_at", "date", "channel", "domain", "url", "excerpt", "project", "stance", "voice", "dup_key", "is_first_copy", "run_id"]:
        assert col in S.posts.columns, col
    for col in ["cid", "doc_id", "claim", "project", "ts", "topic", "polarity", "voice", "family_id", "run_id"]:
        assert col in S.claims.columns, col
    assert len(S.emb) == len(S.claims) and S.emb.shape[1] == 1024
    assert np.allclose(np.linalg.norm(S.emb[:200], axis=1), 1, atol=1e-3)
    assert S.claims.cid.is_unique
    assert set(S.claims.doc_id) <= set(S.posts.doc_id), "every claim must point to a stored post"


def test_no_personal_identifiers(S):
    banned = {"author", "authors", "author_name", "handle", "username", "user", "author_hash"}
    assert not banned & set(S.posts.columns) and not banned & set(S.claims.columns)
    assert S.posts.voice.map(lambda v: bool(re.fullmatch(r"[0-9a-f]{6}", str(v)))).all()
    assert S.posts.excerpt.str.len().max() <= 400


def test_dedup_and_stable_ids(S):
    base = S.posts[S.posts.run_id == "base"]
    first = base[base.is_first_copy]
    assert first.dup_key.is_unique, "exactly one first copy per distinct text"
    assert first.doc_id.is_unique
    assert (base.groupby("dup_key").size() <= base.groupby("dup_key").dup_count.first()).all()
    # ids are stable across loads
    again = pd.read_parquet(config.DATA / "claims.parquet", columns=["cid", "doc_id", "claim"])
    assert again.set_index("cid").claim.to_dict() == S.claims[S.claims.run_id == "base"].set_index("cid").claim.to_dict()


def test_project_filter_query(S):
    n_sql = S.sql("select count(*) n from posts where project = ? and is_first_copy and date >= '2026-07-01'", [PROJECT])[0]["n"]
    n_pd = int(((S.posts.project == PROJECT) & S.posts.is_first_copy & (S.posts.date >= "2026-07-01")).sum())
    assert n_sql == n_pd > 0


# ---------- chronological replay without look-ahead ----------
def test_cached_candidates_are_older(S):
    P = S.pair_scores
    assert len(P) > 0
    ts = S.claims_by_cid.ts
    assert (ts.reindex(P.cand).to_numpy() < ts.reindex(P.qid).to_numpy()).all()
    doc = S.claims_by_cid.doc_id
    assert (doc.reindex(P.cand).values != doc.reindex(P.qid).values).all(), "a post is never matched against itself"


def test_replay_order_and_cutoff(S):
    r = replay.run(PROJECT, "2026-07-01")
    ts = [s["ts"] for s in r["steps"]]
    assert ts == sorted(ts) and len(ts) == r["counts"]["n_claims"] > 0
    assert min(ts) >= "2026-07-01"
    for s in r["steps"]:
        if s["matched"]:
            assert S.claims_by_cid.ts[s["matched"]["cid"]] < pd.Timestamp(s["ts"])
    assert r["simulation"] is True and "SIMULATION" in r["label"]
    before = S.claims[(S.claims.project == PROJECT) & (S.claims.ts < pd.Timestamp("2026-07-01", tz="UTC"))]
    assert r["known_before"]["n_claims"] == len(before)


def test_replay_rejects_cutoff_inside_training_period():
    with pytest.raises(ValueError):
        replay.run(PROJECT, "2026-03-01")


def test_later_claims_do_not_change_earlier_evidence(S):
    """The match found for a claim depends only on older claims: it is identical whichever cutoff the replay starts from."""
    a = {s["claim"]["cid"]: s for s in replay.run(PROJECT, "2026-07-01")["steps"]}
    b = {s["claim"]["cid"]: s for s in replay.run(PROJECT, "2026-08-01")["steps"]}
    assert b and set(b) <= set(a)
    for cid, s in b.items():
        assert s["novelty_score"] == a[cid]["novelty_score"]
        assert (s["matched"] or {}).get("cid") == (a[cid]["matched"] or {}).get("cid")


# ---------- novelty detection ----------
def test_states_follow_thresholds(S):
    r = replay.run(PROJECT, "2026-07-01")
    t = r["thresholds"]
    assert 0 <= t["new"] <= t["familiar"] <= 1
    for s in r["steps"]:
        p = 1 - s["novelty_score"]
        if s["decision"] in ("familiar", "joins_new"):
            assert p >= t["familiar"] - 1e-6
        if s["decision"] == "opens_new":
            assert p < t["new"] + 1e-6
        if s["decision"] == "ambiguous":
            assert t["new"] - 1e-6 <= p < t["familiar"] + 1e-6
    valid = {"new_emerging", "new_single", "ambiguous", "gaining", "recurring"}
    for c in r["concerns"]:
        assert c["state"] in valid
        if c["state"] == "new_emerging":
            assert c["n_voices"] >= 2 and c["n_claims"] >= 2 and c["flagged_at"] >= c["first_seen"]
        if c["state"] == "new_single":
            assert c["flagged_at"] is None
    assert sum(len(c["claims"]) for c in r["concerns"] if c["concern_id"].startswith("g:")) == r["counts"]["opens_new"] + r["counts"]["joins_new"] + r["counts"]["ambiguous"]


def test_one_post_is_one_voice(S):
    doc = S.claims[S.claims.project == PROJECT].groupby("doc_id").cid.apply(list)
    multi = [c for c in doc if len(c) >= 2][0]
    assert replay._n_voices(S, multi, {}) == 1


# ---------- evidence traceability ----------
def test_every_finding_links_to_a_stored_post(S):
    r = replay.run(PROJECT, "2026-07-01")
    cards = [s["claim"] for s in r["steps"]] + [c for k in r["concerns"] for c in k["claims"]] + [e["claim"] for k in r["concerns"] for e in k["elsewhere"]]
    assert cards
    for c in cards:
        assert c["doc_id"] in S.posts_by_id.index
        p = S.posts_by_id.loc[c["doc_id"]]
        assert p.date == c["date"] or str(p.date)[:10] == c["date"]
        assert isinstance(p.url, str) and p.url.startswith("http")


# ---------- matching and retrieval ----------
def test_equivalent_and_related_never_mix(S):
    cid = replay.run(PROJECT, "2026-07-01")["steps"][-1]["claim"]["cid"]
    m = search.claim_matches(cid)
    eq, rel = {x["cid"] for x in m["equivalent"]}, {x["cid"] for x in m["related"]}
    assert not eq & rel
    assert all(x["relation"] == "equivalent" for x in m["equivalent"]) and all(x["relation"] == "related" for x in m["related"])


def test_search_falls_back_to_keywords_and_says_so(S, monkeypatch):
    def down(texts):
        raise RuntimeError("embedder unavailable (test)")
    monkeypatch.setattr(search, "embed", down)
    r = search.semantic("hospital closure money cable car", project=PROJECT, k=5)
    assert r["mode"] == "keyword-fallback" and r["results"]
    assert any("hospital" in x["claim"].lower() for x in r["results"])
    assert all(x["project"] == PROJECT for x in r["results"])


def test_cross_city_cases_are_other_projects(S):
    r = replay.run(PROJECT, "2026-07-01")
    for k in r["concerns"]:
        for e in k["elsewhere"]:
            assert e["claim"]["project"] != PROJECT and "not a forecast" in e["note"]
            for ev in e["after"]:
                assert ev["date"] > e["claim"]["date"]


@pytest.mark.live
def test_semantic_search_finds_exact_claim(S):
    c = S.claims[S.claims.project == PROJECT].iloc[10]
    r = search.semantic(c.claim, project=PROJECT, k=3)
    assert r["mode"] == "semantic" and r["results"][0]["claim"] == c.claim


@pytest.mark.skipif(not (config.MODEL_DIR / "model.safetensors").exists(), reason="matcher weights not on this machine (see models/MODEL_CARD.md)")
def test_live_matcher_agrees_with_cached_scores(S):
    assert matcher.available(), matcher.status()
    pr = matcher.probs(["The cable car is too expensive"], ["The cable car costs far too much money"])
    assert pr.shape == (1, 4) and abs(pr.sum() - 1) < 1e-4 and pr[0, 0] > 0.5
    cid = replay.run(PROJECT, "2026-07-01")["steps"][5]["claim"]["cid"]
    lc = replay.live_check(cid)
    assert lc["available"] and lc["max_abs_diff"] < 0.03, lc
