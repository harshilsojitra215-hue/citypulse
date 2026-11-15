"""Step 10: argument map. Cluster the short English claims the LLM extracted (one per argument),
so arguments line up across languages and cities ("too expensive", "Stadtbahn would be better", ...).

python -I src/10_argument_map.py data/labelled.parquet -> out/argument_clusters.csv, out/argument_claims.csv
Each cluster is named by its most central claim (medoid), so every label is a real sentence from the data.
"""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "pipeline")
from embed import embed
from umap import UMAP
from hdbscan import HDBSCAN

df = pd.read_parquet(sys.argv[1])
CC = ["heilbronn_cablecar", "paris_c1", "bonn_cablecar", "other_urban_cablecar"]
d = df[df.project.isin(CC) & df.is_first_copy]
rows = []
for r in d.itertuples():
    args = r.arguments if isinstance(r.arguments, (list, np.ndarray)) else []
    for a in args:
        if isinstance(a, dict) and a.get("claim"):
            rows.append(dict(id=r.mention_id, project=r.project, channel=r.channel, date=r.date, topic=a.get("topic"),
                             polarity=a.get("polarity"), claim=a["claim"], stance=r.stance))
A = pd.DataFrame(rows)
print("claims:", len(A), A.project.value_counts().to_dict())
E = embed(A.claim.tolist())
Z = UMAP(n_neighbors=15, n_components=8, min_dist=0.0, metric="cosine", random_state=42).fit_transform(E)
A["cluster"] = HDBSCAN(min_cluster_size=8, min_samples=3).fit_predict(Z)
out = []
for c, g in A[A.cluster >= 0].groupby("cluster"):
    idx = g.index.values
    cen = E[idx].mean(0)
    med = g.claim.iloc[int(np.argmax(E[idx] @ cen))]
    pol = g.polarity.value_counts(normalize=True)
    out.append(dict(cluster=c, n=len(g), name=med, main_topic=g.topic.mode().iloc[0],
                    pro=round(pol.get("pro", 0), 2), contra=round(pol.get("contra", 0), 2),
                    **{p: int((g.project == p).sum()) for p in CC},
                    examples=" | ".join(g.claim.sample(min(3, len(g)), random_state=0))))
C = pd.DataFrame(out).sort_values("n", ascending=False)
A.to_csv("out/argument_claims.csv", index=False)
C.to_csv("out/argument_clusters.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 80)
print("clusters:", len(C), " unclustered claims:", int((A.cluster < 0).sum()))
print(C.drop(columns="examples").head(40).to_string(index=False))
# Heilbronn-specific vs shared: clusters where Heilbronn's share of claims is much higher than its share overall
hn_share = (A.project == "heilbronn_cablecar").mean()
C["hn_lift"] = (C.heilbronn_cablecar / C.n / hn_share).round(2)
print("\nmost Heilbronn-specific clusters (lift = HN share in cluster / HN share overall):")
print(C[C.heilbronn_cablecar >= 3].sort_values("hn_lift", ascending=False)[["n", "hn_lift", "contra", "name"]].head(10).to_string(index=False))
