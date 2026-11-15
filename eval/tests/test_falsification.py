"""Falsification regression suite. Any model that labels posts must pass these.

Default model under test = majority of the 3 pilot AI labellers (what the system would publish).
Test another model:   EVAL_PREDS=path/to/labels.jsonl python -m pytest eval/tests/test_falsification.py
Test another dedup:   EVAL_DEDUP=package.module:function  (signature: list[str] -> list[int])
Cases whose pid the model never labelled are skipped, not passed.
"""
import importlib
import os
import re

import pytest

from evallib.dedup import cluster
from evallib.io import load_labels, load_pilot_ai
from evallib.metrics import majority
from evallib.regression import load_cases, check_model, check_label, check_dedup, lookup

CASES = load_cases()


def model_labels():
    p = os.environ.get('EVAL_PREDS')
    if p:
        return os.path.basename(p), load_labels(p)
    A = load_pilot_ai()
    pids = set.intersection(*[set(L) for L in A.values()])
    maj = {}
    for pid in pids:
        r = {f: majority([A[n][pid][f] for n in A]) for f in ('project', 'stance')}
        maj[pid] = {f: (None if v == 'TIE' else v) for f, v in r.items()}
    return 'ai_majority_3', maj


NAME, LABELS = model_labels()


def test_suite_is_well_formed():
    rules = {c['rule'] for c in CASES}
    assert rules == {'R1_ski_lift_irrelevant', 'R2_council_report_neutral', 'R3_accident_elsewhere_not_hn',
                     'R4_syndicated_count_once', 'R5_ipai_without_cablecar'}
    for r in rules:
        assert sum(c['rule'] == r for c in CASES) >= 3, r
    for c in CASES:
        texts = c.get('texts') or [c['text']]
        for t in texts:
            assert not re.search(r'@\w{3,}', t), f'unmasked handle in {c["case_id"]}'
            assert not re.search(r'https?://', t), f'unmasked URL in {c["case_id"]}'


@pytest.mark.parametrize('case', [c for c in CASES if 'members' not in c], ids=lambda c: c['case_id'])
def test_model_passes_case(case):
    lab = lookup(LABELS, case)
    if lab is None:
        pytest.skip(f'{NAME} has no label for {case["pid"]}')
    status, why = check_label(case, lab)
    if status == 'n/a':
        pytest.skip(why)
    assert status == 'pass', f'{NAME}: {why} ({case["why"]})'


@pytest.mark.parametrize('case', [c for c in CASES if 'members' in c], ids=lambda c: c['case_id'])
def test_copies_get_same_labels(case):
    out, _ = check_model([case], LABELS)
    if out[0]['status'] in ('missing', 'n/a'):
        pytest.skip(out[0]['reason'])
    assert out[0]['status'] == 'pass', out[0]['reason']


def _dedup_fn():
    spec = os.environ.get('EVAL_DEDUP')
    if not spec:
        return cluster
    mod, fn = spec.split(':')
    return getattr(importlib.import_module(mod), fn)


def test_syndicated_copies_count_once():
    res = check_dedup(CASES, _dedup_fn())
    assert res and all(r['status'] == 'pass' for r in res), res


def test_suite_has_teeth():
    """A careless model (everything = Heilbronn cable car, oppose) must fail R1, R2, R3 and R5."""
    bad = {c['pid']: {'project': 'heilbronn_cablecar', 'stance': 'oppose'} for c in CASES if 'pid' in c}
    _, summ = check_model(CASES, bad)
    for rule in ('R1_ski_lift_irrelevant', 'R2_council_report_neutral', 'R3_accident_elsewhere_not_hn',
                 'R5_ipai_without_cablecar'):
        assert summ[rule]['pass'] == 0, rule
    # and a dedup that never merges fails the 'same' cases
    res = check_dedup(CASES, lambda texts: list(range(len(texts))))
    assert any(r['status'] == 'fail' for r in res)
