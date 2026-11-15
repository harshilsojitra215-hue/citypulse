"""Step 33: Store the fine-tuned matcher in half precision (558 MB instead of 1.1 GB) and prove the scores do not change.
The weights are loaded back as float32 for inference; only the file is smaller."""
import sys, json, hashlib, torch, numpy as np, pandas as pd
from transformers import AutoTokenizer, AutoModelForSequenceClassification
src, dst, pairs = sys.argv[1:4]
tok = AutoTokenizer.from_pretrained(src)
m = AutoModelForSequenceClassification.from_pretrained(src)
m.half().save_pretrained(dst, safe_serialization=True); tok.save_pretrained(dst)
S = pd.read_csv(pairs).head(3000)
def probs(path):
    mm = AutoModelForSequenceClassification.from_pretrained(path, torch_dtype=torch.float32).cuda().eval(); out = []
    with torch.no_grad():
        for i in range(0, len(S), 128):
            e = tok(S.q_claim[i:i+128].tolist(), S.c_claim[i:i+128].tolist(), padding=True, truncation=True, max_length=96, return_tensors="pt").to("cuda")
            out.append(mm(**e).logits.float().softmax(-1).cpu())
    return torch.cat(out).numpy()
a, b = probs(src), probs(dst)
sha = hashlib.sha256(open(f"{dst}/model.safetensors", "rb").read()).hexdigest()
info = dict(max_abs_prob_diff=float(np.abs(a - b).max()), n_pairs=len(S), sha256_model_safetensors=sha, labels=m.config.id2label)
json.dump(info, open(f"{dst}/export_check.json", "w"), indent=1); print(info)
