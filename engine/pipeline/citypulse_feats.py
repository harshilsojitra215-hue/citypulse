"""Shared feature builder for the CityPulse matchers (used by the benchmark and by the replay)."""
import glob, os, re
import numpy as np, pandas as pd

OUT = "out/citypulse"
LABELS = ["same", "related", "opposing", "unrelated"]


def add_features(P, C, stem):
    """P: pair table with pid, qid, cand, cos, same_project. C: claims indexed by cid.
    stem: 'pairs' or 'replay_pairs' -> picks up <stem-scores>.csv and <stem>_ft_<tag>_s<seed>.csv from the GPU box."""
    P = P.copy()
    for side, col in (("q", "qid"), ("c", "cand")):
        P[f"{side}_pol"], P[f"{side}_topic"] = P[col].map(C.polarity), P[col].map(C.topic)
    P["same_pol"] = (P.q_pol == P.c_pol).astype(float)
    P["flip_pol"] = ((P.q_pol.isin(["pro", "contra"])) & (P.c_pol.isin(["pro", "contra"])) & (P.q_pol != P.c_pol)).astype(float)
    P["same_topic"] = (P.q_topic == P.c_topic).astype(float)
    P["same_proj"] = P.same_project.astype(float)
    meta = ["cos", "same_pol", "flip_pol", "same_topic", "same_proj"]
    feats = {"cosine (current baseline)": ["cos"], "cosine + topic/polarity": meta}
    sf = f"{OUT}/{'scores' if stem == 'pairs' else 'replay_scores'}.csv"
    off = []
    if os.path.exists(sf):
        P = P.merge(pd.read_csv(sf), on="pid", how="left")
        P["rr"] = (P.reranker_ab + P.reranker_ba) / 2
        feats["bge-reranker-v2-m3, off the shelf"] = ["rr"]; off += ["rr"]
        for m, nice in (("nli", "mDeBERTa NLI, off the shelf"), ("nli_en", "DeBERTa-large NLI, off the shelf")):
            P[f"{m}_ent_min"] = np.minimum(P[f"{m}_ent_ab"], P[f"{m}_ent_ba"])
            P[f"{m}_ent_max"] = np.maximum(P[f"{m}_ent_ab"], P[f"{m}_ent_ba"])
            P[f"{m}_con_max"] = np.maximum(P[f"{m}_con_ab"], P[f"{m}_con_ba"])
            feats[nice] = [f"{m}_ent_min", f"{m}_ent_max", f"{m}_con_max"]; off += feats[nice]
        feats["stack of all off-the-shelf models + meta"] = meta + off
    seeds = {}
    for f in sorted(glob.glob(f"{OUT}/{stem}_ft_*_s*.csv")):
        tag, seed = re.search(rf"{stem}_ft_(.+)_s(\d+)\.csv$", f).groups()
        d = pd.read_csv(f).set_index("pid")
        d.columns = [c.replace(f"ft_{tag}_", f"ft_{tag}_s{seed}_") for c in d.columns]
        P = P.join(d, on="pid")
        seeds.setdefault(tag, []).append(seed)
    for tag, ss in seeds.items():
        for l in LABELS:  # average the seeds = a small ensemble; single seeds are reported separately
            P[f"ft_{tag}_{l}"] = P[[f"ft_{tag}_s{s}_{l}" for s in ss]].mean(axis=1)
        cols = [f"ft_{tag}_{l}" for l in LABELS[:3]]
        feats[f"fine-tuned {tag} (ours)"] = cols
        feats[f"fine-tuned {tag} + meta (ours)"] = meta + cols
    return P, feats, seeds
