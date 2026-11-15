"""Experiment 1: precision per source and per project, from hand judgments (judgments.py).
Run: python -X utf8 exp1_precision.py   -> logs/exp1_precision.log, logs/exp1_precision.json, ../data/relevance_judgments.json
"""
import collections, json, os, re
from exp_common import Tee, items, LIVE, LOGS, HERE
from judgments import J
from collector.core import Project, load_config

out = Tee('exp1_precision.log')
cfg = load_config()
P = {k: Project(k, v) for k, v in cfg['projects'].items()}

live = {r['key']: r for r in items('live.db')}
vol = {r['key']: r for r in items('volume_test.db')}
allr = {**vol, **live}
rows, missing = [], []
for k, r in allr.items():
    lab = J.get(k[:6])
    if not lab:
        missing.append((k[:6], r['title'][:80]))
        continue
    r['label'], r['why'] = lab
    r['project'] = r['projects'].split(',')[0]
    r['in_live_db'] = k in live
    r['in_vol_db'] = k in vol
    rows.append(r)
out(f'items in live.db={len(live)}  volume_test.db={len(vol)}  union={len(allr)}  judged={len(rows)}  missing judgments={len(missing)}')
for m in missing:
    out('  MISSING', m)
multi = [r['key'][:6] for r in rows if ',' in r['projects']]
out('items collected for more than one project:', multi or 'none')


def table(title, keyf, subset):
    out(f'\n== {title}')
    out(f'{"group":38} {"n":>3} {"R":>3} {"U":>3} {"N":>3} | {"strict R/n":>10} {"R/(R+N)":>8} {"lenient (R+U)/n":>16}')
    g = collections.defaultdict(collections.Counter)
    for r in subset:
        g[keyf(r)][r['label']] += 1
    res = {}
    for k in sorted(g):
        c = g[k]
        n = sum(c.values())
        sr = c['R'] / n
        dec = c['R'] / (c['R'] + c['N']) if c['R'] + c['N'] else float('nan')
        le = (c['R'] + c['U']) / n
        res[str(k)] = dict(n=n, R=c['R'], U=c['U'], N=c['N'], strict=round(sr, 2), decided=None if dec != dec else round(dec, 2), lenient=round(le, 2))
        out(f'{str(k):38} {n:3} {c["R"]:3} {c["U"]:3} {c["N"]:3} | {sr:10.0%} {dec:8.0%} {le:16.0%}')
    return res


since = '2026-10-27'
w1 = [r for r in rows if r['in_live_db']]           # collected in the real run since 27 Oct (incl. 7 OParl papers dated earlier)
w1_news = [r for r in w1 if r['source'] != 'oparl']  # the 27 exported items
w2 = rows                                            # 60-day volume test plus real run
R = {}
R['A_real_run_27items_by_source'] = table('A. Real run since 27 Oct, items the collector exported (gnews + bluesky, n=27)', lambda r: r['source'], w1_news)
R['A_real_run_by_project'] = table('A. same, by project', lambda r: r['project'], w1_news)
R['B_union_by_source'] = table('B. Union of real run + 60-day volume test (n=%d)' % len(w2), lambda r: r['source'], w2)
R['B_union_by_project'] = table('B. same, by project', lambda r: r['project'], w2)
R['B_union_by_source_project'] = table('B. same, by source and project', lambda r: f"{r['source']} / {r['project']}", w2)

# how good is the title filter (title_hit) as an automatic relevance flag?
out('\n== title_hit flag (collector pre-filter on the headline) against my judgment, items from gnews/bluesky/mastodon in union')
soc = [r for r in w2 if r['source'] in ('gnews', 'bluesky', 'mastodon')]
for hit in (1, 0):
    c = collections.Counter(r['label'] for r in soc if r['title_hit'] == hit)
    n = sum(c.values())
    out(f'  title_hit={hit}: n={n} R={c["R"]} U={c["U"]} N={c["N"]}  R share={c["R"] / n:.0%}' if n else f'  title_hit={hit}: n=0')
out('  title_hit=0 but judged R (the filter would lose these if it dropped them):')
for r in soc:
    if r['title_hit'] == 0 and r['label'] == 'R':
        out('   ', r['project'], '|', r['title'][:100])

# matcher before and after the keyword change made during this experiment (data/projects_before_exp.yaml vs projects.yaml)
OLD = {k: Project(k, v) for k, v in load_config(os.path.join(HERE, 'data', 'projects_before_exp.yaml'))['projects'].items()}
out('\n== title filter before and after the yaml change (added: Heilbronner, IPAI alone, Ile-de-France as place word, "du C1")')
c0, c1 = collections.Counter(), collections.Counter()
for r in soc:
    c0[(bool(OLD[r['project']].matches(r['title'])), r['label'])] += 1
    c1[(bool(P[r['project']].matches(r['title'])), r['label'])] += 1
for nm, c in (('before', c0), ('after', c1)):
    kept = {l: c[(True, l)] for l in 'RUN'}
    out(f'  {nm:7} flags {sum(kept.values())} of {len(soc)} headlines: R={kept["R"]} U={kept["U"]} N={kept["N"]}; relevant headlines missed: {c[(False, "R")]}')

json.dump({'rows': [{k: r[k] for k in ('key', 'source', 'project', 'title', 'label', 'why', 'title_hit', 'in_live_db')} for r in rows],
           'tables': R}, open(os.path.join(LOGS, 'exp1_precision.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
# the collector's receipt reads this file if it exists
json.dump({r['key']: r['label'] for r in rows}, open(os.path.join(LIVE, 'data', 'relevance_judgments.json'), 'w'), indent=0)
out('\nwrote logs/exp1_precision.json and data/relevance_judgments.json')
