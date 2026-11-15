"""Stage 8: stance shares with intervals, prevalence correction, reliability numbers -> `metrics` table.

Stance shares (per project x voice), from labels_final where label_source is human or vote:
- counts per stance, plus 'uncertain' (runs disagreed: shown, never counted as a side)
- raw share with a Wilson 95% interval (method 'count')
- if a human gold set overlaps the LLM-labelled posts (>= 30 posts with both): ACC-corrected shares
  with bootstrap intervals and a PPI cross-check, using eval/evallib/prevalence.py (method 'acc', 'ppi').
  For Heilbronn, if humans label all posts, the human counts ARE the result (census, no correction).
Reliability: pairwise Cohen's kappa between LLM runs on project and stance; vendor sentiment vs stance match.
"""
import json
import os
import sys
from itertools import combinations

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import PARQUET, RELEVANT, eval_lib, log, read_table, write_table  # noqa: E402

S4 = ['support', 'oppose', 'neutral_informative', 'other']


def s4(s):
    return None if s is None or (isinstance(s, float) and pd.isna(s)) else (s if s in S4[:3] else 'other')


def run():
    ev = eval_lib()
    from evallib import metrics as M
    from evallib import prevalence as PV
    now = pd.Timestamp.now(tz='UTC')
    f = read_table('labels_final')
    labels, runs, human = read_table('labels'), read_table('label_runs'), read_table('human_labels')
    rows = []

    def add(mid, name, value, lo=None, hi=None, n=None, method='count', project=None, voice=None, src=''):
        rows.append({'metric_id': mid, 'project': project, 'voice': voice, 'name': name, 'value': value,
                     'ci_low': lo, 'ci_high': hi, 'n': n, 'method': method, 'source_run_ids': src, 'computed_at': now})

    lab = f[f.label_source.isin(['human', 'vote']) & f.project.isin(RELEVANT)]
    for proj in RELEVANT:
        pp = lab[lab.project == proj]
        for voice in ['all'] + sorted(pp.voice.dropna().unique()):
            g = pp if voice == 'all' else pp[pp.voice == voice]
            sided = g[~g.abstain]
            n = len(sided)
            add(f'stance_n.{proj}.{voice}', 'posts with a stance label', n, n=n, project=proj, voice=voice)
            add(f'stance_uncertain.{proj}.{voice}', 'posts where runs disagreed', int(g.abstain.sum()), n=len(g), project=proj, voice=voice)
            for st in ['support', 'oppose', 'neutral_informative', 'mixed', 'unclear']:
                k = int((sided.stance == st).sum())
                w = M.wilson(k, n)
                add(f'stance_share.{proj}.{voice}.{st}', f'share {st}', w['value'], w['lo'], w['hi'], n, 'count', proj, voice)

    # prevalence correction when human gold overlaps LLM votes
    llm_kinds = set(runs[runs.kind.isin(['llm_cloud', 'llm_local'])].run_id) if len(runs) else set()
    if len(human) and llm_kinds:
        ll = labels[labels.run_id.isin(llm_kinds) & ~labels.abstain]
        vote = ll.groupby('post_id').stance.agg(lambda s: s.mode().iloc[0] if len(s.mode()) == 1 else None)
        hum = human.drop_duplicates('post_id').set_index('post_id').stance
        both = [p for p in hum.index if p in vote.index and vote[p] and hum[p]]
        add('gold.n_overlap', 'human-labelled posts that also have an LLM vote', len(both), n=len(both), method='count')
        if len(both) >= 30:
            ref, pred = [s4(hum[p]) for p in both], [s4(vote[p]) for p in both]
            add('gold.kappa_stance', "Cohen's kappa human vs LLM vote (stance, 4 classes)", M.cohen_kappa(ref, pred), n=len(both), method='kappa')
            for proj in RELEVANT:
                ids = set(f[(f.project == proj)].post_id) & set(vote.index)
                unl = [s4(vote[p]) for p in ids if vote[p]]
                if len(unl) < 10:
                    continue
                est, info = PV.acc_bootstrap(ref, pred, unl, S4)
                for st, d in est.items():
                    add(f'stance_share_acc.{proj}.all.{st}', f'ACC-corrected share {st}', d['value'], d['lo'], d['hi'], len(unl), 'acc', proj, 'all')
                for st, d in PV.ppi(ref, pred, unl, S4).items():
                    add(f'stance_share_ppi.{proj}.all.{st}', f'PPI share {st}', d['value'], d['lo'], d['hi'], len(unl), 'ppi', proj, 'all')
        else:
            log('measure', f'only {len(both)} gold posts overlap LLM votes (need 30): no ACC/PPI yet, raw shares only')

    # agreement between LLM runs (consistency, not accuracy)
    if llm_kinds:
        piv = labels[labels.run_id.isin(llm_kinds)].pivot_table(index='post_id', columns='run_id', values=['project', 'stance'], aggfunc='first')
        for a, b in combinations(sorted(llm_kinds), 2):
            for field in ['project', 'stance']:
                if (field, a) in piv and (field, b) in piv:
                    d = piv[[(field, a), (field, b)]].dropna()
                    if len(d) >= 20:
                        x, y = d.iloc[:, 0].tolist(), d.iloc[:, 1].tolist()
                        if field == 'stance':
                            x, y = [s4(v) for v in x], [s4(v) for v in y]
                        add(f'agreement.{field}.{a}~{b}', f"Cohen's kappa {field} between two AI runs", M.cohen_kappa(x, y), n=len(d), method='kappa', src=f'{a};{b}')
            # stance only where both runs call the post relevant (the honest stance number; eval session note)
            if ('project', a) in piv and ('project', b) in piv:
                d = piv[[('project', a), ('project', b), ('stance', a), ('stance', b)]].dropna()
                d = d[d[('project', a)].isin(RELEVANT) & d[('project', b)].isin(RELEVANT)]
                if len(d) >= 20:
                    add(f'agreement.stance_relevant.{a}~{b}', "Cohen's kappa stance between two AI runs, posts both call relevant",
                        M.cohen_kappa([s4(v) for v in d[('stance', a)]], [s4(v) for v in d[('stance', b)]]), n=len(d), method='kappa', src=f'{a};{b}')

    # vendor sentiment read as stance, vs the vote
    posts = read_table('posts', columns=['post_id', 'vendor_sentiment'])
    v = lab[~lab.abstain].merge(posts, on='post_id')
    v = v[v.vendor_sentiment.notna()]
    if len(v):
        mapped = v.vendor_sentiment.map({1: 'support', 0: 'neutral_informative', -1: 'oppose'})
        k = int((mapped == v.stance).sum())
        w = M.wilson(k, len(v))
        add('vendor_vs_stance.match', 'vendor sentiment read as stance matches the stance label', w['value'], w['lo'], w['hi'], len(v), 'count')

    cal = os.path.join(PARQUET, 'metrics_calibration.parquet')
    m = pd.DataFrame(rows)
    if os.path.exists(cal):
        c = pd.read_parquet(cal)
        c['computed_at'] = now
        m = pd.concat([m, c.drop(columns=['note'], errors='ignore')], ignore_index=True)
    write_table('metrics', m)
    hn = m[m.metric_id.str.startswith('stance_share.heilbronn_cablecar.all.')][['metric_id', 'value', 'ci_low', 'ci_high', 'n']]
    log('measure', f'{len(m)} metrics. Heilbronn (all voices): ' +
        '; '.join(f"{r.metric_id.split('.')[-1]}={r.value:.2f} [{r.ci_low:.2f},{r.ci_high:.2f}] n={r.n}" for r in hn.itertuples() if r.value is not None))
    return m


if __name__ == '__main__':
    run()
