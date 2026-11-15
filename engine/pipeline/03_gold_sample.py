"""Step 3: stratified evaluation sample (unique texts only). Fixed seed -> same sample every run."""
import sys, pandas as pd
QUOTA = {"heilbronn_cand": None, "ipai_cand": 100, "paris_c1_cand": 90, "paris_loose_cand": 60,
         "bonn_cand": 90, "other_urban_cand": 110, "background": 150}  # None = take all
df = pd.read_parquet(sys.argv[1]); u = df[df.is_first_copy]
parts = []
for b, q in QUOTA.items():
    g = u[u.bucket == b]
    parts.append(g if q is None or len(g) <= q else g.sample(q, random_state=42))
s = pd.concat(parts).sample(frac=1, random_state=7)  # shuffle so batches mix buckets
s["sample_weight"] = s.bucket.map(lambda b: len(u[u.bucket == b]) / (s.bucket == b).sum())
s.to_parquet(sys.argv[2], index=False)
print(s.bucket.value_counts().to_string(), "\ntotal", len(s))
