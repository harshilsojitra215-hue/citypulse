"""Write a training file for the matcher that contains the human-corrected pair labels.

    python -m citypulse.review.export_training [--out review/results/train_with_human.csv] [--labeller NAME]

Output columns: pid,qid,q_claim,c_claim,label,label_source,model_label
  - the first five are what `pipeline/27_finetune_matcher.py --train` reads
  - label_source is "opus" (model label, unchanged) or "human" (label from the review store)
  - model_label keeps the model's label next to a human one, so nothing is lost

The model labels come from <lab>/out/citypulse/v2/train.csv (else <lab>/out/citypulse/train.csv) and are not modified; this script only writes a new file.
Training is NOT started here. Retraining command (needs a GPU):

    python pipeline/27_finetune_matcher.py --train review/results/train_with_human.csv \
        --base MoritzLaurer/mDeBERTa-v3-base-mnli-xnli --tag mdeberta_h --save models/mdeberta_h --seed 0 \
        --score out/citypulse/v2/eval.csv out/citypulse/v2/index.csv

IMPORTANT: the 120 reviewed pairs come from the TEST period. A model trained on this file has seen those test
queries. Its benchmark must leave them out; they are listed in the .meta.json written next to the CSV.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from . import config, queues, store
from .evaluate import consensus, load_model_pair_labels

COLUMNS = ["pid", "qid", "q_claim", "c_claim", "label", "label_source", "model_label"]


def _fallback_qid(q_claim: str) -> str:
    return "h" + hashlib.sha1(str(q_claim).encode("utf-8")).hexdigest()[:8]


def build(labeller=None):
    """Returns (DataFrame, meta) or (None, meta) when there is nothing to export."""
    meta = {"generated_at": store.now(), "labeller_filter": labeller, "n_human": 0}
    try:
        q = queues.load("pairs")
    except queues.QueueUnavailable as e:
        meta["message"] = f"pair queue missing: {e}"
        return None, meta
    labels, conflicts, _ = consensus("pairs", store.current("pairs"), set(q.ids), labeller)
    meta["n_conflicts_left_out"] = len(conflicts)
    if not labels:
        meta["message"] = "no human labels yet"
        return None, meta
    human = pd.DataFrame([{"pid": p, "q_claim": q.rows[p]["q_claim"], "c_claim": q.rows[p]["c_claim"],
                           "label": labels[p]["relation"]} for p in q.ids if p in labels])
    # query ids: the trainer splits train/dev by query, so pairs of one query must share a qid
    pairs_file = config.lab_out() / "pairs.parquet"
    qid = {}
    if pairs_file.exists():
        P = pd.read_parquet(pairs_file, columns=["pid", "qid"])
        qid = dict(zip(P.pid, P.qid))
    human["qid"] = [qid.get(p) or _fallback_qid(c) for p, c in zip(human.pid, human.q_claim)]
    opus = load_model_pair_labels().get("opus", {})
    human["model_label"] = human.pid.map(opus)
    human["label_source"] = "human"

    # v2 training set (strict time split) when present, else the v1 file
    train_file = next((f for f in (config.lab_out() / "v2" / "train.csv", config.lab_out() / "train.csv") if f.exists()), config.lab_out() / "train.csv")
    if train_file.exists():
        base = pd.read_csv(train_file)[["pid", "qid", "q_claim", "c_claim", "label"]]
        base["label_source"], base["model_label"] = "opus", base["label"]
        meta["model_train_file"] = str(train_file)
    else:
        base = pd.DataFrame(columns=COLUMNS)
        meta["model_train_file"] = None
        meta["warning"] = f"{train_file} not found: the output holds the human labels only (set CITYPULSE_LAB)"
    overridden = base.pid.isin(human.pid)
    # a human label replaces the model label of the same pair; keep what the model had said in model_label
    human.loc[human.pid.isin(base.pid), "model_label"] = human.pid.map(dict(zip(base.pid, base.label)))
    out = pd.concat([base[~overridden], human], ignore_index=True)[COLUMNS]
    meta.update(n_rows=len(out), n_model=int((out.label_source == "opus").sum()), n_human=len(human),
                n_human_replacing_a_train_label=int(overridden.sum()),
                n_human_changed_vs_model=int((human.model_label.notna() & (human.model_label != human.label)).sum()),
                human_label_counts=human.label.value_counts().to_dict(),
                test_queries_now_in_training=sorted(set(human.qid)),
                warning_test_leak="The human-labelled pairs come from the TEST period. Exclude the queries in "
                                  "'test_queries_now_in_training' from any benchmark of a model trained on this file.")
    return out, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="Export human-corrected pair labels for retraining the matcher.")
    ap.add_argument("--out", default=None, help="output CSV (default review/results/train_with_human.csv)")
    ap.add_argument("--labeller", default=None, help="use only this labeller's labels")
    a = ap.parse_args(argv)
    out_file = Path(a.out) if a.out else config.results_dir() / "train_with_human.csv"
    df, meta = build(store.normalise_labeller(a.labeller) if a.labeller else None)
    if df is None:
        print(f"{meta['message']}: nothing written.")
        return 0
    out_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_file, index=False)
    out_file.with_suffix(".meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"written: {out_file}  ({meta['n_rows']} pairs: {meta['n_model']} model labels, {meta['n_human']} human labels, "
          f"{meta['n_human_changed_vs_model']} of the human labels differ from the model)")
    if meta.get("warning"):
        print("warning:", meta["warning"])
    print("warning:", meta["warning_test_leak"])
    print("retrain (GPU, not started here):")
    print(f"  python pipeline/27_finetune_matcher.py --train {out_file} --base MoritzLaurer/mDeBERTa-v3-base-mnli-xnli "
          f"--tag mdeberta_h --save models/mdeberta_h --seed 0 --score out/citypulse/v2/eval.csv out/citypulse/v2/index.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
