"""The fine-tuned argument matcher (mDeBERTa-v3-base cross-encoder, 4 classes: same / related / opposing / unrelated).

The weights live in config.MODEL_DIR (not in git, see models/MODEL_CARD.md). If they are missing the engine keeps
working from cached scores and says so: status()["mode"] == "cached-only". It never falls back to a weaker model
under the same name: callers get score_source "baseline-cosine" and no equivalence verdict.

The "opposing" class is NOT used by the product (measured F1 too low); it stays in the model output only.
"""
import os, threading
import numpy as np, pandas as pd
from .. import config
from . import store

LABELS = ["same", "related", "opposing", "unrelated"]
_lock = threading.Lock()
_M, _err = None, None


def _load():
    global _M, _err
    with _lock:
        if _M is not None or _err is not None:
            return _M
        try:
            if not (config.MODEL_DIR / "model.safetensors").exists():
                raise FileNotFoundError(f"no model weights in {config.MODEL_DIR}")
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            dev = os.environ.get("CITYPULSE_DEVICE") or ("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
            tok = AutoTokenizer.from_pretrained(config.MODEL_DIR)
            model = AutoModelForSequenceClassification.from_pretrained(config.MODEL_DIR, dtype=torch.float32).eval()
            try:
                model.to(dev)
                with torch.no_grad():
                    model(**tok(["a"], ["b"], return_tensors="pt").to(dev))
            except Exception:
                dev = "cpu"; model.to(dev)
            # refuse broken weights (e.g. a run that diverged to NaN) instead of serving garbage scores
            with torch.no_grad():
                probe = model(**tok(["Die Seilbahn ist zu teuer"], ["The cable car costs too much"], return_tensors="pt").to(dev)).logits
            if not torch.isfinite(probe).all():
                raise ValueError(f"matcher weights in {config.MODEL_DIR} produce non-finite outputs")
            _M = dict(tok=tok, model=model, dev=dev, torch=torch)
        except Exception as e:
            _err = repr(e)[:300]
        return _M


def available() -> bool:
    return _load() is not None


def status() -> dict:
    cfg = store.get().matcher_cfg
    m = _load()
    return dict(available=m is not None, mode="local-model" if m else "cached-only", version=cfg.get("version"),
                device=m["dev"] if m else None, reason=None if m else _err, model_dir=str(config.MODEL_DIR),
                contradiction_detection="disabled (not reliable in this release)")


def probs(left, right, bs=32) -> np.ndarray:
    """Class probabilities [n, 4] for text pairs, averaged over both orders (the relation is symmetric)."""
    m = _load()
    if m is None:
        raise RuntimeError("matcher model not loaded: " + str(_err))
    tok, model, dev, torch = m["tok"], m["model"], m["dev"], m["torch"]
    left, right, out = list(left), list(right), []
    with torch.no_grad():
        for i in range(0, len(left), bs):
            a, b = left[i:i + bs], right[i:i + bs]
            e1 = tok(a, b, padding=True, truncation=True, max_length=96, return_tensors="pt").to(dev)
            e2 = tok(b, a, padding=True, truncation=True, max_length=96, return_tensors="pt").to(dev)
            p = (model(**e1).logits.float().softmax(-1) + model(**e2).logits.float().softmax(-1)) / 2
            out.append(p.cpu().numpy())
    return np.vstack(out) if out else np.zeros((0, 4), dtype=np.float32)


def _combine(name, X: pd.DataFrame) -> np.ndarray:
    c = store.get().matcher_cfg[name]
    z = ((X[c["cols"]].values.astype(float) - np.array(c["mean"])) / np.array(c["scale"])) @ np.array(c["coef"]) + c["intercept"]
    return 1 / (1 + np.exp(-z))


def meta_features(q, c, cos) -> pd.DataFrame:
    """q, c: DataFrames (same length) with columns topic, polarity, project. The cheap features the pipeline already has."""
    qp, cp = q.polarity.values, c.polarity.values
    return pd.DataFrame(dict(cos=np.asarray(cos, dtype=float), same_pol=(qp == cp).astype(float),
                             flip_pol=(np.isin(qp, ["pro", "contra"]) & np.isin(cp, ["pro", "contra"]) & (qp != cp)).astype(float),
                             same_topic=(q.topic.values == c.topic.values).astype(float),
                             same_proj=(q.project.values == c.project.values).astype(float)))


def score(q: pd.DataFrame, c: pd.DataFrame, cos, with_meta=True) -> pd.DataFrame:
    """Live scores for aligned claim rows. Returns ft_same, ft_related, p_same (calibrated), p_rel."""
    pr = probs(q.claim.tolist(), c.claim.tolist())
    X = meta_features(q, c, cos) if with_meta else pd.DataFrame(dict(cos=np.asarray(cos, dtype=float)))
    for i, l in enumerate(LABELS[:3]):
        X[f"ft_{l}"] = pr[:, i]
        X[f"s0_{l}"] = pr[:, i]   # the v2 combiner (pipeline/32_eval_v2.py) names the model outputs s0_*
    X["p_same"] = _combine("combiner_meta" if with_meta else "combiner_text", X)
    X["p_rel"] = X.ft_same + X.ft_related
    return X


def relation(p_same, p_rel, text_only=False) -> str:
    t = store.get().matcher_cfg.get("thresholds", {})
    if p_same is None or (isinstance(p_same, float) and np.isnan(p_same)):
        return "unscored"
    if p_same >= t.get("text_pair_same" if text_only else "pair_same", 0.5):
        return "equivalent"
    if p_rel is not None and p_rel >= t.get("related", 0.5):
        return "related"
    return "unrelated"


def novelty_state(best_p_same, text_only=False) -> str:
    """familiar: an equivalent older claim exists. new: clearly none. ambiguous: in between, needs a human look."""
    t = store.get().matcher_cfg.get("thresholds", {})
    hi, lo = t.get("text_familiar" if text_only else "familiar", 0.5), t.get("text_new" if text_only else "new", 0.2)
    return "familiar" if best_p_same >= hi else ("new" if best_p_same < lo else "ambiguous")
