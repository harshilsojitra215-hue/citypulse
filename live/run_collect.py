"""Live collector for the public debate on urban cable cars (and later other projects).

  python run_collect.py --since 2026-10-27
  python run_collect.py --since 2026-09-15 --db data/volume_test.db --out out/volume_test_raw.json --examples 3
  python -I -X utf8 run_collect.py --radar --since 2026-11-01   # all enabled sources, receipt plus out/radar_<run_id>.md
  python run_collect.py --health          # check the last runs, exit code 1 if a source looks broken

Writes (default folder out/, change with --out-dir):
  raw_live.json            raw records in the shape pipeline/stages/s01_ingest.py accepts (duplicates left out)
  receipt_<run_id>.json    the run receipt (machine readable), always with "published": false
  receipt_<run_id>.md      the same, readable by a person
  run_log.jsonl            one line per run: per source and project items, new, errors
data/live.db is SQLite and idempotent: key = sha1(canonical URL), content hash decides 'updated' vs 'seen'.
Exit code: 0 = every source ran clean, 2 = partial (something failed or is gated), 1 = failed (no source ran clean).
Standard library + PyYAML. No logins, no keys, no proxies, no CAPTCHA handling. Publishing is the pipeline's job, never ours.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collector.adapters import ADAPTERS  # noqa: E402
from collector.core import DATASET_EDGE, ROOT, UTC, Http, SkipSource, Store, load_config, load_projects, mask_for_kind  # noqa: E402
from collector.dates import fix_activity_dates, recover_dates  # noqa: E402

COLLECTOR_VERSION = '0.3'
JUDGMENTS = os.path.join(ROOT, 'data', 'relevance_judgments.json')   # written by experiments/exp1_precision.py, optional
DETAIL_ATTRS = ('feed_status', 'endpoint_status', 'page_status')


def parse_since(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC) if 'T' not in s else dt.datetime.fromisoformat(s).astimezone(UTC)


def source_status(rows):
    """success: nothing failed. partial: something failed, was skipped or gated. failed: nothing worked."""
    prj = [r for r in rows if r['project'] != '*']
    if prj and all(r.get('skipped') for r in prj):
        return 'skipped'          # no key, or quota used up before anything ran: not a failure, listed in the receipt
    bad = [r for r in prj if r.get('error') or r.get('skipped')]
    detail_bad = []
    for r in rows:
        for attr in DETAIL_ATTRS:
            for k, v in (r.get(attr) or {}).items():
                if v[0] in ('error', 'gated'):
                    detail_bad.append((k, v[0], v[1]))
    if prj and len(bad) == len(prj):
        return 'failed'
    # every feed, endpoint or page of the source errored and nothing came back: that is a failure, not "partial"
    details = [v for r in rows for attr in DETAIL_ATTRS for v in (r.get(attr) or {}).values()]
    if details and all(v[0] in ('error', 'gated') for v in details) and not sum(r.get('items', 0) for r in prj):
        return 'failed'
    return 'partial' if bad or detail_bad else 'success'


def build_receipt(run_id, started, finished, since, args, cfg, projects, rows, store, adapters, db_new_rows, n_export, edge=DATASET_EDGE):
    by_src = {}
    for r in rows:
        by_src.setdefault(r['source'], []).append(r)
    sources = []
    for name, rs in by_src.items():
        prj = [r for r in rs if r['project'] != '*']
        detail = {}
        for r in rs:
            for attr in DETAIL_ATTRS:
                if r.get(attr):
                    detail[attr] = r[attr]
        sources.append({
            'source': name, 'status': source_status(rs),
            'projects_ok': [r['project'] for r in prj if not r.get('error')],
            'projects_failed': [{'project': r['project'], 'reason': r['error']} for r in prj if r.get('error')],
            'projects_skipped': [{'project': r['project'], 'reason': r['skipped']} for r in prj if r.get('skipped')],
            'warnings': [w for r in rs for w in (r.get('warnings') or [])],
            'items_returned': sum(r.get('items', 0) for r in prj), 'new': sum(r.get('new', 0) for r in prj),
            'updated': sum(r.get('updated', 0) for r in prj), 'seen_before': sum(r.get('seen', 0) for r in prj),
            'duplicates': sum(r.get('dup', 0) for r in prj), 'detail': detail})
    sources_skipped = [{'source': s['source'], 'reason': (s['projects_skipped'] or [{'reason': 'skipped'}])[0]['reason']}
                       for s in sources if s['status'] == 'skipped']
    sources = [s for s in sources if s['status'] != 'skipped']
    statuses = [s['status'] for s in sources]
    if not sources:
        status, why = 'failed', 'no source was attempted'
    elif all(s == 'success' for s in statuses):
        status, why = 'success', 'every attempted source answered without error'
    elif all(s == 'failed' for s in statuses):
        status, why = 'failed', 'every attempted source failed'
    else:
        bad = [f"{s['source']} ({s['status']})" for s in sources if s['status'] != 'success']
        status, why = 'partial', 'not clean: ' + ', '.join(bad)
    judg = {}
    if os.path.exists(JUDGMENTS):
        judg = json.load(open(JUDGMENTS, encoding='utf-8'))
    per_project = {}
    cur = store.db.execute('SELECT key, projects, title, source, source_name, kind, published_at, title_hit, mention_id, dup_of, radar_match, date_known FROM items')
    meta = {r[0]: r for r in cur.fetchall()}
    for p in projects:
        pr = {'name': p.name, 'new': 0, 'updated': 0, 'duplicates': 0, 'new_title_hit': 0,
              'new_relevance_known_by_hand': {'R': 0, 'U': 0, 'N': 0}, 'new_not_judged': 0,
              'new_radar_match': {'strong': 0, 'weak': 0, 'none': 0}, 'new_date_unknown': 0,
              'sources_returning_items': sorted({r['source'] for r in rows if r['project'] == p.id and r.get('items')}),
              'sources_failed': sorted({r['source'] for r in rows if r['project'] == p.id and r.get('error')})}
        per_project[p.id] = pr
    new_items = []
    for k in store.run['new']:
        m = meta[k]
        pid = m[1].split(',')[0]
        if pid in per_project:
            per_project[pid]['new'] += 1
            per_project[pid]['new_title_hit'] += int(m[7] or 0)
            per_project[pid]['new_radar_match'][m[10] or 'none'] += 1
            per_project[pid]['new_date_unknown'] += int(m[11] == 0)
            lab = judg.get(k)
            if lab:
                per_project[pid]['new_relevance_known_by_hand'][lab] += 1
            else:
                per_project[pid]['new_not_judged'] += 1
        new_items.append({'mention_id': m[8], 'project': pid, 'kind': m[5], 'source': m[3], 'outlet': m[4],
                          'published_at': m[6], 'date_known': m[11] != 0, 'radar_match': m[10], 'title_hit': bool(m[7]),
                          'title': mask_for_kind(m[5], m[2]), 'late_discovered': m[6] < edge})
    for k in store.run['updated']:
        pid = meta[k][1].split(',')[0]
        if pid in per_project:
            per_project[pid]['updated'] += 1
    for k in store.run['dup']:
        pid = meta[k][1].split(',')[0]
        if pid in per_project:
            per_project[pid]['duplicates'] += 1
    page_changes = []
    for ad in adapters:
        page_changes += getattr(ad, 'changes', [])
    gaps = []
    for s in sources:
        for f in s['projects_failed']:
            gaps.append(f"{s['source']} / {f['project']}: {f['reason']}")
        for attr in DETAIL_ATTRS:
            for k, v in (s['detail'].get(attr) or {}).items():
                if v[0] in ('error', 'gated'):
                    gaps.append(f"{s['source']} {k}: {v[0]} ({v[1]})")
    for s in sources_skipped:
        gaps.append('SKIPPED: ' + s['reason'])
    for s in sources:
        gaps += [w for w in s['warnings']]
        for f in s['projects_skipped']:
            gaps.append(f"{s['source']} / {f['project']}: skipped ({f['reason']})")
    for pid, pr in per_project.items():
        if not pr['sources_returning_items']:
            gaps.append(f'{pid}: no source returned any item in this window. This is not evidence that nobody discussed it.')
    gaps += ['NOT COVERED BY DESIGN: ' + g for g in cfg['defaults'].get('known_not_covered', [])]
    totals = {
        'sources_attempted': len(sources), 'sources_clean': statuses.count('success'),
        'sources_partial': statuses.count('partial'), 'sources_failed': statuses.count('failed'),
        'items_returned_by_adapters': sum(s['items_returned'] for s in sources),
        'unique_items_seen': len(store.run['new'] | store.run['updated'] | store.run['seen'] | store.run['dup']),
        'truly_new': len(store.run['new']), 'changed_versions': len(store.run['updated']),
        'late_discovered_new': sum(1 for i in new_items if i['late_discovered']), 'sightings_recorded': store.run['sightings'],
        'official_page_changes': len(page_changes), 'duplicates_flagged_not_exported': len(store.run['dup']),
        'already_known': len(store.run['seen']), 'exported_records_in_window': n_export}
    msg = (f"{status.upper()}: {totals['truly_new']} new, {totals['changed_versions']} changed, "
           f"{totals['official_page_changes']} official page change(s) from {totals['sources_attempted']} sources "
           f"({totals['sources_clean']} clean, {totals['sources_partial']} partial, {totals['sources_failed']} failed). "
           'Nothing is published by the collector.')
    if status != 'success':
        msg += ' The run is incomplete: do not read zero as "nothing happened".'
    elif totals['truly_new'] == 0 and totals['changed_versions'] == 0:
        msg += ' No new items from the sources checked. This is not evidence that nobody discussed the projects.'
    return {
        'schema_version': 1, 'collector_version': COLLECTOR_VERSION, 'run_id': run_id, 'published': False,
        'status': status, 'status_reason': why, 'message': msg,
        'started_at': started.isoformat(timespec='seconds'), 'finished_at': finished.isoformat(timespec='seconds'),
        'seconds': round((finished - started).total_seconds()), 'since': since.isoformat(timespec='seconds'),
        'db': os.path.basename(args.db), 'projects': [p.id for p in projects], 'sources': sources, 'totals': totals,
        'per_project': per_project, 'sources_skipped': sources_skipped, 'official_page_changes': page_changes, 'new_items': sorted(new_items, key=lambda x: x['published_at']),
        'coverage_gaps': gaps, 'export': {'mode': args.export_mode, 'records': n_export, 'dataset_edge': edge},
        'date_fields': {'published_at': "the source's own date (for page changes: the time we detected the change)",
                        'modified_at': 'source says it changed, when known (OParl papers)',
                        'discovered_at': 'first time our collector saw it, never changes',
                        'last_seen_at (retrieved_at)': 'last run that saw it again',
                        'ingested_at': "set by the pipeline when it loads the record, not by the collector"},
        'relevance_rule': ("radar_match (strong, weak, none) is the radar gate: strong = a project phrase, or a cable word and a place word in the same snippet fragment, "
                           "at most 100 characters apart; weak = only one of them, or both far apart; none = neither or a negative word. All items stay stored. "
                           "title_hit = the headline or text names the project (specific phrase, or keyword plus place word). "
                           "Manual judgments (R relevant, U unclear, N not) exist only for items judged earlier by hand "
                           "(data/relevance_judgments.json); new items are listed as not judged. Pipeline stage 2 and the labels decide relevance."),
    }


def receipt_md(r):
    L = [f"# Run receipt {r['run_id']}", '', f"**{r['message']}**", '',
         f"- Started {r['started_at']}, finished {r['finished_at']} ({r['seconds']} s), looking back to {r['since'][:10]}",
         f"- Published: **{r['published']}** (the collector never publishes; the pipeline does)",
         f"- Status: **{r['status']}** ({r['status_reason']})", '', '## Sources', '',
         '| Source | Status | Items returned | New | Changed | Known | Dup | Problems |', '|---|---|---|---|---|---|---|---|']
    for s in r['sources']:
        prob = '; '.join(f"{f['project']}: {f['reason'][:90]}" for f in s['projects_failed']) or '-'
        for attr in DETAIL_ATTRS:
            for k, v in (s['detail'].get(attr) or {}).items():
                if v[0] in ('error', 'gated'):
                    prob += f" | {k}: {v[0]}"
        L.append(f"| {s['source']} | {s['status']} | {s['items_returned']} | {s['new']} | {s['updated']} | {s['seen_before']} | {s['duplicates']} | {prob} |")
    t = r['totals']
    for s in r.get('sources_skipped', []):
        L.append(f"| {s['source']} | skipped | - | - | - | - | - | {s['reason'][:120]} |")
    t = r['totals']
    L += ['', '## Counts', '',
          f"- Unique items seen: {t['unique_items_seen']} (adapters returned {t['items_returned_by_adapters']} in total, an item found for two projects or by two queries counts once)",
          f"- Truly new: {t['truly_new']} (late discovered, published before the dataset edge: {t['late_discovered_new']}); changed versions: {t['changed_versions']}; official page changes: {t['official_page_changes']}; sightings recorded: {t['sightings_recorded']}",
          f"- Already known: {t['already_known']}; duplicates flagged and not exported: {t['duplicates_flagged_not_exported']}",
          f"- Records in the export file ({r['export']['mode']} mode): {t['exported_records_in_window']}", '', '## Per project', '',
          '| Project | New | Radar strong/weak/none | Date unknown | Changed | Dup | New with title hit | New judged by hand R/U/N | New not judged | Sources with items | Sources failed |',
          '|---|---|---|---|---|---|---|---|---|---|---|']
    for pid, p in r['per_project'].items():
        h = p['new_relevance_known_by_hand']
        rm = p['new_radar_match']
        L.append(f"| {pid} | {p['new']} | {rm['strong']}/{rm['weak']}/{rm['none']} | {p['new_date_unknown']} | {p['updated']} | {p['duplicates']} | {p['new_title_hit']} | {h['R']}/{h['U']}/{h['N']} | "
                 f"{p['new_not_judged']} | {', '.join(p['sources_returning_items']) or '-'} | {', '.join(p['sources_failed']) or '-'} |")
    if r['official_page_changes']:
        L += ['', '## Official page changes', '']
        for c in r['official_page_changes']:
            L.append(f"- {'**TEST (simulated change on a local copy)** ' if c.get('test') else ''}{c['page_id']} {c['url']}: +{c['added']} / -{c['removed']} lines")
            L += ([f'    - changed: {x}' for x in c['changed_lines'][:4]] + [f'    - added: {x}' for x in c['added_lines'][:4]]
                  + [f'    - removed: {x}' for x in c['removed_lines'][:4]])
    L += ['', '## New items', '']
    L += [f"- {i['published_at'][:10] if i['date_known'] else 'date unknown'}{' LATE' if i['late_discovered'] else ''} [{i['project']}] "
          f"({i['source']}, {i['outlet']}, {i['radar_match'] or '-'}) {i['title'][:120]}" for i in r['new_items']] or ['- none']
    L += ['', '## Coverage gaps', ''] + [f'- {g}' for g in r['coverage_gaps']]
    L += ['', '## How to read the dates', ''] + [f'- {k}: {v}' for k, v in r['date_fields'].items()]
    L += ['', f"Relevance: {r['relevance_rule']}", '']
    return '\n'.join(L)


def run(args):
    cfg = load_config(args.config)
    d = cfg['defaults']
    since = parse_since(args.since or str(d['since']))
    projects = load_projects(cfg, args.project)
    http = Http(d['user_agent'], timeout=d.get('http_timeout_s', 30), retries=d.get('http_retries', 2))
    store = Store(args.db)
    store.backfill_radar(projects)
    n_purged = store.purge_api_text('youtube', days=cfg['sources'].get('youtube', {}).get('keep_days', 30))
    if n_purged:
        print(f'youtube: {n_purged} items older than 30 days lost their text (API terms)', flush=True)
    only = set(args.source) if args.source else None
    started = dt.datetime.now(UTC)
    run_id = started.strftime('%Y%m%dT%H%M%SZ')
    n = 2
    while os.path.exists(os.path.join(args.out_dir, f'receipt_{run_id}.json')):     # two runs in the same second
        run_id, n = started.strftime('%Y%m%dT%H%M%SZ') + f'_{n}', n + 1
    store.reset_run(run_id)
    rows, examples, adapters = [], {}, []
    for cls in ADAPTERS:
        scfg = cfg['sources'].get(cls.name, {})
        if not scfg.get('enabled', False) or (only and cls.name not in only):
            continue
        ad = cls(scfg, http)
        if hasattr(ad, 'bind_store'):
            ad.bind_store(store)
        adapters.append(ad)
        fails = 0
        for pr in projects:
            row = {'source': cls.name, 'project': pr.id, 'items': 0, 'new': 0, 'updated': 0, 'seen': 0, 'dup': 0, 'error': None}
            if fails >= 2:
                row['error'] = 'skipped: source failed twice in this run'
                rows.append(row)
                continue
            t = time.time()
            try:
                items = ad.fetch(pr, since)
                for it in items:
                    if it.radar_match is None:      # adapters that do not gate on a search snippet: title + start of the text
                        it.radar_match = 'strong' if it.source == 'pagewatch' else pr.relevance(it.title, (it.text or '')[:600])
                    st = store.upsert(it)
                    row['items'] += 1
                    row[st] += 1
                    ex = examples.setdefault((cls.name, pr.id), [])
                    if len(ex) < args.examples and st != 'dup':
                        ex.append((it.published_at.date().isoformat(), it.source_name, it.title[:110]))
                store.commit()
            except SkipSource as e:     # no key, or quota used up: skipped with a reason, not a failure
                row['skipped'] = str(e)[:200]
            except Exception as e:      # one broken source must not stop the run
                row['error'] = f'{type(e).__name__}: {e}'[:200]
                fails += 1
            row['seconds'] = round(time.time() - t, 1)
            rows.append(row)
            print(f"{cls.name:9} {pr.id:18} items={row['items']:4} new={row['new']:4} dup={row['dup']:3} "
                  f"err={row['error'] or '-'}" + (f" skipped={row['skipped']}" if row.get('skipped') else ''), flush=True)
        for attr in DETAIL_ATTRS + ('warnings', 'stats', 'cost_usd'):
            if getattr(ad, attr, None):
                rows.append({'source': cls.name, 'project': '*', attr: getattr(ad, attr)})
    if n_purged:
        rows.append({'source': 'youtube', 'project': '*', 'purged_after_30_days': n_purged})
    # dates for undated new records (link, text, then the page's own date tag where robots.txt allows); unknown stays unknown
    if not getattr(args, 'no_date_recovery', False) and store.run['new']:
        try:
            rows.append({'source': 'date_recovery', 'project': '*',
                         'stats': recover_dates(store, http, keys=store.run['new'], max_pages=getattr(args, 'date_pages', 150))})
        except Exception as e:      # recovery is a bonus; it must never stop the export
            rows.append({'source': 'date_recovery', 'project': '*', 'error': f'{type(e).__name__}: {e}'[:200]})
    # Post-processing, not sources: a receipt row only when something changed (an empty row would list them as sources).
    try:    # a date written in the item's own text beats a crawl date (collector/dates.py fix_activity_dates)
        if (n := fix_activity_dates(store)):
            rows.append({'source': 'activity_dates', 'project': '*', 'stats': {'redated': n}})
    except Exception as e:
        rows.append({'source': 'activity_dates', 'project': '*', 'error': f'{type(e).__name__}: {e}'[:200]})
    try:    # hand-checked corrections with evidence in the stored text (tools/fix_known_dates.py), re-applied on every run
        from tools.fix_known_dates import apply as apply_known_dates
        if (n := apply_known_dates(store.db)):
            rows.append({'source': 'known_date_fixes', 'project': '*', 'stats': {'changed': n}})
    except Exception as e:
        rows.append({'source': 'known_date_fixes', 'project': '*', 'error': f'{type(e).__name__}: {e}'[:200]})
    out_dir = args.out_dir
    out_path = args.out or os.path.join(out_dir, 'raw_live.json')
    n_export = store.export_raw(out_path, since, args.export_mode, d.get('dataset_edge', DATASET_EDGE), run_id)
    finished = dt.datetime.now(UTC)
    rc = build_receipt(run_id, started, finished, since, args, cfg, projects, rows, store, adapters, None, n_export)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f'receipt_{run_id}.json'), 'w', encoding='utf-8') as f:
        json.dump(rc, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, f'receipt_{run_id}.md'), 'w', encoding='utf-8') as f:
        f.write(receipt_md(rc))
    if getattr(args, 'radar', False):
        import radar
        rp = radar.write_radar(os.path.join(out_dir, f'radar_{run_id}.md'), rc, rows, store, adapters, projects, since)
        print('radar report ->', rp)
    log = {'started': started.isoformat(timespec='seconds'), 'run_id': run_id, 'status': rc['status'], 'since': since.isoformat(),
           'db': os.path.basename(args.db), 'exported': n_export, 'rows': rows}
    with open(os.path.join(out_dir, 'run_log.jsonl'), 'a', encoding='utf-8') as f:
        f.write(json.dumps(log, ensure_ascii=False) + '\n')
    print(f'exported {n_export} raw records (without duplicates) -> {out_path}')
    print(f"receipt {run_id}: {rc['message']}")
    if args.examples:
        for (src, pid), ex in sorted(examples.items()):
            print(f'\n[{src} / {pid}]')
            for dd, s, t in ex:
                print(f'  {dd} {s} | {t}')
    return rc


def health(out_dir):
    """Compare the last run with the runs before. Flags: source with errors, source that returned 0 items now but items before,
    feed, page or endpoint that is gated or failing. Exit 1 if anything is flagged."""
    log = os.path.join(out_dir, 'run_log.jsonl')
    if not os.path.exists(log):
        print('no run log yet')
        return 1
    runs = [json.loads(x) for x in open(log, encoding='utf-8') if x.strip()]
    last, before = runs[-1], runs[:-1]
    problems = []
    for r in last['rows']:
        if r.get('error') and not r['error'].startswith('skipped'):
            problems.append(f"{r['source']}/{r['project']}: {r['error']}")
        for attr in DETAIL_ATTRS:
            for k, v in (r.get(attr) or {}).items():
                if v[0] in ('error', 'gated'):
                    problems.append(f"{r['source']} {k}: {v[0]} {v[1]}")
    tot = lambda run_, s: sum(r.get('items', 0) for r in run_['rows'] if r['source'] == s)  # noqa: E731
    for s in {r['source'] for r in last['rows']}:
        if tot(last, s) == 0 and any(tot(b, s) > 0 for b in before[-3:]):
            problems.append(f'{s}: 0 items now, had items in earlier runs (feed changed or blocked?)')
    print(f"last run {last['started']} status={last.get('status', '?')} since {last['since'][:10]}, exported {last['exported']}")
    print('OK' if not problems else 'PROBLEMS:\n  ' + '\n  '.join(problems))
    return 1 if problems else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--since', help='ISO date, e.g. 2026-10-27 (default: dataset end in projects.yaml)')
    ap.add_argument('--config', default=None)
    ap.add_argument('--db', default=os.path.join(ROOT, 'data', 'live.db'))
    ap.add_argument('--out-dir', default=os.path.join(ROOT, 'out'), help='folder for raw_live.json, receipts and run_log.jsonl')
    ap.add_argument('--out', default=None, help='raw export path (default: <out-dir>/raw_live.json)')
    ap.add_argument('--export-mode', default='discovered', choices=['discovered', 'run', 'published'],
                    help='discovered (default): first seen or changed since --since; run: only this run; published: old behaviour, by publish date')
    ap.add_argument('--project', action='append', help='only this project id (repeatable)')
    ap.add_argument('--source', action='append', help='only this source (repeatable)')
    ap.add_argument('--examples', type=int, default=0, help='print N example titles per source and project')
    ap.add_argument('--health', action='store_true')
    ap.add_argument('--no-date-recovery', action='store_true', help='skip date recovery for undated new records (collector/dates.py)')
    ap.add_argument('--date-pages', type=int, default=150, help='at most this many pages read for their date tag per run')
    ap.add_argument('--radar', action='store_true', help='scan all enabled sources for all projects and write out/radar_<run_id>.md next to the receipt')
    a = ap.parse_args()
    if a.health:
        sys.exit(health(a.out_dir))
    r = run(a)
    sys.exit({'success': 0, 'partial': 2, 'failed': 1}[r['status']])
