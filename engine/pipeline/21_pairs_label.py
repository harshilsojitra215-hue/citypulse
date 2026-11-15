"""Step 21 (CityPulse): label the claim pairs with one annotator model (Claude CLI on the subscription, or Ollama).

python -I src/21_pairs_label.py --model opus   -> out/citypulse/pairlabels_opus.jsonl
python -I src/21_pairs_label.py --model sonnet -> out/citypulse/pairlabels_sonnet.jsonl
Each annotator sees the queries in its own random batches and the candidates in its own random order,
so two annotators are independent readings. Resumable. These are MODEL labels, not human labels.
"""
import argparse, json, os, sys, hashlib, time, random
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
sys.path.insert(0, "pipeline")
from llm_label import call_claude, call_ollama, parse_array

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--backend", default="claude")
ap.add_argument("--pairs", default="out/citypulse/pairs.parquet")
ap.add_argument("--prompt", default="prompts/pair_codebook_v1.md")
ap.add_argument("--batch", type=int, default=4)
ap.add_argument("--workers", type=int, default=6)
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--tag", default="")
a = ap.parse_args()

system = open(a.prompt, encoding="utf-8").read()
phash = hashlib.sha1(system.encode()).hexdigest()[:8]
P = pd.read_csv(a.pairs) if a.pairs.endswith(".csv") else pd.read_parquet(a.pairs)
out = f"out/citypulse/pairlabels_{a.tag or a.model.replace(':', '-')}.jsonl"
done = set()
if os.path.exists(out):
    done = {json.loads(l)["pid"] for l in open(out, encoding="utf-8")}
rnd = random.Random("annot-" + a.model)
qids = sorted(P.qid.unique())
rnd.shuffle(qids)
qids = [q for q in qids if not set(P.pid[P.qid == q]) <= done]
if a.limit:
    qids = qids[:a.limit]
batches = [qids[i:i + a.batch] for i in range(0, len(qids), a.batch)]
print(f"{len(done)} pairs done, {len(qids)} queries to label in {len(batches)} calls ({a.backend}:{a.model}, prompt {phash})", flush=True)
LET = "abcdefghijklmnopqrstuvwxyz"
VALID = {"same", "opposing", "related", "unrelated"}


def run(batch):
    blocks, key = [], {}
    for n, q in enumerate(batch, 1):
        g = P[P.qid == q].sample(frac=1, random_state=rnd.randint(0, 10**6))
        lines = [f'### QUERY {n} [{g.q_project.iloc[0]}] "{g.q_claim.iloc[0]}"']
        for l, r in zip(LET, g.itertuples()):
            lines.append(f'{l} [{r.c_project}] "{r.c_claim}"')
            key[(str(n), l)] = r.pid
        blocks.append("\n".join(lines))
    user = "Label every candidate of every query:\n\n" + "\n\n".join(blocks)
    err = None
    for attempt in range(3):
        t = time.time()
        try:
            txt, _ = call_claude(system, user, a.model) if a.backend == "claude" else call_ollama(system, user, a.model)
            rows = []
            for o in parse_array(txt):
                for l, lab in o.get("labels", {}).items():
                    k = (str(o.get("q")).strip(), l.strip().lower())
                    if k in key and str(lab).strip().lower() in VALID:
                        rows.append(dict(pid=key[k], label=str(lab).strip().lower(), _model=f"{a.backend}:{a.model}", _prompt=phash))
            if len(rows) < 0.9 * len(key):
                raise ValueError(f"only {len(rows)}/{len(key)} labels parsed")
            return rows, round(time.time() - t, 1), None
        except Exception as e:
            err = repr(e)[:300]
            time.sleep(3 * (attempt + 1))
    return [], 0, err


n_ok = 0
with ThreadPoolExecutor(max_workers=a.workers) as ex, open(out, "a", encoding="utf-8") as f:
    futs = [ex.submit(run, b) for b in batches]
    for k, fu in enumerate(as_completed(futs), 1):
        rows, secs, err = fu.result()
        for o in rows:
            f.write(json.dumps(o) + "\n")
        f.flush()
        n_ok += len(rows)
        print(f"[{k}/{len(batches)}] +{len(rows)} in {secs}s {'ERR ' + err if err else ''}", flush=True)
print("done, labelled", n_ok)
