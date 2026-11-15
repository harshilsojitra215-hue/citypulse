"""Calibration code on synthetic data with known truth."""
import numpy as np

from evallib import calibration as CAL


def test_ece_near_zero_when_calibrated():
    rng = np.random.default_rng(0)
    conf = rng.uniform(0.3, 1.0, 20000)
    correct = rng.random(20000) < conf
    assert CAL.ece(conf, correct) < 0.02


def test_ece_large_when_overconfident():
    rng = np.random.default_rng(1)
    conf = rng.uniform(0.6, 1.0, 20000)
    correct = rng.random(20000) < conf - 0.2      # says 90%, right 70%
    e = CAL.ece(conf, correct)
    assert 0.17 < e < 0.23


def test_temperature_scaling_recovers_T_and_lowers_ece():
    rng = np.random.default_rng(2)
    n, k = 6000, 4
    z = rng.normal(0, 1.5, (n, k))
    p_true = CAL.softmax(z)
    y = np.array([rng.choice(k, p=row) for row in p_true])
    logits = 3.0 * z                              # model is 3x too confident
    half = n // 2
    T = CAL.fit_temperature(logits[:half], y[:half])
    assert 2.6 < T < 3.4, T
    before = CAL.softmax(logits[half:])
    after = CAL.apply_temperature(logits[half:], T)
    ece_b = CAL.ece(before.max(1), before.argmax(1) == y[half:])
    ece_a = CAL.ece(after.max(1), after.argmax(1) == y[half:])
    assert ece_a < 0.03 < ece_b
    assert CAL.brier(after, y[half:]) < CAL.brier(before, y[half:])


def test_vote_confidence():
    assert CAL.vote_confidence(['a', 'a', 'a']) == ('a', 1.0)
    lab, s = CAL.vote_confidence(['a', 'b', 'a'])
    assert lab == 'a' and abs(s - 2 / 3) < 1e-12
    assert CAL.vote_confidence(['b', 'a'])[1] == 0.5


def test_ece_by_levels():
    e, rows = CAL.ece_by_levels([1, 1, 1, 1, 0.5, 0.5], [1, 1, 1, 0, 1, 0])
    assert abs(e - (4 / 6 * 0.25 + 0)) < 1e-12
