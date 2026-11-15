"""Step 25 (CityPulse): the historical replay. Freeze on 2026-07-01, then feed every later claim in its real order.

For each arriving claim:
  1. candidates = older claims only (step 24), scored by the matcher chosen in step 23 (fitted on CAL only)
  2. familiar in its project if its best same-project match clears the conformal cut-off, else NEW to the project
  3. new claims that match each other form a group; a group is EMERGING once it has >= 2 claims from >= 2 independent voices
  4. each new group is looked up in the other projects (historical case retrieval, not a forecast)
Also: which KNOWN arguments got louder (Poisson rate test against the project's own past), and the old
embedding-cluster baseline (HDBSCAN fitted on the frozen history) for comparison.

python -I src/25_replay_run.py -> out/citypulse/replay.json, replay_claims.csv
"""
import json, sys
import numpy as np, pandas as pd, joblib
from scipy.stats import poisson_means_test
sys.path.insert(0, "pipeline")
from citypulse_feats import add_features

OUT = "out/citypulse"
T0 = pd.Timestamp("2026-07-01", tz="UTC")
C = pd.read_parquet(f"{OUT}/claims.parquet").set_index("cid")
E = np.load(f"{OUT}/claims_emb.npy")
ts = pd.read_parquet("data/labelled.parquet", columns=["mention_id", "published_at"]).drop_duplicates("mention_id").set_index("mention_id").published_at
C["ts"] = C.id.map(ts)
M = joblib.load(f"{OUT}/matcher.joblib")
R, _, _ = add_features(pd.read_parquet(f"{OUT}/replay_pairs.parquet"), C, "replay_pairs")
R["p_same"] = M["model"].predict_proba(R[M["cols"]])[:, 1]
tau_p, tau_a = M["tau_project"], M["tau_any"]
EV = pd.read_csv("data/events_timeline.csv"); EV["date"] = pd.to_datetime(EV.date, errors="coerce")
NICE = {"heilbronn_cablecar": "Heilbronn", "bonn_cablecar": "Bonn", "paris_c1": "Paris Câble C1", "other_urban_cablecar": "other cities"}


def ev_ctx(project, date):
    e = EV[EV.project == project].dropna(subset=["date"]).sort_values("date")
    if e.empty:
        return dict(stage=None, after=[])
    b, a = e[e.date <= date], e[e.date > date]
    f = lambda r: dict(date=str(r.date.date()), title=r.title_en, verified=r.verified, source=r.source_url)
    return dict(stage=f(b.iloc[-1]) if len(b) else None, after=[f(r) for r in a.head(2).itertuples()])


def card(cid, p=None):
    r = C.loc[cid]
    d = dict(cid=cid, claim=r.claim, project=NICE[r.project], date=str(r.ts.date()), channel=r.channel, domain=r.domain, url=r.url,
             topic=r.topic, polarity=r.polarity, voice=str(r.source_key)[-6:])
    if p is not None:
        d["p_same"] = round(float(p), 3)
    return d


stream = C[C.ts >= T0].sort_values("ts", kind="stable")
TXT = pd.read_parquet("data/labelled.parquet", columns=["mention_id", "text_clean"]).drop_duplicates("mention_id").set_index("mention_id").text_clean
_sh = {}
def shingles(post):
    if post not in _sh:
        w = str(TXT.get(post, "")).lower().split()
        _sh[post] = {" ".join(w[i:i + 5]) for i in range(max(len(w) - 4, 1))}
    return _sh[post]

def n_voices(cids):
    """independent voices among claims: one per author (or domain), and re-published copies of one article count once"""
    cids = list(cids); par = list(range(len(cids)))
    def f(i):
        while par[i] != i: i = par[i]
        return i
    for i in range(len(cids)):
        for j in range(i):
            a, b = C.loc[cids[i]], C.loc[cids[j]]
            sa, sb = shingles(a.id), shingles(b.id)
            if a.source_key == b.source_key or a.id == b.id or len(sa & sb) / max(len(sa | sb), 1) >= 0.3:
                par[f(i)] = f(j)
    return len({f(i) for i in range(len(cids))})

# argument families of the frozen history = the existing argument map, refitted on pre-freeze claims only
from umap import UMAP
from hdbscan import HDBSCAN
oldmask = (C.ts < T0).values
Z = UMAP(n_neighbors=15, n_components=8, min_dist=0.0, metric="cosine", random_state=42).fit_transform(E[oldmask])
C["family"] = None
C.loc[oldmask, "family"] = ["fam%d" % l if l >= 0 else None for l in HDBSCAN(min_cluster_size=8, min_samples=3).fit_predict(Z)]
C["family"] = C.family.fillna(pd.Series(C.index, index=C.index))   # a claim outside every cluster is its own family
POS = {c: i for i, c in enumerate(C.index)}
def fam_name(f):
    idx = [POS[c] for c in C.index[(C.family == f).values]]
    return C.claim.iloc[idx[int(np.argmax(E[idx] @ E[idx].mean(0)))]]
parent, rows = {}, []
def root(x):
    while parent.get(x, x) != x:
        x = parent[x]
    return x

for q in stream.index:
    g = R[R.qid == q]
    sp, op = g[g.same_project].sort_values("p_same", ascending=False), g[~g.same_project].sort_values("p_same", ascending=False)
    best_p = sp.iloc[0] if len(sp) else None
    best_o = op.iloc[0] if len(op) else None
    fam = best_p is not None and best_p.p_same >= tau_p
    # a claim that is not familiar may still belong to a NEW argument opened earlier in the replay: join it when the
    # pair decision threshold (F1-optimal on CAL) says "same" for one of that group's claims
    joins = [c for c, p in zip(sp.cand, sp.p_same) if p >= M["thr"] and c in parent and C.ts[root(c)] >= T0]
    if fam:
        parent[q] = root(best_p.cand)       # joins whatever that older claim belongs to
    elif joins:
        parent[q] = root(joins[0])
    else:
        parent[q] = q                         # opens a new argument in this project
    rows.append(dict(cid=q, project=C.project[q], ts=C.ts[q], status="familiar" if fam else ("joins_new" if joins else "new_in_project"),
                     new_anywhere=bool(max(g.p_same.max(), 0) < tau_a),
                     best_project=best_p.cand if best_p is not None else None, p_project=float(best_p.p_same) if best_p is not None else 0.0,
                     best_other=best_o.cand if best_o is not None else None, p_other=float(best_o.p_same) if best_o is not None else 0.0))
S = pd.DataFrame(rows).set_index("cid")
S["group"] = [root(q) for q in S.index]
S["group_is_new"] = S.group.map(lambda r: C.ts[r] >= T0)   # the root is itself a replay claim -> nothing older to hang on
S.join(C[["claim", "channel", "domain", "topic", "polarity", "source_key"]]).to_csv(f"{OUT}/replay_claims.csv")

out = {"frozen_at": str(T0.date()), "matcher": M["name"], "tau_project": tau_p, "tau_any": tau_a, "projects": {}}
for proj, sub in S.groupby("project"):
    groups = []
    for gid, g in sub[sub.group_is_new].groupby("group"):
        g = g.sort_values("ts")
        flag_at = None   # the moment the group had 2 claims from 2 independent voices = when CityPulse would have raised it
        for i in range(2, len(g) + 1):
            if n_voices(g.index[:i]) >= 2:
                flag_at = g.ts.iloc[i - 1]; break
        nv = n_voices(g.index)
        # cross-city: equivalent claims elsewhere, found for any member
        oth = R[R.qid.isin(g.index) & ~R.same_project].sort_values("p_same", ascending=False).drop_duplicates("cand")
        eq = oth[oth.p_same >= tau_a].head(4)
        near = oth.head(2) if eq.empty else eq
        cases = []
        for r in near.itertuples():
            c = card(r.cand, r.p_same); c["equivalent"] = bool(r.p_same >= tau_a)
            c.update(ev_ctx(C.project[r.cand], C.ts[r.cand].tz_localize(None)))
            cases.append(c)
        first = g.index[0]
        near_ev = EV[(EV.project == proj) & ((EV.date - C.ts[first].tz_localize(None)).abs() <= pd.Timedelta(days=14))].sort_values("date")
        groups.append(dict(label=C.claim[first], n_claims=len(g), n_voices=nv, first_seen=str(g.ts.iloc[0].date()),
                           flagged_at=str(flag_at.date()) if flag_at is not None else None,
                           status="emerging" if flag_at is not None else "single voice, watch",
                           new_anywhere=bool(g.new_anywhere.all()), polarity=C.polarity[g.index].value_counts().to_dict(),
                           claims=[card(c, S.p_project[c]) for c in g.index],
                           closest_older_in_project=[card(S.best_project[c], S.p_project[c]) for c in g.index[:1] if S.best_project[c]],
                           elsewhere=cases,
                           events_nearby=[dict(date=str(e.date.date()), title=e.title_en, verified=e.verified) for e in near_ev.itertuples()]))
    groups.sort(key=lambda d: (-(d["status"] == "emerging"), -d["n_voices"], -d["n_claims"]))
    # known arguments that got louder: claims per month in the replay window vs the same argument family's own past in this project
    fam = sub[~sub.group_is_new].copy()
    fam["family"] = C.family[fam.group].values
    months_new = max((stream.ts.max() - T0).days / 30.4, 1)
    months_old = max((T0 - C.ts[C.project == proj].min()).days / 30.4, 1)
    louder = []
    for f, g in fam.groupby("family"):
        k_new, k_old = len(g), int(((C.family == f) & (C.project == proj) & (C.ts < T0)).sum())
        if k_new >= 3:
            pval = float(poisson_means_test(k_new, months_new, k_old, months_old, alternative="greater").pvalue)
            louder.append(dict(label=fam_name(f), n_replay=k_new, n_before=k_old, per_month_replay=round(k_new / months_new, 2),
                               per_month_before=round(k_old / months_old, 2), p_value=round(pval, 4), n_voices=n_voices(g.index),
                               claims=[card(c, S.p_project[c]) for c in g.sort_values("ts").index]))
    louder.sort(key=lambda d: d["p_value"])
    out["n_louder_tests"] = out.get("n_louder_tests", 0) + len(louder)
    out["projects"][proj] = dict(name=NICE[proj], n_claims=len(sub), n_familiar=int((~sub.group_is_new).sum()),
                                 n_new=int(sub.group_is_new.sum()), n_new_groups=len(groups),
                                 n_emerging=sum(g["status"] == "emerging" for g in groups), groups=groups, louder=louder)
json.dump(out, open(f"{OUT}/replay.json", "w"), indent=1, ensure_ascii=False, default=str)

for proj in ["heilbronn_cablecar", "bonn_cablecar", "paris_c1"]:
    d = out["projects"][proj]
    print(f"\n=== {d['name']}: {d['n_claims']} claims after the freeze | match a pre-freeze argument {d['n_familiar']} | new {d['n_new']} claims in {d['n_new_groups']} groups | EMERGING {d['n_emerging']}")
    for g in d["groups"][:12]:
        if g["status"] != "emerging" and proj != "heilbronn_cablecar":
            continue
        print(f"  [{g['status']:>19}] {g['n_claims']} claims / {g['n_voices']} voices, first {g['first_seen']}, flagged {g['flagged_at']} | {g['label']}")
        for c in g["claims"][1:4]:
            print(f"        + {c['claim']}  ({c['channel']}, p={c['p_same']})")
        for c in g["elsewhere"][:2]:
            print(f"        ~ {'SAME' if c['equivalent'] else 'closest'} elsewhere: {c['project']} {c['date']}: {c['claim']} (p={c['p_same']})")
    for l in d["louder"][:4]:
        print(f"  louder: {l['label']} | {l['per_month_replay']}/month in replay vs {l['per_month_before']}/month before ({l['n_replay']} vs {l['n_before']} claims, {l['n_voices']} voices), p={l['p_value']}")
