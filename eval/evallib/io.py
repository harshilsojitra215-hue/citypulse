"""Loading labels from every source into one shape:  {pid: {'project','stance','voice','arguments'}}.

Accepted inputs:
- pilot JSONL (scripts/pilot/labels_<name>.jsonl): {"pid","project","stance","arguments","voice","evidence"}
- label tool CSV (eval/gold/labels_<name>.csv): pid,labeller,project,stance,voice,arguments,note,saved_at
- pipeline output: JSONL with the same fields; 'id' or 'post_id' accepted instead of 'pid',
  optional 'confidence' / 'probs' kept as-is. Adjust FIELD_ALIASES when pipeline/CONTRACT.md is final.
"""
import csv
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
ROOT = os.path.dirname(EVAL)
PILOT = os.path.join(ROOT, 'scripts', 'pilot')
GOLD = os.path.join(EVAL, 'gold')
RESULTS = os.path.join(EVAL, 'results')

PROJECTS = ['heilbronn_cablecar', 'bonn_cablecar', 'paris_c1', 'ipai', 'other_cablecar', 'irrelevant']
RELEVANT = {'heilbronn_cablecar', 'bonn_cablecar', 'paris_c1', 'ipai'}
STANCES = ['support', 'oppose', 'neutral_informative', 'mixed', 'unclear']
STANCE4 = ['support', 'oppose', 'neutral_informative', 'other']   # mixed + unclear folded into other
VOICES = ['news_institutional', 'politician_official', 'citizen', 'company_vendor', 'unclear']
ARGS = ['cost', 'climate_environment', 'traffic_mobility', 'noise_privacy_overflight', 'cityscape_design',
        'safety_technology', 'ipai_who_benefits', 'process_participation', 'tourism_image', 'other']

FIELD_ALIASES = {'pid': ['pid', 'id', 'post_id', 'mention_id'], 'project': ['project'], 'stance': ['stance'],
                 'voice': ['voice'], 'arguments': ['arguments', 'args']}


def norm(v):
    return str(v).strip().lower() if v not in (None, '') else None


def stance4(s):
    s = norm(s)
    if s is None:
        return None
    return s if s in ('support', 'oppose', 'neutral_informative') else 'other'


def _get(r, field):
    for k in FIELD_ALIASES[field]:
        if k in r and r[k] not in (None, ''):
            return r[k]
    return None


def _args(a):
    if a is None:
        return []
    if isinstance(a, str):
        a = re.split(r'[;,|]', a)
    return sorted({norm(x) for x in a if norm(x)})


def _rec(r):
    a = _get(r, 'arguments')
    if isinstance(a, str) and a.startswith('['):
        r = dict(r, arguments=json.loads(a))      # contract: JSON list stored as a string
    out = {'project': norm(_get(r, 'project')), 'stance': norm(_get(r, 'stance')),
           'voice': norm(_get(r, 'voice')), 'arguments': _args(_get(r, 'arguments'))}
    if str(r.get('abstain', '')).lower() in ('true', '1'):   # contract: abstained = no stance
        out['stance'] = None
        out['abstain'] = True
    for k in ('confidence', 'probs', 'stance_probs', 'project_prob', 'labeller', 'note', 'ref'):
        if k in r:
            out[k] = r[k]
    return out


def load_labels(path):
    """Load a JSONL or CSV label file. Rows without a project label are skipped (not yet labelled)."""
    d = {}
    if path.endswith('.csv'):
        with open(path, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                pid = _get(r, 'pid')
                if pid and norm(r.get('project')):
                    d[str(pid)] = _rec(r)
    else:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                pid = _get(r, 'pid')
                if pid and norm(_get(r, 'project')):
                    d[str(pid)] = _rec(r)
    return d


def load_sample(path=None):
    path = path or os.path.join(PILOT, 'sample.jsonl')
    d = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                d[r['pid']] = r
    return d


def load_pilot_ai():
    names = ['haiku', 'sonnet_a', 'sonnet_b']
    return {n: load_labels(os.path.join(PILOT, f'labels_{n}.jsonl')) for n in names}


def mention_to_pilot():
    """export mention_id (contract post_id) -> pilot pid (P###)."""
    with open(os.path.join(PILOT, 'sample_key.csv'), encoding='utf-8-sig', newline='') as f:
        return {r['mention_id']: r['pid'] for r in csv.DictReader(f)}


def to_pilot_ids(d):
    """Re-key {post_id: rec} to pilot pids where the post is in the pilot sample (others keep post_id)."""
    m = mention_to_pilot()
    return {m.get(k, k): dict(v, post_id=k) for k, v in d.items()}


def load_human():
    """All eval/gold/labels_<name>.csv files with at least one label, keyed by pilot pid where possible.
    labels_adjudicated.csv is returned separately."""
    hum, adj = {}, None
    if not os.path.isdir(GOLD):
        return hum, adj
    for fn in sorted(os.listdir(GOLD)):
        m = re.match(r'labels_(.+)\.csv$', fn)
        if not m:
            continue
        d = to_pilot_ids(load_labels(os.path.join(GOLD, fn)))
        if not d:
            continue
        if m.group(1) == 'adjudicated':
            adj = d
        else:
            hum[m.group(1)] = d
    return hum, adj


# Keyword baseline, copied from scripts/pilot/score.py so the eval does not import pilot code.
KW = r'seilbahn|gondel|kabinenbahn|cable car|téléphérique|telepherique|câble|schwebebahn'
PROJ_KW = {'heilbronn_cablecar': r'heilbronn', 'bonn_cablecar': r'bonn|venusberg',
           'paris_c1': r'c1\b|créteil|creteil|paris|val-de-marne', 'ipai': r'\bipai\b|ki-park|innovation park'}


def keyword_baseline(text):
    from collections import Counter
    t = text.lower()
    ipai = bool(re.search(r'\bipai\b|ki-park|innovation park', t))
    found = []
    for m in re.finditer(KW, t):
        seg = t[max(0, m.start() - 300):m.end() + 300]
        for p in ('heilbronn_cablecar', 'bonn_cablecar', 'paris_c1'):
            if re.search(PROJ_KW[p], seg):
                found.append(p)
    if found:
        return Counter(found).most_common(1)[0][0]
    return 'ipai' if ipai else 'irrelevant'
