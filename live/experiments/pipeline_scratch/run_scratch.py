
import json, os, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import DATA, PARQUET, log, read_table, write_table
from stages import s01_ingest, s02_candidates, s03_dedup, s04_labels, s11_export
ORIG = sys.argv[1]
log('scratch', 'DATA dir is ' + DATA)
assert os.path.abspath(DATA).startswith(HERE), 'data dir is not inside the scratch folder'
posts = s01_ingest.run()                                   # stage 1 on the collector export (live items only)
orig = pd.read_parquet(os.path.join(ORIG, 'posts.parquet'))
cand = pd.read_parquet(os.path.join(ORIG, 'candidates.parquet'), columns=['post_id'])
ds = orig[(orig.origin == 'dataset') & orig.post_id.isin(cand.post_id)]
posts['origin'] = 'live'
merged = pd.concat([ds, posts], ignore_index=True).drop_duplicates('post_id')
write_table('posts', merged)
log('scratch', f'posts = {len(ds):,} historical rule-net posts (read-only subset) + {len(posts)} live items from the collector')
for t in ('faq', 'faq_matches', 'events', 'peaks', 'placebo', 'metrics', 'metrics_calibration'):
    pq = os.path.join(ORIG, t + '.parquet')
    if os.path.exists(pq):
        write_table(t, pd.read_parquet(pq))                # copied as they are: stages 5-10 are NOT re-run
s02_candidates.run()
s03_dedup.run()
s04_labels.run()
s11_export.run()
