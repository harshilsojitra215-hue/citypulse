"""Step 20 (CityPulse): build the argument-pair evaluation set as a historical replay.

Every QUERY is a claim that arrives at its real date. Its CANDIDATES are claims that existed strictly before
that date (never the same post), found with the current baseline (bge-m3 cosine):
  top-5 from the same project's history, top-5 from the other projects' history, plus 2 from ranks 6-40.
So the labelled pairs are exactly what a matcher sees in production, and no later claim can leak in.

Time split (no leakage): CAL = queries dated 2025-07-01..2026-06-30, TEST = queries dated >= 2026-07-01.
Thresholds and any trained combiner are fitted on CAL only.

python -I src/20_pairs_build.py  ->  out/citypulse/claims.parquet, queries.parquet, pairs.parquet
"""
import sys, hashlib
import numpy as np, pandas as pd
sys.path.insert(0, "pipeline")
from embed import embed

OUT = "out/citypulse"
T_CAL, T_TEST = pd.Timestamp("2025-07-01"), pd.Timestamp("2026-07-01")
rng = np.random.default_rng(7)

c = pd.read_csv("out/argument_claims.csv")
c["date"] = pd.to_datetime(c.date)
c = c.sort_values(["date", "id"]).reset_index(drop=True)
c["cid"] = ["c%04d" % i for i in range(len(c))]
meta = pd.read_parquet("data/labelled.parquet", columns=["mention_id", "author_hash", "domain", "url", "lang", "title"]).drop_duplicates("mention_id")
c = c.merge(meta, left_on="id", right_on="mention_id", how="left").drop(columns="mention_id")
# an independent voice = pseudonymised author where we have one, else the publishing domain
c["source_key"] = c.author_hash.fillna("dom:" + c.domain.fillna("unknown"))
c["norm"] = c.claim.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.split().str.join(" ")
E = embed(c.claim.tolist())
np.save(f"{OUT}/claims_emb.npy", E)
c.rename(columns={"cluster": "cluster_all"}).to_parquet(f"{OUT}/claims.parquet", index=False)
print("claims", len(c), "unique texts", c.norm.nunique())


def pick(mask, n):
    idx = np.flatnonzero(mask)
    return rng.choice(idx, size=min(n, len(idx)), replace=False)


d, p = c.date.values, c.project.values
cal = (c.date >= T_CAL) & (c.date < T_TEST)
test = c.date >= T_TEST
q_idx = np.concatenate([
    pick(cal & (p == "heilbronn_cablecar"), 50), pick(cal & (p == "bonn_cablecar"), 30),
    pick(cal & (p == "paris_c1"), 30), pick(cal & (p == "other_urban_cablecar"), 30),
    pick(test & (p == "heilbronn_cablecar"), 999), pick(test & (p == "bonn_cablecar"), 999),
    pick(test & (p == "paris_c1"), 30), pick(test & (p == "other_urban_cablecar"), 40)])

pairs, queries = [], []
for qi in q_idx:
    hist = np.flatnonzero((c.date.values < d[qi]) & (c.id.values != c.id.values[qi]))
    # one row per distinct historical text (earliest copy), so candidates are not 5 copies of one sentence
    hist = c.iloc[hist].drop_duplicates("norm", keep="first").index.values
    sims = E[hist] @ E[qi]
    order = hist[np.argsort(-sims)]
    same_p = [j for j in order if p[j] == p[qi]]
    other_p = [j for j in order if p[j] != p[qi]]
    chosen = list(same_p[:5]) + list(other_p[:5])
    pool = [j for j in order[:40] if j not in chosen]
    chosen += list(rng.choice(pool, size=min(2, len(pool)), replace=False))
    exact = bool((c.norm.values[hist] == c.norm.values[qi]).any())
    queries.append(dict(qid=c.cid[qi], split="test" if d[qi] >= np.datetime64(T_TEST) else "cal", project=p[qi],
                        date=c.date[qi], claim=c.claim[qi], n_hist=len(hist), n_hist_same_project=len(same_p),
                        exact_text_in_history=exact))
    rank = {j: r + 1 for r, j in enumerate(order)}
    for j in chosen:
        pairs.append(dict(qid=c.cid[qi], cand=c.cid[j], split=queries[-1]["split"], q_project=p[qi], c_project=p[j],
                          same_project=p[j] == p[qi], cos=float(E[j] @ E[qi]), cos_rank=rank[j],
                          q_claim=c.claim[qi], c_claim=c.claim[j], q_date=c.date[qi], c_date=c.date[j]))
Q, P = pd.DataFrame(queries), pd.DataFrame(pairs)
P["pid"] = [hashlib.md5((a + b).encode()).hexdigest()[:10] for a, b in zip(P.qid, P.cand)]
Q.to_parquet(f"{OUT}/queries.parquet", index=False)
P.to_parquet(f"{OUT}/pairs.parquet", index=False)
print(Q.groupby(["split", "project"]).size().unstack(fill_value=0))
print("pairs", len(P), "| leak check, any candidate not older than its query:", int((P.c_date >= P.q_date).sum()))
print(P.groupby("split").cos.describe().round(2))
