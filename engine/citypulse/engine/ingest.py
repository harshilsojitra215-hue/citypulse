"""Match newly extracted claims against everything already known (used by the batch workflow).

match_new_claims(claims_df) -> (claims_df, pair_scores_df, emb)
  claims_df needs: cid, doc_id, claim, project, ts (UTC timestamp), topic, polarity
  adds: norm, novelty_state (familiar | ambiguous | new | unscored), novelty_score, best_match_cid
Candidates for a claim are the 10 nearest OLDER claims in its project and 10 in other projects (other posts only).
Raises RuntimeError if the embedder is unreachable. If the matcher model is not on this machine, similarity is stored
and the state is "unscored": the weaker cosine baseline is never passed off as the matcher.
"""
import hashlib
import numpy as np, pandas as pd
from . import store, matcher, search

K = 10


def match_new_claims(claims_df: pd.DataFrame):
    S = store.get()
    N = claims_df.copy().reset_index(drop=True)
    N["ts"] = pd.to_datetime(N.ts, utc=True)
    N["norm"] = N.claim.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.split().str.join(" ")
    emb = search.embed(N.claim.tolist()).astype(np.float32)
    A = pd.concat([S.claims[["cid", "doc_id", "claim", "project", "ts", "topic", "polarity", "norm"]],
                   N[["cid", "doc_id", "claim", "project", "ts", "topic", "polarity", "norm"]]], ignore_index=True)
    E = np.vstack([S.emb, emb])
    t, doc, proj = A.ts.values, A.doc_id.values, A.project.values
    base_n, rows = len(S.claims), []
    for n in range(len(N)):
        qi = base_n + n
        hist = np.flatnonzero((t < t[qi]) & (doc != doc[qi]))
        if not len(hist):
            continue
        hist = A.iloc[hist].sort_values("ts").drop_duplicates("norm", keep="first").index.values
        o = hist[np.argsort(-(E[hist] @ E[qi]))]
        for same in (True, False):
            side = [j for j in o if (proj[j] == proj[qi]) == same][:K]
            rows += [(qi, j, same, r, float(E[j] @ E[qi])) for r, j in enumerate(side, 1)]
    P = pd.DataFrame(rows, columns=["qi", "ci", "same_project", "side_rank", "cos"])
    P["qid"], P["cand"] = A.cid.values[P.qi.values] if len(P) else [], A.cid.values[P.ci.values] if len(P) else []
    version = S.matcher_cfg.get("version")
    if len(P) and matcher.available():
        X = matcher.score(A.iloc[P.qi.values].reset_index(drop=True), A.iloc[P.ci.values].reset_index(drop=True), P.cos.values, with_meta=True)
        P["p_same"], P["p_rel"], P["ft_same"], P["score_source"] = X.p_same.values, X.p_rel.values, X.ft_same.values, "live"
    else:
        P["p_same"], P["p_rel"], P["ft_same"], P["score_source"] = np.nan, np.nan, np.nan, "baseline-cosine"
    P["model_version"] = version
    best = P[P.same_project].sort_values("p_same", ascending=False).drop_duplicates("qid").set_index("qid") if len(P) else pd.DataFrame()
    states, scores, bests = [], [], []
    for cid in N.cid:
        if not matcher.available():
            states.append("unscored"); scores.append(None); bests.append(None)
        elif cid in best.index:
            p = float(best.p_same[cid])
            states.append(matcher.novelty_state(p)); scores.append(round(1 - p, 4)); bests.append(best.cand[cid])
        else:
            states.append("new"); scores.append(1.0); bests.append(None)
    N["novelty_state"], N["novelty_score"], N["best_match_cid"] = states, scores, bests
    P["pid"] = [hashlib.md5((a + b).encode()).hexdigest()[:10] for a, b in zip(P.qid, P.cand)] if len(P) else []
    return N, P.drop(columns=["qi", "ci"]), emb
