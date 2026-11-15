"""Step 29 (CityPulse v2): one pair table with retrieval depth 10 and a strictly ordered time split.

Fixes two weaknesses of v1:
  * depth: v1 looked at the 5 nearest older claims per side; v2 looks at 10 (own project) + 10 (other projects)
  * split: v1 TRAIN (Jan 2025-Jun 2026) and CAL (Jul 2025-Jun 2026) overlapped in time, so thresholds were calibrated
    on a period the model had been trained on. v2: TRAIN queries < 2026-01-01 < CAL queries < 2026-07-01 <= TEST queries.
All 943 already-labelled queries are reused; only the new deeper candidates need labels.

python -I src/29_pairs_v2.py -> out/citypulse/pairs_all.parquet, pairs_v2_new.parquet, pairs_v2_new_eval.parquet
"""
import hashlib
import numpy as np, pandas as pd
OUT = "out/citypulse"
C = pd.read_parquet(f"{OUT}/claims.parquet"); E = np.load(f"{OUT}/claims_emb.npy")
old = pd.concat([pd.read_parquet(f"{OUT}/pairs.parquet"), pd.read_parquet(f"{OUT}/train_pairs.parquet")], ignore_index=True)
pos = {c: i for i, c in enumerate(C.cid)}
d, p, post = C.date.values, C.project.values, C.id.values
rows = []
for q in old.qid.unique():
    qi = pos[q]
    hist = np.flatnonzero((d < d[qi]) & (post != post[qi]))
    hist = C.iloc[hist].drop_duplicates("norm", keep="first").index.values
    order = hist[np.argsort(-(E[hist] @ E[qi]))]
    rs = ro = 0
    for j in order:
        same = p[j] == p[qi]
        rs, ro = rs + same, ro + (not same)
        rank = rs if same else ro
        rows.append((q, C.cid[j], bool(same), int(rank), float(E[j] @ E[qi])))
        if rs >= 40 and ro >= 40:
            break
R = pd.DataFrame(rows, columns=["qid", "cand", "same_project", "side_rank", "cos"])
R["pid"] = [hashlib.md5((a + b).encode()).hexdigest()[:10] for a, b in zip(R.qid, R.cand)]
keep = R[(R.side_rank <= 10) | R.pid.isin(old.pid)].copy()
cc = C.set_index("cid")
keep["q_project"], keep["c_project"] = keep.qid.map(cc.project), keep.cand.map(cc.project)
keep["q_claim"], keep["c_claim"] = keep.qid.map(cc.claim), keep.cand.map(cc.claim)
keep["q_date"], keep["c_date"] = keep.qid.map(cc.date), keep.cand.map(cc.date)
keep["split"] = np.where(keep.q_date >= pd.Timestamp("2026-07-01"), "test", np.where(keep.q_date >= pd.Timestamp("2026-01-01"), "cal", "train"))
keep["labelled_v1"] = keep.pid.isin(old.pid)
assert (keep.c_date < keep.q_date).all()
missing_old = set(old.pid) - set(keep.pid)
assert not missing_old, len(missing_old)
keep.to_parquet(f"{OUT}/pairs_all.parquet", index=False)
new = keep[~keep.labelled_v1]
new.to_parquet(f"{OUT}/pairs_v2_new.parquet", index=False)
new[new.split != "train"].to_parquet(f"{OUT}/pairs_v2_new_eval.parquet", index=False)
q = keep.drop_duplicates("qid")
print(q.groupby(["split", "q_project"]).size().unstack(fill_value=0))
print("pairs", len(keep), "| new to label", len(new), "| of which cal+test", int((new.split != "train").sum()), "| depth<=10 pairs per split", keep[keep.side_rank <= 10].groupby("split").size().to_dict())
