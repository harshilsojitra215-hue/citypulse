"""Is this collector handoff valid? One command, exit code 0 = yes, 1 = no. Contract: live/CONTRACT_LIVE_TO_PIPELINE.md.

  python -I -X utf8 live/tools/check_handoff.py                       # live/out/raw_live.json + newest receipt
  python -I -X utf8 live/tools/check_handoff.py --raw path.json --receipt path.json

Checks
  records : required fields present and typed, id format live:<12 hex>, UTC timestamps, allowed values for kind,
            radar_match, text_scope; authors hold only 16-hex hashes (never a name); published and replay are false;
            no duplicate ids.
  receipt : required keys, status in success/partial/failed, published false.
  pipeline: the team's own pipeline/stages/s01_ingest.normalise() accepts the records (imported read only, nothing written).
"""
import argparse
import glob
import json
import os
import re
import sys

LIVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(LIVE)
TS = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\+0000|\+00:00)$')
REQUIRED = {'mention_id': str, 'published_at': str, 'url': str, 'media_type_name': str, 'source_name': str, 'language_code': str,
            'sentiment': int, 'engagements': int, 'authors': list, 'title': str, 'content': str, 'discovered_at': str,
            'retrieved_at': str, 'last_changed_at': str, 'version_no': int, 'late_discovered': bool, 'kind': str, 'replay': bool,
            'published': bool, 'collector_source': str, 'project_hint': str, 'content_hash': str, 'radar_match': str,
            'text_scope': str, 'date_known': bool, 'found_by_sources': list, 'n_sightings': int}
KINDS = {'article', 'official_news', 'council_paper', 'social_post', 'official_page_change', 'social_link', 'web', 'news',
         'official', 'forum', 'video', 'video_comment'}
RECEIPT_KEYS = ['run_id', 'status', 'published', 'started_at', 'finished_at', 'since', 'sources', 'totals', 'coverage_gaps', 'export']


def check_records(recs):
    errs, seen = [], set()
    for n, r in enumerate(recs):
        where = f"record {n} ({r.get('mention_id', '?')})"
        for f, t in REQUIRED.items():
            if f not in r:
                errs.append(f'{where}: missing {f}')
            elif r[f] is not None and not isinstance(r[f], t):
                errs.append(f'{where}: {f} is {type(r[f]).__name__}, expected {t.__name__}')
        if not re.match(r'^live:[0-9a-f]{12}$', str(r.get('mention_id'))):
            errs.append(f'{where}: id is not live:<12 hex>')
        if r.get('mention_id') in seen:
            errs.append(f'{where}: duplicate id')
        seen.add(r.get('mention_id'))
        for f in ('published_at', 'discovered_at'):
            if r.get(f) and not TS.match(r[f]):
                errs.append(f'{where}: {f} not UTC ISO ({r[f]})')
        if r.get('kind') not in KINDS:
            errs.append(f"{where}: kind {r.get('kind')!r} not allowed")
        if r.get('radar_match') not in ('strong', 'weak', 'none'):
            errs.append(f"{where}: radar_match {r.get('radar_match')!r}")
        if r.get('text_scope') not in ('full', 'snippet', 'title', None):
            errs.append(f"{where}: text_scope {r.get('text_scope')!r}")
        if any(not re.match(r'^[0-9a-f]{16}$', str(a)) for a in r.get('authors') or []):
            errs.append(f'{where}: authors must be 16-hex hashes only (a name would leak)')
        if r.get('published') or r.get('replay'):
            errs.append(f'{where}: published or replay is true')
    return errs


def check_receipt(rc, n_records):
    errs = [f'receipt: missing {k}' for k in RECEIPT_KEYS if k not in rc]
    if rc.get('status') not in ('success', 'partial', 'failed'):
        errs.append(f"receipt: status {rc.get('status')!r}")
    if rc.get('published'):
        errs.append('receipt: published is true (the collector never publishes)')
    return errs


def check_pipeline(recs):
    sys.path.insert(0, os.path.join(REPO, 'pipeline'))
    try:
        from stages.s01_ingest import normalise
        df = normalise(recs, origin='live')
    except SystemExit as e:
        return [f'pipeline normalise() refused the file: {e}']
    except Exception as e:  # noqa: BLE001
        return [f'pipeline normalise() failed: {type(e).__name__}: {e}']
    return [] if len(df) == len(recs) else [f'pipeline normalise() returned {len(df)} rows for {len(recs)} records']


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default=os.path.join(LIVE, 'out', 'raw_live.json'))
    ap.add_argument('--receipt', default=None)
    ap.add_argument('--no-pipeline', action='store_true', help='skip the normalise() check (no pandas)')
    a = ap.parse_args(argv)
    recs = json.load(open(a.raw, encoding='utf-8'))
    rp = a.receipt or (sorted(glob.glob(os.path.join(os.path.dirname(a.raw), 'receipt_*.json')), key=os.path.getmtime) or [None])[-1]
    errs = check_records(recs)
    if rp:
        errs += check_receipt(json.load(open(rp, encoding='utf-8')), len(recs))
    else:
        errs.append('no receipt found next to the export')
    if not a.no_pipeline:
        errs += check_pipeline(recs)
    print(f"records: {len(recs)}  receipt: {os.path.basename(rp) if rp else 'none'}")
    for e in errs[:30]:
        print('  FAIL', e)
    if len(errs) > 30:
        print(f'  ... and {len(errs) - 30} more')
    print('HANDOFF OK' if not errs else f'HANDOFF NOT OK ({len(errs)} problems)')
    return 0 if not errs else 1


if __name__ == '__main__':
    sys.exit(main())
