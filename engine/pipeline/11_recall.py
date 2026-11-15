"""Step 11: recall audit. Did the regex rules miss relevant posts?
Train a classifier (bge-m3 + logistic regression) on the reference sample, score every background post,
send the likely-relevant ones to the LLM labeller. Output: data/recall_items.parquet (to label) + printed estimate.
"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "pipeline")
from embed import embed
from sklearn.linear_model import LogisticRegression

TARGETS = ["heilbronn_cablecar", "paris_c1", "bonn_cablecar", "ipai", "other_urban_cablecar"]
g = pd.read_parquet("data/gold_items.parquet"); g["id"] = g.mention_id.astype(str)
ref = pd.DataFrame([json.loads(l) for l in open("labels/gold_opus.jsonl")]).drop_duplicates("id").set_index("id")
y = g.id.map(lambda i: ref.loc[i, "project"] if ref.loc[i, "project"] in TARGETS else "none")
Eg = np.load("data/emb_gold.npy")
clf = LogisticRegression(max_iter=3000, C=4, class_weight="balanced").fit(Eg, y)
c = pd.read_parquet("data/candidates.parquet")
bg_all = c[(c.bucket == "background") & c.is_first_copy & ~c.mention_id.isin(g.mention_id)]
bg = bg_all.sample(3000, random_state=11).copy()  # random sample; scale counts by len(bg_all)/3000
print("background unique posts:", len(bg_all), "scored sample:", len(bg), flush=True)
SCALE = len(bg_all) / len(bg)
E = embed(bg.snippet.str.slice(0, 1500).tolist(), batch=64)
P = pd.DataFrame(clf.predict_proba(E), columns=clf.classes_, index=bg.index)
bg["p_target"] = 1 - P["none"]
bg["pred"] = P.idxmax(axis=1)
for th in [0.3, 0.5, 0.7]:
    s = bg[bg.p_target >= th]
    print(f"p_target >= {th}: {len(s)} posts in sample (~{len(s)*SCALE:.0f} in all background)  by predicted project: {s.pred.value_counts().to_dict()}")
sel = bg[bg.p_target >= 0.3].sort_values("p_target", ascending=False)
sel.drop(columns=["p_target", "pred"]).to_parquet("data/recall_items.parquet", index=False)
print("sent to labelling:", len(sel))
