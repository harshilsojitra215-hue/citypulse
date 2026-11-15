"""Experiment 9: radar precision per project, and whether extra negative words remove junk without losing good items.

Reference = the model's project verdict from the Update-now labels (Sonnet 5.5, 3 runs, vote; live/out/update/latest.json).
That is a second opinion, not human truth. A radar hit counts as "on topic" when the model files it under the same project,
or under the neighbour project (Heilbronn cable car <-> IPAI), because the radar's job is to find the debate, not to split it.

Then: re-run the radar gate (Project.relevance on title + stored text, first 600 characters) with candidate negative words
added, and count junk removed vs on-topic lost. Words were chosen after looking at these same items, so the result is
optimistic (tuned and tested on the same 101 items) and must be rechecked on the next scans.
Run: python -I -X utf8 live/experiments/exp9_radar_precision.py   -> logs/exp9_radar_precision.log
"""
import json
import os
import sqlite3
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.dirname(HERE)
sys.path.insert(0, LIVE)
from collector.core import load_config, load_projects  # noqa: E402

CANDIDATES = {
    'heilbronn_cablecar': ['Ausflugsziel', 'Ausflugsziele', 'Tripsdrill', 'Erlebnisberg', 'Stollen', 'Bergwerk', 'Salzbergwerk',
                           'Ski', 'Skigebiet', 'Skilift', 'Alpen', 'Bergbahn'],
    'paris_c1': ['Emplois', 'Emploi', 'Indeed', "offres d'emploi", 'CDI', 'CDD'],
    'bonn_cablecar': ['Ski', 'Skigebiet', 'Skilift', 'Alpen', 'Bergbahn'],
}
NEIGHBOUR = {'heilbronn_cablecar': 'ipai', 'ipai': 'heilbronn_cablecar'}
CORE = ['heilbronn_cablecar', 'ipai', 'bonn_cablecar', 'paris_c1']

lines = []
out = lambda s='': (print(s), lines.append(s))  # noqa: E731

upd = json.load(open(os.path.join(LIVE, 'out', 'update', 'latest.json'), encoding='utf-8'))
db = sqlite3.connect(os.path.join(LIVE, 'data', 'live_radar_v2.db'))
text = {mid: (t or '', x or '') for mid, t, x in db.execute('SELECT mention_id, title, text FROM items')}
cfg = load_config(None)
projects = {p.id: p for p in load_projects(cfg, None)}

items = [i for i in upd['items'] if i['label_state'] != 'pending' and i['radar_project'] in CORE]
on = lambda i: i['llm_project'] in (i['radar_project'], NEIGHBOUR.get(i['radar_project']))  # noqa: E731

out('# Radar precision vs the model\'s project verdict (101 core items, 14 Nov scans)')
out()
out('| Project | strong radar hits | model: on topic | precision | junk |')
out('|---|---|---|---|---|')
for p in CORE:
    g = [i for i in items if i['radar_project'] == p]
    k = sum(on(i) for i in g)
    out(f'| {p} | {len(g)} | {k} | {k / len(g):.0%} | {len(g) - k} |')
k = sum(on(i) for i in items)
out(f'| all | {len(items)} | {k} | {k / len(items):.0%} | {len(items) - k} |')
out()
out('Junk by kind: ' + str(Counter(i['kind'] for i in items if not on(i)).most_common()))
out('On topic by kind: ' + str(Counter(i['kind'] for i in items if on(i)).most_common()))
out()
out('## Candidate negative words (re-gate with the same rule, words added)')
for p, words in CANDIDATES.items():
    pr = projects[p]
    g = [i for i in items if i['radar_project'] == p]
    gate = lambda i: pr.relevance(*text.get(i['id'], ('', '')))  # noqa: E731
    base = {i['id']: gate(i) for i in g}                 # same gate, old words, on the stored text
    old_neg = list(pr.negative_words)
    pr.negative_words = old_neg + words
    pr._neg = pr._rx(pr.negative_words)
    new = {i['id']: gate(i) for i in g}
    pr.negative_words = old_neg
    pr._neg = pr._rx(old_neg)
    dropped = [i for i in g if base[i['id']] == 'strong' and new[i['id']] != 'strong']
    removed_junk = [i for i in dropped if not on(i)]
    lost_good = [i for i in dropped if on(i)]
    n_junk = sum(not on(i) for i in g)
    out(f'- {p}: baseline strong on stored text {sum(v == "strong" for v in base.values())} of {len(g)}; '
        f'new words remove junk {len(removed_junk)} of {n_junk}, lose on-topic {len(lost_good)} of {len(g) - n_junk}')
    for i in removed_junk:
        out(f'    removed junk: {(i["title"] or i.get("snippet") or "")[:80]}')
    for i in lost_good:
        out(f'    LOST GOOD   : {(i["title"] or i.get("snippet") or "")[:80]}')
    for i in g:
        if not on(i) and i not in removed_junk:
            out(f'    still junk  : {(i["title"] or i.get("snippet") or "")[:80]}')
os.makedirs(os.path.join(HERE, 'logs'), exist_ok=True)
open(os.path.join(HERE, 'logs', 'exp9_radar_precision.log'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
