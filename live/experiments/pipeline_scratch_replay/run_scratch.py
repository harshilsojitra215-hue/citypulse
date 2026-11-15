
import os, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import DATA, log, write_table
from stages import s01_ingest, s02_candidates, s03_dedup, s04_labels, s11_export
assert os.path.abspath(DATA).startswith(HERE)
posts = s01_ingest.run()
ORIG = sys.argv[1]
orig = pd.read_parquet(os.path.join(ORIG, 'posts.parquet'))
cand = pd.read_parquet(os.path.join(ORIG, 'candidates.parquet'), columns=['post_id'])
rep_orig = set(posts.post_id.str.replace('replay:', '', regex=False))
ds = orig[(orig.origin == 'dataset') & orig.post_id.isin(cand.post_id) & ~orig.post_id.isin(rep_orig)]   # baseline WITHOUT the replayed originals
write_table('posts', pd.concat([ds, posts], ignore_index=True))
log('scratch', f'baseline {len(ds):,} historical posts (the {len(rep_orig)} replayed originals removed) + {len(posts)} replay records')
for t in ('faq', 'faq_matches', 'events', 'peaks', 'placebo', 'metrics', 'metrics_calibration'):
    pq = os.path.join(ORIG, t + '.parquet')
    if os.path.exists(pq):
        write_table(t, pd.read_parquet(pq))
s02_candidates.run(); s03_dedup.run(); s04_labels.run(); s11_export.run()
