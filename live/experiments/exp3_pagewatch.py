"""Experiment 3: official page change monitor.
Part A (real pages): run twice on a scratch DB. Expect baseline, then unchanged.
Part B (TEST, clearly labelled): save a local copy of the real Heilbronn Seilbahn page, run baseline and unchanged on the copy,
edit the COPY (never the real page), run again: expect 'changed' with a short diff, an item in the export and an alert in the receipt.
Run: python -X utf8 exp3_pagewatch.py   -> logs/exp3_pagewatch.log
"""
import glob, json, os, re, subprocess, sys, urllib.request
import yaml
from exp_common import Tee, LIVE, HERE

out = Tee('exp3_pagewatch.log')
PY = [sys.executable, '-X', 'utf8', os.path.join(LIVE, 'run_collect.py')]
UA = yaml.safe_load(open(os.path.join(LIVE, 'projects.yaml'), encoding='utf-8'))['defaults']['user_agent']


def run(db, outdir, cfg=None, extra=()):
    cmd = PY + ['--source', 'pagewatch', '--since', '2026-10-27', '--db', db, '--out-dir', outdir] + (['--config', cfg] if cfg else []) + list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    rc = sorted(glob.glob(os.path.join(outdir, 'receipt_*.json')))[-1]
    return r.returncode, json.load(open(rc, encoding='utf-8')), r.stdout


def show(tag, code, rc):
    out(f'--- {tag}: exit={code} status={rc["status"]} message={rc["message"]}')
    for s in rc['sources']:
        for pid, v in (s['detail'].get('page_status') or {}).items():
            out(f'    {pid:15} {v[0]:10} {v[1]}')
    for c in rc['official_page_changes']:
        out(f'    CHANGE {"(TEST) " if c["test"] else ""}{c["page_id"]} +{c["added"]} -{c["removed"]}')
        for x in c['changed_lines']: out('       ~ ' + x)
        for x in c['added_lines']: out('       + ' + x)
        for x in c['removed_lines']: out('       - ' + x)


# ---------------- Part A: real pages
db_a = os.path.join(HERE, 'data', 'pw_real.db')
out_a = os.path.join(HERE, 'out_pagewatch_real')
for f in [db_a] + glob.glob(out_a + '/*'):
    if os.path.exists(f): os.remove(f)
out('PART A: the five real official pages, two runs on a scratch DB (real network, 1 request per page per run)')
for i in (1, 2):
    code, rc, _ = run(db_a, out_a)
    show(f'real run {i}', code, rc)

# ---------------- Part B: simulated change on a local copy
out('\nPART B (TEST ONLY, simulated): local copy of the Heilbronn Seilbahn page, edited by hand to simulate a change')
tdir = os.path.join(HERE, 'test_pages')
os.makedirs(tdir, exist_ok=True)
copy = os.path.join(tdir, 'hn_seilbahn_TEST_COPY.html')
req = urllib.request.Request('https://www.heilbronn.de/umwelt-mobilitaet/mobilitaet/seilbahn.html', headers={'User-Agent': UA})
html = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
open(copy, 'w', encoding='utf-8').write(html)
out(f'saved copy: {os.path.relpath(copy, LIVE)} ({len(html)} bytes)')
cfg = yaml.safe_load(open(os.path.join(LIVE, 'projects.yaml'), encoding='utf-8'))
cfg['sources'] = {'pagewatch': {'enabled': True, 'min_interval_s': 0, 'pages': [
    {'id': 'TEST_hn_seilbahn_copy', 'project': 'heilbronn_cablecar', 'url': __import__('pathlib').Path(copy).as_uri(),
     'title': 'TEST COPY of Heilbronn Seilbahn page', 'outlet': 'heilbronn.de', 'language': 'de', 'country': 'DE', 'test': True}]}}
cfg_path = os.path.join(HERE, 'data', 'pagewatch_test_config.yaml')
yaml.safe_dump(cfg, open(cfg_path, 'w', encoding='utf-8'), allow_unicode=True)
db_b = os.path.join(HERE, 'data', 'pw_test.db')
out_b = os.path.join(HERE, 'out_pagewatch_test')
for f in [db_b] + glob.glob(out_b + '/*'):
    if os.path.exists(f): os.remove(f)
for i in (1, 2):
    code, rc, _ = run(db_b, out_b, cfg_path)
    show(f'test run {i} (copy untouched)', code, rc)
# simulate the change: edit a number and add a FAQ sentence in the copy
m = re.search(r'Auf einer Strecke von 4,7 km', html)
assert m, 'expected sentence not found'
html2 = html.replace('Auf einer Strecke von 4,7 km', 'Auf einer Strecke von 5,1 km', 1)
html2 = html2.replace('Häufig gestellte Fragen rund um die geplante Seilbahn',
                      'Häufig gestellte Fragen rund um die geplante Seilbahn</h2><p>TEST ONLY, NOT REAL: Wann wird der Gemeinderat entscheiden? Antwort: Termin folgt.</p><h2>', 1)
open(copy, 'w', encoding='utf-8').write(html2)
out('edited the COPY: "4,7 km" -> "5,1 km" and added one TEST ONLY FAQ paragraph')
code, rc, _ = run(db_b, out_b, cfg_path)
show('test run 3 (copy edited)', code, rc)
raw = json.load(open(os.path.join(out_b, 'raw_live.json'), encoding='utf-8'))
out(f'export after the change: {len(raw)} record(s)')
for r in raw:
    out('   kind=%s project_hint=%s published_at=%s discovered_at=%s\n   title=%s\n   content=%s' % (r['kind'], r['project_hint'], r['published_at'], r['discovered_at'], r['title'], r['content'][:400]))
code, rc, _ = run(db_b, out_b, cfg_path)
show('test run 4 (copy unchanged since edit: no second alert)', code, rc)
out('receipt md of the changing run:')
mds = sorted(glob.glob(os.path.join(out_b, 'receipt_*.md')))
out(open(mds[-2], encoding='utf-8').read())
