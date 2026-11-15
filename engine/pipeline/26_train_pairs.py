"""Step 26 (CityPulse): TRAIN pairs for fine-tuning the matcher. Same recipe as step 20, but the queries are
claims dated before 2026-07-01 that are NOT in the CAL or TEST query sets. Candidates are strictly older than
their query, so the training set contains nothing from the replay period.

python -I src/26_train_pairs.py -> out/citypulse/train_pairs.parquet / .csv
"""
import hashlib
import numpy as np, pandas as pd
OUT = "out/citypulse"
rng = np.random.default_rng(23)
C = pd.read_parquet(f"{OUT}/claims.parquet")
E = np.load(f"{OUT}/claims_emb.npy")
used = set(pd.read_parquet(f"{OUT}/queries.parquet").index if False else pd.read_parquet(f"{OUT}/queries.parquet").qid)
T_TEST = pd.Timestamp("2026-07-01")
d, p, post, norm = C.date.values, C.project.values, C.id.values, C.norm.values
ok = (C.date < T_TEST) & ~C.cid.isin(used) & (C.date >= pd.Timestamp("2025-01-01"))
want = {"heilbronn_cablecar": 999, "bonn_cablecar": 110, "paris_c1": 160, "other_urban_cablecar": 170}
q_idx = np.concatenate([rng.choice(np.flatnonzero(ok & (p == k)), size=min(n, int((ok & (p == k)).sum())), replace=False) for k, n in want.items()])
rows = []
for qi in q_idx:
    hist = np.flatnonzero((d < d[qi]) & (post != post[qi]))
    hist = C.iloc[hist].drop_duplicates("norm", keep="first").index.values
    if len(hist) < 60:
        continue
    order = hist[np.argsort(-(E[hist] @ E[qi]))]
    same = [j for j in order if p[j] == p[qi]][:5]
    other = [j for j in order if p[j] != p[qi]][:5]
    chosen = same + other
    pool = [j for j in order[:40] if j not in chosen]
    chosen += list(rng.choice(pool, size=min(2, len(pool)), replace=False))
    for j in chosen:
        rows.append(dict(qid=C.cid[qi], cand=C.cid[j], split="train", q_project=p[qi], c_project=p[j], same_project=p[j] == p[qi],
                         cos=float(E[j] @ E[qi]), q_claim=C.claim[qi], c_claim=C.claim[j], q_date=C.date[qi], c_date=C.date[j]))
P = pd.DataFrame(rows)
P["pid"] = [hashlib.md5((a + b).encode()).hexdigest()[:10] for a, b in zip(P.qid, P.cand)]
assert (P.c_date < P.q_date).all() and P.q_date.max() < T_TEST and not set(P.qid) & used
P.to_parquet(f"{OUT}/train_pairs.parquet", index=False)
print("train queries", P.qid.nunique(), P.drop_duplicates("qid").q_project.value_counts().to_dict(), "pairs", len(P), "| newest query", P.q_date.max().date())
