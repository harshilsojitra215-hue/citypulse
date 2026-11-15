"""Step 31 (CityPulse v2): training / evaluation files for the leak-free retrain, and the full candidate index.

Run from the lab directory. Writes into out/citypulse/v2/:
  train.csv     TRAIN pairs (queries before 2026-01-01) with Opus labels, minus any pair whose two texts also occur
                as a pair in CAL or TEST (exact duplicates of evaluation pairs would inflate results)
  eval.csv      all CAL + TEST pairs (queries from 2026-01-01), to be scored by the trained model
  index.csv     for EVERY claim: its 10 nearest older claims in its own project and 10 in the other projects
                (older = published earlier, another post, one row per distinct text). This is what the app caches.
"""
import json, os, hashlib
import numpy as np, pandas as pd
OUT = "out/citypulse"; V2 = f"{OUT}/v2"; os.makedirs(V2, exist_ok=True)
A = pd.read_parquet(f"{OUT}/pairs_all.parquet")
lab = {}
for f in ["pairlabels_train_opus", "pairlabels_opus", "pairlabels_v2_opus"]:   # later files win
    for l in open(f"{OUT}/{f}.jsonl"):
        d = json.loads(l); lab[d["pid"]] = d["label"]
A["label"] = A.pid.map(lab)
print("pairs", len(A), "unlabelled", int(A.label.isna().sum()))
A = A[A.label.notna()].copy()
norm = lambda s: " ".join("".join(ch for ch in s.lower() if ch.isalnum() or ch == " ").split())
A["tk"] = [" || ".join(sorted((norm(a), norm(b)))) for a, b in zip(A.q_claim, A.c_claim)]
ev_keys = set(A.tk[A.split != "train"])
tr = A[A.split == "train"]
leak = tr.tk.isin(ev_keys)
print("train pairs", len(tr), "| dropped because the same text pair is in CAL/TEST:", int(leak.sum()))
tr = tr[~leak]
tr[["pid", "qid", "q_claim", "c_claim", "label"]].to_csv(f"{V2}/train.csv", index=False)
A[A.split != "train"][["pid", "q_claim", "c_claim"]].to_csv(f"{V2}/eval.csv", index=False)
A.drop(columns="tk").to_parquet(f"{V2}/pairs_labelled.parquet", index=False)
print(tr.label.value_counts().to_dict(), "| eval pairs", int((A.split != "train").sum()))

C = pd.read_parquet(f"{OUT}/claims.parquet"); E = np.load(f"{OUT}/claims_emb.npy")
ts = pd.read_parquet("data/labelled.parquet", columns=["mention_id", "published_at"]).drop_duplicates("mention_id").set_index("mention_id").published_at
C["ts"] = C.id.map(ts)
order_all = np.argsort(C.ts.values, kind="stable")
t, post, proj, nrm = C.ts.values, C.id.values, C.project.values, C.norm.values
rows = []
for qi in range(len(C)):
    hist = np.flatnonzero((t < t[qi]) & (post != post[qi]))
    if not len(hist):
        continue
    hist = C.iloc[hist].sort_values("ts").drop_duplicates("norm", keep="first").index.values
    sims = E[hist] @ E[qi]
    o = hist[np.argsort(-sims)]
    for same in (True, False):
        side = [j for j in o if (proj[j] == proj[qi]) == same][:10]
        for r, j in enumerate(side, 1):
            rows.append((C.cid[qi], C.cid[j], same, r, float(E[j] @ E[qi]), C.claim[qi], C.claim[j]))
I = pd.DataFrame(rows, columns=["qid", "cand", "same_project", "side_rank", "cos", "q_claim", "c_claim"])
I["pid"] = [hashlib.md5((a + b).encode()).hexdigest()[:10] for a, b in zip(I.qid, I.cand)]
cc = C.set_index("cid")
assert (I.cand.map(cc.ts).values < I.qid.map(cc.ts).values).all(), "future leak in index"
I.to_parquet(f"{V2}/index_pairs.parquet", index=False)
I[["pid", "q_claim", "c_claim"]].to_csv(f"{V2}/index.csv", index=False)
print("index pairs", len(I), "claims with history", I.qid.nunique())
