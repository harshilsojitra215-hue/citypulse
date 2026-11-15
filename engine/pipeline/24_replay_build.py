"""Step 24 (CityPulse): build the full historical replay stream.

Freeze the system on 2026-07-01. Every claim published after that arrives one by one in its real order
(published_at). For each arriving claim we retrieve candidates only from claims published BEFORE it
(other posts, one row per distinct text): top-5 from its own project and top-5 from the other projects.

python -I src/24_replay_build.py -> out/citypulse/replay_pairs.parquet (+ .csv for the GPU box)
"""
import hashlib
import numpy as np, pandas as pd

OUT = "out/citypulse"
T0 = pd.Timestamp("2026-07-01", tz="UTC")
C = pd.read_parquet(f"{OUT}/claims.parquet")
E = np.load(f"{OUT}/claims_emb.npy")
ts = pd.read_parquet("data/labelled.parquet", columns=["mention_id", "published_at"]).drop_duplicates("mention_id").set_index("mention_id").published_at
C["ts"] = C.id.map(ts)
assert C.ts.notna().all()
t, post, proj, norm = C.ts.values, C.id.values, C.project.values, C.norm.values
stream = np.flatnonzero(C.ts >= T0)
stream = stream[np.argsort(C.ts.values[stream], kind="stable")]
rows = []
for qi in stream:
    hist = np.flatnonzero((t < t[qi]) & (post != post[qi]))
    hist = C.iloc[hist].sort_values("ts").drop_duplicates("norm", keep="first").index.values
    order = hist[np.argsort(-(E[hist] @ E[qi]))]
    same = [j for j in order if proj[j] == proj[qi]][:5]
    other = [j for j in order if proj[j] != proj[qi]][:5]
    for j in same + other:
        rows.append(dict(qid=C.cid[qi], cand=C.cid[j], q_project=proj[qi], c_project=proj[j], same_project=proj[j] == proj[qi],
                         cos=float(E[j] @ E[qi]), q_claim=C.claim[qi], c_claim=C.claim[j], q_ts=C.ts[qi], c_ts=C.ts[j]))
R = pd.DataFrame(rows)
R["pid"] = [hashlib.md5((a + b).encode()).hexdigest()[:10] for a, b in zip(R.qid, R.cand)]
assert (R.c_ts < R.q_ts).all(), "future leak"
R.to_parquet(f"{OUT}/replay_pairs.parquet", index=False)
R[["pid", "q_claim", "c_claim"]].to_csv(f"{OUT}/replay_pairs.csv", index=False)
print("stream claims", len(stream), C.iloc[stream].project.value_counts().to_dict(), "| pairs", len(R), "| leak check passed")
