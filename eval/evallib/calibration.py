"""Calibration: does "80% sure" mean right 80% of the time?

- reliability_table: bins by confidence, accuracy per bin.
- ece: expected calibration error = weighted mean |accuracy - confidence| over bins.
- brier: mean squared error of the probability for the true class (multiclass form).
- fit_temperature / apply_temperature: temperature scaling of logits (one number T).
- vote_confidence: turns K labeller votes into (majority label, share of votes).
"""
from collections import Counter
import numpy as np
from scipy.optimize import minimize_scalar


def reliability_table(conf, correct, n_bins=10):
    conf = np.asarray(conf, float)
    correct = np.asarray(correct, float)
    edges = np.linspace(0, 1, n_bins + 1)
    rows = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (conf > lo) & (conf <= hi) if i else (conf >= lo) & (conf <= hi)
        if m.sum() == 0:
            continue
        rows.append({'bin': [round(lo, 2), round(hi, 2)], 'n': int(m.sum()),
                     'mean_conf': float(conf[m].mean()), 'accuracy': float(correct[m].mean())})
    return rows


def ece(conf, correct, n_bins=10):
    rows = reliability_table(conf, correct, n_bins)
    n = sum(r['n'] for r in rows)
    if n == 0:
        return None
    return float(sum(r['n'] / n * abs(r['accuracy'] - r['mean_conf']) for r in rows))


def ece_by_levels(conf, correct):
    """ECE when confidence takes only a few discrete values (vote shares): one bin per value."""
    conf = np.asarray(conf, float)
    correct = np.asarray(correct, float)
    rows = []
    for v in sorted(set(np.round(conf, 6))):
        m = np.isclose(conf, v)
        rows.append({'conf': float(v), 'n': int(m.sum()), 'accuracy': float(correct[m].mean())})
    n = len(conf)
    e = float(sum(r['n'] / n * abs(r['accuracy'] - r['conf']) for r in rows)) if n else None
    return e, rows


def brier(probs, y_idx):
    """probs: (n, k) array; y_idx: true class index per item."""
    probs = np.asarray(probs, float)
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y_idx)), y_idx] = 1
    return float(((probs - onehot) ** 2).sum(axis=1).mean())


def softmax(z):
    z = np.asarray(z, float)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature(logits, y_idx):
    """Find T > 0 minimising negative log likelihood of softmax(logits / T). Fit on held-out data only."""
    logits = np.asarray(logits, float)
    y_idx = np.asarray(y_idx)

    def nll(logT):
        p = softmax(logits / np.exp(logT))
        return -np.log(p[np.arange(len(y_idx)), y_idx] + 1e-12).mean()
    r = minimize_scalar(nll, bounds=(-3, 3), method='bounded')
    return float(np.exp(r.x))


def apply_temperature(logits, T):
    return softmax(np.asarray(logits, float) / T)


def vote_confidence(votes):
    """votes: list of labels from K labellers. Returns (label, share). Ties return the alphabetically first
    top label with its share (e.g. 0.5 for 1-1), so ties show up as low confidence, not hidden."""
    v = [x for x in votes if x is not None]
    if not v:
        return None, 0.0
    c = Counter(v).most_common()
    top_n = c[0][1]
    label = sorted(l for l, k in c if k == top_n)[0]
    return label, top_n / len(v)
