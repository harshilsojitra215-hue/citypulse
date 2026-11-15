"""Replay mode: re-present HELD-OUT HISTORICAL records as if they had just been collected, clearly labelled, for a demo when
nothing new exists. Design in knowledge/STADT_LIVE_EXPERIMENTS.md section 7. This file only builds the input; no UI.

  python replay.py --from 2026-10-06 --to 2026-10-27 --n 12 --out-dir out

Rules (they are what keeps a replay honest):
  * every record has replay=true, mention_id 'replay:<original mention_id>' (never 'live:'), kind from the original, and
    replay_of = the original id. published_at stays the ORIGINAL date (we never pretend it is new).
  * the receipt has mode 'replay', status 'replay' (never 'success'), published false, and a message that starts with REPLAY.
  * records come from the city's historical export (read only), only ones the pipeline already counted as relevant
    (label_source human, vote or rules_curated), so the demo shows real classified material.
  * a replay must run on a pipeline copy where this window is REMOVED from the baseline, or the originals count twice.
Reads pipeline/data/parquet (read only). Writes only into --out-dir.
"""
import argparse
import datetime as dt
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PQ = os.path.join(ROOT, 'pipeline', 'data', 'parquet')
RELEVANT = ['heilbronn_cablecar', 'bonn_cablecar', 'paris_c1', 'ipai']


def build(date_from, date_to, n, seed=7):
    posts = pd.read_parquet(os.path.join(PQ, 'posts.parquet'))
    lf = pd.read_parquet(os.path.join(PQ, 'labels_final.parquet'), columns=['post_id', 'project', 'label_source'])
    lf = lf[lf.project.isin(RELEVANT) & lf.label_source.isin(['human', 'vote', 'rules_curated'])]
    d = posts[posts.origin == 'dataset'].merge(lf, on='post_id')
    d = d[(d.published_at >= pd.Timestamp(date_from, tz='UTC')) & (d.published_at < pd.Timestamp(date_to, tz='UTC') + pd.Timedelta(days=1))]
    d = d[d.media_type.isin(['News', 'Other', 'Blog']) | (d.text_len > 60)]
    # spread over projects: take the same number per project where possible, then fill up
    per = max(1, n // len(RELEVANT))
    pick = pd.concat([g.sample(min(per, len(g)), random_state=seed) for _, g in d.groupby('project')])
    if len(pick) < n:
        rest = d[~d.post_id.isin(pick.post_id)]
        pick = pd.concat([pick, rest.sample(min(n - len(pick), len(rest)), random_state=seed)])
    pick = pick.sort_values('published_at')
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    recs = []
    for r in pick.itertuples():
        recs.append({
            'mention_id': 'replay:' + str(r.post_id), 'replay': True, 'replay_of': str(r.post_id), 'published': False,
            'media_type_name': r.media_type, 'published_at': pd.Timestamp(r.published_at).strftime('%Y-%m-%dT%H:%M:%S+0000'),
            'source_name': r.source, 'url': r.url, 'country_code': r.country_code, 'language_code': r.language,
            'sentiment': -99, 'reach': None, 'engagements': int(r.engagements), 'authors': [], 'title': r.title, 'content': r.text,
            'kind': 'article' if r.media_type == 'News' else 'other', 'discovered_at': now, 'modified_at': None,
            'project_hint': r.project, 'collector_source': 'replay_of_historical_export'})
    return recs, d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--from', dest='dfrom', default='2026-10-06')
    ap.add_argument('--to', dest='dto', default='2026-10-27')
    ap.add_argument('--n', type=int, default=12)
    ap.add_argument('--out-dir', default=os.path.join(HERE, 'out'))
    a = ap.parse_args()
    recs, pool = build(a.dfrom, a.dto, a.n)
    now = dt.datetime.now(dt.timezone.utc)
    run_id = 'REPLAY_' + now.strftime('%Y%m%dT%H%M%SZ')
    os.makedirs(a.out_dir, exist_ok=True)
    raw = os.path.join(a.out_dir, 'replay_raw.json')
    json.dump(recs, open(raw, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    by_p = {}
    for r in recs:
        by_p[r['project_hint']] = by_p.get(r['project_hint'], 0) + 1
    rc = {
        'schema_version': 1, 'run_id': run_id, 'mode': 'replay', 'replay': True, 'published': False, 'status': 'replay',
        'message': (f'REPLAY: {len(recs)} historical records from {a.dfrom} to {a.dto} re-presented for a demo. '
                    'These are NOT new posts and were not collected today. Do not count them as live evidence.'),
        'started_at': now.isoformat(timespec='seconds'), 'finished_at': now.isoformat(timespec='seconds'),
        'replay_window': {'from': a.dfrom, 'to': a.dto, 'pool_size': int(len(pool)), 'picked': len(recs)},
        'replay_source': "city's historical export (read only), only records the pipeline already counted as relevant",
        'sources': [], 'totals': {'truly_new': 0, 'replayed_records': len(recs)}, 'per_project_replayed': by_p,
        'coverage_gaps': ['No live collection ran in this receipt. This is a replay.'],
        'rules': ['mention_id starts with replay:', 'published_at is the original date', 'pipeline origin must be replay, never live',
                  'dashboard shows a banner and keeps replay out of live counters and out of "what changed"']}
    with open(os.path.join(a.out_dir, f'receipt_{run_id}.json'), 'w', encoding='utf-8') as f:
        json.dump(rc, f, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out_dir, f'receipt_{run_id}.md'), 'w', encoding='utf-8') as f:
        f.write(f"# Run receipt {run_id}\n\n**{rc['message']}**\n\n- Mode: replay. Status: replay (never success). Published: false.\n"
                f"- Pool in the window: {len(pool)} relevant records; picked {len(recs)}: {by_p}\n- Each record: replay=true, id replay:<original>, original date kept.\n")
    print(rc['message'])
    print('wrote', raw)
    return 0


if __name__ == '__main__':
    sys.exit(main())
