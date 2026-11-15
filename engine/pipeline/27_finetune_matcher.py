"""Step 27 (CityPulse): fine-tune a compact cross-encoder to judge two claims: same / related / opposing / unrelated.

Runs on the Hamburg GPU. Supervision = Opus labels on TRAIN pairs (queries before 2026-07-01, none of them in
CAL or TEST). 12% of the TRAIN queries are held out as DEV to pick the epoch. After training, the model scores
the evaluation pair files (both claim orders, averaged) and writes its class probabilities.

python 27_finetune_matcher.py --train train.csv --base MoritzLaurer/mDeBERTa-v3-base-mnli-xnli --tag mdeberta \
       --score out/citypulse/pairs.csv out/citypulse/replay_pairs.csv [--save models/mdeberta] [--seed 0]
"""
import argparse, json, time, os
import numpy as np, pandas as pd, torch
from torch.utils.data import DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
from sklearn.metrics import f1_score, precision_recall_fscore_support as prf

ap = argparse.ArgumentParser()
ap.add_argument("--train", required=True)
ap.add_argument("--base", required=True)
ap.add_argument("--tag", required=True)
ap.add_argument("--score", nargs="*", default=[])
ap.add_argument("--save", default="")
ap.add_argument("--epochs", type=int, default=4)
ap.add_argument("--lr", type=float, default=2e-5)
ap.add_argument("--batch", type=int, default=32)
ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()
torch.manual_seed(a.seed); np.random.seed(a.seed)
LABELS = ["same", "related", "opposing", "unrelated"]
L2I = {l: i for i, l in enumerate(LABELS)}
dev_ = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")

T = pd.read_csv(a.train)
T = T[T.label.isin(LABELS)].reset_index(drop=True)
qs = np.array(sorted(T.qid.unique()))
np.random.default_rng(1).shuffle(qs)  # the DEV split is the same for every seed and base model
dev_q = set(qs[: int(0.12 * len(qs))])
tr, dv = T[~T.qid.isin(dev_q)], T[T.qid.isin(dev_q)]
print(f"train pairs {len(tr)} dev pairs {len(dv)} | label mix {tr.label.value_counts(normalize=True).round(3).to_dict()}", flush=True)

tok = AutoTokenizer.from_pretrained(a.base)
# float32 explicitly: the base checkpoint is stored in fp16 and newer transformers keep that dtype, which turns the
# loss into NaN after the first optimiser step (seen on the Mac, 15 Nov). Older transformers loaded float32 by default.
model = AutoModelForSequenceClassification.from_pretrained(a.base, num_labels=4, ignore_mismatched_sizes=True, dtype=torch.float32).to(dev_)
# both orders of every pair: the relation is symmetric
A = tr.q_claim.tolist() + tr.c_claim.tolist()
B = tr.c_claim.tolist() + tr.q_claim.tolist()
Y = torch.tensor([L2I[l] for l in tr.label] * 2)
freq = np.bincount(Y.numpy(), minlength=4) / len(Y)
w = torch.tensor(1 / np.sqrt(freq + 1e-6), dtype=torch.float)
w = (w / w.mean()).to(dev_)


def enc(x, y):
    return tok(x, y, padding=True, truncation=True, max_length=96, return_tensors="pt").to(dev_)


@torch.no_grad()
def probs(left, right, bs=128):
    model.eval()
    out = []
    for i in range(0, len(left), bs):
        ab = model(**enc(left[i:i + bs], right[i:i + bs])).logits.float().softmax(-1)
        ba = model(**enc(right[i:i + bs], left[i:i + bs])).logits.float().softmax(-1)
        out.append(((ab + ba) / 2).cpu())
    return torch.cat(out).numpy()


opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
steps = a.epochs * (len(Y) // a.batch + 1)
sch = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)
lossf = torch.nn.CrossEntropyLoss(weight=w)
best, best_state, hist, t0 = -1, None, [], time.time()
yd = np.array([L2I[l] for l in dv.label])
for ep in range(a.epochs):
    model.train()
    perm = torch.randperm(len(Y))
    for i in range(0, len(perm), a.batch):
        idx = perm[i:i + a.batch].tolist()
        loss = lossf(model(**enc([A[j] for j in idx], [B[j] for j in idx])).logits.float(), Y[idx].to(dev_))
        loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); sch.step(); opt.zero_grad()
    pd_ = probs(dv.q_claim.tolist(), dv.c_claim.tolist())
    p, r, f, _ = prf(yd == 0, pd_.argmax(1) == 0, average="binary", zero_division=0)
    mf = f1_score(yd, pd_.argmax(1), average="macro")
    hist.append(dict(epoch=ep + 1, dev_same_f1=float(f), dev_same_p=float(p), dev_same_r=float(r), dev_macro_f1=float(mf)))
    print(hist[-1], f"{time.time() - t0:.0f}s", flush=True)
    if f > best:
        best, best_state = f, {k: v.detach().clone() for k, v in model.state_dict().items()}
model.load_state_dict(best_state)
train_secs = time.time() - t0

info = dict(base=a.base, tag=a.tag, seed=a.seed, n_train_pairs=len(tr), n_dev_pairs=len(dv), train_secs=round(train_secs, 1),
            history=hist, best_dev_same_f1=float(best), params=sum(p.numel() for p in model.parameters()))
for f in a.score:
    S = pd.read_csv(f)
    t = time.time()
    pr = probs(S.q_claim.tolist(), S.c_claim.tolist())
    info.setdefault("ms_per_pair_both_orders", round((time.time() - t) * 1000 / len(S), 2))
    out = pd.DataFrame(pr, columns=[f"ft_{a.tag}_{l}" for l in LABELS]); out.insert(0, "pid", S.pid.values)
    o = f.replace(".csv", f"_ft_{a.tag}_s{a.seed}.csv")
    out.to_csv(o, index=False); print("wrote", o, flush=True)
if a.save:
    os.makedirs(a.save, exist_ok=True)
    model.config.id2label = dict(enumerate(LABELS)); model.config.label2id = L2I
    model.save_pretrained(a.save); tok.save_pretrained(a.save)
json.dump(info, open(f"out/citypulse/ft_{a.tag}_s{a.seed}.json", "w"), indent=1)
print(json.dumps({k: v for k, v in info.items() if k != "history"}), flush=True)
