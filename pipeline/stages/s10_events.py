"""Stage 10: weekly peaks, links to documented events, placebo check.

Counts: stories per week (one per near-duplicate cluster), per relevant project, from labels_final
(label_source human, vote or rules_curated).
Baseline: mean of the 6 weeks before and 6 weeks after (the week itself excluded), floor 0.25.
Burst test: Poisson exceedance P(X >= observed | baseline); Benjamini-Hochberg q over all weeks of
the project. Peak = q < peak_q and stories >= peak_min_stories. Weak = stories < weak_below.
Link: a documented event (reference/events_seed.json) within -3 to +7 days of the week start.
Placebo: put the same number of fake event dates at random weeks 1,000 times; p = share of draws
that link at least as many peaks as the real events do. With few peaks the power is low:
read "consistent with", never "caused by".
Honest limit: the seed events were partly found by reading the data around peaks, so this placebo p is
optimistic. A clean test uses only events from an official calendar fixed before looking at counts.
"""
import json
import os
import re
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.stats import poisson

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import CFG, RELEVANT, log, path, read_table, write_table  # noqa: E402

E = CFG['events']
warnings.filterwarnings('ignore', message='This pattern is interpreted as a regular expression')


def bh(p):
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank, i in zip(range(n, 0, -1), order[::-1]):
        prev = min(prev, p[i] * n / rank)
        q[i] = prev
    return q


def weekly(stories, proj):
    s = stories[stories.project == proj]
    weeks = pd.date_range(stories.week.min(), stories.week.max(), freq='W-MON')
    return s.groupby('week').size().reindex(weeks, fill_value=0)


def peaks_for(series):
    v = series.values.astype(float)
    base = np.array([max(0.25, np.mean(np.r_[v[max(0, i - 6):i], v[i + 1:i + 7]])) for i in range(len(v))])
    p = poisson.sf(v - 1, base)  # P(X >= v)
    q = bh(p)
    return pd.DataFrame({'week': series.index, 'stories': v.astype(int), 'baseline': base, 'p_value': p, 'q_value': q})


def linked(week_starts, event_dates):
    b, a = pd.Timedelta(days=E['window_before_days']), pd.Timedelta(days=E['window_after_days'])
    out = []
    for w in week_starts:
        hit = [eid for eid, d in event_dates if w - b <= d <= w + pd.Timedelta(days=6) + a]
        out.append(hit[0] if hit else None)
    return out


def run():
    f = read_table('labels_final')
    posts = read_table('posts', columns=['post_id', 'week', 'title', 'url', 'published_at'])
    cl = read_table('clusters')
    rel = f[f.project.isin(RELEVANT) & f.label_source.isin(['human', 'vote', 'rules_curated'])][['post_id', 'project']]
    st = rel.merge(cl[['post_id', 'cluster_id']], on='post_id').merge(posts, on='post_id')
    st = st.sort_values('published_at').drop_duplicates(['project', 'cluster_id'])
    st['week'] = pd.to_datetime(st.week)

    seed = json.load(open(path('events'), encoding='utf-8'))['events']
    ev_rows = []
    for e in seed:
        url, pid = e.get('source_url_checked'), None
        if e.get('evidence_title_regex'):
            d0 = pd.Timestamp(e['date'], tz='UTC')
            cand = st[(st.project == e['project']) & (st.published_at.between(d0 - pd.Timedelta(days=3), d0 + pd.Timedelta(days=7)))]
            cand = cand[cand.title.str.contains(e['evidence_title_regex'], regex=True, na=False)]
            if len(cand):
                pid = cand.iloc[0].post_id
                url = url or cand.iloc[0].url
        ev_rows.append({'event_id': e['event_id'], 'date': pd.Timestamp(e['date']), 'project': e['project'], 'type': e['type'],
                        'title': e['title'], 'source_url': url, 'evidence_post_id': pid, 'after_dataset': bool(e.get('after_dataset', False))})
    events = pd.DataFrame(ev_rows)

    all_peaks, placebo = [], []
    rng = np.random.default_rng(0)
    for proj in RELEVANT:
        s = weekly(st, proj)
        if s.sum() == 0:
            continue
        pk = peaks_for(s)
        pk['project'] = proj
        pk['is_peak'] = (pk.q_value < E['peak_q']) & (pk.stories >= E['peak_min_stories'])
        pk['weak'] = pk.stories < E['weak_below']
        evp = [(r.event_id, r.date) for r in events[(events.project == proj) & ~events.after_dataset].itertuples()]
        pk['linked_event_id'] = linked(pk.week, evp)
        pk.loc[~pk.is_peak, 'linked_event_id'] = None
        all_peaks.append(pk)
        peak_weeks = pk[pk.is_peak].week.tolist()
        if evp and peak_weeks:
            real = sum(1 for w in peak_weeks if linked([w], evp)[0])
            draws = []
            for _ in range(E['placebo_draws']):
                fake = [(i, d) for i, d in enumerate(rng.choice(pk.week.values, len(evp), replace=False))]
                fake = [(i, pd.Timestamp(d)) for i, d in fake]
                draws.append(sum(1 for w in peak_weeks if linked([w], fake)[0]))
            p = float(np.mean(np.array(draws) >= real))
            placebo.append({'project': proj, 'n_events': len(evp), 'n_peaks': len(peak_weeks), 'peaks_linked': real,
                            'placebo_mean_linked': float(np.mean(draws)), 'placebo_p': p})
    peaks = pd.concat(all_peaks, ignore_index=True)
    peaks = peaks[['project', 'week', 'stories', 'baseline', 'p_value', 'q_value', 'is_peak', 'weak', 'linked_event_id']]
    write_table('events', events)
    write_table('peaks', peaks)
    write_table('placebo', pd.DataFrame(placebo))
    for r in placebo:
        log('events', f"{r['project']}: {r['n_peaks']} peak weeks, {r['peaks_linked']} linked to {r['n_events']} documented events; "
                      f"random dates link {r['placebo_mean_linked']:.2f} on average, placebo p={r['placebo_p']:.3f}")
    log('events', f"events with a dataset post: {int(events.evidence_post_id.notna().sum())}/{len(events)}")
    return peaks


if __name__ == '__main__':
    run()
