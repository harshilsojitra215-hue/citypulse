"""Step 5: run the non-LLM methods on the evaluation sample and save their predictions.

Produces labels/enc_preds.parquet with one row per gold item:
  rule_project            regex bucket -> project (baseline)
  tool_stance             provided `sentiment` field mapped to support/oppose/neutral (baseline)
  xlmr_sent               cardiffnlp twitter-xlm-roberta sentiment (pos/neg/neu)
  gbert_sent              oliverguhr german-sentiment-bert (German only)
  nli_stance              mDeBERTa XNLI zero-shot stance
and caches bge-m3 embeddings in data/emb_gold.npy (used for the trained classifiers in 06_eval).
"""
import sys, numpy as np, pandas as pd, torch
from transformers import pipeline

dev = "mps" if torch.backends.mps.is_available() else "cpu"
items = pd.read_parquet("data/gold_items.parquet")
texts = items.snippet.str.slice(0, 1500).tolist()
out = pd.DataFrame({"id": items.mention_id.astype(str)})

BUCKET2PROJ = {"heilbronn_cand": "heilbronn_cablecar", "paris_c1_cand": "paris_c1", "paris_loose_cand": "paris_c1",
               "bonn_cand": "bonn_cablecar", "ipai_cand": "ipai", "other_urban_cand": "other_urban_cablecar",
               "background": "leisure_or_unrelated"}
out["rule_project"] = items.bucket.map(BUCKET2PROJ).values
out["tool_stance"] = items.tool_sentiment.map({1: "support", -1: "oppose", 0: "neutral"}).values  # -99 -> NaN

import os
MP = lambda m: f"models/{m.replace('/', '_')}" if os.path.exists(f"models/{m.replace('/', '_')}/.done") else None

# --- embeddings (bge-m3 via local Ollama) ---
sys.path.insert(0, "pipeline")
from embed import embed
E = embed(texts)
np.save("data/emb_gold.npy", E)
print("embeddings", E.shape, flush=True)

# --- off-the-shelf sentiment models ---
short = [t[:1200] for t in texts]
if MP("cardiffnlp/twitter-xlm-roberta-base-sentiment"):
    xl = pipeline("text-classification", model=MP("cardiffnlp/twitter-xlm-roberta-base-sentiment"), device=dev, truncation=True, max_length=512)
    out["xlmr_sent"] = [r["label"].lower() for r in xl(short, batch_size=16)]
    print("xlmr done", out.xlmr_sent.value_counts().to_dict(), flush=True)
if MP("oliverguhr/german-sentiment-bert"):
    gb = pipeline("text-classification", model=MP("oliverguhr/german-sentiment-bert"), device=dev, truncation=True, max_length=512)
    de = (items.lang == "de").values
    res = gb([t for t, d in zip(short, de) if d], batch_size=16)
    it = iter(res)
    out["gbert_sent"] = [next(it)["label"].lower() if d else None for d in de]
    print("gbert done", out.gbert_sent.value_counts().to_dict(), flush=True)

# --- zero-shot stance via NLI (skipped: model not downloaded over the hotspot; the local-LLM zero-shot covers this family) ---
if MP("MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"):
    nli = pipeline("zero-shot-classification", model=MP("MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"), device=dev)
    labels = {"support": "Der Autor befürwortet das Projekt.", "oppose": "Der Autor lehnt das Projekt ab.", "neutral": "Der Text berichtet sachlich ohne Meinung."}
    inv = {v: k for k, v in labels.items()}
    preds = []
    for i in range(0, len(short), 16):
        rs = nli([t[:900] for t in short[i:i + 16]], candidate_labels=list(labels.values()), hypothesis_template="{}", multi_label=False)
        preds += [inv[r["labels"][0]] for r in rs]
    out["nli_stance"] = preds
out.to_parquet("labels/enc_preds.parquet", index=False)
