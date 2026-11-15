"""Step 9: one labelled table for analysis and the dashboard.

python -I src/09_assemble.py  -> data/labelled.parquet
Priority of label sources per unique text: Opus (reference sample) > Haiku (full candidate run).
Labels are copied to syndicated duplicates (same dup_key). Posts never sent to an LLM keep project="not_reviewed".
"""
import json, os
import pandas as pd


def load(p):
    if not os.path.exists(p):
        return pd.DataFrame()
    return pd.DataFrame([json.loads(l) for l in open(p, encoding="utf-8")]).drop_duplicates("id", keep="last")


c = pd.read_parquet("data/candidates.parquet")
c["id"] = c.mention_id.astype(str)
src = []
for p, tag in [("labels/gold_opus.jsonl", "opus"), ("labels/full_haiku.jsonl", "haiku")]:
    d = load(p)
    if len(d):
        d["label_source"] = tag
        src.append(d)
L = pd.concat(src).drop_duplicates("id", keep="first")
keep = ["id", "project", "passing", "city", "stance", "tone", "arguments", "label_source"]
L = L[[k for k in keep if k in L]]
lab = c.merge(L, on="id", how="left")
# copy labels from the labelled copy to its syndicated duplicates
first = lab[lab.project.notna()].drop_duplicates("dup_key")[["dup_key"] + keep[1:]]
lab = lab.drop(columns=keep[1:]).merge(first, on="dup_key", how="left")
lab["project"] = lab.project.fillna("not_reviewed")
lab["passing"] = lab.passing.fillna(False).astype(bool)
lab.to_parquet("data/labelled.parquet", index=False)
print(lab.project.value_counts().to_string())
print(lab.label_source.value_counts(dropna=False).to_string())
