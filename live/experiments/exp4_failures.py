"""Experiment 4: failure tests and idempotence.
 4a  bad sources (DNS failure, timeout, HTTP 404, refused, bad page) in a test config: the run must finish, mark them failed,
     and the receipt must not say success.
 4b  rerun with nothing new: receipt says 0 new and lists the sources checked.
 4c  idempotence: after a second run the item table, the export file and the counts must not grow.
Run: python -X utf8 exp4_failures.py [--full]
     --full also runs ALL sources incl. OParl and GDELT twice on a COPY of live.db (about 6 minutes)
"""
import glob, hashlib, json, os, shutil, sqlite3, subprocess, sys
import yaml
from exp_common import Tee, LIVE, HERE

out = Tee('exp4_failures.log' if '--full' not in sys.argv else 'exp4_failures_full.log')
PY = [sys.executable, '-X', 'utf8', os.path.join(LIVE, 'run_collect.py')]
base = yaml.safe_load(open(os.path.join(LIVE, 'projects.yaml'), encoding='utf-8'))


def run(db, outdir, cfg=None, extra=()):
    cmd = PY + ['--since', '2026-10-27', '--db', db, '--out-dir', outdir] + (['--config', cfg] if cfg else []) + list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    rc = sorted(glob.glob(os.path.join(outdir, 'receipt_*.json')))[-1]
    return r.returncode, json.load(open(rc, encoding='utf-8')), r.stdout + r.stderr


def fresh(*paths):
    for p in paths:
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)


def summary(tag, code, rc):
    out(f'--- {tag}: exit code={code}  status={rc["status"]}  published={rc["published"]}')
    out(f'    message: {rc["message"]}')
    for s in rc['sources']:
        out(f'    source {s["source"]:10} {s["status"]:8} items={s["items_returned"]} new={s["new"]} '
            + ('failed: ' + '; '.join(f['project'] + ': ' + f['reason'][:110] for f in s['projects_failed']) if s['projects_failed'] else ''))
        for attr in ('feed_status', 'page_status', 'endpoint_status'):
            for k, v in (s['detail'].get(attr) or {}).items():
                out(f'        {attr[:-7]} {k}: {v[0]} {str(v[1])[:110]}')
    t = rc['totals']
    out(f'    totals: attempted={t["sources_attempted"]} clean={t["sources_clean"]} partial={t["sources_partial"]} failed={t["sources_failed"]} '
        f'truly_new={t["truly_new"]} changed={t["changed_versions"]} known={t["already_known"]} dup={t["duplicates_flagged_not_exported"]}')


def snapshot(db, od):
    c = sqlite3.connect(db)
    return dict(items=c.execute('select count(*) from items').fetchone()[0],
                versions=c.execute('select count(*) from item_versions').fetchone()[0],
                page_snapshots=c.execute('select count(*) from page_snapshots').fetchone()[0],
                # the export carries retrieved_at (last seen), which changes on every run by design; compare the identity fields
                export_sha=hashlib.sha1(json.dumps(sorted((r['mention_id'], r['content_hash'], r['discovered_at'], r['published_at'])
                                                          for r in json.load(open(os.path.join(od, 'raw_live.json'), encoding='utf-8')))).encode()).hexdigest()[:12])


src_db = os.path.join(LIVE, 'data', 'live.db')

if '--full' not in sys.argv:
    out('4a. FAILING SOURCES (test config: http timeout 3 s, no retries; bad feeds are fake or unreachable on purpose)')
    bad_feeds = [
        {'id': 'TEST_dns_fail', 'url': 'https://this-host-does-not-exist.invalid/feed.xml', 'outlet': 'x', 'language': 'de', 'country': 'DE'},
        {'id': 'TEST_timeout', 'url': 'http://10.255.255.1/feed.xml', 'outlet': 'x', 'language': 'de', 'country': 'DE'},
        {'id': 'TEST_refused', 'url': 'http://127.0.0.1:9/feed.xml', 'outlet': 'x', 'language': 'de', 'country': 'DE'},
        {'id': 'TEST_http404', 'url': 'https://www.heilbronn.de/this-feed-does-not-exist-test.xml', 'outlet': 'heilbronn.de', 'language': 'de', 'country': 'DE'},
    ]
    good_feed = [f for f in base['sources']['rss']['feeds'] if f['id'] == 'heilbronn_de']
    cfg = dict(base)
    cfg['defaults'] = dict(base['defaults'], http_timeout_s=3, http_retries=0)
    cfg['sources'] = {'rss': {'enabled': True, 'min_interval_s': 0.2, 'feeds': good_feed + bad_feeds},
                      'pagewatch': {'enabled': True, 'min_interval_s': 0.2, 'pages': [
                          {'id': 'TEST_bad_page', 'project': 'heilbronn_cablecar', 'url': 'https://www.heilbronn.de/no-such-page-test.html', 'title': 'TEST bad page'}]}}
    p1 = os.path.join(HERE, 'data', 'fail_mixed.yaml')
    yaml.safe_dump(cfg, open(p1, 'w', encoding='utf-8'), allow_unicode=True)
    db, od = os.path.join(HERE, 'data', 'fail_a.db'), os.path.join(HERE, 'out_fail_a')
    fresh(db, od)
    code, rc, _ = run(db, od, p1)
    summary('4a-1 one good feed + 3 bad feeds + 1 bad page', code, rc)
    out('    CHECK: run finished, status is not success, exit code is not 0 -> ' + ('PASS' if rc['status'] != 'success' and code != 0 else 'FAIL'))

    cfg['sources'] = {'rss': {'enabled': True, 'min_interval_s': 0.2, 'feeds': bad_feeds}}
    p2 = os.path.join(HERE, 'data', 'fail_all.yaml')
    yaml.safe_dump(cfg, open(p2, 'w', encoding='utf-8'), allow_unicode=True)
    db2, od2 = os.path.join(HERE, 'data', 'fail_b.db'), os.path.join(HERE, 'out_fail_b')
    fresh(db2, od2)
    code, rc, _ = run(db2, od2, p2)
    summary('4a-2 only bad feeds (every source fails)', code, rc)
    out('    CHECK: status is failed and exit code is 1 -> ' + ('PASS' if rc['status'] == 'failed' and code == 1 else 'FAIL'))
    out('    health check on that run:')
    h = subprocess.run(PY + ['--health', '--out-dir', od2], capture_output=True, text=True, encoding='utf-8')
    out('      ' + h.stdout.strip().replace('\n', '\n      ') + f'\n      health exit code={h.returncode}')
    fresh(db, db2)

    sel = ['--source', 'bluesky', '--source', 'rss', '--source', 'pagewatch', '--source', 'mastodon']
    db3, od3 = os.path.join(HERE, 'data', 'idem.db'), os.path.join(HERE, 'out_idem')
    fresh(db3, od3)
    shutil.copy(src_db, db3)          # a COPY of the real store: the real live.db is not touched by this experiment
    out('\n4b/4c. RERUN WITHOUT NEW ITEMS and IDEMPOTENCE (scratch copy of live.db; sources: Bluesky, Mastodon, RSS, pagewatch; Google News and GDELT are off)')
    code, rc1, _ = run(db3, od3, None, sel)
    summary('run 1 on copy of live.db', code, rc1)
    s1 = snapshot(db3, od3)
    out('    store after run 1:', s1)
    code, rc2, _ = run(db3, od3, None, sel)
    summary('run 2 straight after (nothing should be new)', code, rc2)
    s2 = snapshot(db3, od3)
    out('    store after run 2:', s2)
    ok_zero = rc2['totals']['truly_new'] == 0 and rc2['totals']['changed_versions'] == 0
    out('    CHECK 4b: receipt says 0 new and 0 changed -> ' + ('PASS' if ok_zero else 'FAIL'))
    out('    CHECK 4b: receipt lists the sources checked: ' + ', '.join(s['source'] for s in rc2['sources']) + ' -> ' + ('PASS' if len(rc2['sources']) == 4 else 'FAIL'))
    out('    CHECK 4b: message says zero is not proof of silence -> ' + ('PASS' if 'not evidence' in rc2['message'] or rc2['status'] != 'success' else 'FAIL'))
    out('    CHECK 4c: item rows, versions, snapshots and export file identical between run 1 and run 2 -> ' + ('PASS' if s1 == s2 else 'FAIL ' + str((s1, s2))))
    out('\nreceipt markdown of run 2:\n')
    out(open(sorted(glob.glob(os.path.join(od3, 'receipt_*.md')))[-1], encoding='utf-8').read())
else:
    out('4c-full. ALL sources incl. OParl (about 2 minutes each) and GDELT (6 s spacing, back-off on 429) on a COPY of live.db, twice')
    db4, od4 = os.path.join(HERE, 'data', 'idem_full.db'), os.path.join(HERE, 'out_idem_full')
    fresh(db4, od4)
    shutil.copy(src_db, db4)
    code, a, _ = run(db4, od4)
    summary('full run 1', code, a)
    sa = snapshot(db4, od4)
    code, b, _ = run(db4, od4)
    summary('full run 2', code, b)
    sb = snapshot(db4, od4)
    out('    store after run 1:', sa)
    out('    store after run 2:', sb)
    out('    CHECK 4c full: nothing new and nothing changed in run 2, store identical -> ' +
        ('PASS' if sa == sb and b['totals']['truly_new'] == 0 and b['totals']['changed_versions'] == 0 else 'FAIL'))
