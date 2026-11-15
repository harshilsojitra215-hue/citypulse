"""Update now: one command (or one double-click on UPDATE_NOW.cmd) for the city's refresh.

  python -I -X utf8 live/update_now.py                     # radar scan, label new strong items, write the report
  python -I -X utf8 live/update_now.py --no-collect        # no network scan: reuse the store (offline stage demo)
  python -I -X utf8 live/update_now.py --provider none     # scan and report, labels shown as "pending"
  python -I -X utf8 live/update_now.py --include-comparators --max-usd 5

Steps
  1. run_collect.py --radar (Exa, Tavily, YouTube; keys in live/.env). Its receipt says which sources answered.
  2. Pick the radar's strong matches (official page changes and replay records are left out).
  3. Build a scratch copy of the team's pipeline/ code (live/bridge/scratch, not in git) and run his stages on those items:
     s01 normalise, s02 candidates, s03 dedup, s05 LLM labels (only items not labelled before), s04 vote, s11 export.
     pipeline/ itself is never written. See live/bridge/driver.py.
  4. Labels are cached in live/data/label_cache/ (one file per LLM run, each row carries the item's content hash):
     an item is labelled once, and again only if its text changes.
  5. Writes live/out/update/update_<id>.md (the "what changed" report), live_update_<id>.json (for the dashboard),
     latest.md and latest.json (copies of the newest).

Honesty rules: a quiet run says "nothing new found in the sources checked", never "nobody talked". Undated items are
"found now, date unknown". No author names, no social URLs in the report. Costs are counted from the API's own token counts.
"""
import os
# one maths thread before pandas or numpy load: on a laptop with little free memory the default thread buffers fail to allocate
for _v in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ.setdefault(_v, '1')
import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import glob
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from collections import Counter, defaultdict

LIVE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(LIVE)
PIPE = os.path.join(REPO, 'pipeline')
sys.path.insert(0, LIVE)

CORE = ['heilbronn_cablecar', 'ipai', 'bonn_cablecar', 'paris_c1']
NAMES = {'heilbronn_cablecar': 'Heilbronn cable car', 'ipai': 'IPAI Heilbronn', 'bonn_cablecar': 'Bonn cable car',
         'paris_c1': 'Paris Câble C1', 'wuppertal_cablecar': 'Wuppertal', 'koblenz_cablecar': 'Koblenz',
         'koeln_cablecar': 'Köln', 'berlin_cablecar': 'Berlin', 'hamburg_cablecar': 'Hamburg',
         'stuttgart_cablecar': 'Stuttgart', 'muenchen_cablecar': 'München'}
MODEL_NAMES = {'claude-sonnet-5-5': 'Claude Sonnet 5.5', 'claude-haiku-5-5': 'Claude Haiku 5.5', 'claude-opus-5-5': 'Claude Opus 5.5'}
SOCIAL = ('social_link', 'social_post', 'video_comment')
DATASET_EDGE = '2026-10-27T12:29:00+0000'   # same as collector/core.py and pipeline/config.toml
DATE_SRC_NAMES = {'source': 'from the search service', 'url': 'from the link', 'text': 'from the text', 'page_meta': "from the page's date tag",
                  None: 'from the source'}


def date_class(x):
    """'after' (published after the city's data ends), 'late' (published before, found by us later) or 'unknown'."""
    if not x.get('date_known', True):
        return 'unknown'
    pub = (x.get('published_at') or '').replace('Z', '+0000')
    return 'late' if pub and pub < DATASET_EDGE else 'after'


def coverage_line():
    """One honest line from the backtest against the city's own monitoring tool (experiments/exp10), if it was run."""
    p = os.path.join(LIVE, 'experiments', 'logs', 'exp10_recall.json')
    if not os.path.exists(p):
        return ''
    try:
        d = json.load(open(p, encoding='utf-8'))
        hn = d.get('heilbronn_cablecar', {}).get('web')
        tot = [sum(v[0] for pl in d.values() for v in pl.values()), sum(v[1] for pl in d.values() for v in pl.values())]
    except Exception:
        return ''
    part = f"Heilbronn cable car web articles {hn[1]} of {hn[0]}, " if hn else ''
    return (f"**Coverage, measured:** this radar is an extra discovery layer, not a replacement for the city's monitoring service. "
            f"Backtest on the same days against the city's own tool: {part}all projects and platforms {tot[1]} of {tot[0]} "
            f"(`live/experiments/exp10_recall_vs_city_tool.py`).")


MEMORY_ERR = re.compile(r'OutOfMemory|Out of Memory|bad allocation|Allocation failure|MemoryError|OpenBLAS.*memory', re.I)
STANCE_COLS = ['support', 'oppose', 'neutral_informative', 'mixed', 'unclear']
# rough cost per item before the run (to choose how many fit under the cap): codebook prompt about 2,300 tokens,
# snippet about 250, answer about 150 tokens, per run. The real cost is counted from the API afterwards.
EST_IN, EST_OUT = 2600, 150


def load_env(path):
    if not os.path.exists(path):
        return
    for line in open(path, encoding='utf-8'):
        m = re.match(r'\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)\s*$', line)
        if m and m.group(2).strip().strip('"\''):
            os.environ.setdefault(m.group(1), m.group(2).strip().strip('"\''))


def primary_project(hint):
    parts = [p for p in (hint or '').split(',') if p]
    for p in CORE:
        if p in parts:
            return p
    return parts[0] if parts else 'unknown'


def cached_labels(cache_dir):
    """{(post_id, content_hash): number of runs with a label}"""
    n = Counter()
    for p in glob.glob(os.path.join(cache_dir, '*.jsonl')):
        for line in open(p, encoding='utf-8'):
            if line.strip():
                r = json.loads(line)
                if '_run' not in r:
                    n[(r.get('post_id'), r.get('content_hash'))] += 1
    return n


def copy_cache(cache_dir, dest, hashes):
    """Copy cached run files, keeping only rows whose content hash is still the item's current one."""
    kept = 0
    for p in glob.glob(os.path.join(cache_dir, '*.jsonl')):
        lines = [json.loads(x) for x in open(p, encoding='utf-8') if x.strip()]
        rows = [r for r in lines[1:] if hashes.get(r.get('post_id')) == r.get('content_hash')]
        kept += len(rows)
        with open(os.path.join(dest, os.path.basename(p)), 'w', encoding='utf-8') as f:
            for o in lines[:1] + rows:
                f.write(json.dumps(o, ensure_ascii=False) + '\n')
    return kept


def build_scratch(scratch):
    """Fresh copy of the team's current code each time, so the bridge always runs his latest stages."""
    if os.path.exists(scratch):
        shutil.rmtree(scratch)
    os.makedirs(scratch)
    for name in ('common.py', 'config.toml'):
        shutil.copy(os.path.join(PIPE, name), scratch)
    shutil.copytree(os.path.join(PIPE, 'stages'), os.path.join(scratch, 'stages'), ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(os.path.join(PIPE, 'reference'), os.path.join(scratch, 'reference'))
    shutil.copy(os.path.join(LIVE, 'bridge', 'driver.py'), scratch)
    a = lambda *p: os.path.normpath(os.path.join(REPO, *p)).replace(os.sep, '/')  # noqa: E731
    cfg = open(os.path.join(scratch, 'config.toml'), encoding='utf-8').read()
    for key, val in (('codebook', a('scripts', 'pilot', 'codebook.md')), ('pilot_dir', a('scripts', 'pilot')),
                     ('gold_dir', a('eval', 'gold')), ('eval_lib', a('eval'))):
        cfg = re.sub(rf'^{key}\s*=.*$', f'{key} = "{val}"', cfg, flags=re.M)
    open(os.path.join(scratch, 'config.toml'), 'w', encoding='utf-8').write(cfg)
    os.makedirs(os.path.join(scratch, 'data', 'label_runs'), exist_ok=True)
    os.makedirs(os.path.join(scratch, 'inputs'), exist_ok=True)
    for p in glob.glob(os.path.join(PIPE, 'data', 'label_runs', '*.jsonl')):   # the team's own runs, read-only copies
        shutil.copy(p, os.path.join(scratch, 'data', 'label_runs'))


def latest_receipt(out_dir, after=None):
    ps = sorted(glob.glob(os.path.join(out_dir, 'receipt_*.json')), key=os.path.getmtime)
    if not ps:
        return None
    if after and os.path.getmtime(ps[-1]) < after:
        return None
    return json.load(open(ps[-1], encoding='utf-8'))


_ACTIVITY = re.compile(r'activity[-:](\d{10,})')


def public_url(kind, url):
    """The link shown in the report data. Social links often name the account in the path (linkedin.com/in/<first-last>,
    facebook.com/<name>, x.com/<handle>), so for social kinds only links without an account name are kept: Instagram /p/ and
    /reel/, YouTube videos, Reddit threads; X and LinkedIn posts are rewritten to their id-only form. Others: None (withheld)."""
    if kind not in SOCIAL + ('video',) or not url:
        return url
    p = urllib.parse.urlsplit(url)
    host, parts = p.netloc.lower().removeprefix('www.').removeprefix('m.'), [x for x in p.path.split('/') if x]
    if host == 'instagram.com' and len(parts) == 2 and parts[0] in ('p', 'reel', 'tv'):
        return f'https://www.instagram.com/{parts[0]}/{parts[1]}/'
    if host in ('youtube.com', 'youtu.be'):
        v = urllib.parse.parse_qs(p.query).get('v', [None])[0]
        if host == 'youtube.com' and parts[:1] == ['watch'] and v:
            return f'https://www.youtube.com/watch?v={v}'
        if host == 'youtube.com' and len(parts) == 2 and parts[0] == 'shorts':
            return f'https://www.youtube.com/shorts/{parts[1]}'
        if host == 'youtu.be' and len(parts) == 1:
            return f'https://youtu.be/{parts[0]}'
        return None
    if host == 'reddit.com' and parts[:1] == ['r'] and 'comments' in parts:
        return f'https://www.reddit.com/{"/".join(parts[:parts.index("comments") + 2])}/'
    if host in ('x.com', 'twitter.com') and len(parts) >= 3 and parts[1] == 'status' and parts[2].isdigit():
        return f'https://x.com/i/web/status/{parts[2]}'
    m = _ACTIVITY.search(url)
    if host == 'linkedin.com' and m:
        return f'https://www.linkedin.com/feed/update/urn:li:activity:{m.group(1)}/'
    return None


def short(s, n=110):
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s if len(s) <= n else s[:n - 1] + '…'


def scan_costs(out_dir, run_id, month):
    """From run_log.jsonl: cost per source for this scan, and the month-to-date total per source (all scans this month).
    Exa and Apify report USD; Tavily reports credits (1,000 free per month), YouTube is free within the daily quota."""
    this, mtd = Counter(), Counter()
    p = os.path.join(out_dir, 'run_log.jsonl')
    if not os.path.exists(p):
        return this, mtd
    for line in open(p, encoding='utf-8'):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        in_month = (d.get('started') or '').startswith(month)
        for r in d.get('rows', []):
            if r.get('project') != '*':
                continue
            for key, val in (('usd', r.get('cost_usd')), ('credits', (r.get('stats') or {}).get('credits'))):
                if val and not (r['source'] == 'tavily' and key == 'usd'):   # Tavily: free credits, its USD is only an estimate
                    k = (r['source'], key)
                    if in_month:
                        mtd[k] += float(val)
                    if d.get('run_id') == run_id:
                        this[k] += float(val)
    return this, mtd


def fmt_costs(c):
    return ', '.join(f"{src} {v:.2f} USD" if unit == 'usd' else f"{src} {v:.0f} credits" for (src, unit), v in sorted(c.items())) or 'none recorded'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--since', default='2026-10-27', help='window start for the scan and the report (default: dataset end)')
    ap.add_argument('--db', default=os.path.join(LIVE, 'data', 'live_radar_v2.db'), help='collector store (radar store by default)')
    ap.add_argument('--no-collect', action='store_true', help='skip the network scan, reuse the last export')
    ap.add_argument('--provider', default='auto', choices=['auto', 'anthropic', 'openrouter', 'none', 'fake'],
                    help='auto = anthropic if ANTHROPIC_API_KEY is set, else openrouter if OPENROUTER_API_KEY is set, else none (labels pending). fake = tests only')
    ap.add_argument('--model', default='claude-sonnet-5-5')
    ap.add_argument('--runs', type=int, default=3, help='LLM runs per item; the vote needs at least 2')
    ap.add_argument('--max-label', type=int, default=120, help='at most this many items labelled per update')
    ap.add_argument('--max-usd', type=float, default=1.0, help='cost cap per update (stops calling when reached)')
    ap.add_argument('--quick', action='store_true', help='live demo: scan only Heilbronn cable car and IPAI with Exa, Tavily, RSS and the page monitor '
                    '(a few minutes instead of 20 to 30); the report still covers everything stored')
    ap.add_argument('--include-comparators', action='store_true', help='also label the 7 comparator cities (default: the 4 core projects)')
    ap.add_argument('--no-engine', action='store_true', help='skip step 5 (feeding new dated items to the argument engine)')
    ap.add_argument('--out-dir', default=os.path.join(LIVE, 'out'))
    ap.add_argument('--cache-dir', default=os.path.join(LIVE, 'data', 'label_cache'))
    ap.add_argument('--scratch', default=os.path.join(LIVE, 'bridge', 'scratch'))
    a = ap.parse_args(argv)
    load_env(os.path.join(LIVE, '.env'))
    t_start = time.time()
    now = dt.datetime.now(dt.timezone.utc)
    update_id = now.strftime('%Y%m%dT%H%M%SZ')
    upd_dir = os.path.join(a.out_dir, 'update')
    os.makedirs(upd_dir, exist_ok=True)
    prev = None   # the last real update, to say what changed since then
    try:
        prev = json.load(open(os.path.join(upd_dir, 'latest.json'), encoding='utf-8'))['meta']
    except (OSError, ValueError, KeyError):
        pass
    provider = a.provider
    if provider == 'auto':
        # The OpenRouter key in live/.env is the key owner's; he agreed to this use (Harshil, 15 Nov evening, debate/DECISIONS.md).
        provider = 'anthropic' if os.environ.get('ANTHROPIC_API_KEY') else ('openrouter' if os.environ.get('OPENROUTER_API_KEY') else 'none')
    if provider == 'anthropic':
        try:
            import anthropic  # noqa: F401
        except ImportError:
            print('anthropic package missing: pip install anthropic. Labels stay pending.')
            provider = 'none'
    steps = []

    # ---- 1. collect
    receipt, collect_note = None, None
    if not a.no_collect:
        print(f'[1/4] radar scan since {a.since} ...', flush=True)
        log_path = os.path.join(upd_dir, f'collect_{update_id}.log')
        t = time.time()
        r = subprocess.run([sys.executable, '-I', '-X', 'utf8', os.path.join(LIVE, 'run_collect.py'), '--radar',
                            '--since', a.since, '--db', a.db, '--out-dir', a.out_dir]
                           + (['--project', 'heilbronn_cablecar', '--project', 'ipai', '--source', 'exa', '--source', 'tavily',
                               '--source', 'rss', '--source', 'pagewatch'] if a.quick else []),
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        open(log_path, 'w', encoding='utf-8').write(r.stdout + '\n' + r.stderr)
        receipt = latest_receipt(a.out_dir, after=t - 1)
        if receipt is None:
            collect_note = f'collection crashed (exit {r.returncode}); the report uses the last export in the store'
        steps.append(f'radar scan exit code {r.returncode} ({time.time() - t:.0f}s), log {os.path.relpath(log_path, REPO)}')
    else:
        receipt = latest_receipt(a.out_dir)
        collect_note = 'no new scan in this update (--no-collect): items come from the last scan'
    raw_path = os.path.join(a.out_dir, 'raw_live.json')
    recs = json.load(open(raw_path, encoding='utf-8')) if os.path.exists(raw_path) else []

    # ---- 2. choose
    strong = [x for x in recs if x.get('radar_match') == 'strong' and x.get('kind') != 'official_page_change' and not x.get('replay')]
    page_changes = [x for x in recs if x.get('kind') == 'official_page_change']
    scan_started = receipt['started_at'] if (receipt and not a.no_collect) else None
    is_new = lambda x: bool(scan_started) and ((x.get('discovered_at') or '') >= scan_started or  # noqa: E731
                                               ((x.get('last_changed_at') or '') >= scan_started and (x.get('version_no') or 1) > 1))
    hashes = {x['mention_id']: x.get('content_hash') for x in strong}
    cache = cached_labels(a.cache_dir)
    done = {pid for pid in hashes if cache.get((pid, hashes[pid]), 0) >= a.runs}
    todo = [x for x in strong if x['mention_id'] not in done
            and (a.include_comparators or primary_project(x.get('project_hint')) in CORE)]
    order = {p: i for i, p in enumerate(CORE)}
    todo.sort(key=lambda x: (order.get(primary_project(x.get('project_hint')), 9), not is_new(x), x.get('published_at') or ''), reverse=False)
    est_item = a.runs * 0.0025   # USD per item and run: measured 0.0017 on 303 calls with the cached prompt (14 Nov), plus margin
    fit = int(a.max_usd / est_item) if provider in ('anthropic', 'openrouter') else len(todo)
    label_ids = [x['mention_id'] for x in todo[:min(a.max_label, fit)]] if provider in ('anthropic', 'openrouter', 'fake') else []
    print(f'[2/4] {len(strong)} strong items, {len(done)} already labelled, {len(todo)} waiting, labelling {len(label_ids)} now '
          f'(provider {provider})', flush=True)

    # ---- 3. The team's stages in the scratch copy
    print('[3/4] pipeline stages in a scratch copy of pipeline/ ...', flush=True)
    build_scratch(a.scratch)
    kept = copy_cache(a.cache_dir, os.path.join(a.scratch, 'data', 'label_runs'), hashes)
    raw_in = os.path.join(a.scratch, 'inputs', 'raw_strong.json')
    json.dump(strong, open(raw_in, 'w', encoding='utf-8'), ensure_ascii=False)
    usage_p = os.path.join(a.scratch, 'usage.json')
    params = {'raw': raw_in, 'orig_parquet': os.path.join(PIPE, 'data', 'parquet'), 'label_ids': label_ids,
              'provider': provider, 'model': a.model, 'runs': a.runs, 'max_usd': a.max_usd, 'update_id': update_id,
              'content_hash': hashes, 'cache_dir': a.cache_dir, 'usage_out': usage_p,
              'test_cache_dir': a.cache_dir if provider == 'fake' else None,
              'or_model': 'anthropic/' + a.model.replace('claude-', 'claude-', 1).rsplit('-', 1)[0] + '.' + a.model.rsplit('-', 1)[1]}
    pj = os.path.join(a.scratch, 'params.json')
    json.dump(params, open(pj, 'w', encoding='utf-8'))
    t = time.time()
    # single-threaded maths libraries from the start: the live batch is small, and many threads each reserve memory
    one_thread = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    r = subprocess.run([sys.executable, '-I', '-X', 'utf8', 'driver.py', pj], cwd=a.scratch, env=one_thread,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    drv_log = os.path.join(upd_dir, f'pipeline_{update_id}.log')
    open(drv_log, 'w', encoding='utf-8').write(r.stdout + '\n' + r.stderr)
    # A laptop short of memory makes DuckDB or numpy fail now and then (seen 15 Nov: "Out of Memory Error", "bad allocation").
    # One retry with single-threaded maths libraries; labels are cached by content hash, so a retry costs no extra model calls.
    if r.returncode != 0 and MEMORY_ERR.search(r.stdout + r.stderr):
        print('pipeline stages ran out of memory; retrying once', flush=True)
        time.sleep(5)
        r = subprocess.run([sys.executable, '-I', '-X', 'utf8', 'driver.py', pj], cwd=a.scratch, env=one_thread,
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        open(drv_log, 'a', encoding='utf-8').write('\n---- retry after a memory error ----\n' + r.stdout + '\n' + r.stderr)
        steps.append('pipeline stages hit a memory error; retried once')
    steps.append(f'pipeline stages exit code {r.returncode} ({time.time() - t:.0f}s), log {os.path.relpath(drv_log, REPO)}')
    pipeline_ok = r.returncode == 0
    if not pipeline_ok:   # the team's code may change; the collection report must still be written
        print(f'pipeline stages failed (exit {r.returncode}), see {drv_log}; writing the collection report without labels', flush=True)
    usage = json.load(open(usage_p, encoding='utf-8')) if pipeline_ok and os.path.exists(usage_p) else {}

    # ---- 4. report
    print('[4/4] writing the report ...', flush=True)
    import pandas as pd
    pq = os.path.join(a.scratch, 'data', 'parquet')
    ids = set(hashes)
    if pipeline_ok:
        cands = pd.read_parquet(os.path.join(pq, 'candidates.parquet'))
        lf = pd.read_parquet(os.path.join(pq, 'labels_final.parquet'))
        labs = pd.read_parquet(os.path.join(pq, 'labels.parquet'))
        lf = lf[lf.post_id.isin(ids)].set_index('post_id')
        labs = labs[labs.post_id.isin(ids) & ~labs.abstain.astype(bool) & labs.run_id.str.startswith('live_')]
        evid = labs.dropna(subset=['evidence']).groupby('post_id').evidence.first().to_dict()
        in_rules = set(cands.post_id) & ids
    else:
        lf, evid, in_rules = pd.DataFrame(columns=['label_source']), {}, set()
    items = []
    for x in strong:
        pid = x['mention_id']
        f = lf.loc[pid] if pid in lf.index else None
        voted = f is not None and f['label_source'] == 'vote'
        state = 'pending' if not voted else ('uncertain' if bool(f['abstain']) else 'labelled')
        items.append({
            'id': pid, 'radar_project': primary_project(x.get('project_hint')), 'radar_projects': x.get('project_hint'),
            'date': (x.get('published_at') or '')[:10] if x.get('date_known', True) else None,
            'date_known': bool(x.get('date_known', True)), 'discovered_at': x.get('discovered_at'),
            'date_source': x.get('date_source'), 'date_class': date_class(x),
            'new_this_update': is_new(x), 'kind': x.get('kind'), 'text_scope': x.get('text_scope'),
            'source': x.get('source_name'), 'collector_source': x.get('collector_source'), 'url': public_url(x.get('kind'), x.get('url')),
            'url_withheld': bool(x.get('url')) and public_url(x.get('kind'), x.get('url')) is None,
            # social pages: the title is often the profile's name, so it is never shown; a piece of the snippet is shown instead
            'title': None if x.get('kind') in SOCIAL else x.get('title'),
            'snippet': short(x.get('content') or '', 160) if x.get('kind') in SOCIAL else None,
            'in_pipeline_rules': pid in in_rules, 'label_state': state,
            'llm_project': f['project'] if voted else None, 'stance': (None if f['abstain'] else f['stance']) if voted else None,
            'voice': f['voice'] if voted else None, 'arguments': json.loads(f['arguments'] or '[]') if voted else [],
            'confidence': f['confidence'] if voted else None, 'n_runs': int(f['n_runs']) if voted else 0,
            'agreement_stance': None if not voted or pd.isna(f['agreement_stance']) else round(float(f['agreement_stance']), 2),
            'evidence': evid.get(pid), 'label_source': f['label_source'] if f is not None else None})
    new_items = [i for i in items if i['new_this_update']]
    labelled_now = set()
    for name in usage.get('new_run_files', []):
        p = os.path.join(a.scratch, 'data', 'label_runs', name)
        if os.path.exists(p):
            labelled_now |= {json.loads(x).get('post_id') for x in open(p, encoding='utf-8') if x.strip() and '_run' not in x}
    labelled_now.discard(None)

    per = defaultdict(lambda: Counter())
    for i in items:
        rp = i['radar_project']
        c = per[rp]
        c['found'] += 1
        c['new'] += i['new_this_update']
        c['d_' + i['date_class']] += 1
        i['counted_project'] = None
        if i['label_state'] == 'pending':
            c['pending'] += 1
            continue
        lp = i['llm_project']
        # where the model puts it: a core project, or (for a comparator city) "other cable car" = still that city
        target = lp if lp in CORE else (rp if (rp not in CORE and lp == 'other_cablecar') else None)
        if target != rp:
            c['not_this'] += 1          # radar said rp, the model says another project or nothing relevant
        if target is None:
            continue
        i['counted_project'] = target
        t = per[target]
        t['about'] += 1
        t['moved_in'] += target != rp
        t[i['stance'] if i['label_state'] == 'labelled' else 'uncertain'] += 1

    model_name = MODEL_NAMES.get(a.model, a.model) + (' via OpenRouter' if provider == 'openrouter' else '')
    status = receipt['status'] if receipt else 'unknown'
    src = receipt['sources'] if receipt else []
    clean = [s['source'] for s in src if s['status'] == 'success']
    bad = [f"{s['source']} ({s['status']})" for s in src if s['status'] != 'success']
    skipped = receipt.get('sources_skipped', []) if receipt else []
    gaps = list(dict.fromkeys(receipt.get('coverage_gaps', []))) if receipt else []   # one line per gap, in order
    lab_total = sum(1 for i in items if i['label_state'] in ('labelled', 'uncertain'))
    pend = sum(1 for i in items if i['label_state'] == 'pending')

    cet = now + dt.timedelta(hours=1)   # Heilbronn is on CET (UTC+1) from late October to late March
    L = [f"# What changed: update {cet.strftime('%a %d %b %Y, %H:%M')} Heilbronn time ({now.strftime('%H:%M')} UTC)", '']
    if collect_note:
        L.append(f'Note: {collect_note}.')
    if receipt:
        L.append(f"**Collection: {status}.** Scan {receipt['run_id']}, window since {receipt['since'][:10]}. "
                 f"Sources that answered: {', '.join(clean) or 'none'}" + (f"; problems: {', '.join(bad)}" if bad else '') + '.')
        if skipped:
            L.append('Skipped (no key or switched off): ' + ', '.join(str(s.get('source', s)) if isinstance(s, dict) else str(s) for s in skipped) + '.')
    L.append('')
    if not a.no_collect:
        if new_items:
            by = Counter(NAMES.get(i['radar_project'], i['radar_project']) for i in new_items)
            L.append(f"**New in this scan: {len(new_items)} strong matches** ({', '.join(f'{k} {v}' for k, v in by.most_common())}).")
        else:
            L.append('**New in this scan: nothing new found in the sources checked.** This does not mean nobody talked; see "Not covered" below.')
    L.append(f"**Labels:** {lab_total} of {len(strong)} strong items have an LLM label ({model_name}, {a.runs} runs, majority vote); "
             f"{len(labelled_now)} were labelled in this update; {pend} pending"
             + ('' if a.include_comparators else ' (comparator cities are not labelled by default)')
             + ('.' if provider in ('anthropic', 'openrouter', 'fake') else '. **No labelling in this update** (switched off, or no model key in live/.env).'))
    if not pipeline_ok:
        L.append(f"**the team's pipeline stages failed in this update** (log `{os.path.relpath(drv_log, REPO)}`). The collection part above is complete; labels are not shown.")
    L.append("Labels are provisional: they come from the team's pipeline code as it stands today (not final). "
             "The bridge reruns whatever pipeline/ holds at the click.")
    if provider == 'fake':
        L.append('**TEST RUN: labels come from a fake test labeller, not a model. Never show them.**')
    L += ['', '## Per project (strong radar matches found since ' + a.since + ')', '',
          '| Project | radar found | new now | model: about it | support | oppose | neutral | mixed | unclear or uncertain | label pending | model: not about it |',
          '|---|---|---|---|---|---|---|---|---|---|---|']
    for p in CORE + [p for p in sorted(per) if p not in CORE]:
        if p not in per:
            continue
        c = per[p]
        about = f"{c['about']}" + (f" ({c['moved_in']} moved in)" if c['moved_in'] else '')
        L.append(f"| {NAMES.get(p, p)} | {c['found']} | {c['new']} | {about} | {c['support']} | {c['oppose']} | "
                 f"{c['neutral_informative']} | {c['mixed']} | {c['unclear'] + c['uncertain']} | {c['pending']} | {c['not_this']} |")
    L += ['', 'Counts are items, not people, and not a poll. "Model: about it" = the model read the text and agrees it is about this project; '
          'only those are counted for stance. "Moved in" = the radar filed it under a neighbour project (for example Heilbronn cable car '
          'versus IPAI). "Model: not about it" = radar hits the model put elsewhere or found irrelevant (radar precision check). '
          '"Uncertain" = the runs disagreed, never counted as a side.', '']
    # when were they published? The city's data ends at DATASET_EDGE; only dated items after it are new evidence for that period
    edge_txt = DATASET_EDGE[:10]
    L += [f'## When were they published? (the city\'s data ends {edge_txt}, 12:29 UTC)', '',
          f'| Project | published after {edge_txt} | published before, found late | date unknown |', '|---|---|---|---|']
    for p in CORE + [p for p in sorted(per) if p not in CORE]:
        if p in per and per[p]['found']:
            c = per[p]
            L.append(f"| {NAMES.get(p, p)} | {c['d_after']} | {c['d_late']} | {c['d_unknown']} |")
    src_n = Counter(i['date_source'] for i in items if i['date_class'] != 'unknown')
    L += ['', 'Only the first column is new evidence for the period after the city\'s data. "Found late" = published before the edge but '
          'not in the city\'s data (our sources found it later). "Date unknown" = no service and no rule gave a date; such items are '
          'never counted as new. Where dates come from: ' + ', '.join(f'{DATE_SRC_NAMES.get(k, k)} {v}' for k, v in src_n.most_common()) + '.', '']
    cov = coverage_line()
    if cov:
        L += [cov, '']

    if prev and provider != 'fake':
        pp = prev.get('per_project', {})
        diffs = [f"{NAMES.get(p, p)} {per[p]['found'] - pp.get(p, {}).get('found', 0):+d}" for p in CORE + sorted(x for x in per if x not in CORE)
                 if per[p]['found'] != pp.get(p, {}).get('found', 0)]
        asked = {s['source'] for s in (receipt or {}).get('sources', [])} | {s['source'] for s in (receipt or {}).get('sources_skipped', [])}
        was = set(prev.get('sources_clean', [])) - {'date_recovery'}
        gone = sorted(s for s in was - set(clean) if s in asked)                    # asked this time and did not answer cleanly
        not_asked = sorted(s for s in was - set(clean) if s not in asked)           # e.g. a --quick scan uses fewer sources
        back = sorted(set(clean) - {'date_recovery'} - set(prev.get('sources_clean', [])))
        L += [f"## Since the last update ({prev.get('generated_at', '')[:16].replace('T', ' ')} UTC)", '',
              f"- Strong items stored: {prev.get('counts', {}).get('strong', 0)} then, {len(strong)} now"
              + (f" ({', '.join(diffs)})." if diffs else ' (no change per project).'),
              f"- With a label: {prev.get('counts', {}).get('with_label', 0)} then, {lab_total} now.",
              f"- Sources that answered: {', '.join(clean) or 'none'}" + (f"; not answering any more: {', '.join(gone)}" if gone else '')
              + (f"; not asked in this scan: {', '.join(not_asked)}" if not_asked else '')
              + (f"; answering again: {', '.join(back)}" if back else '') + '.', '']

    show = new_items if new_items else [i for i in items if i['id'] in labelled_now]
    head = 'New items' if new_items else ('Labelled in this update' if show else None)
    if head:
        show = sorted(show, key=lambda i: (CORE.index(i['radar_project']) if i['radar_project'] in CORE else 9, i['date'] or ''))[:25]
        L += [f'## {head} (up to 25, core projects first)', '']
        for i in show:
            st = {'labelled': f"{i['stance']} ({i['confidence']})", 'uncertain': 'uncertain (runs disagree)', 'pending': 'label pending'}[i['label_state']]
            if i['label_state'] != 'pending' and i['counted_project'] != i['radar_project']:
                st += f", model says {i['llm_project']}"
            where = 'link and snippet only' if i['text_scope'] == 'snippet' else (i['source'] or '')
            if i['kind'] in ('social_link', 'social_post', 'video_comment'):
                where = f"{i['kind'].replace('_', ' ')}, {'snippet only' if i['text_scope'] == 'snippet' else 'text'}"
            ev = f' "{short(i["evidence"], 100)}"' if i['evidence'] else ''
            L.append(f"- {i['date'] or 'date unknown'} | {NAMES.get(i['radar_project'], i['radar_project'])} | {st} | {where} | {short(i['title'] or i['snippet'] or '')}{ev}")
        L.append('')
    if page_changes:
        L += ['## Official pages that changed', ''] + [f"- {short(x.get('title'))} ({x.get('source_name')})" for x in page_changes[:10]] + ['']

    not_rules = [i for i in items if not i['in_pipeline_rules'] and i['radar_project'] in CORE]
    L += ['## Checks', '',
          f"- the team's stage 2 rules also catch {sum(1 for i in items if i['in_pipeline_rules'])} of {len(items)} strong items; "
          f"{len(not_rules)} core-project items reach the labels only through the radar (input for codebook v2).",
          f"- Cost of this update: {usage.get('calls', 0)} model calls, {usage.get('input_tokens', 0):,} input tokens "
          f"({usage.get('cache_read_tokens', 0):,} read from cache), {usage.get('output_tokens', 0):,} output tokens, "
          f"{usage.get('usd', 0):.2f} USD at list price (cap {a.max_usd:.2f}). Failed calls: {usage.get('errors', 0)}, "
          f"refusals: {usage.get('refusals', 0)}, not called because of the cap: {usage.get('budget_stopped', 0)}.",
          f"- Pipeline: {', '.join(steps)}. pipeline/ was not written; everything ran in {os.path.relpath(a.scratch, REPO)}.", '']
    this_c, mtd_c = scan_costs(a.out_dir, receipt['run_id'] if receipt else None, now.strftime('%Y-%m'))
    L.insert(L.index('## Not covered') if '## Not covered' in L else len(L) - 1,
             f"- Search cost: this scan {fmt_costs(this_c) if not a.no_collect else 'no scan'}; this month so far {fmt_costs(mtd_c)} "
             "(free tiers: Tavily 1,000 credits, Exa 10 USD, YouTube 10,000 units a day).")
    L += ['## Not covered', ''] + [f'- {g}' for g in gaps] + [
        '- The radar sees what search services index. Undated items count as "found now, date unknown", never as new posts.',
        '- Labels are AI labels checked by agreement between runs, not by a person. Staff corrections go in the review queue.', '']
    md = '\n'.join(L)

    out = {'meta': {'update_id': update_id, 'generated_at': now.isoformat(), 'since': a.since, 'collect_status': status,
                    'collect_run_id': receipt['run_id'] if receipt else None, 'collect_note': collect_note,
                    'sources_clean': clean, 'sources_problems': bad, 'coverage_gaps': gaps,
                    'labeller': model_name if provider in ('anthropic', 'openrouter') else provider, 'runs': a.runs, 'test_only': provider == 'fake',
                    'counts': {'strong': len(strong), 'new_this_update': len(new_items), 'with_label': lab_total,
                               'labelled_this_update': len(labelled_now), 'pending': pend},
                    'per_project': {p: dict(c) for p, c in per.items()}, 'usage': usage, 'cache_rows_used': kept,
                    'seconds': round(time.time() - t_start, 1), 'published': False},
           'items': items}
    md_p = os.path.join(upd_dir, f'update_{update_id}.md')
    js_p = os.path.join(upd_dir, f'live_update_{update_id}.json')
    open(md_p, 'w', encoding='utf-8').write(md)
    json.dump(out, open(js_p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    if provider != 'fake':
        shutil.copy(md_p, os.path.join(upd_dir, 'latest.md'))
        shutil.copy(js_p, os.path.join(upd_dir, 'latest.json'))
    print(md)
    print(f'\nreport: {os.path.relpath(md_p, REPO)}\ndata:   {os.path.relpath(js_p, REPO)}  ({out["meta"]["seconds"]}s)')

    # ---- 5. the argument engine reads the new dated items, then the website gets a fresh engine snapshot
    # (15 Nov, the team left: his engine in engine runs on this laptop; START_CITYPULSE.cmd keeps its API warm on 8000)
    if not a.no_engine and provider != 'fake':
        print('[5/5] argument engine: new dated items -> claims, matching, new concerns ...', flush=True)
        eng = os.path.join(LIVE, 'engine_bridge')
        t = time.time()
        r = subprocess.run([sys.executable, '-I', '-X', 'utf8', os.path.join(eng, 'feed_engine.py')], text=True, encoding='utf-8', errors='replace')
        r2 = subprocess.run([sys.executable, '-I', '-X', 'utf8', os.path.join(eng, 'snapshot.py')], text=True, encoding='utf-8', errors='replace')
        print(f'engine step: feed exit {r.returncode}, snapshot exit {r2.returncode} ({time.time() - t:.0f}s); '
              'receipt live/out/engine_feed_receipt.json', flush=True)
    return out


if __name__ == '__main__':
    main()
