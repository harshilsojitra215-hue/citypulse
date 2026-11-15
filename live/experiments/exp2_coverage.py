"""Experiment 2: coverage cross-check.
 A  overlap and unique finds between the independent discovery methods, per project (stored runs, see DB list below)
 B  bounded recall estimate against the historical dataset: of the last 10 Heilbronn cable car records, how many would
    today's collector have matched (1) by headline filter, (2) by the query words in headline+text, (3) with a live Google News
    query for that period. THIS IS NOT TRUE RECALL: the 10 records are a small non-random sample, labelled by our own pipeline.
Run: python -X utf8 exp2_coverage.py   -> logs/exp2_coverage.log, logs/exp2_coverage.json
"""
import collections, datetime as dt, json, os, re, sqlite3, subprocess, sys, time
import pandas as pd
import yaml
from exp_common import Tee, LIVE, HERE, ROOT, LOGS
from judgments import J
from collector.core import Project, Http, load_config
from collector.adapters.gnews import GNews

out = Tee('exp2_coverage.log')
cfg = load_config()
P = {k: Project(k, v) for k, v in cfg['projects'].items()}
DBS = ['live.db', 'volume_test.db', 'gdelt_probe.db', 'complete_probe.db']          # data/ folder and experiments/data/
paths = [os.path.join(LIVE, 'data', 'live.db'), os.path.join(LIVE, 'data', 'volume_test.db'),
         os.path.join(HERE, 'data', 'idem_full.db'), os.path.join(HERE, 'data', 'idem.db')]


def toks(t):
    t = re.sub(r'^(actu paris|actu)\s*-\s*', '', t.lower())
    return set(w for w in re.findall(r'\w+', t) if len(w) > 2)


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


# ---------------------------------------------------------------- A
rows = {}
for pth in paths:
    if not os.path.exists(pth):
        out(f'(db not present: {os.path.relpath(pth, LIVE)})')
        continue
    c = sqlite3.connect(pth)
    c.row_factory = sqlite3.Row
    for r in c.execute("SELECT key, source, projects, title, source_name, published_at, dup_of FROM items WHERE source != 'oparl'"):
        d = dict(r)
        if d['published_at'] < '2026-09-15':
            continue
        rows.setdefault(d['key'], d)
out(f'A. stories since 2026-09-15 from stored runs ({len(rows)} distinct items, article-like and social posts; council papers handled in B2 below)')
items = list(rows.values())
for it in items:
    it['project'] = it['projects'].split(',')[0]
    it['tk'] = toks(it['title'])
# cluster per project by title similarity
cl = {}
for pid in P:
    sub = [i for i in items if i['project'] == pid]
    groups = []
    for it in sub:
        for g in groups:
            if any(jac(it['tk'], m['tk']) >= 0.7 for m in g):
                g.append(it)
                break
        else:
            groups.append([it])
    cl[pid] = groups
method_label = {'gnews': 'Google News', 'bluesky': 'Bluesky', 'gdelt': 'GDELT', 'rss': 'outlet RSS', 'mastodon': 'Mastodon', 'oparl': 'OParl'}
res = {}
for pid, groups in cl.items():
    out(f'\n-- {pid}: {sum(len(g) for g in groups)} items, {len(groups)} distinct stories')
    meth = collections.defaultdict(set)
    for gi, g in enumerate(groups):
        for m in g:
            meth[m['source']].add(gi)
    judged_rel = {gi for gi, g in enumerate(groups) if any(J.get(m['key'][:6], ('?',))[0] == 'R' for m in g)}
    out(f'   stories judged relevant (R) by hand: {len(judged_rel)} of {len(groups)}')
    out(f'   {"method":14} {"items":>5} {"stories":>7} {"unique":>6} {"relevant stories":>16} {"unique relevant":>15}')
    for m, gs in sorted(meth.items()):
        others = set().union(*[v for k, v in meth.items() if k != m]) if len(meth) > 1 else set()
        n_items = sum(1 for g in groups for x in g if x['source'] == m)
        out(f'   {method_label.get(m, m):14} {n_items:5} {len(gs):7} {len(gs - others):6} {len(gs & judged_rel):16} {len((gs - others) & judged_rel):15}')
    srcs = sorted(meth)
    for i, a in enumerate(srcs):
        for b in srcs[i + 1:]:
            out(f'   overlap {method_label.get(a, a)} and {method_label.get(b, b)}: {len(meth[a] & meth[b])} stories in both, '
                f'{len(meth[a] - meth[b])} only {method_label.get(a, a)}, {len(meth[b] - meth[a])} only {method_label.get(b, b)}')
    multi = [g for g in groups if len({m['source'] for m in g}) > 1]
    for g in multi:
        out('   found by several methods: ' + ' | '.join(sorted({m['source'] for m in g})) + ' :: ' + g[0]['title'][:100])
    res[pid] = {'stories': len(groups), 'relevant_stories': len(judged_rel),
                'by_method': {m: {'stories': len(gs), 'relevant': len(gs & judged_rel)} for m, gs in meth.items()}}

# ---------------------------------------------------------------- A2: official pages and council papers
out('\nA2. other discovery routes (not article stories)')
c = sqlite3.connect(os.path.join(LIVE, 'data', 'live.db'))
for r in c.execute("SELECT projects, count(*), min(published_at), max(published_at) FROM items WHERE source='oparl' GROUP BY projects"):
    out(f'   Heilbronn OParl council papers modified since 27 Oct: project={r[0]} n={r[1]} paper dates {r[2][:10]}..{r[3][:10]} (none of these appeared in news headlines)')
out('   Bonn OParl: gated (proof-of-work page), 0 papers, not bypassed.')
out('   Official pages: see logs/exp3_pagewatch.log (5 pages baseline stored, 2nd run unchanged, simulated change detected on a local copy).')

# ---------------------------------------------------------------- B: bounded recall against the historical dataset
out('\nB. BOUNDED RECALL ESTIMATE (NOT true recall): last 10 Heilbronn cable car records in the historical dataset')
posts = pd.read_parquet(os.path.join(ROOT, 'pipeline', 'data', 'parquet', 'posts.parquet'))
lf = pd.read_parquet(os.path.join(ROOT, 'pipeline', 'data', 'parquet', 'labels_final.parquet'))
h = lf[(lf.project == 'heilbronn_cablecar') & (lf.label_source != 'wide_net')].merge(posts, on='post_id', suffixes=('', '_p'))
h = h.sort_values('published_at', ascending=False)
rec = h.head(10).copy()
out('label_source of these 10: ' + str(rec.label_source.value_counts().to_dict()) + ' ; media types: ' + str(rec.media_type.value_counts().to_dict()))
hp = P['heilbronn_cablecar']
query_words = []
for lang, qs in hp.cfg['queries'].items():
    for q in qs:
        quoted = re.findall(r'"([^"]+)"', q)
        rest = re.sub(r'"[^"]+"', ' ', q).split()
        query_words.append((q, [w for w in quoted + rest]))


def query_match(txt):
    """A search engine matching the whole text: all words of a query present (quotes ignored, case-insensitive)."""
    hits = []
    for q, ws in query_words:
        if all(re.search(re.escape(w), txt, re.I) for w in ws):
            hits.append(q)
    return hits


out(f'{"date":10} {"type":16} {"headline filter":>15} {"query words in title+text":>26}  title')
bres = []
for _, r in rec.iterrows():
    t = r['title'] or ''
    full = t + ' ' + (r['text'] or '')
    f1 = bool(hp.matches(t))
    f1b = bool(hp.matches(full))
    qm = query_match(full)
    bres.append({'date': str(r['published_at'])[:10], 'type': r['media_type'], 'title': t[:80], 'headline_filter': f1,
                 'filter_on_title_plus_text': f1b, 'queries_matching_title_plus_text': qm})
    out(f'{str(r["published_at"])[:10]} {r["media_type"][:16]:16} {str(f1):>15} {("yes: " + str(len(qm)) + " query(ies)") if qm else "no":>26}  {t[:70]}')
n = len(rec)
out(f'\nheadline filter alone matches {sum(b["headline_filter"] for b in bres)} of {n}; filter on title+text {sum(b["filter_on_title_plus_text"] for b in bres)} of {n}; '
    f'at least one query would match title+text in {sum(bool(b["queries_matching_title_plus_text"]) for b in bres)} of {n}')
out('Reading: several of these 10 are social comments or posts (not news). The collector has no source for Instagram, Facebook or YouTube comments, so those cannot be found whatever the query.')

# live Google News test: would the actual queries have returned the news records of Jul-Aug 2026?
out('\nB2. LIVE Google News test: run the real Heilbronn queries with after:2026-07-20 and see whether the NEWS records among the last 30 historical ones are found')
news30 = h[h.media_type == 'News'].head(30)
since = dt.datetime(2026, 7, 20, tzinfo=dt.timezone.utc)
http = Http(cfg['defaults']['user_agent'])
gn = GNews(cfg['sources']['gnews'], http)
got = []
try:
    got = gn.fetch(hp, since)
    out(f'Google News returned {len(got)} items for the Heilbronn queries since 20 Jul (all queries, before our headline filter)')
except Exception as e:
    out('Google News failed:', e)
gt = [(toks(g.title), g.title, g.source_name, g.published_at.date().isoformat()) for g in got]
hist = news30[news30.published_at >= '2026-07-20']
found = 0
rows_b2 = []
for _, r in hist.iterrows():
    t = re.sub(r'\s*-\s*(STIMME\.de|stimme\.de|.*Nachrichten.*)$', '', r['title'] or '')
    tk = toks(t)
    best = max(gt, key=lambda x: jac(tk, x[0]), default=None)
    sc = jac(tk, best[0]) if best else 0
    ok = sc >= 0.6
    found += ok
    rows_b2.append({'date': str(r['published_at'])[:10], 'source': r['source'], 'title': t[:80], 'found_by_gnews': ok, 'best_score': round(sc, 2)})
    out(f'   {str(r["published_at"])[:10]} {r["source"][:22]:22} found={"yes" if ok else "no ":3} (best title similarity {sc:.2f})  {t[:70]}')
out(f'Google News live queries found {found} of {len(hist)} historical NEWS records dated 20 Jul or later. '
    'Caveat: Google keeps only part of its index, matches wording we cannot see, and these records came from the city vendor, not from Google.')
json.dump({'A': res, 'B_last10': bres, 'B2': rows_b2, 'B2_found': found, 'B2_n': len(hist)},
          open(os.path.join(LOGS, 'exp2_coverage.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
