"""Step 6: compare every method against the reference labels (Opus) on the evaluation sample.

python -I src/06_eval.py  -> prints tables, writes out/eval_summary.json
"""
import json, glob, os, sys
import numpy as np, pandas as pd
from sklearn.metrics import f1_score, cohen_kappa_score, accuracy_score, confusion_matrix
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

TARGETS = ["heilbronn_cablecar", "paris_c1", "bonn_cablecar", "ipai", "other_urban_cablecar"]
REF = sys.argv[1] if len(sys.argv) > 1 else "opus"


def load(name):
    p = f"labels/gold_{name}.jsonl"
    rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    df = pd.DataFrame(rows).drop_duplicates("id", keep="last").set_index("id")
    return df


def proj5(p):  # collapse non-target labels
    return p if p in TARGETS else "none"


def stance4(s):
    return {"support": "support", "oppose": "oppose", "neutral": "neutral"}.get(s, "mixed_unclear")


def stance3(s):
    return {"support": "support", "oppose": "oppose"}.get(s, "other")


def score(y, p, name, task, rows):
    m = pd.notna(p) & pd.notna(y)
    y, p = np.asarray(y)[m], np.asarray(p)[m]
    rows.append(dict(task=task, method=name, n=int(m.sum()), acc=round(accuracy_score(y, p), 3),
                     macro_f1=round(f1_score(y, p, average="macro"), 3), kappa=round(cohen_kappa_score(y, p), 3)))


items = pd.read_parquet("data/gold_items.parquet")
items["id"] = items.mention_id.astype(str)
items = items.set_index("id")
llm = {os.path.basename(p)[5:-6]: load(os.path.basename(p)[5:-6]) for p in sorted(glob.glob("labels/gold_*.jsonl"))}
ref = llm[REF]
ids = [i for i in items.index if i in ref.index]
items, ref = items.loc[ids], ref.loc[ids]
enc = pd.read_parquet("labels/enc_preds.parquet").set_index("id").reindex(ids) if os.path.exists("labels/enc_preds.parquet") else None
E = np.load("data/emb_gold.npy") if os.path.exists("data/emb_gold.npy") else None
if E is not None:
    E = pd.DataFrame(E, index=pd.read_parquet("data/gold_items.parquet").mention_id.astype(str)).loc[ids].values

rows = []
y_proj = ref.project.map(proj5)
y_rel = (y_proj != "none")
# ---- relevance / project ----
if enc is not None:
    score(y_proj, enc.rule_project.map(lambda x: x if x in TARGETS else "none"), "regex rules", "project", rows)
for name, d in llm.items():
    if name != REF:
        score(y_proj, d.reindex(ids).project.map(lambda x: proj5(x) if isinstance(x, str) else None), f"llm:{name}", "project", rows)
if E is not None:
    skf = StratifiedKFold(5, shuffle=True, random_state=0)
    pred = cross_val_predict(LogisticRegression(max_iter=3000, C=4, class_weight="balanced"), E, y_proj, cv=skf)
    score(y_proj, pred, "bge-m3 + logreg (5-fold, trained on ref)", "project", rows)
    Xr = np.hstack([E, pd.get_dummies(items.bucket).values.astype(float)])
    pred = cross_val_predict(LogisticRegression(max_iter=3000, C=4, class_weight="balanced"), Xr, y_proj, cv=skf)
    score(y_proj, pred, "bge-m3 + rule flags + logreg (5-fold)", "project", rows)

# ---- stance (only items the reference says are about a target, not passing) ----
st_ids = [i for i in ids if y_proj[i] != "none" and not bool(ref.loc[i].get("passing", False))]
y_st = ref.loc[st_ids].stance.map(stance4)
y_st3 = ref.loc[st_ids].stance.map(stance3)
sent2st = {"positive": "support", "negative": "oppose", "neutral": "neutral"}
if enc is not None:
    e = enc.loc[st_ids]
    score(y_st, e.tool_stance, "provided sentiment field", "stance4", rows)
    for c in ["xlmr_sent", "gbert_sent"]:
        if c in e:
            score(y_st, e[c].map(sent2st), c.replace("_sent", " sentiment as stance"), "stance4", rows)
    if "nli_stance" in e:
        score(y_st, e.nli_stance, "mDeBERTa NLI zero-shot", "stance4", rows)
for name, d in llm.items():
    if name != REF:
        dd = d.reindex(st_ids)
        score(y_st, dd.stance.map(lambda s: stance4(s) if isinstance(s, str) else None), f"llm:{name}", "stance4", rows)
        score(y_st3, dd.stance.map(lambda s: stance3(s) if isinstance(s, str) else None), f"llm:{name}", "stance3", rows)
if E is not None:
    Es = pd.DataFrame(E, index=ids).loc[st_ids].values
    skf = StratifiedKFold(5, shuffle=True, random_state=0)
    pred = cross_val_predict(LogisticRegression(max_iter=3000, C=2, class_weight="balanced"), Es, y_st, cv=skf)
    score(y_st, pred, "bge-m3 + logreg (5-fold, trained on ref)", "stance4", rows)
    pred3 = cross_val_predict(LogisticRegression(max_iter=3000, C=2, class_weight="balanced"), Es, y_st3, cv=skf)
    score(y_st3, pred3, "bge-m3 + logreg (5-fold, trained on ref)", "stance3", rows)

# ---- tone vs stance: how often does tone mislead? ----
tone = ref.loc[st_ids].tone
ct = pd.crosstab(tone, y_st)
print("\nREFERENCE tone x stance (target items, not passing):\n", ct)
neg = tone == "negative"
print(f"negative-tone items that are NOT opposition: {(neg & (y_st != 'oppose')).sum()}/{neg.sum()}")
opp = y_st == "oppose"
print(f"opposing items whose tone is NOT negative: {(opp & (tone != 'negative')).sum()}/{opp.sum()}")
if enc is not None:
    for c in ["xlmr_sent"]:
        if c in enc:
            score(tone, enc.loc[st_ids][c], c + " (as TONE)", "tone", rows)

res = pd.DataFrame(rows)
pd.set_option("display.width", 200)
for t, g in res.groupby("task", sort=False):
    print(f"\n== {t} (reference = {REF}) ==\n", g.drop(columns="task").sort_values("macro_f1", ascending=False).to_string(index=False))
print("\nreference project distribution:\n", y_proj.value_counts().to_string())
print("passing share among target items:", round(ref.loc[[i for i in ids if y_proj[i] != 'none']].passing.mean(), 3))
# rule-bucket precision (what fraction of each regex bucket is really about its project)
b = items.bucket
print("\nprecision of regex buckets vs reference:")
B2P = {"heilbronn_cand": "heilbronn_cablecar", "paris_c1_cand": "paris_c1", "paris_loose_cand": "paris_c1",
       "bonn_cand": "bonn_cablecar", "ipai_cand": "ipai", "other_urban_cand": "other_urban_cablecar", "background": "none"}
for k, v in B2P.items():
    m = b == k
    print(f"  {k:18s} n={m.sum():4d}  matches={(y_proj[m] == v).mean():.2f}  any-target={(y_proj[m] != 'none').mean():.2f}  top={y_proj[m].value_counts().head(3).to_dict()}")
res.to_json("out/eval_summary.json", orient="records", indent=1)
