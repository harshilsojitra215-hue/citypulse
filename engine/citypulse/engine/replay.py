"""Historical replay and emerging-concern detection.

Freeze the system at a cutoff date. Every later claim arrives in its real order. For each arriving claim only OLDER
claims are candidates (the cached candidate index was built that way and is asserted again here). Decisions:
  familiar   its best same-project match clears the "familiar" cut-off -> counts on that argument
  ambiguous  score between the two cut-offs -> shown as "needs review", never as an established finding
  opens_new  no equivalent older claim -> opens a new concern
  joins_new  matches a claim that itself belongs to a concern opened during the replay
A new concern becomes "new_emerging" once it has claims from 2 independent voices; before that it is "new_single".
Known arguments are tested for "gaining" with a Poisson rate test against their own past in the same project.

The same function serves an uploaded batch: then the stream is the batch's claims instead of "everything after the cutoff".
"""
import threading
import numpy as np, pandas as pd
from scipy.stats import poisson_means_test
from .. import config
from . import store, matcher, crosscity
from .search import match_dict, claim_card

_cache, _lock = {}, threading.Lock()


def clear_cache():
    with _lock:
        _cache.clear()


def cutoffs():
    return dict(cutoffs=["2026-07-01", "2026-08-01", "2026-09-01"], earliest_allowed=config.EARLIEST_REPLAY_CUTOFF,
                reason="the matcher was trained and calibrated only on claims published before this date; an earlier cutoff would let it use knowledge from the future")


def _shingles(S, doc_id, memo):
    if doc_id not in memo:
        w = str(S.posts_by_id.excerpt.get(doc_id, "")).lower().split()
        memo[doc_id] = {" ".join(w[i:i + 5]) for i in range(max(len(w) - 4, 1))}
    return memo[doc_id]


def _n_voices(S, cids, memo):
    """Independent voices: one per author hash or publishing domain; the same post, or re-published copies of one article
    (their opening text overlaps), count once."""
    cids = list(cids)
    par = list(range(len(cids)))
    def f(i):
        while par[i] != i:
            i = par[i]
        return i
    rows = [S.claims_by_cid.loc[c] for c in cids]
    for i in range(len(cids)):
        for j in range(i):
            a, b = rows[i], rows[j]
            sa, sb = _shingles(S, a.doc_id, memo), _shingles(S, b.doc_id, memo)
            if a.voice == b.voice or a.doc_id == b.doc_id or len(sa & sb) / max(len(sa | sb), 1) >= 0.3:
                par[f(i)] = f(j)
    return len({f(i) for i in range(len(cids))})


def run(project=None, cutoff=None, run_id=None) -> dict:
    S = store.get()
    cutoff = cutoff or config.EARLIEST_REPLAY_CUTOFF
    if run_id is None and cutoff < config.EARLIEST_REPLAY_CUTOFF:
        raise ValueError(f"cutoff must be {config.EARLIEST_REPLAY_CUTOFF} or later: " + cutoffs()["reason"])
    key = (project, cutoff, run_id, S.data_version)
    with _lock:
        if key in _cache:
            return _cache[key]
    T0 = pd.Timestamp(cutoff, tz="UTC")
    C, CB = S.claims, S.claims_by_cid
    if run_id is not None:
        in_stream = (C.run_id == run_id)
    else:
        in_stream = (C.ts >= T0) & (C.run_id == "base")
    if project:
        in_stream &= (C.project == project)
    stream = C[in_stream].sort_values("ts", kind="stable")
    stream_set = set(stream.cid)
    thr = S.matcher_cfg.get("thresholds", {})
    t_fam, t_new, t_pair = thr.get("familiar", 0.5), thr.get("new", 0.2), thr.get("pair_same", 0.5)
    P = S.pair_scores[S.pair_scores.qid.isin(stream_set) & S.pair_scores.cand.isin(S.cidx)]
    ts_of = CB.ts
    # no look-ahead, checked on every call: a candidate must be older than the claim it is compared with
    if len(P):
        assert (ts_of.reindex(P.cand).to_numpy() < ts_of.reindex(P.qid).to_numpy()).all(), "replay candidate from the future"
    by_q = {q: g.sort_values("p_same", ascending=False) for q, g in P.groupby("qid")}
    fam_col = "family_frozen" if "family_frozen" in C.columns else "family_id"
    parent, memo, steps, grp_members, raised_at, decisions = {}, {}, [], {}, {}, {}
    def root(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x
    for i, q in enumerate(stream.cid):
        g = by_q.get(q)
        sp = g[g.same_project.astype(bool)] if g is not None else None
        best = sp.iloc[0] if sp is not None and len(sp) else None
        bp = float(best.p_same) if best is not None and not pd.isna(best.p_same) else 0.0
        scored = best is not None and not pd.isna(best.p_same)
        if scored and bp >= t_fam:
            r = root(best.cand)
            parent[q] = r
            decision = "joins_new" if r in stream_set else "familiar"
        elif scored and bp >= t_new:
            parent[q] = q; decision = "ambiguous"
        else:
            parent[q] = q; decision = "opens_new" if (scored or g is None or sp is None or not len(sp)) else "ambiguous"
        decisions[q] = decision
        r = root(q)
        raised = []
        if r in stream_set:
            grp_members.setdefault(r, []).append(q)
            if r not in raised_at and len(grp_members[r]) >= 2 and _n_voices(S, grp_members[r], memo) >= 2:
                raised_at[r] = (i, CB.ts[q]); raised = [f"g:{r}"]
        steps.append(dict(i=i, ts=CB.ts[q].isoformat(), claim=claim_card(q), decision=decision,
                          matched=match_dict(best.cand, best.p_same, best.p_rel, best.cos, getattr(best, "score_source", "cached")) if best is not None else None,
                          concern_id=f"g:{r}" if r in stream_set else f"f:{CB[fam_col][r]}", raised=raised, novelty_score=round(1 - bp, 4)))
    # ---------- concerns ----------
    concerns = []
    rel_thr = thr.get("related", 0.5)
    for r, members in grp_members.items():
        m_df = P[P.qid.isin(members)]
        nv = _n_voices(S, members, memo)
        amb = decisions[r] == "ambiguous"
        state = "ambiguous" if amb else ("new_emerging" if r in raised_at else "new_single")
        oth = m_df[~m_df.same_project.astype(bool)].sort_values("p_same", ascending=False).drop_duplicates("cand")
        eq = oth[oth.p_same >= t_pair].head(4)
        rel = oth[(oth.p_same < t_pair) & (oth.p_rel >= rel_thr)].head(2)
        cases = [crosscity.case(x.cand, x.p_same, x.p_rel) for x in pd.concat([eq, rel]).itertuples()]
        root_best = by_q[r][by_q[r].same_project.astype(bool)].head(2) if r in by_q else P.head(0)
        # other replay claims that are related (not equivalent) to this concern: shown next to it, never counted in it
        rp = P[((P.qid.isin(members)) | (P.cand.isin(members))) & P.same_project.astype(bool) & (P.p_same < t_fam) & (P.p_rel >= rel_thr)]
        rel_new = []
        for x in rp.sort_values("p_rel", ascending=False).itertuples():
            o = x.cand if x.qid in members else x.qid
            if o in stream_set and o not in members and o not in [d["cid"] for d in rel_new]:
                rel_new.append(match_dict(o, x.p_same, x.p_rel, x.cos, "cached"))
        first = CB.loc[members[0]]
        d0 = pd.Timestamp(first.date)
        near = S.events[(S.events.project == first.project)].copy()
        near = near[(pd.to_datetime(near.date, errors="coerce") - d0).abs() <= pd.Timedelta(days=14)].sort_values("date")
        bp = 1 - steps[[s["claim"]["cid"] for s in steps].index(r)]["novelty_score"]
        concerns.append(dict(
            concern_id=f"g:{r}", state=state, label=first.claim, project=first.project, project_name=first.project_name,
            first_seen=str(first.date)[:10], flagged_at=raised_at[r][1].strftime("%Y-%m-%d") if r in raised_at else None,
            flagged_at_step=raised_at[r][0] if r in raised_at else None, n_claims=len(members), n_voices=nv,
            polarity=CB.polarity[members].value_counts().to_dict(), topic=first.topic,
            uncertainty=dict(novelty_score=round(1 - bp, 4), best_older_p_same=round(bp, 4), cutoffs=dict(new=t_new, familiar=t_fam),
                             note=("score lies between the two cut-offs: may be a variant of a known argument" if amb else
                                   "no equivalent among the nearest older claims of this project") +
                                  ("" if nv >= 2 else "; one voice only so far")),
            new_anywhere=bool(eq.empty), claims=[match_dict(c, *( (by_q[c].iloc[0].p_same, by_q[c].iloc[0].p_rel, by_q[c].iloc[0].cos) if c in by_q and c != r else (None, None, None)), "cached") for c in members],
            related_new_claims=rel_new[:8], closest_older=[match_dict(x.cand, x.p_same, x.p_rel, x.cos, "cached") for x in root_best.itertuples()],
            elsewhere=cases, events_nearby=[dict(date=e.date, title=e.title_en, verified=e.verified, source=e.source_url) for e in near.itertuples()]))
    # known arguments: gaining or recurring
    known = [q for q in stream.cid if root(q) not in stream_set]
    if known:
        kdf = pd.DataFrame(dict(cid=known, fam=[CB[fam_col][root(q)] for q in known], project=CB.project[known].values))
        end = stream.ts.max()
        for (proj, fam), g in kdf.groupby(["project", "fam"]):
            hist = C[(C.project == proj) & (C.ts < (T0 if run_id is None else stream.ts.min())) & (C[fam_col] == fam)]
            start = T0 if run_id is None else stream.ts.min()
            months_new = max((end - start).days / 30.4, 1.0)
            pj = C[(C.project == proj) & (C.ts < start)]
            months_old = max((start - pj.ts.min()).days / 30.4, 1.0) if len(pj) else 1.0
            k_new, k_old = len(g), len(hist)
            pval = float(poisson_means_test(k_new, months_new, k_old, months_old, alternative="greater").pvalue) if k_new >= 3 else None
            gaining = pval is not None and pval < 0.01
            members = list(g.cid)
            name = hist.family_name.iloc[0] if len(hist) and fam_col == "family_id" else (CB.claim[fam] if fam in CB.index else (hist.claim.iloc[0] if len(hist) else CB.claim[root(members[0])]))
            first = CB.loc[members[0]]
            concerns.append(dict(
                concern_id=f"f:{proj}:{fam}", state="gaining" if gaining else "recurring", label=name, project=proj, project_name=first.project_name,
                first_seen=str(hist.date.min())[:10] if len(hist) else None, flagged_at=None, n_claims=k_new, n_voices=_n_voices(S, members[:40], memo),
                polarity=CB.polarity[members].value_counts().to_dict(), topic=first.topic,
                uncertainty=dict(per_month_now=round(k_new / months_new, 2), per_month_before=round(k_old / months_old, 2), n_before=k_old, p_value=None if pval is None else round(pval, 4),
                                 note="Poisson rate test against this argument's own past in this project; several arguments are tested, so treat p near 0.01 as weak" if pval is not None else "fewer than 3 claims in the window: no test"),
                new_anywhere=False, claims=[match_dict(c, by_q[c].iloc[0].p_same, by_q[c].iloc[0].p_rel, by_q[c].iloc[0].cos, "cached") for c in members[:30]],
                related_new_claims=[], closest_older=[], elsewhere=[], events_nearby=[]))
    order = {"new_emerging": 0, "ambiguous": 1, "new_single": 2, "gaining": 3, "recurring": 4}
    concerns.sort(key=lambda d: (order[d["state"]], -d["n_voices"], -d["n_claims"]))
    wk = pd.DataFrame(dict(week=(stream.ts.dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")).values,
                           d=[decisions[q] for q in stream.cid])) if len(stream) else pd.DataFrame(columns=["week", "d"])
    activity = [dict(week=w, n=len(g), new=int(g.d.isin(["opens_new", "joins_new"]).sum()), ambiguous=int((g.d == "ambiguous").sum()),
                     familiar=int((g.d == "familiar").sum())) for w, g in wk.groupby("week")]
    before = C[(C.ts < T0) & ((C.project == project) if project else True)] if run_id is None else C[~in_stream & ((C.project == project) if project else True)]
    topf = before[before.cluster_all >= 0].groupby(["family_id", "family_name"]).size().sort_values(ascending=False).head(8)
    out = dict(project=project, cutoff=cutoff if run_id is None else None, run_id=run_id, simulation=run_id is None,
               mode="cached-scores" if run_id is None else "batch-run", model_version=S.matcher_cfg.get("version"),
               label="HISTORICAL SIMULATION: decisions use only claims published before each replayed claim; model scores were computed once and cached" if run_id is None else "Claims of an uploaded batch, matched against everything published before them",
               known_before=dict(n_claims=int(len(before)), n_posts=int(before.doc_id.nunique()),
                                 top_families=[dict(family_id=f, name=n, n=int(v)) for (f, n), v in topf.items()]),
               counts=dict(n_claims=len(stream), familiar=sum(d == "familiar" for d in decisions.values()), joins_new=sum(d == "joins_new" for d in decisions.values()),
                           opens_new=sum(d == "opens_new" for d in decisions.values()), ambiguous=sum(d == "ambiguous" for d in decisions.values()),
                           concerns_new_emerging=sum(c["state"] == "new_emerging" for c in concerns),
                           concerns_flagged=len(raised_at),   # 2+ independent voices, including variants that need review
                           concerns_flagged_review=sum(c["state"] == "ambiguous" and c["flagged_at"] is not None for c in concerns)),
               thresholds=dict(familiar=t_fam, new=t_new, pair_same=t_pair, related=rel_thr),
               steps=steps, concerns=concerns, activity=activity)
    with _lock:
        _cache[key] = out
    return out


def concerns(project=None, cutoff=None, state=None, run_id=None) -> list:
    S = store.get()
    projs = [project] if project else [p for p in S.meta.get("arguments_available_for", []) ]
    out = []
    for p in projs:
        out += run(p, cutoff, run_id)["concerns"]
    return [c for c in out if state is None or c["state"] == state]


def live_check(cid) -> dict:
    """Re-run the matcher now, on this machine, for one claim's cached candidates, and compare with the cached scores."""
    S = store.get()
    P = S.pair_scores[(S.pair_scores.qid == cid) & S.pair_scores.cand.isin(S.cidx)]
    cached = [dict(cand=r.cand, p_same=round(float(r.p_same), 4)) for r in P.itertuples()]
    if not matcher.available():
        return dict(available=False, reason=matcher.status()["reason"], cached=cached, live=[], max_abs_diff=None)
    q = S.claims_by_cid.loc[[cid] * len(P)].reset_index(drop=True)
    c = S.claims_by_cid.loc[P.cand].reset_index(drop=True)
    X = matcher.score(q, c, P.cos.values, with_meta=True)
    live = [dict(cand=cand, p_same=round(float(p), 4)) for cand, p in zip(P.cand, X.p_same)]
    return dict(available=True, device=matcher.status()["device"], cached=cached, live=live,
                max_abs_diff=round(float(np.abs(X.p_same.values - P.p_same.values).max()), 4) if len(P) else None)
