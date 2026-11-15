"""Semantic retrieval (bge-m3 embeddings through Ollama) and argument matching for free text and stored claims."""
import json, re, urllib.request, hashlib
import numpy as np, pandas as pd
from .. import config
from . import store, matcher

_cache = {}


def embed(texts):
    """bge-m3 vectors, L2-normalised. Raises RuntimeError when the embedder cannot be reached."""
    texts = [t[:2000] for t in texts]
    todo = [t for t in dict.fromkeys(texts) if t not in _cache]
    try:
        for i in range(0, len(todo), 32):
            body = json.dumps({"model": config.EMBED_MODEL, "input": todo[i:i + 32], "truncate": True}).encode()
            req = urllib.request.Request(config.OLLAMA_URL + "/api/embed", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                for t, v in zip(todo[i:i + 32], json.load(r)["embeddings"]):
                    v = np.asarray(v, dtype=np.float32)
                    _cache[t] = v / (np.linalg.norm(v) + 1e-9)
    except Exception as e:
        raise RuntimeError(f"embedder unavailable ({config.EMBED_MODEL} at {config.OLLAMA_URL}): {e!r}"[:300])
    return np.vstack([_cache[t] for t in texts]) if texts else np.zeros((0, 1024), dtype=np.float32)


def embedder_status():
    try:
        embed(["ping"])
        return dict(available=True, backend=f"ollama:{config.EMBED_MODEL}")
    except Exception as e:
        return dict(available=False, backend=f"ollama:{config.EMBED_MODEL}", reason=str(e)[:200])


def claim_card(cid) -> dict:
    r = store.get().claims_by_cid.loc[cid]
    return dict(cid=r.cid, claim=r.claim, project=r.project, project_name=r.project_name, date=str(r.date)[:10], channel=r.channel,
                domain=r.domain, url=r.url, topic=r.topic, polarity=r.polarity, doc_id=r.doc_id, voice=r.voice,
                family_id=r.family_id, family_name=r.family_name, run_id=r.run_id)


def match_dict(cid, p_same=None, p_rel=None, cos=None, source="cached", text_only=False) -> dict:
    d = claim_card(cid)
    f = lambda x: None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 4)
    d.update(relation=matcher.relation(p_same, p_rel, text_only) if source != "baseline-cosine" else "unscored",
             p_same=f(p_same), p_related=f(p_rel), cos=f(cos), score_source=source)
    return d


def _mask(S, project=None, topic=None):
    m = np.ones(len(S.claims), dtype=bool)
    if project:
        m &= (S.claims.project == project).values
    if topic:
        m &= (S.claims.topic == topic).values
    return m


def _score_text(S, text, idx, cos):
    """Free text has no extracted topic/polarity, so the text-only calibration is used."""
    c = S.claims.iloc[idx]
    q = pd.DataFrame(dict(claim=[text] * len(c)))
    X = matcher.score(q, c, cos, with_meta=False)
    return X.p_same.values, X.p_rel.values


def semantic(text, project=None, topic=None, k=20) -> dict:
    S = store.get()
    m = _mask(S, project, topic)
    try:
        v = embed([text])[0]
        sims = S.emb @ v
        sims[~m] = -1
        idx = np.argsort(-sims)[:k]
        idx = idx[sims[idx] > -1]
        mode = "semantic"
    except RuntimeError:
        toks = set(re.findall(r"\w{3,}", text.lower()))
        sc = S.claims.claim.str.lower().map(lambda c: len(toks & set(re.findall(r"\w{3,}", c)))).values * m
        idx = np.argsort(-sc)[:k]
        idx = idx[sc[idx] > 0]
        sims, mode = sc / max(len(toks), 1), "keyword-fallback"
    if matcher.available() and len(idx):
        ps, pr = _score_text(S, text, idx, sims[idx])
        res = [match_dict(S.claims.cid.iloc[i], ps[n], pr[n], sims[i], "live", True) for n, i in enumerate(idx)]
    else:
        res = [match_dict(S.claims.cid.iloc[i], None, None, sims[i], "baseline-cosine") for i in idx]
    return dict(mode=mode, matcher_mode=matcher.status()["mode"], query=text, results=res)


def match_text(text, project=None) -> dict:
    """Is this free-text argument already known? Looks at the 10 nearest claims in the project and 10 elsewhere."""
    S = store.get()
    try:
        v = embed([text])[0]
    except RuntimeError as e:
        return dict(mode="unavailable", novelty=dict(state="unknown", note=str(e)), matches=[], elsewhere=[])
    sims = S.emb @ v
    order = np.argsort(-sims)
    proj = S.claims.project.values
    own = [i for i in order if project is None or proj[i] == project][:10]
    other = [i for i in order if project is not None and proj[i] != project][:10]
    idx = np.array(own + other, dtype=int)
    t = S.matcher_cfg.get("thresholds", {})
    if not matcher.available():
        return dict(mode="baseline-cosine", novelty=dict(state="unknown", note="matcher model not loaded on this machine; showing similarity only"),
                    matches=[match_dict(S.claims.cid.iloc[i], None, None, sims[i], "baseline-cosine") for i in own], elsewhere=[])
    ps, pr = _score_text(S, text, idx, sims[idx])
    own_m = sorted([match_dict(S.claims.cid.iloc[i], ps[n], pr[n], sims[i], "live", True) for n, i in enumerate(idx[:len(own)])], key=lambda d: -d["p_same"])
    best = max([d["p_same"] for d in own_m], default=0.0)
    from . import crosscity
    els = [crosscity.case(S.claims.cid.iloc[i], ps[len(own) + n], pr[len(own) + n], "live", True) for n, i in enumerate(idx[len(own):])]
    els = sorted([e for e in els if e["relation"] != "unrelated"], key=lambda d: -d["p_same"])[:5]
    return dict(mode="live", query=text, project=project,
                novelty=dict(state=matcher.novelty_state(best, True), score=round(1 - best, 4), best_p_same=round(best, 4),
                             cutoffs=dict(new=t.get("text_new"), familiar=t.get("text_familiar")),
                             note="familiar = an equivalent older claim was found; new = none among the 10 nearest; ambiguous = needs review"),
                matches=[d for d in own_m if d["relation"] != "unrelated"][:10], elsewhere=els)


def claim_matches(cid) -> dict:
    """Equivalent and related claims of a stored claim, from cached model scores (older candidates and later claims that point to it)."""
    S = store.get()
    if cid not in S.cidx:
        raise KeyError(cid)
    P = S.pair_scores
    a = P[P.qid == cid][["cand", "same_project", "cos", "p_same", "p_rel"]].rename(columns={"cand": "other"})
    b = P[P.cand == cid][["qid", "same_project", "cos", "p_same", "p_rel"]].rename(columns={"qid": "other"})
    allm = pd.concat([a, b]).sort_values("p_same", ascending=False).drop_duplicates("other")
    allm = allm[allm.other.isin(S.cidx)]
    ms = [dict(match_dict(r.other, r.p_same, r.p_rel, r.cos, "cached"), same_project=bool(r.same_project)) for r in allm.itertuples()]
    from . import crosscity
    post = S.posts_by_id.loc[S.claims_by_cid.loc[cid].doc_id] if S.claims_by_cid.loc[cid].doc_id in S.posts_by_id.index else None
    return dict(claim=claim_card(cid), doc_id=S.claims_by_cid.loc[cid].doc_id,
                equivalent=[m for m in ms if m["relation"] == "equivalent" and m["same_project"]],
                related=[m for m in ms if m["relation"] == "related" and m["same_project"]][:15],
                elsewhere=crosscity.similar(cid=cid)["cases"], mode="cached" if len(P) else "unscored",
                note="equivalent = the matcher judges both claims to make the same argument; related = same sub-issue, different point")
