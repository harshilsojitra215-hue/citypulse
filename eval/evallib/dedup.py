"""Reference near-duplicate clustering (syndicated copies count once).

Word 5-gram shingles, Jaccard similarity, single-link clusters at a threshold (default 0.8).
Pure Python, fine for a few thousand posts. The pipeline may use MinHash (datasketch) instead;
the regression test in eval/tests/test_falsification.py checks any function with the same signature:
    cluster(texts: list[str]) -> list[int]   (cluster id per text)
"""
import re


def shingles(text, k=5):
    w = re.findall(r'\w+', (text or '').lower())
    if len(w) < k:
        return {' '.join(w)} if w else set()
    return {' '.join(w[i:i + k]) for i in range(len(w) - k + 1)}


def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if a | b else 0.0


def cluster(texts, threshold=0.8, k=5):
    sh = [shingles(t, k) for t in texts]
    parent = list(range(len(texts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if jaccard(sh[i], sh[j]) >= threshold:
                parent[find(j)] = find(i)
    roots = {}
    return [roots.setdefault(find(i), len(roots)) for i in range(len(texts))]


def pair_precision(cluster_ids, is_true_dup_pair):
    """Precision of merges: share of merged pairs that a human confirms as the same story.
    is_true_dup_pair(i, j) -> bool (from human check)."""
    pairs = [(i, j) for i in range(len(cluster_ids)) for j in range(i + 1, len(cluster_ids))
             if cluster_ids[i] == cluster_ids[j]]
    if not pairs:
        return None, 0
    ok = sum(1 for i, j in pairs if is_true_dup_pair(i, j))
    return ok / len(pairs), len(pairs)
