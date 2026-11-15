"""Stage 3: near-duplicate clustering, so a syndicated story counts once.

Method: MinHash over word 5-gram shingles (128 hash functions), LSH banding (16 bands x 8 rows)
to find candidate pairs, merge pairs whose estimated Jaccard >= 0.8 (union-find).
Short texts (under `min_words`, mostly comments) are only merged when the text is identical
AND the URL is the same (an exact re-crawl), so two people writing "Super Idee!" are not one story.

`cluster(texts)` has the same signature as eval/evallib/dedup.py so the eval regression test can call it.
No extra library: numpy only, so the city can run it anywhere.
"""
import os
import re
import sys
import time
import zlib
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import CFG, log, read_table, write_table  # noqa: E402

D = CFG['dedup']
PRIME = np.uint64(4294967311)  # smallest prime above 2^32
_rng = np.random.default_rng(1)
_A = _rng.integers(1, 1 << 31, D['num_perm'], dtype=np.uint64)  # a < 2^31 and h < 2^32, so a*h < 2^63: no overflow
_B = _rng.integers(0, 1 << 32, D['num_perm'], dtype=np.uint64)


def words(text):
    return re.findall(r'\w+', (text or '').lower())


def signature(text, k=D['shingle_words'], max_chars=D['max_chars']):
    w = words(text[:max_chars])
    if len(w) < k:
        sh = {' '.join(w)}
    else:
        sh = {' '.join(w[i:i + k]) for i in range(len(w) - k + 1)}
    h = np.fromiter((zlib.crc32(s.encode()) for s in sh), dtype=np.uint64, count=len(sh))
    x = (np.outer(h, _A) + _B) % PRIME
    return x.min(axis=0)


class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def cluster(texts, sources=None, threshold=D['threshold'], min_words=D['min_words']):
    """Return a cluster id (int) per text. Same id = near-duplicate story."""
    n = len(texts)
    uf = UF(n)
    sources = sources if sources is not None else [''] * n
    long_idx, short_key = [], defaultdict(list)
    for i, t in enumerate(texts):
        if len(words(t)) >= min_words:
            long_idx.append(i)
        else:
            short_key[(' '.join(words(t)), sources[i])].append(i)
    for idx in short_key.values():
        for j in idx[1:]:
            uf.union(idx[0], j)
    if long_idx:
        sig = np.vstack([signature(texts[i]) for i in long_idx])
        rows = D['num_perm'] // D['bands']
        pairs = set()
        for b in range(D['bands']):
            buckets = defaultdict(list)
            band = sig[:, b * rows:(b + 1) * rows]
            for r, key in enumerate(map(bytes, band)):
                buckets[key].append(r)
            for members in buckets.values():
                if 1 < len(members) <= 200:
                    for x in members[1:]:
                        pairs.add((members[0], x))
                elif len(members) > 200:  # boilerplate page; compare to first only
                    for x in members[1:]:
                        pairs.add((members[0], x))
        for a, b in pairs:
            if (sig[a] == sig[b]).mean() >= threshold:
                uf.union(long_idx[a], long_idx[b])
    return [uf.find(i) for i in range(n)]


def run():
    t0 = time.time()
    posts = read_table('posts', columns=['post_id', 'published_at', 'source', 'url', 'title', 'text'])
    posts = posts.sort_values('published_at').reset_index(drop=True)
    texts = (posts.title + ' ' + posts.text).tolist()
    cid = cluster(texts, posts.url.tolist())  # short texts merge only on the same URL
    posts['root'] = cid
    first = posts.groupby('root').post_id.transform('first')  # earliest member (sorted by time)
    out = pd.DataFrame({'post_id': posts.post_id, 'cluster_id': first})
    g = posts.groupby('root')
    out['cluster_size'] = g.post_id.transform('size').values
    out['n_outlets'] = g.source.transform('nunique').values
    out['is_representative'] = (out.post_id == out.cluster_id)
    write_table('clusters', out)
    multi = out[out.cluster_size > 1]
    log('dedup', f"{len(out):,} posts -> {out.is_representative.sum():,} stories; "
                 f"{multi.cluster_id.nunique():,} clusters with copies hold {len(multi):,} posts; "
                 f"largest {out.cluster_size.max()} ({time.time() - t0:.0f}s)")
    return out


if __name__ == '__main__':
    run()
