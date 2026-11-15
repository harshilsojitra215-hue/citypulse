"""The metric code must agree with scikit-learn / scipy and must recover known truth on synthetic data."""
import numpy as np
from scipy.stats import binomtest
from sklearn.metrics import cohen_kappa_score, f1_score

from evallib import metrics as M

LABELS = ['support', 'oppose', 'neutral_informative', 'other']


def _rand_pairs(n=500, agree=0.7, seed=0):
    rng = np.random.default_rng(seed)
    a = list(rng.choice(LABELS, n, p=[0.15, 0.1, 0.65, 0.1]))
    b = [x if rng.random() < agree else str(rng.choice(LABELS)) for x in a]
    return a, b


def test_kappa_matches_sklearn():
    for seed in range(5):
        a, b = _rand_pairs(seed=seed)
        assert abs(M.cohen_kappa(a, b) - cohen_kappa_score(a, b)) < 1e-12


def test_macro_f1_matches_sklearn():
    for seed in range(5):
        a, b = _rand_pairs(seed=seed)
        present = sorted(set(a))
        ours = M.macro_f1(a, b, LABELS)
        ref = f1_score(a, b, labels=present, average='macro', zero_division=0)
        assert abs(ours - ref) < 1e-12


def test_kappa_edge_cases():
    assert M.cohen_kappa(['a'] * 5, ['a'] * 5) is None          # no variation: undefined, not 1
    assert M.cohen_kappa(['a', 'b'] * 50, ['a', 'b'] * 50) == 1.0


def test_krippendorff_known_values():
    assert M.krippendorff_alpha_nominal([['a', 'a', 'a'], ['b', 'b', 'b'], ['a', 'a', None]]) == 1.0
    rng = np.random.default_rng(1)
    units = [list(rng.choice(['a', 'b', 'c'], 3)) for _ in range(5000)]
    assert abs(M.krippendorff_alpha_nominal(units)) < 0.03     # independent coders -> about 0
    # textbook example (Krippendorff, "Computing Krippendorff's alpha-reliability", 4 observers, 12 units,
    # missing values): nominal alpha = 0.743
    data = [
        [1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None],
        [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3],
        [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None],
        [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None],
    ]
    units = [[row[i] for row in data] for i in range(12)]
    assert abs(M.krippendorff_alpha_nominal(units) - 0.743) < 0.001


def test_wilson_matches_scipy():
    for k, n in [(8, 12), (46, 127), (0, 22), (22, 22)]:
        ours = M.wilson(k, n)
        ref = binomtest(k, n).proportion_ci(method='wilson')
        assert abs(ours['lo'] - ref.low) < 1e-9 and abs(ours['hi'] - ref.high) < 1e-9


def test_bootstrap_interval_covers_truth():
    """Accuracy of a classifier that is right 80% of the time: the 95% interval should cover 0.8 about 95% of runs."""
    rng = np.random.default_rng(3)
    hits = 0
    runs = 120
    for r in range(runs):
        ok = rng.random(150) < 0.8
        ref = ['x'] * 150
        pred = ['x' if o else 'y' for o in ok]
        ci = M.bootstrap(M.accuracy, ref, pred, B=400, seed=r)
        hits += ci['lo'] <= 0.8 <= ci['hi']
    assert 0.88 <= hits / runs <= 1.0


def test_binary_prf():
    d = M.binary_prf([1, 1, 0, 0, 1], [1, 0, 1, 0, 1])
    assert d['tp'] == 2 and d['fp'] == 1 and d['fn'] == 1 and abs(d['precision'] - 2 / 3) < 1e-12
