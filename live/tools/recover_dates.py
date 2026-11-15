"""Backfill dates for undated records already in a collector store (new scans do this by themselves).

Run: python -I -X utf8 live/tools/recover_dates.py [--db live/data/live_radar_v2.db] [--no-pages] [--max-pages 400]
Rules and safety: see live/collector/dates.py. Prints one line with the counts per rule.
"""
import argparse
import os
import sys

LIVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LIVE)
from collector.core import Http, Store, load_config  # noqa: E402
from collector.dates import recover_dates  # noqa: E402

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', default=os.path.join(LIVE, 'data', 'live_radar_v2.db'))
    ap.add_argument('--no-pages', action='store_true', help='only link and text rules, no page reads')
    ap.add_argument('--max-pages', type=int, default=400)
    a = ap.parse_args()
    d = load_config(None)['defaults']
    http = Http(d['user_agent'], timeout=15, retries=0)
    recover_dates(Store(a.db), http, fetch_pages=not a.no_pages, max_pages=a.max_pages)
