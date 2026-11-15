"""Experiment 8: independent reference set, found vs missed, with Google News ON and OFF.
Reference set = relevant NEWS/blog/official records from the city's historical export (an independent vendor, read only):
the last 8 per project that the pipeline counted as relevant (label_source human, vote or rules_curated).
We only have a window of stored collector output (since 15 Sep 2026), so reference items older than that are reported as
"outside the tested window" and NOT as missed.
Found = a collector item (title similarity >= 0.6) in any stored collector DB:
  with Google News ON : all sources stored in live.db, volume_test.db, experiments/data/idem*.db
  with Google News OFF: the same without items found only by Google News, plus the current content of the 5 outlet RSS feeds (fetched now, 5 requests)
No new Google News request is made here (it is switched off). NOT true recall: 8 records per project, chosen by our own pipeline.
Run: python -X utf8 exp8_reference_set.py -> logs/exp8_reference_set.log
"""
import json, os, re, sqlite3
import pandas as pd
from exp_common import Tee, LIVE, HERE, ROOT, LOGS
from collector.core import Http, load_config
from collector.adapters.rss import Rss

out = Tee('exp8_reference_set.log')
cfg = load_config()
WINDOW = '2026-09-15'
RELEVANT = ['heilbronn_cablecar', 'bonn_cablecar', 'paris_c1', 'ipai']


def toks(t):
    t = re.sub(r'\s*[-|]\s*(stimme\.de|.*nachrichten.*)$', '', (t or '').lower())
    return set(w for w in re.findall(r'\w+', t) if len(w) > 2)


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


posts = pd.read_parquet(os.path.join(ROOT, 'pipeline', 'data', 'parquet', 'posts.parquet'))
lf = pd.read_parquet(os.path.join(ROOT, 'pipeline', 'data', 'parquet', 'labels_final.parquet'))
ref = lf[lf.project.isin(RELEVANT) & lf.label_source.isin(['human', 'vote', 'rules_curated'])].merge(posts, on='post_id', suffixes=('', '_p'))
ref = ref[ref.media_type.isin(['News', 'Other', 'Blog'])].sort_values('published_at', ascending=False)

# stored collector output
col = []                      # (tokens, source, db)
for dbn in [os.path.join(LIVE, 'data', 'live.db'), os.path.join(LIVE, 'data', 'volume_test.db'),
            os.path.join(HERE, 'data', 'idem.db'), os.path.join(HERE, 'data', 'idem_full.db')]:
    if os.path.exists(dbn):
        c = sqlite3.connect(dbn)
        for title, src, pub in c.execute('SELECT title, source, published_at FROM items'):
            col.append((toks(title), src, pub))
# current content of the outlet feeds
http = Http(cfg['defaults']['user_agent'])
rss = Rss(cfg['sources']['rss'], http)
feed_titles = []
for f in cfg['sources']['rss']['feeds']:
    ents = rss._feed(f)
    for t, d, l, p in ents or []:
        feed_titles.append(toks(t))
out(f'collector items stored: {len(col)} ({sum(1 for x in col if x[1] == "gnews")} from Google News); outlet feeds now hold {len(feed_titles)} entries')


def found(tk, methods):
    best = 0.0
    how = set()
    for t, src, _ in col:
        if src in methods:
            s = jac(tk, t)
            if s >= 0.6:
                how.add(src)
            best = max(best, s)
    if 'rss_now' in methods:
        if any(jac(tk, t) >= 0.6 for t in feed_titles):
            how.add('rss_now')
    return how


ON = {'gnews', 'bluesky', 'mastodon', 'oparl', 'rss', 'rss_now', 'gdelt'}
OFF = ON - {'gnews'}
res = {}
tot = {'in_window': 0, 'found_on': 0, 'found_off': 0, 'outside': 0}
out(f'\n{"project":20} {"ref items":>9} {"in window":>9} {"found ON":>9} {"found OFF":>10} {"outside window":>14}')
for p in RELEVANT:
    r = ref[ref.project == p].head(8)
    inw = r[r.published_at >= pd.Timestamp(WINDOW, tz='UTC')]
    rows = []
    for _, x in inw.iterrows():
        tk = toks(x['title'])
        rows.append((str(x['published_at'])[:10], x['source'], x['title'][:70], sorted(found(tk, ON)), sorted(found(tk, OFF))))
    fon = sum(bool(a) for *_, a, b in rows)
    foff = sum(bool(b) for *_, a, b in rows)
    res[p] = {'ref': len(r), 'in_window': len(inw), 'found_on': fon, 'found_off': foff, 'outside_window': len(r) - len(inw), 'rows': rows}
    out(f'{p:20} {len(r):9} {len(inw):9} {fon:9} {foff:10} {len(r) - len(inw):14}')
    for d, s, t, a, b in rows:
        out(f'    {d} {s[:22]:22} ON={",".join(a) or "MISSED":18} OFF={",".join(b) or "MISSED":10} {t}')
    for k, v in (('in_window', len(inw)), ('found_on', fon), ('found_off', foff), ('outside', len(r) - len(inw))):
        tot[k] += v
out(f'\nTOTAL in-window reference items {tot["in_window"]}: found with Google News ON {tot["found_on"]}, found with Google News OFF {tot["found_off"]}; {tot["outside"]} reference items are older than {WINDOW} (not testable, not counted as missed)')
out('Earlier bounded test (exp2 B2): live Google News queries found 6 of 11 historical Heilbronn NEWS records dated 20 Jul or later; the 5 missed were non-Stimme outlets.')
out('What is lost without Google News: every non-RSS news headline (Stimme, Le Parisien, actu.fr, Ouest-France, laclepublique). What remains: official pages, OParl, Bluesky news posts, current outlet feeds (hold only a few days).')
out('GDELT, the intended replacement, answered 429 on 11 of 12 requests today (exp2_gdelt_probe.log), so it contributes nothing yet.')
json.dump(res, open(os.path.join(LOGS, 'exp8_reference_set.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
