"""Experiment 10: how much of what the city's paid monitoring tool found does our open radar find? (backtest)

Reference = the city's export (an independent vendor), records published 1 Jul to 27 Oct 2026 that the team's pipeline counts as
relevant to one of the 4 core projects (label_source human, vote or rules_curated). Read only.
Radar = a backtest scan with the real collector (`run_collect.py --radar --since 2026-07-01`, 4 core projects, all enabled
sources) into its own store (experiments/data/backtest.db), so the live store is not touched.
Found = same canonical link, or title word overlap (Jaccard) >= 0.6 with any radar item (title + start of text).
Reported per project and per platform. Social platforms can only be found as search-result links.

Limits (say them): search indexes forget and re-rank, so a backtest finds less than a scan made at the time; the reference
is labelled by our own pipeline (rules + AI), not by people; title matching can miss renamed copies.
Run (after the backtest scan): python -I -X utf8 live/experiments/exp10_recall_vs_city_tool.py
"""
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.dirname(HERE)
ROOT = os.path.dirname(LIVE)
sys.path.insert(0, LIVE)
import pandas as pd  # noqa: E402
from collector.core import canonical_url  # noqa: E402

DB = os.path.join(HERE, 'data', 'backtest.db')
CORE = ['heilbronn_cablecar', 'ipai', 'bonn_cablecar', 'paris_c1']
FROM, TO = '2026-07-01', '2026-10-27T12:29:00+00:00'
lines = []
out = lambda s='': (print(s), lines.append(s))  # noqa: E731


def toks(t):
    t = re.sub(r'\s*[-|–]\s*[^-|–]{0,40}$', '', (t or '').lower())    # drop " - Outlet name" endings
    return {w for w in re.findall(r'\w+', t) if len(w) > 2}


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


P = os.path.join(ROOT, 'pipeline', 'data', 'parquet')
posts = pd.read_parquet(os.path.join(P, 'posts.parquet'), columns=['post_id', 'published_at', 'platform', 'source', 'title', 'url', 'media_type'])
f = pd.read_parquet(os.path.join(P, 'labels_final.parquet'))
ref = f[f.project.isin(CORE) & f.label_source.isin(['human', 'vote', 'rules_curated'])].merge(posts, on='post_id')
ref = ref[(ref.published_at >= pd.Timestamp(FROM, tz='UTC')) & (ref.published_at <= pd.Timestamp(TO))]

db = sqlite3.connect(DB)
radar = [dict(zip(('url', 'title', 'text', 'source', 'radar_match', 'published_at'), r))
         for r in db.execute('SELECT url, title, text, source, radar_match, published_at FROM items WHERE dup_of IS NULL')]
by_url = {canonical_url(r['url']): r for r in radar}
rtoks = [(toks(r['title']), r) for r in radar]

res = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))   # project -> platform -> [reference, found any, found strong]
examples = []
for x in ref.itertuples():
    hit = by_url.get(canonical_url(x.url))
    if hit is None:
        tt = toks(x.title)
        best = max(rtoks, key=lambda z: jac(tt, z[0]), default=(None, None))
        if best[1] is not None and jac(tt, best[0]) >= 0.6:
            hit = best[1]
    c = res[x.project][x.platform]
    c[0] += 1
    if hit:
        c[1] += 1
        c[2] += hit['radar_match'] == 'strong'
    elif x.platform == 'web' and len(examples) < 12:
        examples.append(f'{str(x.published_at)[:10]} {x.project:18} {x.source:25} {str(x.title)[:70]}')

out(f'# Backtest: radar vs the city\'s tool, items published {FROM} to 27 Oct 2026')
out(f'Radar store: {len(radar)} items; reference: {len(ref)} relevant records from the city export.')
out()
out('| Project | Platform | city tool found | radar found | of those: strong match | share found |')
out('|---|---|---|---|---|---|')
tot = defaultdict(lambda: [0, 0, 0])
for p in CORE:
    for pl, (n, k, s) in sorted(res[p].items(), key=lambda z: -z[1][0]):
        out(f'| {p} | {pl} | {n} | {k} | {s} | {k / n:.0%} |')
        for key in (pl, 'all'):
            for i, v in enumerate((n, k, s)):
                tot[key][i] += v
out()
for key in ['web', 'youtube', 'instagram', 'facebook', 'linkedin', 'all']:
    if key in tot:
        n, k, s = tot[key]
        out(f'- {key}: {k} of {n} found ({k / n:.0%}), {s} as strong match')
out()
out('Missed web examples (to learn from):')
for e in examples:
    out('  ' + e)
json.dump({p: {pl: v for pl, v in d.items()} for p, d in res.items()}, open(os.path.join(HERE, 'logs', 'exp10_recall.json'), 'w'), indent=1)
open(os.path.join(HERE, 'logs', 'exp10_recall_vs_city_tool.log'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
