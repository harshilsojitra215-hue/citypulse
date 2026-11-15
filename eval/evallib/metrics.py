"""Agreement and classification metrics with bootstrap intervals.

Plain numpy. Every function takes two aligned lists (reference, prediction) of labels.
Tested against scikit-learn and against synthetic data with known truth in eval/tests/.
"""
from collections import Counter
import math
import numpy as np


# ---------- agreement ----------

def cohen_kappa(a, b):
    """Cohen's kappa for two aligned label lists. None if undefined (no variation)."""
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if pe == 1:
        return None
    return (po - pe) / (1 - pe)


def krippendorff_alpha_nominal(units):
    """units: one list of labels per item (None = missing). Nominal alpha over all coders."""
    units = [[v for v in u if v is not None] for u in units]
    units = [u for u in units if len(u) >= 2]
    if not units:
        return None
    o = Counter()
    n = 0
    for u in units:
        m = len(u)
        for i, x in enumerate(u):
            for j, y in enumerate(u):
                if i != j:
                    o[(x, y)] += 1 / (m - 1)
        n += m
    nc = Counter()
    for (x, _), v in o.items():
        nc[x] += v
    do = sum(v for (x, y), v in o.items() if x != y)
    de = sum(nc[x] * nc[y] for x in nc for y in nc if x != y) / (n - 1)
    return 1 - do / de if de else 1.0


# ---------- classification ----------

def accuracy(ref, pred):
    return sum(r == p for r, p in zip(ref, pred)) / len(ref) if ref else None


def confusion(ref, pred, labels=None):
    """Return (labels, matrix) with rows = reference (truth), columns = prediction."""
    labels = labels or sorted(set(ref) | set(pred))
    idx = {l: i for i, l in enumerate(labels)}
    m = np.zeros((len(labels), len(labels)), dtype=int)
    for r, p in zip(ref, pred):
        if r in idx and p in idx:
            m[idx[r], idx[p]] += 1
    return labels, m


def per_class(ref, pred, labels=None):
    """Precision, recall, F1 and support per class. Classes with no support and no predictions are skipped."""
    labels, m = confusion(ref, pred, labels)
    out = {}
    for i, l in enumerate(labels):
        tp = m[i, i]
        fp = m[:, i].sum() - tp
        fn = m[i, :].sum() - tp
        sup = int(m[i, :].sum())
        if sup == 0 and m[:, i].sum() == 0:
            continue
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        out[l] = {'precision': float(p), 'recall': float(r), 'f1': float(f), 'support': sup}
    return out


def macro_f1(ref, pred, labels=None):
    """Mean F1 over classes that occur in the reference (classes only predicted count as 0 via precision of others)."""
    pc = per_class(ref, pred, labels)
    present = [l for l, v in pc.items() if v['support'] > 0]
    if not present:
        return None
    return float(np.mean([pc[l]['f1'] for l in present]))


def binary_prf(ref_bool, pred_bool):
    tp = sum(1 for g, p in zip(ref_bool, pred_bool) if g and p)
    fp = sum(1 for g, p in zip(ref_bool, pred_bool) if not g and p)
    fn = sum(1 for g, p in zip(ref_bool, pred_bool) if g and not p)
    tn = sum(1 for g, p in zip(ref_bool, pred_bool) if not g and not p)
    pr = tp / (tp + fp) if tp + fp else None
    rc = tp / (tp + fn) if tp + fn else None
    f1 = 2 * pr * rc / (pr + rc) if pr and rc else None
    return {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn, 'precision': pr, 'recall': rc, 'f1': f1}


# ---------- intervals ----------

def bootstrap(stat, *arrays, B=2000, seed=0, alpha=0.05):
    """Paired percentile bootstrap over items.

    stat(*resampled_arrays) -> float or None. Arrays are aligned per item.
    Returns {'value', 'lo', 'hi', 'n', 'B_valid'}.
    """
    arrays = [list(a) for a in arrays]
    n = len(arrays[0])
    value = stat(*arrays) if n else None
    if n == 0 or value is None:
        return {'value': value, 'lo': None, 'hi': None, 'n': n, 'B_valid': 0}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        ix = rng.integers(0, n, n)
        v = stat(*[[a[i] for i in ix] for a in arrays])
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            vals.append(v)
    if not vals:
        return {'value': value, 'lo': None, 'hi': None, 'n': n, 'B_valid': 0}
    lo, hi = np.percentile(vals, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {'value': float(value), 'lo': float(lo), 'hi': float(hi), 'n': n, 'B_valid': len(vals)}


Z95 = 1.959963984540054  # exact 97.5% normal quantile


def wilson(k, n, z=Z95):
    """Wilson score interval for a proportion k/n."""
    if n == 0:
        return {'value': None, 'lo': None, 'hi': None, 'n': 0}
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return {'value': p, 'lo': max(0.0, c - h), 'hi': min(1.0, c + h), 'n': n, 'k': k}


def half_width(p, n, z=1.96):
    """Normal-approximation 95% half-width for a proportion p with n items."""
    return z * math.sqrt(p * (1 - p) / n)


def sample_size_table(ns=(10, 22, 30, 60, 100, 166, 300, 1000), ps=(0.5, 0.8, 0.9)):
    rows = []
    for n in ns:
        row = {'n': n}
        for p in ps:
            w = wilson(round(p * n), n)
            row[f'p={p}'] = {'normal_half_width': round(half_width(p, n), 3),
                             'wilson': [round(w['lo'], 3), round(w['hi'], 3)]}
        rows.append(row)
    return rows


def majority(vals):
    """Majority label; 'TIE' if the top two are equal; None if empty."""
    c = Counter(v for v in vals if v is not None)
    if not c:
        return None
    top = c.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return 'TIE'
    return top[0][0]
