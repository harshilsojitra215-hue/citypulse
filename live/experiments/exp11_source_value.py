"""Experiment 11: what is each source worth? Unique, on-topic records by kind, not raw counts.

Data: the radar store (live/data/live_radar_v2.db: items + sightings = which source found which item) and the model's
project verdict from the last update report (live/out/update/latest.json; a second opinion, not a person; core projects only).
Per source:
  strong          strong radar matches this source found (any project)
  core labelled   of those, core-project items with a model verdict
  on topic        model files it under the same project (or the Heilbronn/IPAI neighbour)
  unique on topic on-topic items that NO other source found (what we would lose without this source)
  by kind         unique on-topic items by kind: voice (social post, comment, forum, social link), official (official page,
                  council paper, page change), news, web
"Voice" is a hint from the record type (who could have written it), not a judgement of who is speaking; the team's labels decide that.
Run: python -I -X utf8 live/experiments/exp11_source_value.py   -> logs/exp11_source_value.log
"""
import json
import os
import sqlite3
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.dirname(HERE)
NEIGHBOUR = {'heilbronn_cablecar': 'ipai', 'ipai': 'heilbronn_cablecar'}
GROUP = {'social_post': 'voice', 'video_comment': 'voice', 'forum': 'voice', 'social_link': 'voice', 'official': 'official',
         'council_paper': 'official', 'official_page_change': 'official', 'official_news': 'official', 'news': 'news',
         'article': 'news', 'web': 'web', 'video': 'web'}
lines = []
out = lambda s='': (print(s), lines.append(s))  # noqa: E731

db = sqlite3.connect(os.path.join(LIVE, 'data', 'live_radar_v2.db'))
items = {r[0]: {'mid': r[1], 'kind': r[2], 'match': r[3], 'scope': r[4]}
         for r in db.execute("SELECT key, mention_id, kind, radar_match, text_scope FROM items WHERE dup_of IS NULL")}
found = defaultdict(set)
for key, src in db.execute('SELECT DISTINCT key, source FROM sightings'):
    if key in items:
        found[key].add(src)
upd = {i['id']: i for i in json.load(open(os.path.join(LIVE, 'out', 'update', 'latest.json'), encoding='utf-8'))['items']}


def on_topic(mid):
    i = upd.get(mid)
    if not i or i['label_state'] == 'pending' or i['llm_project'] is None:
        return None
    return i['llm_project'] in (i['radar_project'], NEIGHBOUR.get(i['radar_project']))


rows = defaultdict(Counter)
uniq_kind = defaultdict(Counter)
for key, it in items.items():
    if it['match'] != 'strong':
        continue
    ot = on_topic(it['mid'])
    for src in found[key]:
        c = rows[src]
        c['strong'] += 1
        c['snippet_only'] += it['scope'] == 'snippet'
        if ot is not None:
            c['labelled'] += 1
            c['on_topic'] += ot
            c['citizen'] += bool(ot) and upd[it['mid']].get('voice') == 'citizen'
            if ot and found[key] == {src}:
                c['unique'] += 1
                c['unique_citizen'] += upd[it['mid']].get('voice') == 'citizen'
                uniq_kind[src][GROUP.get(it['kind'], 'web')] += 1

out('# Source value (radar store, strong matches; on topic = model verdict for core projects)')
out()
out('| Source | strong | snippet only | core labelled | on topic | model: citizen | unique on topic | unique citizen | unique by record type: voice / official / news / web |')
out('|---|---|---|---|---|---|---|---|---|')
for src, c in sorted(rows.items(), key=lambda z: -z[1]['unique']):
    k = uniq_kind[src]
    out(f"| {src} | {c['strong']} | {c['snippet_only']} | {c['labelled']} | {c['on_topic']} | {c['citizen']} | {c['unique']} | {c['unique_citizen']} | "
        f"{k['voice']} / {k['official']} / {k['news']} / {k['web']} |")
multi = sum(1 for k, it in items.items() if it['match'] == 'strong' and len(found[k]) > 1)
out()
out(f"Strong items found by more than one source: {multi} of {sum(1 for it in items.values() if it['match'] == 'strong')}.")
out('Limits: one evening of scans; the model is the judge; "unique" depends on which sources ran in which scans.')
os.makedirs(os.path.join(HERE, 'logs'), exist_ok=True)
open(os.path.join(HERE, 'logs', 'exp11_source_value.log'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
