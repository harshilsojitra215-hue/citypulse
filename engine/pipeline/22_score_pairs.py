"""Step 22 (CityPulse): score every claim pair with the candidate matchers. Runs on the Hamburg GPU (or any machine).

python 22_score_pairs.py --pairs pairs.parquet --out scores.parquet --models reranker nli nli_en
Writes one row per pair with the raw model scores, plus scores_timing.json (ms per pair, device).
Self-contained on purpose: only needs torch, transformers, pandas, pyarrow.
"""
import argparse, json, time
import numpy as np, pandas as pd, torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

ap = argparse.ArgumentParser()
ap.add_argument("--pairs", default="pairs.parquet")
ap.add_argument("--out", default="scores.parquet")
ap.add_argument("--models", nargs="+", default=["reranker", "nli"])
ap.add_argument("--batch", type=int, default=64)
a = ap.parse_args()

HF = {"reranker": "BAAI/bge-reranker-v2-m3",
      "nli": "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
      "nli_en": "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"}
dev = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
P = pd.read_csv(a.pairs) if a.pairs.endswith(".csv") else pd.read_parquet(a.pairs)
A, B = P.q_claim.tolist(), P.c_claim.tolist()
out, timing = P[["pid"]].copy(), {"device": dev, "n_pairs": len(P)}


@torch.no_grad()
def logits(name, left, right):
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForSequenceClassification.from_pretrained(name).to(dev).eval()
    res = []
    for i in range(0, len(left), a.batch):
        enc = tok(left[i:i + a.batch], right[i:i + a.batch], padding=True, truncation=True, max_length=128, return_tensors="pt").to(dev)
        res.append(model(**enc).logits.float().cpu())
    # timing: one warm pass over the first 256 pairs, both directions already counted by the caller
    t = time.time()
    for i in range(0, min(256, len(left)), a.batch):
        enc = tok(left[i:i + a.batch], right[i:i + a.batch], padding=True, truncation=True, max_length=128, return_tensors="pt").to(dev)
        model(**enc).logits.float().cpu()
    ms = (time.time() - t) * 1000 / min(256, len(left))
    return torch.cat(res), model.config.id2label, ms


for m in a.models:
    name = HF[m]
    ab, id2label, ms = logits(name, A, B)
    ba, _, _ = logits(name, B, A)
    if ab.shape[1] == 1:  # reranker: one relevance logit
        out[f"{m}_ab"], out[f"{m}_ba"] = ab[:, 0].numpy(), ba[:, 0].numpy()
    else:  # NLI: probabilities per class, both directions
        pa, pb = ab.softmax(-1).numpy(), ba.softmax(-1).numpy()
        for k, lab in id2label.items():
            key = lab.lower()[:3]  # ent / neu / con
            out[f"{m}_{key}_ab"], out[f"{m}_{key}_ba"] = pa[:, int(k)], pb[:, int(k)]
    timing[m] = {"hf": name, "ms_per_pair_one_direction": round(ms, 2), "ms_per_pair_both": round(2 * ms, 2)}
    print(m, name, timing[m], flush=True)
    out.to_csv(a.out, index=False) if a.out.endswith(".csv") else out.to_parquet(a.out, index=False)
json.dump(timing, open(a.out.rsplit(".", 1)[0] + "_timing.json", "w"), indent=1)
print("wrote", a.out, out.shape)
