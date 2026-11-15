"""Two checks for features built by other sessions; input formats are plain so any implementation can be scored.

1. placebo_test: are the detected peaks really at the documented event dates, or would random dates look as good?
   statistic = mean over events of (stories in the event window) / (baseline median of that series)
   placebo   = the same statistic at random dates (same count, outside +/- `guard` weeks of real events)
   p-value   = (1 + number of placebo draws >= real) / (1 + draws)

2. score_qa: "ask the debate" faithfulness.
   quote accuracy  = share of quoted strings that appear verbatim (whitespace-normalised) in the cited post
   number accuracy = share of numbers in the answer text that are in the allowed facts (from SQL), ignoring years
   refusal         = for questions marked unanswerable, the system must refuse; for answerable ones it must not
"""
import re
import numpy as np


def placebo_test(weekly, event_idx, window=(0, 1), guard=3, draws=5000, seed=0):
    """weekly: list of story counts per week. event_idx: week indices of documented events."""
    y = np.asarray(weekly, float)
    base = max(np.median(y), 0.5)
    lo, hi = window

    def stat(idx):
        return float(np.mean([y[max(0, i + lo):i + hi + 1].sum() / base for i in idx]))
    real = stat(event_idx)
    banned = set()
    for e in event_idx:
        banned.update(range(e - guard, e + guard + 1))
    pool = [i for i in range(len(y)) if i not in banned]
    rng = np.random.default_rng(seed)
    k = len(event_idx)
    sims = np.array([stat(rng.choice(pool, k, replace=False)) for _ in range(draws)])
    p = (1 + (sims >= real).sum()) / (1 + draws)
    return {'real': real, 'placebo_mean': float(sims.mean()), 'placebo_p95': float(np.percentile(sims, 95)),
            'p_value': float(p), 'n_events': k, 'draws': draws}


def _norm(s):
    return re.sub(r'\s+', ' ', (s or '').lower()).strip()


NUM = re.compile(r'(?<![\w.,])(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?![\w])')


def numbers_in(text):
    out = []
    for m in NUM.findall(text or ''):
        if re.fullmatch(r'\d{1,3}(\.\d{3})+(,\d+)?', m):        # German thousands: 157.000.000 or 1.234,5
            v = float(m.replace('.', '').replace(',', '.'))
        else:
            v = float(m.replace(',', '.'))
        if 1900 <= v <= 2100 and float(v).is_integer():
            continue      # years are dates, not claims
        out.append(v)
    return out


def score_qa(items, posts):
    """items: [{'qid','answerable': bool, 'refused': bool, 'answer': str,
                'quotes': [{'post_id','quote'}], 'allowed_numbers': [floats]}]
    posts: {post_id: text}."""
    q_ok = q_n = n_ok = n_n = 0
    refusal_ok = 0
    rows = []
    for it in items:
        r = {'qid': it['qid']}
        r['refusal_correct'] = bool(it['refused']) == (not it['answerable'])
        refusal_ok += r['refusal_correct']
        if not it['refused']:
            for q in it.get('quotes', []):
                ok = _norm(q['quote']) in _norm(posts.get(q['post_id'], ''))
                q_ok += ok
                q_n += 1
            allowed = {round(float(x), 6) for x in it.get('allowed_numbers', [])}
            for v in numbers_in(it.get('answer', '')):
                n_ok += round(v, 6) in allowed
                n_n += 1
        rows.append(r)
    return {'n_questions': len(items), 'refusal_accuracy': refusal_ok / len(items) if items else None,
            'quote_accuracy': q_ok / q_n if q_n else None, 'n_quotes': q_n,
            'number_accuracy': n_ok / n_n if n_n else None, 'n_numbers': n_n, 'rows': rows}
