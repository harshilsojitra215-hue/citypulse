"""Apply the activity-date rule (collector/dates.py fix_activity_dates) to an existing store and re-export raw_live.json.

    python -I -X utf8 live/tools/apply_activity_dates.py [--db live/data/live_radar_v2.db]

Same export call as run_collect.py (since 27 Oct, mode 'discovered', the last run id), so nothing else in the export changes.
"""
import argparse
import datetime as dt
import glob
import os
import sys

LIVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LIVE)
from collector.core import Store, UTC, DATASET_EDGE  # noqa: E402
from collector.dates import fix_activity_dates  # noqa: E402

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', default=os.path.join(LIVE, 'data', 'live_radar_v2.db'))
    ap.add_argument('--out', default=os.path.join(LIVE, 'out', 'raw_live.json'))
    a = ap.parse_args()
    store = Store(a.db)
    fix_activity_dates(store)
    from tools.fix_known_dates import apply as apply_known_dates
    apply_known_dates(store.db)
    last = sorted(glob.glob(os.path.join(LIVE, 'out', 'receipt_*.json')))[-1]
    run_id = os.path.basename(last)[len('receipt_'):-len('.json')]
    n = store.export_raw(a.out, dt.datetime(2026, 10, 27, tzinfo=UTC), 'discovered', DATASET_EDGE, run_id)
    print(f'exported {n} records to {a.out} (run {run_id})')
