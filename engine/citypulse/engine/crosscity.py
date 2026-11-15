"""Cross-city case retrieval: the same or a related argument in another project, with that project's stage at the time
and what was observed afterwards (from the sourced event timeline). Historical cases, never a forecast."""
import numpy as np, pandas as pd
from . import store, matcher


def ev_ctx(project, date) -> dict:
    S = store.get()
    e = S.events[(S.events.project == project)].sort_values("date")
    if e.empty:
        return dict(stage=None, after=[], timeline_available=False)
    d = str(date)[:10]
    b, a = e[e.date <= d], e[e.date > d]
    f = lambda r: dict(date=r.date, title=r.title_en, verified=r.verified, source=r.source_url, event_type=r.event_type)
    return dict(stage=f(b.iloc[-1]) if len(b) else None, after=[f(r) for r in a.head(2).itertuples()], timeline_available=True)


def case(cid, p_same, p_rel, source="cached", text_only=False) -> dict:
    from .search import match_dict
    m = match_dict(cid, p_same, p_rel, None, source, text_only)
    d = dict(claim={k: m[k] for k in ("cid", "claim", "project", "project_name", "date", "channel", "domain", "url", "topic", "polarity", "doc_id", "voice")},
             relation=m["relation"], p_same=m["p_same"], p_related=m["p_related"], score_source=source,
             note="historical case, not a forecast")
    d.update(ev_ctx(m["project"], m["date"]))
    return d


def similar(cid=None, text=None, project=None, k=6) -> dict:
    S = store.get()
    if cid is not None:
        if cid not in S.cidx:
            raise KeyError(cid)
        P = S.pair_scores
        a = P[(P.qid == cid) & ~P.same_project.astype(bool)][["cand", "p_same", "p_rel"]].rename(columns={"cand": "other"})
        b = P[(P.cand == cid) & ~P.same_project.astype(bool)][["qid", "p_same", "p_rel"]].rename(columns={"qid": "other"})
        m = pd.concat([a, b]).sort_values("p_same", ascending=False).drop_duplicates("other")
        m = m[m.other.isin(S.cidx)]
        cases = [case(r.other, r.p_same, r.p_rel) for r in m.itertuples()]
        cases = [c for c in cases if c["relation"] != "unrelated"][:k]
        return dict(mode="cached", cases=cases)
    from . import search
    r = search.match_text(text, project=project)
    if project is None:   # no home project: every match is a case
        cases = [case(m["cid"], m["p_same"], m["p_related"], "live", True) for m in r.get("matches", [])][:k]
        return dict(mode=r["mode"], cases=cases)
    return dict(mode=r["mode"], cases=r.get("elsewhere", [])[:k], novelty=r.get("novelty"))
