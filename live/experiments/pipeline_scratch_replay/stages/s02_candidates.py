"""Stage 2: candidate retrieval (wide net) and snippet extraction.

Net 1, rules: a cable word and a place word within `window_chars` of each other, per project,
minus known noise (alpine lifts, the Heilbronner Kreuz motorway junction, strike sidebars).
Rules are written to over-include. Relevance is decided later by labels, not here.

Net 2, embeddings (optional, `[embeddings] enabled`): posts that mention a cable word or a project
place but missed the rules are compared with relevant seed posts from the pilot (cosine).

Snippet: the title plus the text around each mention, merged, up to `snippet_chars`.
This is what every labeller (human, cloud LLM, local model) reads.
"""
import os
import re
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import CFG, log, path, read_table, write_table  # noqa: E402

W = CFG['candidates']['window_chars']
SNIP = CFG['candidates']['snippet_chars']

CABLE_DE = r'seilbahn|gondel|kabinenbahn|seilschwebebahn|stadtseilbahn|ropeway|cable car|cablecar|urban gondola'
CABLE_FR = r't[ée]l[ée]ph[ée]rique|c[âa]ble c?1\b|t[ée]l[ée]c[âa]ble|c[âa]ble a\b'
CABLE = f'(?:{CABLE_DE}|{CABLE_FR})'

RULES = {
    'heilbronn_cablecar': (CABLE, r'heilbronn(?!er (?:kreuz|runde|rundweg))|\bipai\b|ki-park|bildungscampus|wohlgelegen|neckarturm'),
    'bonn_cablecar': (CABLE, r'\bbonn(?!er (?:kreuz|münster))|venusberg|rheinseilbahn|beuel|ramersdorf'),
    'paris_c1': (CABLE, r'cr[ée]teil|limeil|villeneuve-saint-georges|val-de-marne|\bc1\b'),
}
IPAI = r'\bipai\b|innovation park artificial intelligence|innovationspark k(?:ü|ue)nstliche intelligenz'
OTHER_URBAN = r'urbane seilbahn|stadtseilbahn|seilbahn (?:als|im) (?:öpnv|nahverkehr)|urban cable car|t[ée]l[ée]ph[ée]rique urbain'
NOISE = r'krippenstein|dachstein|obertraun|bergrettung|skigebiet|skipiste|sessellift|schlepplift|gletscher'
# Hint order when several projects match: the more specific first.
ORDER = ['paris_c1', 'bonn_cablecar', 'heilbronn_cablecar']


def near_spans(t, a, b, w=W):
    """Spans of matches of `a` that have a match of `b` within w characters."""
    spans = []
    for m in re.finditer(a, t):
        lo, hi = max(0, m.start() - w), m.end() + w
        if re.search(b, t[lo:hi]):
            spans.append((m.start(), m.end()))
    return spans


def snippet(title, text, spans, max_chars=SNIP):
    """Title + windows around the mention spans, merged, cut at sentence-ish boundaries."""
    if not spans:
        return (title + ' | ' + text[:max_chars]).strip(' |')
    half = max(80, max_chars // (2 * min(len(spans), 3)))
    wins = []
    for s, e in spans:
        lo, hi = max(0, s - half), min(len(text), e + half)
        # extend to a sentence start / end if one is close
        dot = text.rfind('. ', max(0, lo - 80), lo + 1)
        lo = dot + 2 if dot != -1 else lo
        nxt = text.find('. ', hi - 1, hi + 80)
        hi = nxt + 1 if nxt != -1 else hi
        if wins and lo <= wins[-1][1]:
            wins[-1] = (wins[-1][0], max(wins[-1][1], hi))
        else:
            wins.append((lo, hi))
    parts, used = [], 0
    for lo, hi in wins:
        piece = text[lo:hi].strip()
        if used + len(piece) > max_chars:
            piece = piece[:max(0, max_chars - used)]
        if piece:
            parts.append(piece)
            used += len(piece)
        if used >= max_chars:
            break
    body = ' … '.join(parts)
    return f'{title} | {body}' if title else body


def classify_row(title, text):
    t = f'{title}\n{text}'.lower()
    hits, spans_by = [], {}
    noise = bool(re.search(NOISE, t))
    for proj, (a, b) in RULES.items():
        sp = near_spans(t, a, b)
        if sp:
            hits.append(proj)
            spans_by[proj] = sp
    if re.search(IPAI, t):
        hits.append('ipai')
        spans_by['ipai'] = [(m.start(), m.end()) for m in re.finditer(IPAI, t)]
    if not hits and re.search(OTHER_URBAN, t):
        hits.append('other_cablecar')
        spans_by['other_cablecar'] = [(m.start(), m.end()) for m in re.finditer(OTHER_URBAN, t)]
    if not hits:
        return None
    if noise and hits != ['ipai'] and not re.search(r'urban|stadt|öpnv|nahverkehr|ipai', t):
        return None  # alpine noise with no urban context
    hint = next((p for p in ORDER if p in hits), hits[0])
    # IPAI article that only mentions the cable car in passing: keep the cable car hint only if the title says so
    if hint == 'heilbronn_cablecar' and 'ipai' in hits and not re.search(CABLE, title.lower()):
        n_cable = len(spans_by['heilbronn_cablecar'])
        if n_cable == 1:
            hint = 'ipai'
    spans = spans_by[hint]
    # spans are offsets in "title\ntext" (lowercased, same length); shift to text offsets
    off = len(title) + 1
    tspans = [(max(0, s - off), max(0, e - off)) for s, e in spans if e > off] or [(0, 0)]
    return {'project_hint': hint, 'rule_hits': ';'.join(sorted(set(hits)) + (['noise_word'] if noise else [])),
            'snippet': snippet(title, text, tspans), 'n_mentions': len(spans)}


def embedding_net(posts, cands):
    """Optional: nearest-neighbour search against relevant pilot posts. Slow on CPU."""
    from sentence_transformers import SentenceTransformer
    import numpy as np
    import json
    e = CFG['embeddings']
    pilot = path('pilot_dir')
    key = pd.read_csv(os.path.join(pilot, 'sample_key.csv'), encoding='utf-8-sig', dtype=str)
    seeds = []
    labs = {}
    for name in ('sonnet_a', 'sonnet_b', 'haiku'):
        for line in open(os.path.join(pilot, f'labels_{name}.jsonl'), encoding='utf-8'):
            if line.strip():
                r = json.loads(line)
                labs.setdefault(r['pid'], []).append(r['project'])
    rel = {p for p, v in labs.items() if sum(x in ('heilbronn_cablecar', 'bonn_cablecar', 'paris_c1') for x in v) >= 2}
    seed_ids = set(key[key.pid.isin(rel)].mention_id)
    seed_txt = posts[posts.post_id.isin(seed_ids)].apply(lambda r: f"passage: {r.title} | {r.text[:600]}", axis=1).tolist()
    loose = posts[~posts.post_id.isin(cands.post_id)]
    t = (loose.title + ' ' + loose.text).str.lower()
    loose = loose[t.str.contains(CABLE) & t.str.contains(r'stadt|city|ville|urban|öpnv|nahverkehr|transport')]
    loose = loose.head(e['max_texts'])
    log('candidates', f'embedding net: {len(seed_txt)} seeds, {len(loose)} loose posts (model {e["model"]})')
    if loose.empty or not seed_txt:
        return pd.DataFrame()
    m = SentenceTransformer(e['model'])
    S = m.encode(seed_txt, normalize_embeddings=True, batch_size=32)
    X = m.encode([f"passage: {a} | {b[:600]}" for a, b in zip(loose.title, loose.text)], normalize_embeddings=True, batch_size=32)
    score = (X @ S.T).max(axis=1)
    hit = loose[score >= e['min_score']].copy()
    hit['emb_score'] = score[score >= e['min_score']]
    return hit


def run(embed=None):
    t0 = time.time()
    posts = read_table('posts')
    rows = []
    for pid, title, text in zip(posts.post_id, posts.title, posts.text):
        r = classify_row(title, text)
        if r:
            r['post_id'] = pid
            rows.append(r)
    c = pd.DataFrame(rows)
    c['by_rule'] = True
    c['by_embedding'] = False
    c['emb_score'] = None
    use_emb = CFG['embeddings']['enabled'] if embed is None else embed
    if use_emb:
        hit = embedding_net(posts, c)
        if len(hit):
            extra = pd.DataFrame({'post_id': hit.post_id, 'project_hint': 'other_cablecar', 'rule_hits': 'embedding',
                                  'snippet': [snippet(a, b, []) for a, b in zip(hit.title, hit.text)], 'n_mentions': 0,
                                  'by_rule': False, 'by_embedding': True, 'emb_score': hit.emb_score.values})
            c = pd.concat([c, extra], ignore_index=True)
    c['emb_score'] = pd.to_numeric(c['emb_score'], errors='coerce')
    c = c[['post_id', 'project_hint', 'rule_hits', 'by_rule', 'by_embedding', 'emb_score', 'snippet', 'n_mentions']]
    write_table('candidates', c)
    log('candidates', f"{len(c):,} candidates of {len(posts):,} posts; by hint: {c.project_hint.value_counts().to_dict()} "
                      f"({time.time() - t0:.0f}s)")
    return c


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--embed', action='store_true', help='also run the embedding net (slow)')
    run(embed=True if ap.parse_args().embed else None)
