"""Prevalence correction must recover a known true share from a biased classifier.

Synthetic world: 4 stance classes with known shares. The classifier over-reads support
(calls 15% of neutral posts 'support', 5% 'oppose'), like haiku in the pilot. A random gold set gives M.
"""
import numpy as np

from evallib import prevalence as PV

LABELS = ['support', 'oppose', 'neutral_informative', 'other']
TRUE_P = np.array([0.12, 0.08, 0.70, 0.10])
# rows = true class, columns = predicted class: P(pred | true)
CONF = np.array([
    [0.85, 0.02, 0.10, 0.03],
    [0.03, 0.85, 0.07, 0.05],
    [0.15, 0.05, 0.75, 0.05],
    [0.10, 0.10, 0.20, 0.60],
])


def world(n, p, rng):
    y = rng.choice(4, n, p=p)
    f = np.array([rng.choice(4, p=CONF[i]) for i in y])
    return [LABELS[i] for i in y], [LABELS[i] for i in f]


def test_acc_exact_algebra():
    q = CONF.T @ TRUE_P
    p = PV.acc_solve(CONF, q)
    assert np.allclose(p, TRUE_P, atol=1e-5)


def test_cc_is_biased_and_acc_is_consistent():
    """With a large gold set ACC lands on the truth; raw counting stays wrong however much data we add."""
    rng = np.random.default_rng(0)
    gy, gf = world(5000, TRUE_P, rng)
    uy, uf = world(20000, TRUE_P, rng)
    cc = PV.cc(uf, LABELS)
    acc, info = PV.acc(gy, gf, uf, LABELS)
    assert cc['support'] - TRUE_P[0] > 0.07          # raw counting nearly doubles support (0.12 -> about 0.22)
    for i, l in enumerate(LABELS):
        assert abs(acc[l] - TRUE_P[i]) < 0.025, (l, acc[l], TRUE_P[i])
    assert abs(sum(acc.values()) - 1) < 1e-6 and min(acc.values()) >= -1e-9


def test_acc_beats_cc_with_small_gold_set():
    """Realistic gold set (n = 300): ACC is noisier per run but much closer on average than raw counting.
    Measured while writing this test: with n = 600 gold, ACC per-class error has p95 of 3 to 6 points."""
    rng = np.random.default_rng(5)
    e_acc, e_cc = [], []
    for r in range(40):
        gy, gf = world(300, TRUE_P, rng)
        uy, uf = world(5000, TRUE_P, rng)
        a, _ = PV.acc(gy, gf, uf, LABELS)
        c = PV.cc(uf, LABELS)
        e_acc.append(sum(abs(a[l] - TRUE_P[i]) for i, l in enumerate(LABELS)))
        e_cc.append(sum(abs(c[l] - TRUE_P[i]) for i, l in enumerate(LABELS)))
    assert np.mean(e_acc) < 0.5 * np.mean(e_cc), (np.mean(e_acc), np.mean(e_cc))


def test_acc_survives_prior_shift():
    """Gold set has a different mix than the unlabelled set (e.g. stratified pilot). ACC still works
    because P(pred | true) does not change. Plain counting and PPI would not be valid here."""
    rng = np.random.default_rng(1)
    gy, gf = world(5000, np.array([0.25, 0.25, 0.25, 0.25]), rng)
    shifted = np.array([0.05, 0.20, 0.70, 0.05])
    uy, uf = world(20000, shifted, rng)
    acc, _ = PV.acc(gy, gf, uf, LABELS)
    for i, l in enumerate(LABELS):
        assert abs(acc[l] - shifted[i]) < 0.025, (l, acc[l])


def test_acc_bootstrap_interval_contains_truth():
    rng = np.random.default_rng(2)
    gy, gf = world(400, TRUE_P, rng)
    uy, uf = world(5000, TRUE_P, rng)
    est, _ = PV.acc_bootstrap(gy, gf, uf, LABELS, B=300, seed=0)
    for i, l in enumerate(LABELS):
        assert est[l]['lo'] <= TRUE_P[i] <= est[l]['hi'], (l, est[l])


def test_ppi_coverage_near_95():
    rng = np.random.default_rng(3)
    hits, total, cc_hits = 0, 0, 0
    for r in range(200):
        gy, gf = world(300, TRUE_P, rng)
        uy, uf = world(3000, TRUE_P, rng)
        est = PV.ppi(gy, gf, uf, LABELS)
        for i, l in enumerate(LABELS):
            hits += est[l]['lo'] <= TRUE_P[i] <= est[l]['hi']
            total += 1
    cov = hits / total
    assert 0.91 <= cov <= 0.99, cov


def test_ppi_point_estimate_unbiased():
    rng = np.random.default_rng(4)
    vals = []
    for r in range(200):
        gy, gf = world(300, TRUE_P, rng)
        uy, uf = world(3000, TRUE_P, rng)
        vals.append(PV.ppi_share(gy, gf, uf, 'support')['value'])
    assert abs(np.mean(vals) - TRUE_P[0]) < 0.01
