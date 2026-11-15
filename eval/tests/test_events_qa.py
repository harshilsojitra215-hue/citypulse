"""Placebo test and Q&A scorer on synthetic data with known answers."""
import numpy as np

from evallib.events_qa import placebo_test, score_qa, numbers_in


def test_placebo_finds_real_peaks():
    rng = np.random.default_rng(0)
    y = rng.poisson(1.0, 100)
    events = [20, 45, 70]
    for e in events:
        y[e] += 15
    r = placebo_test(list(y), events, draws=2000)
    assert r['p_value'] < 0.01 and r['real'] > r['placebo_p95']


def test_placebo_rejects_fake_events():
    rng = np.random.default_rng(1)
    y = rng.poisson(1.0, 100)
    r = placebo_test(list(y), [20, 45, 70], draws=2000)
    assert r['p_value'] > 0.05


def test_numbers_in_skips_years_and_reads_german_format():
    assert numbers_in('Im Jahr 2026 kostet sie 157 Millionen, also 157.000.000 Euro, Anteil 0,5') == [157.0, 157000000.0, 0.5]


def test_score_qa():
    posts = {'1': 'Das ist wieder so ein Sinnlosprojekt, 157 Millionen Euro!', '2': 'Heilbronn sagt Ja zur Seilbahn-Idee'}
    items = [
        {'qid': 'q1', 'answerable': True, 'refused': False, 'answer': '9 posts oppose, one says 157 million.',
         'quotes': [{'post_id': '1', 'quote': 'so ein  Sinnlosprojekt'}, {'post_id': '2', 'quote': 'sagt Nein'}],
         'allowed_numbers': [9, 157]},
        {'qid': 'q2', 'answerable': False, 'refused': True, 'answer': '', 'quotes': []},
        {'qid': 'q3', 'answerable': False, 'refused': False, 'answer': 'Residents want 3 stations.', 'quotes': [],
         'allowed_numbers': []},
    ]
    r = score_qa(items, posts)
    assert r['quote_accuracy'] == 0.5            # one invented quote caught
    assert abs(r['number_accuracy'] - 2 / 3) < 1e-9   # "3 stations" is not an allowed number
    assert abs(r['refusal_accuracy'] - 2 / 3) < 1e-9  # q3 should have refused
