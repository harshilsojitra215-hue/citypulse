"""Prevalence correction: estimate the true share of each class when the classifier makes mistakes.

CC  (classify and count): share of predicted labels. Biased when errors are not symmetric.
ACC (adjusted classify and count, Forman 2008): solve  q = M^T p  for p, where
      q[j]    = share of items predicted as class j (on the big unlabelled set)
      M[i, j] = P(predicted j | true i), estimated on the human gold set
      p       = true class shares (what we want), constrained to p >= 0, sum p = 1.
PPI (prediction-powered inference, Angelopoulos et al. 2023) for one class share:
      theta = mean over unlabelled of 1[pred = k]  +  mean over gold of (1[true = k] - 1[pred = k])
      variance = var_unlabelled / N + var_rectifier / n  ->  normal 95% interval.
Both assume the gold set is a random sample of the same population as the unlabelled set
(or is reweighted to it). A hand-picked gold set breaks that assumption.
"""
import numpy as np
from scipy.optimize import minimize


def cc(pred, labels):
    pred = list(pred)
    n = len(pred)
    return {l: (sum(p == l for p in pred) / n if n else None) for l in labels}


def confusion_rates(ref, pred, labels):
    """M[i, j] = P(pred = j | true = i). Rows with no gold items are set to identity (no information)."""
    k = len(labels)
    idx = {l: i for i, l in enumerate(labels)}
    m = np.zeros((k, k))
    for r, p in zip(ref, pred):
        if r in idx and p in idx:
            m[idx[r], idx[p]] += 1
    rows = m.sum(axis=1, keepdims=True)
    out = np.where(rows > 0, m / np.where(rows == 0, 1, rows), np.eye(k))
    return out, rows.ravel()


def acc_solve(M, q):
    """Least squares  min ||M^T p - q||^2  s.t. p >= 0, sum p = 1."""
    k = len(q)
    q = np.asarray(q, float)
    A = np.asarray(M, float).T
    fun = lambda p: float(((A @ p - q) ** 2).sum())
    jac = lambda p: 2 * A.T @ (A @ p - q)
    r = minimize(fun, np.full(k, 1 / k), jac=jac, method='SLSQP', bounds=[(0, 1)] * k,
                 constraints=[{'type': 'eq', 'fun': lambda p: p.sum() - 1}], options={'ftol': 1e-12, 'maxiter': 500})
    return r.x


def acc(gold_ref, gold_pred, unl_pred, labels):
    """Point estimate of ACC shares. Also returns the conditioning of M (small det / large cond = unstable)."""
    M, rows = confusion_rates(gold_ref, gold_pred, labels)
    q = np.array([sum(p == l for p in unl_pred) / len(unl_pred) for l in labels])
    p = acc_solve(M, q)
    return {l: float(v) for l, v in zip(labels, p)}, {'cond_M': float(np.linalg.cond(M)),
                                                     'gold_rows': {l: int(r) for l, r in zip(labels, rows)}}


def acc_bootstrap(gold_ref, gold_pred, unl_pred, labels, B=1000, seed=0, alpha=0.05):
    """Resample both the gold set (re-estimate M) and the unlabelled set (re-estimate q)."""
    rng = np.random.default_rng(seed)
    gold_ref, gold_pred, unl_pred = list(gold_ref), list(gold_pred), list(unl_pred)
    point, info = acc(gold_ref, gold_pred, unl_pred, labels)
    n, N = len(gold_ref), len(unl_pred)
    draws = []
    for _ in range(B):
        gi = rng.integers(0, n, n)
        ui = rng.integers(0, N, N)
        est, _ = acc([gold_ref[i] for i in gi], [gold_pred[i] for i in gi], [unl_pred[i] for i in ui], labels)
        draws.append([est[l] for l in labels])
    draws = np.array(draws)
    lo = np.percentile(draws, 100 * alpha / 2, axis=0)
    hi = np.percentile(draws, 100 * (1 - alpha / 2), axis=0)
    return {l: {'value': point[l], 'lo': float(lo[i]), 'hi': float(hi[i])} for i, l in enumerate(labels)}, info


def ppi_share(gold_ref, gold_pred, unl_pred, label, z=1.96):
    """PPI estimate and 95% interval for the share of one class."""
    y = np.array([r == label for r in gold_ref], float)
    f_g = np.array([p == label for p in gold_pred], float)
    f_u = np.array([p == label for p in unl_pred], float)
    rect = y - f_g
    theta = f_u.mean() + rect.mean()
    se = np.sqrt(f_u.var(ddof=1) / len(f_u) + rect.var(ddof=1) / len(rect))
    # interval clipped to [0, 1]: a share cannot be negative (clipping never lowers coverage)
    return {'value': float(theta), 'lo': float(max(0.0, theta - z * se)), 'hi': float(min(1.0, theta + z * se)),
            'se': float(se)}


def ppi(gold_ref, gold_pred, unl_pred, labels, z=1.96):
    return {l: ppi_share(gold_ref, gold_pred, unl_pred, l, z) for l in labels}
