"""Stage 4: collect every label run, vote, abstain when runs disagree.

Inputs (all optional; the stage works with whatever exists):
- the pilot: scripts/pilot/labels_{sonnet_a,sonnet_b,haiku}.jsonl, pid mapped to mention_id via sample_key.csv
- pipeline/data/label_runs/*.jsonl (cloud LLM, local LLM, student, Hamburg runs; header line {"_run": {...}})
- eval/gold/labels_<name>.csv (human labels, read only)

Outputs: label_runs, labels, human_labels, labels_final.

Vote rules (labels_final):
- a human label wins (adjudicated file first, then the only/first annotator)
- otherwise the majority over LLM runs (cloud or local); `agreement_*` = share of runs that chose the winner
- stance: if no strict majority, or fewer than `min_runs_for_vote` runs -> abstain=true, stance shown as 'uncertain'
- confidence: high = unanimous with 3+ runs, medium = majority, low = split or abstain
- no LLM label: project from the curated research rules (reference/curated_v0.csv), label_source='rules_curated'
- only the wide net: label_source='wide_net', project = rule hint, NOT counted as relevant in the export
- the student's guess is kept in student_project / student_prob as a second opinion
"""
import csv
import glob
import json
import os
import re
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import CFG, RUNS, codebook_sha, log, path, read_table, write_table  # noqa: E402

PILOT_RUNS = {
    'sonnet_a': ('claude-sonnet (pilot run A)', 'llm_cloud'),
    'sonnet_b': ('claude-sonnet (pilot run B, reversed order)', 'llm_cloud'),
    'haiku': ('claude-haiku (pilot)', 'llm_cloud'),
}
LABEL_COLS = ['run_id', 'post_id', 'project', 'project_prob', 'stance', 'stance_probs', 'voice', 'arguments', 'evidence', 'abstain']


def _row(run_id, r, pid_map=None):
    pid = str(r.get('post_id') or r.get('mention_id') or r.get('id') or r.get('pid'))
    if pid_map is not None:
        pid = pid_map.get(pid, pid)
    args = r.get('arguments') or []
    if isinstance(args, str):
        args = [a for a in re.split(r'[;,|]', args) if a.strip()]
    sp = r.get('stance_probs')
    return {'run_id': run_id, 'post_id': pid, 'project': r.get('project'),
            'project_prob': r.get('project_prob'), 'stance': r.get('stance'),
            'stance_probs': json.dumps(sp) if isinstance(sp, dict) else sp,
            'voice': r.get('voice'), 'arguments': json.dumps(sorted(set(a.strip() for a in args))),
            'evidence': r.get('evidence'), 'abstain': bool(r.get('abstain', False)) or not r.get('project')}


def load_pilot():
    pdir = path('pilot_dir')
    key = pd.read_csv(os.path.join(pdir, 'sample_key.csv'), encoding='utf-8-sig', dtype=str)
    pid_map = dict(zip(key.pid, key.mention_id))
    runs, labels = [], []
    for name, (labeller, kind) in PILOT_RUNS.items():
        p = os.path.join(pdir, f'labels_{name}.jsonl')
        if not os.path.exists(p):
            continue
        run_id = f'pilot_{name}_cb1'
        n = 0
        for line in open(p, encoding='utf-8'):
            if line.strip():
                labels.append(_row(run_id, json.loads(line), pid_map))
                n += 1
        runs.append({'run_id': run_id, 'created_at': pd.Timestamp('2026-11-14', tz='UTC'), 'labeller': labeller,
                     'kind': kind, 'runs_where': 'cloud_us', 'task': 'all', 'prompt_version': 'pilot',
                     'codebook_version': 'v1', 'codebook_sha': codebook_sha(), 'params': '{}', 'n_items': n})
    return runs, labels


def load_run_files():
    runs, labels = [], []
    for p in sorted(glob.glob(os.path.join(RUNS, '*.jsonl'))):
        header, rows = None, []
        for line in open(p, encoding='utf-8'):
            if not line.strip():
                continue
            r = json.loads(line)
            if '_run' in r:
                header = r['_run']
            else:
                rows.append(r)
        if not header:
            log('labels', f'skip {os.path.basename(p)}: no {{"_run": ...}} header line')
            continue
        rid = header['run_id']
        labels += [_row(rid, r) for r in rows]
        runs.append({'run_id': rid, 'created_at': pd.Timestamp(header.get('created_at', pd.Timestamp.now(tz='UTC'))),
                     'labeller': header.get('labeller'), 'kind': header.get('kind'), 'runs_where': header.get('runs_where'),
                     'task': header.get('task', 'all'), 'prompt_version': header.get('prompt_version'),
                     'codebook_version': header.get('codebook_version', 'v1'), 'codebook_sha': header.get('codebook_sha'),
                     'params': json.dumps(header.get('params', {})), 'n_items': len(rows)})
        if header.get('codebook_sha') and header['codebook_sha'] != codebook_sha():
            log('labels', f'WARNING {rid}: codebook_sha differs from the current codebook')
    return runs, labels


def load_human():
    gdir = path('gold_dir')
    rows = []
    for p in sorted(glob.glob(os.path.join(gdir, 'labels_*.csv'))):
        name = re.match(r'labels_(.+)\.csv$', os.path.basename(p)).group(1)
        with open(p, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                if not (r.get('project') or '').strip():
                    continue
                rows.append({'post_id': r.get('pid'), 'annotator': name, 'project': r['project'].strip(),
                             'stance': (r.get('stance') or '').strip() or None, 'voice': (r.get('voice') or '').strip() or None,
                             'arguments': json.dumps(sorted(a.strip() for a in re.split(r'[;,|]', r.get('arguments') or '') if a.strip())),
                             'saved_at': r.get('saved_at')})
    h = pd.DataFrame(rows, columns=['post_id', 'annotator', 'project', 'stance', 'voice', 'arguments', 'saved_at'])
    # gold files may use pilot pids (P001); map them to mention_id
    key = pd.read_csv(os.path.join(path('pilot_dir'), 'sample_key.csv'), encoding='utf-8-sig', dtype=str)
    h['post_id'] = h.post_id.map(dict(zip(key.pid, key.mention_id))).fillna(h.post_id)
    return h


def strict_majority(vals):
    vals = [v for v in vals if v]
    if not vals:
        return None, 0.0
    (top, n), *rest = Counter(vals).most_common()
    if rest and rest[0][1] == n:
        return None, n / len(vals)
    return top, n / len(vals)


def vote(labels, human, cands, kinds=None):
    """Priority: human > LLM vote > curated rules > wide net (not counted as relevant)."""
    kinds = kinds or {}
    minr = CFG['labels']['min_runs_for_vote']
    hum = {}
    if len(human):
        h = human.copy()
        h['prio'] = (h.annotator != 'adjudicated').astype(int)
        for pid, g in h.sort_values('prio').groupby('post_id'):
            hum[pid] = g.iloc[0]
    lab = labels[~labels.abstain].copy() if len(labels) else labels
    lab['kind'] = lab.run_id.map(kinds)
    llm = {pid: g for pid, g in lab[lab.kind.isin(['llm_cloud', 'llm_local'])].groupby('post_id')}
    rules = dict(zip(*lab[lab.kind == 'rules'][['post_id', 'project']].values.T)) if (lab.kind == 'rules').any() else {}
    stu = lab[lab.kind == 'student'].sort_values('project_prob').drop_duplicates('post_id', keep='last')
    stu_p, stu_pr = dict(zip(stu.post_id, stu.project)), dict(zip(stu.post_id, stu.project_prob))
    hint = dict(zip(cands.post_id, cands.project_hint))
    ids = list(dict.fromkeys(list(cands.post_id) + list(llm) + list(rules) + list(hum)))
    out = []
    for pid in ids:
        base = {'post_id': pid, 'student_project': stu_p.get(pid), 'student_prob': stu_pr.get(pid)}
        if pid in hum:
            r = hum[pid]
            out.append({**base, 'project': r.project, 'stance': r.stance, 'voice': r.voice, 'arguments': r.arguments,
                        'n_runs': int(len(llm.get(pid, []))), 'agreement_project': 1.0, 'agreement_stance': 1.0,
                        'confidence': 'high', 'abstain': False, 'label_source': 'human'})
        elif pid in llm:
            g = llm[pid]
            n = len(g)
            proj, ap = strict_majority(g.project.tolist())
            st, ast = strict_majority(g.stance.tolist())
            vo, _ = strict_majority(g.voice.tolist())
            args = Counter(a for x in g.arguments for a in json.loads(x or '[]'))
            arg = sorted(a for a, c in args.items() if c * 2 >= n)
            abstain = st is None or n < minr
            conf = 'low' if abstain or proj is None else ('high' if ap == 1.0 and ast == 1.0 and n >= 3 else 'medium')
            out.append({**base, 'project': proj or rules.get(pid) or hint.get(pid), 'stance': None if abstain else st,
                        'voice': vo, 'arguments': json.dumps(arg), 'n_runs': n, 'agreement_project': ap,
                        'agreement_stance': ast, 'confidence': conf, 'abstain': abstain, 'label_source': 'vote'})
        elif pid in rules:
            out.append({**base, 'project': rules[pid], 'stance': None, 'voice': None, 'arguments': '[]', 'n_runs': 0,
                        'agreement_project': None, 'agreement_stance': None,
                        'confidence': 'medium' if stu_p.get(pid) == rules[pid] else 'low', 'abstain': True,
                        'label_source': 'rules_curated'})
        else:
            out.append({**base, 'project': hint.get(pid), 'stance': None, 'voice': None, 'arguments': '[]', 'n_runs': 0,
                        'agreement_project': None, 'agreement_stance': None, 'confidence': 'low', 'abstain': True,
                        'label_source': 'wide_net'})
    return pd.DataFrame(out)


def load_curated():
    p = os.path.join(os.path.dirname(path('faq')), 'curated_v0.csv')
    if not os.path.exists(p):
        return [], []
    d = pd.read_csv(p, dtype=str)
    run = {'run_id': 'rules_curated_v0', 'created_at': pd.Timestamp('2026-11-14', tz='UTC'),
           'labeller': 'curated keyword rules + manual additions (research phase, scripts/deep_stadt)', 'kind': 'rules',
           'runs_where': 'local_laptop', 'task': 'project', 'prompt_version': None, 'codebook_version': 'v1',
           'codebook_sha': codebook_sha(), 'params': '{}', 'n_items': len(d)}
    labels = [{'run_id': 'rules_curated_v0', 'post_id': r.post_id, 'project': r.project, 'project_prob': None, 'stance': None,
               'stance_probs': None, 'voice': None, 'arguments': '[]', 'evidence': None, 'abstain': False} for r in d.itertuples()]
    return [run], labels


def run():
    cands = read_table('candidates')
    r1, l1 = load_pilot()
    r2, l2 = load_run_files()
    r3, l3 = load_curated()
    runs = pd.DataFrame(r1 + r3 + r2)
    labels = pd.DataFrame(l1 + l3 + l2, columns=LABEL_COLS)
    labels['project_prob'] = pd.to_numeric(labels.project_prob, errors='coerce')
    human = load_human()
    final = vote(labels, human, cands, dict(zip(runs.run_id, runs.kind)) if len(runs) else {})
    write_table('label_runs', runs)
    write_table('labels', labels)
    write_table('human_labels', human)
    write_table('labels_final', final)
    not_in_cands = set(labels.post_id) - set(cands.post_id)
    log('labels', f"{len(runs)} runs, {len(labels):,} labels, {len(human):,} human labels, "
                  f"final={len(final):,} by source {final.label_source.value_counts().to_dict()}, "
                  f"abstain among voted={int(final[final.label_source == 'vote'].abstain.sum())}; "
                  f"{len(not_in_cands)} labelled posts are outside the rule net (kept)")
    return final


if __name__ == '__main__':
    run()
