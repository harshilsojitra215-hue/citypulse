"""Descriptive statistics over the stored posts and claims: overview, trends with peaks, cross-city comparison, families.

Definitions (also returned to the client in `notes`):
  * attention counts (n_posts, series n, channel_counts, top_sources) use every collected post, re-published copies included;
  * stance statistics use unique posts only (is_first_copy) and leave out passing mentions (passing);
  * opposition share = oppose / (support + oppose + mixed) among those posts, with a Wilson 95% interval and n;
  * argument statistics count claims extracted from the filtered posts.
"""
import pandas as pd
from scipy.stats import poisson

from .common import (SIDE, STANCES, Filters, filter_claims, filter_posts, has_arguments, mask, no_arguments_note, project_name,
                     records, wilson)

# Poisson surprise test of pipeline/07_peaks.py, per period instead of per day.
# window = number of earlier periods that form the baseline, min_periods = how many of them must exist,
# min_count = smallest count that can be a peak, gap = periods between two hits that still form one episode.
PEAK_PARAMS = {"week": dict(window=12, min_periods=4, min_count=5, gap=1), "month": dict(window=6, min_periods=3, min_count=5, gap=1)}
PEAK_ALPHA = 0.001
EVENT_LINK_DAYS = 7


# ---------------------------------------------------------------- stance

def stance_block(posts: pd.DataFrame) -> dict:
    counted = posts[posts.is_first_copy & ~posts.passing]
    vc = counted.stance.value_counts()
    counts = {s: int(vc.get(s, 0)) for s in STANCES}
    for k, v in vc.items():                      # labels outside the vocabulary (unclear, na) are reported, not hidden
        if k not in counts:
            counts[str(k)] = int(v)
    side = sum(counts[s] for s in SIDE)
    return {"n_posts": int(len(posts)), "n_unique_posts": int(posts.is_first_copy.sum()), "n_voices": int(posts.voice.nunique()),
            "n_counted": int(len(counted)), "n_with_stance": int(side), "stance_counts": counts,
            "opposition_share": wilson(counts["oppose"], side), "support_share": wilson(counts["support"], side)}


STANCE_NOTES = [
    "n_posts counts every collected post, including re-published copies of the same text (attention). n_unique_posts counts each text once.",
    "Stance figures (stance_counts, n_with_stance, opposition_share, the stance columns of monthly / series) count unique posts only "
    "and leave out posts that mention the project only in passing.",
    "opposition_share = oppose / (support + oppose + mixed): the share of opposing posts among posts that take a side. "
    "lo and hi are a Wilson 95% interval, n is the number of posts that take a side, k the number that oppose.",
    "n_voices counts independent sources (an author hash or a publishing domain).",
    "Stance and tone are AI labels (codebook_v1), not human-validated. This is observable online debate, not a representative poll.",
]


# ---------------------------------------------------------------- arguments

def topic_shares(claims: pd.DataFrame) -> list:
    if len(claims) == 0:
        return []
    t = pd.crosstab(claims.topic, claims.polarity)
    posts_per_topic = claims.groupby("topic").doc_id.nunique()
    total = int(len(claims))
    out = []
    for topic, row in t.iterrows():
        n = int(row.sum())
        out.append({"topic": topic, "n": n, "share": round(n / total, 4), "pro": int(row.get("pro", 0)), "contra": int(row.get("contra", 0)),
                    "neutral": int(row.get("neutral", 0)), "n_posts": int(posts_per_topic.get(topic, 0))})
    return sorted(out, key=lambda r: (-r["n"], r["topic"]))


def is_family(claims: pd.DataFrame) -> pd.Series:
    """Claims that belong to an argument family (not a single claim on its own)."""
    return claims.family_id.notna() & ~claims.family_id.astype(str).str.startswith("solo:")


def family_table(st, claims: pd.DataFrame, spread: pd.DataFrame | None = None, only_families: bool = True) -> list:
    """One row per argument family among `claims`. `by_project` is counted on `spread` (default: the same claims)."""
    c = claims[is_family(claims)] if only_families else claims
    if len(c) == 0:
        return []
    spread = c if spread is None else spread
    g = c.groupby("family_id")
    agg = g.agg(name=("family_name", "first"), n=("cid", "size"), n_voices=("voice", "nunique"), n_posts=("doc_id", "nunique"),
                first_seen=("date", "min"), last_seen=("date", "max"))
    main_topic = g.topic.agg(lambda s: s.mode().iloc[0])
    pol = pd.crosstab(c.family_id, c.polarity)
    bp = pd.crosstab(spread.family_id, spread.project)
    names = dict(zip(st.families.family_id, st.families.name))
    out = []
    for fid, r in agg.iterrows():
        n = int(r.n)
        pro, contra = int(pol.at[fid, "pro"]) if "pro" in pol else 0, int(pol.at[fid, "contra"]) if "contra" in pol else 0
        neutral = int(pol.at[fid, "neutral"]) if "neutral" in pol else 0
        by_project = {p: int(v) for p, v in bp.loc[fid].items() if v > 0} if fid in bp.index else {}
        out.append({"family_id": fid, "name": names.get(fid) or r["name"], "n": n, "main_topic": main_topic[fid],
                    "pro": pro, "contra": contra, "neutral": neutral,
                    "pro_share": round(pro / n, 4), "contra_share": round(contra / n, 4),
                    "by_project": by_project, "first_seen": r.first_seen, "last_seen": r.last_seen,
                    "n_voices": int(r.n_voices), "n_posts": int(r.n_posts)})
    return sorted(out, key=lambda r: (-r["n"], r["family_id"]))


ARGUMENT_NOTES = [
    "Argument figures count claims (one-line arguments extracted from posts). pro / contra / neutral are numbers of claims; "
    "pro_share and contra_share are their share of the family's claims.",
    "An argument family groups claims the argument map put together; claims on their own (family_id 'solo:…') are not families.",
]


# ---------------------------------------------------------------- time series and peaks

def period_of(dates: pd.Series, granularity: str) -> pd.Series:
    """month: YYYY-MM. week: the Monday of the calendar week (computed from the post date)."""
    if granularity == "month":
        return dates.str.slice(0, 7)
    d = pd.to_datetime(dates)
    return (d - pd.to_timedelta(d.dt.day_of_week, unit="D")).dt.strftime("%Y-%m-%d")


def all_periods(first: str, last: str, granularity: str) -> list:
    if granularity == "month":
        return [str(p) for p in pd.period_range(first[:7], last[:7], freq="M")]
    a, b = pd.Timestamp(first), pd.Timestamp(last)
    a, b = a - pd.Timedelta(days=a.weekday()), b - pd.Timedelta(days=b.weekday())
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(a, b, freq="7D")]


def period_bounds(period: str, granularity: str):
    if granularity == "month":
        p = pd.Period(period, freq="M")
        return p.start_time.normalize(), p.end_time.normalize()
    a = pd.Timestamp(period)
    return a, a + pd.Timedelta(days=6)


def series(posts: pd.DataFrame, granularity: str, key: str = "period") -> list:
    """Per period: n = all collected posts; stance columns = unique posts that are not passing mentions. Empty periods are kept."""
    if len(posts) == 0:
        return []
    per = period_of(posts.date, granularity)
    counted = posts.is_first_copy & ~posts.passing
    n = per.groupby(per).size()
    n_unique = per[posts.is_first_copy].groupby(per[posts.is_first_copy]).size()
    st = pd.crosstab(per[counted], posts.stance[counted])
    out = []
    for p in all_periods(posts.date.min(), posts.date.max(), granularity):
        row = {key: p, "n": int(n.get(p, 0)), "n_unique": int(n_unique.get(p, 0))}
        for s in STANCES:
            row[s] = int(st.at[p, s]) if (p in st.index and s in st.columns) else 0
        row["n_counted"] = int(st.loc[p].sum()) if p in st.index else 0
        if key != "period":
            row["period"] = p
        out.append(row)
    return out


def event_refs(df: pd.DataFrame, st) -> list:
    out = []
    for r in records(df):
        out.append({"date": r.get("date"), "title": r.get("title_en"), "event_type": r.get("event_type"), "verified": r.get("verified"),
                    "source_url": r.get("source_url"), "source_name": r.get("source_name"), "project": r.get("project"),
                    "project_name": project_name(st, r.get("project")), "detail": r.get("detail"), "date_precision": r.get("date_precision")})
    return out


def peaks(st, f: Filters, granularity: str) -> list:
    """Periods with significantly more posts than the periods before (Poisson surprise test, as in pipeline/07_peaks.py).

    The baseline uses history before `from`, so the date filters only decide which peaks are reported.
    """
    P = PEAK_PARAMS[granularity]
    hist = filter_posts(st, f.without("from_", "to"))
    if len(hist) == 0:
        return []
    per = period_of(hist.date, granularity)
    idx = all_periods(st.posts.date.min(), st.posts.date.max(), granularity)
    s = per.groupby(per).size().reindex(idx, fill_value=0)
    prior = s.shift(1).rolling(P["window"], min_periods=P["min_periods"]).mean()
    lam = prior.fillna(0) + 0.1
    pval = pd.Series(poisson.sf(s.values - 1, lam.values), index=s.index)
    hit = (pval < PEAK_ALPHA) & (s >= P["min_count"]) & prior.notna()      # no peak without a baseline (first periods of the data)
    pos = [i for i, h in enumerate(hit.values) if h]
    episodes, cur = [], []
    for i in pos:
        if cur and i - cur[-1] > P["gap"]:
            episodes.append(cur)
            cur = []
        cur.append(i)
    if cur:
        episodes.append(cur)
    out = []
    for ep in episodes:
        top = s.iloc[ep[0]:ep[-1] + 1].idxmax()
        if (f.from_ and period_bounds(top, granularity)[1].strftime("%Y-%m-%d") < f.from_) or \
                (f.to and period_bounds(top, granularity)[0].strftime("%Y-%m-%d") > f.to):
            continue
        start, end = period_bounds(idx[ep[0]], granularity)[0], period_bounds(idx[ep[-1]], granularity)[1]
        win = hist[(hist.date >= start.strftime("%Y-%m-%d")) & (hist.date <= end.strftime("%Y-%m-%d"))]
        news = win[win.media_type == "News"].sort_values(["dup_count", "date", "doc_id"], ascending=[False, True, True])
        lead = news.iloc[0] if len(news) else (win.sort_values(["dup_count", "date", "doc_id"], ascending=[False, True, True]).iloc[0] if len(win) else None)
        proj = f.project or (win.project.mode().iloc[0] if len(win) else None)
        a, b = period_bounds(top, granularity)
        ev = st.events[st.events.project == proj].copy() if proj else st.events.iloc[0:0].copy()
        event = None
        if len(ev):
            d = pd.to_datetime(ev.date, errors="coerce")
            dist = pd.concat([(a - d).dt.days, (d - b).dt.days], axis=1).max(axis=1).clip(lower=0)
            ev = ev.assign(_dist=dist)[dist <= EVENT_LINK_DAYS].sort_values(["_dist", "date"])
            if len(ev):
                event = event_refs(ev.head(1).drop(columns="_dist"), st)[0]
        out.append({"period": top, "n": int(s[top]), "expected": round(float(lam[top]), 2), "p_value": float(pval[top]),
                    "headline": mask(str(lead.title)[:110]) if lead is not None else None,
                    "headline_doc_id": lead.doc_id if lead is not None else None, "headline_url": lead.url if lead is not None else None,
                    "event": event, "project": proj, "episode_start": start.strftime("%Y-%m-%d"), "episode_end": end.strftime("%Y-%m-%d"),
                    "episode_n": int(len(win))})
    return out


def peak_method(granularity: str) -> dict:
    P = PEAK_PARAMS[granularity]
    return {"test": "Poisson surprise test (pipeline/07_peaks.py)", "granularity": granularity, **P, "alpha": PEAK_ALPHA,
            "event_link_days": EVENT_LINK_DAYS,
            "description": (f"A {granularity} is a peak when its number of posts (all copies) is at least {P['min_count']} and "
                            f"P(X >= n | Poisson(mean of the previous {P['window']} {granularity}s + 0.1)) < {PEAK_ALPHA}. "
                            f"Neighbouring peak {granularity}s form one episode; the busiest one is reported. "
                            f"'event' is the nearest timeline event of the same project within {EVENT_LINK_DAYS} days; it is a pointer, not a proven cause.")}


# ---------------------------------------------------------------- endpoints

def overview(st, f: Filters) -> dict:
    posts = filter_posts(st, f)
    claims = filter_claims(st, f, posts)
    out = stance_block(posts)
    out["channel_counts"] = {k: int(v) for k, v in posts.channel.value_counts().items()}
    out["top_sources"] = [{"domain": d, "n": int(n)} for d, n in posts.domain.value_counts().head(10).items()]
    out["n_claims"] = int(len(claims))
    out["topic_shares"] = topic_shares(claims)
    out["top_arguments"] = family_table(st, claims)[:10]
    out["monthly"] = series(posts, "month", key="month")
    out["filters"] = f.active()
    notes = list(STANCE_NOTES) + list(ARGUMENT_NOTES)
    notes.append("channel_counts and top_sources count every collected post in the selection. monthly.n is all posts of the month.")
    if f.project:
        out["has_arguments"] = has_arguments(st, f.project)
        if not out["has_arguments"]:
            notes.insert(0, no_arguments_note(st, f.project))
    else:
        without = [p for p in posts.project.unique() if not has_arguments(st, p)]
        out["has_arguments"] = bool(len(claims))
        out["projects_without_arguments"] = without
        for p in without:
            notes.append(no_arguments_note(st, p))
    if f.stance:
        notes.append(f"The selection is limited to posts labelled '{f.stance}', so the opposition share describes only that selection.")
    out["notes"] = notes
    return out


def trends(st, f: Filters, granularity: str) -> dict:
    posts = filter_posts(st, f)
    ev = st.events
    if f.project:
        ev = ev[ev.project == f.project]
    if f.from_:
        ev = ev[ev.date >= f.from_]
    if f.to:
        ev = ev[ev.date <= f.to]
    return {"granularity": granularity, "series": series(posts, granularity), "peaks": peaks(st, f, granularity),
            "events": event_refs(ev.sort_values("date"), st), "peak_method": peak_method(granularity), "filters": f.active(),
            "notes": ["series.n counts every collected post (copies included); the stance columns count unique posts that are not passing mentions.",
                      "A week is named by its Monday. The last period can be incomplete.",
                      "Timeline events are desk research; 'verified' says whether a human confirmed the source."]}


def crosscity(st, f: Filters) -> dict:
    base = f.without("project")
    projects = []
    for pid in [p for p in dict.fromkeys(list(st.meta.get("projects", {})) + sorted(st.posts.project.unique())) if (st.posts.project == p).any()]:
        g = base.without()
        g.project = pid
        posts = filter_posts(st, g)
        claims = filter_claims(st, g, posts)
        b = stance_block(posts)
        projects.append({"id": pid, "name": project_name(st, pid), "has_arguments": has_arguments(st, pid), "n_posts": b["n_posts"],
                         "n_unique_posts": b["n_unique_posts"], "n_voices": b["n_voices"], "n_with_stance": b["n_with_stance"],
                         "stance_counts": b["stance_counts"], "opposition_share": b["opposition_share"], "support_share": b["support_share"],
                         "n_claims": int(len(claims)), "topic_shares": topic_shares(claims)})
    all_claims = filter_claims(st, base)
    fams = [r for r in family_table(st, all_claims) if len(r["by_project"]) >= 2]
    notes = ["shared_arguments lists argument families with claims in at least two projects; by_project gives the number of claims per project.",
             "Projects differ in size and in how they were collected, so compare shares only together with n and the interval."]
    notes += STANCE_NOTES[1:3] + [ARGUMENT_NOTES[0]]
    notes += [no_arguments_note(st, p["id"]) for p in projects if not p["has_arguments"]]
    if f.project:
        notes.append("The 'project' filter is ignored here: this view always compares all projects.")
    return {"projects": projects, "shared_arguments": fams, "filters": base.active(), "notes": notes}
