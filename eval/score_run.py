"""Referee scores for ONE label run file in the pipeline/CONTRACT.md format (section 2).

Usage:  python -I -X utf8 eval/score_run.py <run.jsonl|run.csv> [--name NAME] [--B 2000] [--no-write]

Scores, each only where the run has labels for the items (otherwise it says what to label):
  1. Regression suite     eval/tests/regression_cases.jsonl (33 real hard cases; ids = post_id or pilot pid)
  2. Pilot consensus      agreement with the 3-AI majority on the 240 pilot posts (consistency, NOT accuracy)
  3. X-Stance             ids X001..X200: side accuracy, "no side" rate (truth = the author's own answer)
  4. Edited posts         ids E001..E179: label kept or changed as the codebook rule says
Reuses evallib, eval/run_eval.py, eval/xstance/xstance.py and eval/robustness/score_edits.py. Never edits the run.
Writes eval/results/run_<name>.json and .md unless --no-write. There is no human gold set: nothing here is accuracy
against people.
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'xstance'))
sys.path.insert(0, os.path.join(HERE, 'robustness'))
from evallib import io as IO  # noqa: E402
from evallib import metrics as M  # noqa: E402
from evallib.regression import load_cases, check_model  # noqa: E402

# Common spellings -> codebook values. Anything else is kept and reported as "unknown value", never guessed.
VALUE_ALIASES = {
    'stance': {'neutral': 'neutral_informative', 'informative': 'neutral_informative', 'favor': 'support',
               'favour': 'support', 'pro': 'support', 'for': 'support', 'against': 'oppose', 'con': 'oppose',
               'negative': 'oppose', 'positive': 'support', 'unknown': 'unclear', 'none': None, 'null': None},
    'voice': {'news': 'news_institutional', 'institutional': 'news_institutional', 'politician': 'politician_official',
              'official': 'politician_official', 'company': 'company_vendor', 'vendor': 'company_vendor'},
    'project': {'heilbronn': 'heilbronn_cablecar', 'bonn': 'bonn_cablecar', 'paris': 'paris_c1',
                'other': 'other_cablecar', 'none': 'irrelevant', 'not_relevant': 'irrelevant'},
}
VALID = {'stance': set(IO.STANCES), 'voice': set(IO.VOICES), 'project': set(IO.PROJECTS)}
ID_KEYS = IO.FIELD_ALIASES['pid']


class RunError(Exception):
    pass


def read_rows(path):
    if not os.path.exists(path):
        raise RunError(f'file not found: {path}')
    rows = []
    try:
        if path.lower().endswith('.csv'):
            with open(path, encoding='utf-8-sig', newline='') as f:
                rows = list(csv.DictReader(f))
        else:
            with open(path, encoding='utf-8-sig') as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except ValueError:
                        raise RunError(f'line {i} is not valid JSON')
                    if not isinstance(r, dict):
                        raise RunError(f'line {i} is not a JSON object')
                    rows.append(r)
    except UnicodeDecodeError:
        raise RunError('file is not UTF-8 text')
    return rows


def load_run(path):
    """Return (labels, info). labels: {id: rec} for posts with a project label. info: counts and warnings."""
    rows = read_rows(path)
    header = next((r['_run'] for r in rows if isinstance(r.get('_run'), dict)), {})
    rows = [r for r in rows if '_run' not in r]
    if not rows:
        raise RunError('no label rows found (only a header, or the file is empty)')
    if not any(any(k in r for k in ID_KEYS) for r in rows):
        raise RunError(f'required id column missing: need one of {ID_KEYS} (contract: post_id). '
                       f'Columns seen: {sorted(rows[0])}')
    if not any(k in r for r in rows for k in ('project', 'stance')):
        raise RunError(f'no label column found: need project and/or stance. Columns seen: {sorted(rows[0])}')
    labels, warns = {}, []
    unknown, n_abs, n_no_id, n_no_project = {}, 0, 0, 0
    has_stance = False
    for r in rows:
        pid = IO._get(r, 'pid')
        if pid is None:
            n_no_id += 1
            continue
        r = dict(r)
        for fld, amap in VALUE_ALIASES.items():
            v = r.get(fld)
            if isinstance(v, str):
                v = v.strip().lower()
                v = amap[v] if v in amap else v
                r[fld] = v
                if v and v not in VALID[fld]:
                    unknown.setdefault(fld, set()).add(v)
        try:
            rec = IO._rec(r)
        except (ValueError, TypeError):
            raise RunError(f'could not read the arguments field of post {pid} (expected a JSON list or ;-separated codes)')
        if rec.get('abstain'):
            n_abs += 1
        if rec['stance']:
            has_stance = True
        if not rec['project']:
            n_no_project += 1
            if not (rec.get('abstain') or rec['stance']):
                continue
        labels[str(pid)] = rec
    if n_no_id:
        warns.append(f'{n_no_id} rows had no id and were skipped')
    for fld, vals in unknown.items():
        warns.append(f'unknown {fld} values (kept, not in codebook): {sorted(vals)}')
    if not has_stance:
        warns.append('no stance labels in this run (project-only run): stance scores are skipped')
    info = {'header': header, 'n_rows': len(rows), 'n_labelled': len(labels), 'n_abstain': n_abs,
            'n_no_project': n_no_project, 'has_stance': has_stance, 'warnings': warns}
    return labels, info


def fmt(d):
    if d is None or d.get('value') is None:
        return 'n/a'
    if d.get('lo') is None:
        return f"{d['value']:.2f}"
    return f"{d['value']:.2f} [{d['lo']:.2f}, {d['hi']:.2f}]"


def score_regression(labels):
    cases = load_cases()
    res, summ = check_model(cases, IO.to_pilot_ids(labels) | labels)
    tot = {k: sum(s[k] for s in summ.values()) for k in ('pass', 'fail', 'missing', 'n/a')}
    return {'totals': tot, 'by_rule': summ, 'failures': [r for r in res if r['status'] == 'fail']}


def score_consensus(labels, B):
    import run_eval as RE
    S = IO.load_sample()
    A = IO.load_pilot_ai()
    pids = sorted(S)
    cons = RE.majority_labels(list(A.values()), pids)
    pred = IO.to_pilot_ids(labels)
    covered = [p for p in pids if p in pred and p in cons]
    if not covered:
        return {'n': 0}
    return RE.compare(cons, pred, covered, B)


def score_xstance(labels, B):
    import xstance as XS
    if not os.path.exists(XS.KEY):
        return {'n': 0, 'note': 'X-Stance key not built (needs the 6.4 MB download, see eval/xstance/xstance.py)'}
    key = {json.loads(l)['pid']: json.loads(l) for l in open(XS.KEY, encoding='utf-8') if l.strip()}
    ps = [p for p in key if p in labels and labels[p].get('stance')]
    if not ps:
        return {'n': 0}
    ref = [key[p]['label'] for p in ps]
    pred = [XS.side(labels[p]['stance']) for p in ps]
    given = [(a, b) for a, b in zip(ref, pred) if b != 'NO_SIDE']
    return {'n': len(ps), 'accuracy': M.bootstrap(M.accuracy, ref, pred, B=B),
            'no_side': M.wilson(sum(b == 'NO_SIDE' for b in pred), len(pred)),
            'accuracy_when_side_given': M.wilson(sum(a == b for a, b in given), len(given)),
            'swapped': sum(1 for a, b in given if a != b)}


def score_edits(labels):
    import score_edits as SE
    kp = os.path.join(SE.HERE, '_answer_key', 'edits_key.jsonl')
    if not os.path.exists(kp):
        return {'n': 0, 'note': 'edit answer key missing'}
    key = [json.loads(l) for l in open(kp, encoding='utf-8') if l.strip()]
    if not any(k['pid'] in labels for k in key):
        return {'n': 0}
    pilot = SE.load_pilot_ai()
    own = {p: {f: (lambda v: None if v == 'TIE' else v)(M.majority([pilot[n][p][f] for n in pilot]))
               for f in ('project', 'stance')} for p in pilot['haiku']}
    kept = ['E4_tone_caps', 'E5_sidebar', 'E6_numbers']
    out = {'n': 0, 'pass': 0, 'invariance_n': 0, 'invariance_pass': 0, 'directional_n': 0, 'directional_pass': 0,
           'fails': []}
    for it in key:
        if it['pid'] not in labels:
            continue
        a, _, why = SE.check(it, labels[it['pid']], own.get(it['seed']) if it['seed'] else None)
        if a is None:
            continue
        g = 'directional' if it['family'] in SE.DIRECTIONAL else 'invariance'
        out['n'] += 1
        out['pass'] += a
        out[g + '_n'] += 1
        out[g + '_pass'] += a
        if not a:
            out['fails'].append(f"{it['family']} {it['pid']}: {why}")
    out['kept_families'] = kept
    return out


def render(name, info, R):
    L = [f'# Referee scores for run `{name}`', '']
    h = info['header']
    if h:
        L.append(f"Run header: labeller {h.get('labeller')}, kind {h.get('kind')}, codebook {h.get('codebook_version')} "
                 f"{h.get('codebook_sha')}, prompt {h.get('prompt_version')}.")
    L.append(f"Rows {info['n_rows']}, labelled {info['n_labelled']}, abstained {info['n_abstain']}.")
    for w in info['warnings']:
        L.append(f'WARNING: {w}')
    L.append('')
    r = R['regression']['totals']
    L += ['## 1. Regression suite (33 real hard cases, rules fixed by the codebook, cases picked by Claude)', '',
          f"pass {r['pass']}, fail {r['fail']}, no label for the case {r['missing']}, not checkable (field missing) {r['n/a']}."]
    for f in R['regression']['failures']:
        L.append(f"- FAIL {f['case_id']}: {f['reason']}")
    if r['pass'] + r['fail'] == 0:
        L.append('The run contains none of the 33 case posts: run the labeller on them (post_id in the cases file).')
    c = R['consensus']
    L += ['', '## 2. Agreement with the 3-AI majority on the 240 pilot posts (MODEL-JUDGED: agreement, not accuracy)', '']
    if not c.get('n'):
        L.append('The run contains none of the 240 pilot posts (scripts/pilot/sample_key.csv maps post_id to P###).')
    else:
        L.append(f"n = {c['n']} posts in both; project accuracy {fmt(c['project_accuracy'])}, "
                 f"relevance precision {fmt(c['relevance_precision'])}, recall {fmt(c['relevance_recall'])}.")
        if c.get('stance_n'):
            ob = c['opinion_bearing_exact']
            L.append(f"Stance on {c['stance_n']} relevant posts: accuracy {fmt(c['stance_accuracy'])}, kappa "
                     f"{fmt(c['stance_kappa'])}; of {ob['n']} posts where the consensus says support or oppose, "
                     f"{ob.get('k', 0)} get the same label; support/oppose swaps: {c['opinion_flipped']}.")
        else:
            L.append('No stance overlap with the consensus: stance agreement not computed.')
    x = R['xstance']
    L += ['', '## 3. X-Stance (truth = the author\'s own yes/no answer; German and French comments)', '']
    if not x.get('n'):
        L.append(x.get('note') or 'The run has no X001..X200 items: label eval/xstance/batch_*_blind.jsonl with this '
                 'labeller (ids X###), add them to the run file, rerun.')
    else:
        ns = x['no_side']
        L.append(f"n = {x['n']}; side accuracy {fmt(x['accuracy'])}; said 'no side' {ns['k']}/{ns['n']} ({ns['value']:.0%}); "
                 f"when it gave a side it was right {x['accuracy_when_side_given']['k']}/{x['accuracy_when_side_given']['n']}; "
                 f"swapped sides {x['swapped']}.")
    e = R['edits']
    L += ['', '## 4. Edited posts (codebook rule applied by code; MODEL-JUDGED seed labels for real-post edits)', '']
    if not e.get('n'):
        L.append(e.get('note') or 'The run has no E001..E179 items: label eval/robustness/batch_*_blind.jsonl with this '
                 'labeller (ids E###), add them to the run file, rerun.')
    else:
        L.append(f"{e['pass']}/{e['n']} follow the rule; harmless edits (label must stay) {e['invariance_pass']}/{e['invariance_n']}; "
                 f"rule-forced changes {e['directional_pass']}/{e['directional_n']}.")
        for f in e['fails'][:15]:
            L.append(f'- {f}')
    L += ['', 'Not measured: accuracy against people (no human gold set). The pilot posts are a stratified sample, so '
          'shares are not population shares.', '']
    return '\n'.join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('run', help='label run file (jsonl or csv) in the pipeline/CONTRACT.md format')
    ap.add_argument('--name', default=None)
    ap.add_argument('--B', type=int, default=2000, help='bootstrap resamples')
    ap.add_argument('--no-write', action='store_true')
    a = ap.parse_args(argv)
    name = a.name or os.path.splitext(os.path.basename(a.run))[0]
    try:
        labels, info = load_run(a.run)
    except RunError as e:
        print(f'score_run: cannot score {a.run}: {e}', file=sys.stderr)
        return 2
    R = {'regression': score_regression(labels), 'consensus': score_consensus(labels, a.B),
         'xstance': score_xstance(labels, a.B), 'edits': score_edits(labels)}
    text = render(name, info, R)
    print(text)
    if not a.no_write:
        os.makedirs(IO.RESULTS, exist_ok=True)
        safe = ''.join(c if c.isalnum() or c in '-_.' else '_' for c in name)
        with open(os.path.join(IO.RESULTS, f'run_{safe}.md'), 'w', encoding='utf-8') as f:
            f.write(text + '\n')
        with open(os.path.join(IO.RESULTS, f'run_{safe}.json'), 'w', encoding='utf-8') as f:
            json.dump({'name': name, 'info': info, 'scores': R}, f, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == '__main__':
    sys.exit(main())
