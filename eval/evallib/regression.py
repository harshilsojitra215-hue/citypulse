"""Check any model's labels against the falsification suite (eval/tests/regression_cases.jsonl).

A case passes when every constraint in 'expect' holds for the model's label of that pid.
Constraint forms:
  {"field": "project", "in": [...]}          label must be one of these
  {"field": "project", "not_in": [...]}      label must not be one of these
  {"not_both": {"project": X, "stance": Y}}  not (project == X and stance == Y)
  {"consistent_labels": ["project", "stance"]}   (dedup cases) all copies get the same labels
Dedup cases also check a clustering function: 'same' -> one cluster, 'different' -> separate clusters.
"""
import json
import os

CASES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests', 'regression_cases.jsonl')


def load_cases(path=CASES):
    with open(path, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def lookup(labels, case):
    """Labels may be keyed by pilot pid (P###) or by contract post_id (mention_id)."""
    return labels.get(case.get('pid')) or labels.get(case.get('post_id'))


def check_label(case, lab):
    """Return (status, reason). status in pass / fail / missing / n/a."""
    if lab is None:
        return 'missing', 'no label for this pid'
    for c in case['expect']:
        if 'field' in c:
            v = lab.get(c['field'])
            if v is None:
                return 'n/a', f'model gives no {c["field"]}'
            if 'in' in c and v not in c['in']:
                return 'fail', f'{c["field"]}={v}, expected one of {c["in"]}'
            if 'not_in' in c and v in c['not_in']:
                return 'fail', f'{c["field"]}={v}, must not be {c["not_in"]}'
        elif 'not_both' in c:
            if all(lab.get(k) == v for k, v in c['not_both'].items()):
                return 'fail', f'labelled {c["not_both"]}'
    return 'pass', ''


def check_model(cases, labels):
    """labels: {pid: {'project','stance',...}}. Returns per-case results and a summary by rule."""
    out = []
    for c in cases:
        if 'members' in c:
            labs = [labels.get(p) or labels.get(q) for p, q in zip(c['members'], c.get('member_post_ids', c['members']))]
            if any(l is None for l in labs):
                out.append({'case_id': c['case_id'], 'rule': c['rule'], 'status': 'missing', 'reason': 'not all copies labelled'})
                continue
            st, why = 'pass', ''
            for e in c['expect']:
                for fld in e.get('consistent_labels', []):
                    vals = {l.get(fld) for l in labs}
                    if None in vals:
                        st, why = 'n/a', f'no {fld}'
                    elif len(vals) > 1:
                        st, why = 'fail', f'copies got different {fld}: {sorted(vals)}'
                        break
            out.append({'case_id': c['case_id'], 'rule': c['rule'], 'status': st, 'reason': why})
        else:
            st, why = check_label(c, lookup(labels, c))
            out.append({'case_id': c['case_id'], 'rule': c['rule'], 'status': st, 'reason': why})
    summ = {}
    for r in out:
        s = summ.setdefault(r['rule'], {'pass': 0, 'fail': 0, 'missing': 0, 'n/a': 0})
        s[r['status']] += 1
    return out, summ


def check_dedup(cases, cluster_fn):
    out = []
    for c in cases:
        if 'members' not in c:
            continue
        ids = cluster_fn(c['texts'])
        same = len(set(ids)) == 1
        ok = same if c['dedup'] == 'same' else len(set(ids)) == len(ids)
        out.append({'case_id': c['case_id'], 'expected': c['dedup'], 'clusters': ids, 'status': 'pass' if ok else 'fail'})
    return out
