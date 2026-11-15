"""Stage 11: export data.json for the dashboard (shape: CONTRACT.md section 3).

Only relevant posts (label_source human, vote or rules_curated; project one of the 4) go into `posts`.
No author fields exist anywhere, so none can leak. Snippets are capped at 600 characters.
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import (CFG, DATASET_END, EXPORT, PROJECT_NAMES, RELEVANT, VOICES, codebook_sha, jdump, log, path,  # noqa: E402
                    read_table)

COUNTED = ['human', 'vote', 'rules_curated']


def nn(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def run():
    posts = read_table('posts')
    cands = read_table('candidates')
    f = read_table('labels_final')
    cl = read_table('clusters')
    runs = read_table('label_runs')
    m = read_table('metrics')
    fm = read_table('faq_matches')
    faq = read_table('faq')
    ev = read_table('events')
    pk = read_table('peaks')
    pl = read_table('placebo')

    rel = f[f.project.isin(RELEVANT) & f.label_source.isin(COUNTED)]
    rel = rel.merge(posts, on='post_id').merge(cl, on='post_id').merge(cands[['post_id', 'snippet']], on='post_id', how='left')
    rel['snippet'] = rel.snippet.fillna(rel.title + ' | ' + rel.text.str[:500]).str[:700]
    faq_by_post = fm[fm.match_type == 'concern_answered'].groupby('post_id').faq_id.apply(list).to_dict() if len(fm) else {}

    status = 'human_checked' if (rel.label_source == 'human').any() else ('llm_vote' if (rel.label_source == 'vote').any() else 'rules_only')
    out = {'meta': {'generated_at': pd.Timestamp.now(tz='UTC').isoformat(), 'contract': 'v1', 'dataset_end': DATASET_END,
                    'release': CFG.get('export', {}).get('release'),
                    'codebook_version': 'v1', 'codebook_sha': codebook_sha(), 'label_runs': runs.run_id.tolist(),
                    'status': {'labels': status,
                               'stance_coverage': {p: int(((rel.project == p) & rel.label_source.isin(['human', 'vote'])).sum()) for p in RELEVANT},
                               'note': 'Stance exists only for posts labelled by humans or by the LLM vote. Other relevant posts have project only.'}}}
    ds = set(posts[posts.origin == 'dataset'].post_id)
    out['funnel'] = [
        {'step': 'all records (dataset)', 'n': int(len(ds))},
        {'step': 'unique stories (near-duplicates merged)', 'n': int(cl[cl.post_id.isin(ds)].is_representative.sum())},
        {'step': 'wide net (rules)', 'n': int(cands.post_id.isin(ds).sum())},
        {'step': 'relevant to the 4 projects', 'n': int(len(rel))},
        {'step': 'relevant unique stories', 'n': int(rel.drop_duplicates(['project', 'cluster_id']).shape[0])},
        {'step': 'with a stance label (vote or human)', 'n': int(rel.label_source.isin(['human', 'vote']).sum())},
    ]
    out['funnel_live'] = {'live_items_after_dataset': int((posts.origin == 'live').sum()),
                          'live_in_wide_net': int(cands.post_id.isin(set(posts[posts.origin == 'live'].post_id)).sum())}
    projects = []
    for p in RELEVANT:
        g = rel[rel.project == p]
        projects.append({'id': p, 'name': PROJECT_NAMES[p], 'records': int(len(g)), 'stories': int(g.cluster_id.nunique()),
                         'by_voice': {v: int((g.voice == v).sum()) for v in VOICES},
                         'by_media_type': g.media_type.value_counts().to_dict()})
    out['projects'] = projects

    w = rel.copy()
    w['week'] = pd.to_datetime(w.week).dt.strftime('%Y-%m-%d')
    out['weekly'] = [{'project': p, 'week': wk, 'records': int(len(g)), 'stories': int(g.cluster_id.nunique()),
                      'live': int(g.new_since_dataset.sum())} for (p, wk), g in w.groupby(['project', 'week'])]

    stance = []
    sm = m[m.metric_id.str.startswith('stance_share.')]
    for p in RELEVANT:
        for voice in sorted(set(sm[sm.project == p].voice)):
            g = rel[(rel.project == p) & rel.label_source.isin(['human', 'vote'])]
            g = g if voice == 'all' else g[g.voice == voice]
            sided = g[~g.abstain]
            sub = sm[(sm.project == p) & (sm.voice == voice)]
            acc = m[m.metric_id.str.startswith(f'stance_share_acc.{p}.{voice}.')]
            src = acc if voice == 'all' and len(acc) else sub
            share = {r.metric_id.split('.')[-1]: nn(r.value) for r in src.itertuples()}
            ci = {r.metric_id.split('.')[-1]: [nn(r.ci_low), nn(r.ci_high)] for r in src.itertuples()}
            stance.append({'project': p, 'voice': voice, 'n': int(len(sided)),
                           'counts': {**{s: int((sided.stance == s).sum()) for s in ['support', 'oppose', 'neutral_informative', 'mixed', 'unclear']},
                                      'uncertain': int(g.abstain.sum())},
                           'share_corrected': share, 'ci': ci, 'method': 'acc' if src is acc else 'count',
                           'low_sample': bool(len(sided) < 30)})
    out['stance'] = stance

    args = []
    for p in RELEVANT:
        g = rel[(rel.project == p) & rel.label_source.isin(['human', 'vote'])]
        n = len(g)
        cnt = {}
        for a_list, st in zip(g.arguments, g.stance):
            for a in json.loads(a_list or '[]'):
                c = cnt.setdefault(a, {'n': 0, 'support': 0, 'oppose': 0})
                c['n'] += 1
                if st in ('support', 'oppose'):
                    c[st] += 1
        args += [{'project': p, 'code': a, 'n': c['n'], 'share': round(c['n'] / n, 4) if n else None,
                  'support': c['support'], 'oppose': c['oppose'], 'base_n': n} for a, c in sorted(cnt.items(), key=lambda x: -x[1]['n'])]
    out['arguments'] = args

    out['events'] = [{'event_id': r.event_id, 'date': str(r.date)[:10], 'project': r.project, 'type': r.type, 'title': r.title,
                      'source_url': nn(r.source_url), 'evidence_post_id': nn(r.evidence_post_id), 'after_dataset': bool(r.after_dataset)}
                     for r in ev.itertuples()]
    pkk = pk[pk.is_peak]
    out['peaks'] = [{'project': r.project, 'week': str(r.week)[:10], 'stories': int(r.stories), 'baseline': round(float(r.baseline), 2),
                     'q_value': float(r.q_value), 'weak': bool(r.weak), 'linked_event_id': nn(r.linked_event_id)} for r in pkk.itertuples()]
    out['placebo'] = pl.to_dict('records') if pl is not None else []

    faq_out = []
    for r in faq.itertuples():
        g = fm[fm.faq_id == r.faq_id]
        conc = g[g.match_type == 'concern_answered']
        faq_out.append({'faq_id': r.faq_id, 'project': r.project, 'question': r.question, 'question_en': r.question_en,
                        'answer_summary': r.answer_summary, 'topic': r.topic, 'argument_code': r.argument_code, 'source_url': r.source_url,
                        'n_concern_posts': int(conc.post_id.nunique()), 'n_figure_differs': int((g.match_type == 'figure_differs').sum()),
                        'example_post_ids': conc.post_id.drop_duplicates().head(5).tolist()})
    out['faq'] = faq_out
    out['faq_figure_differs'] = [{'post_id': r.post_id, 'figure_id': nn(getattr(r, 'figure_id', None)), 'post_value': r.post_value,
                                  'official_value': r.official_value, 'matched_text': r.matched_text, 'checked': nn(r.checked)}
                                 for r in fm[fm.match_type == 'figure_differs'].itertuples()]

    rm = m[~m.metric_id.str.startswith(('stance_share', 'stance_n', 'stance_uncertain'))]
    out['reliability'] = [{'metric_id': r.metric_id, 'name': r.name, 'value': nn(r.value), 'ci': [nn(r.ci_low), nn(r.ci_high)],
                           'n': nn(r.n), 'method': r.method} for r in rm.itertuples()]

    out['posts'] = [{'id': r.post_id, 'date': str(r.published_at)[:10], 'project': r.project, 'source': r.source, 'platform': r.platform,
                     'media_type': r.media_type, 'language': r.language, 'url': r.url, 'title': r.title, 'snippet': r.snippet,
                     'stance': nn(r.stance), 'voice': nn(r.voice), 'arguments': json.loads(r.arguments or '[]'),
                     'confidence': r.confidence, 'label_source': r.label_source, 'vendor_sentiment': nn(r.vendor_sentiment),
                     'cluster_id': r.cluster_id, 'cluster_size': int(r.cluster_size), 'is_paywall_stub': bool(r.is_paywall_stub),
                     'new_since_dataset': bool(r.new_since_dataset), 'faq_ids': faq_by_post.get(r.post_id, [])}
                    for r in rel.sort_values('published_at').itertuples()]
    # review queue: Heilbronn posts the rules found but nobody has confirmed, and curated posts the AI vote moved away
    rq = f[((f.label_source == 'wide_net') & (f.project == 'heilbronn_cablecar'))].assign(reason='wide net only, not in curated set')
    cur = read_table('labels')
    cur_hn = set(cur[(cur.run_id == 'rules_curated_v0') & (cur.project == 'heilbronn_cablecar')].post_id)
    moved = f[f.post_id.isin(cur_hn) & (f.project != 'heilbronn_cablecar')].assign(reason='curated as Heilbronn, AI vote says other')
    rq = pd.concat([rq, moved]).merge(posts, on='post_id')
    out['review_queue'] = [{'id': r.post_id, 'date': str(r.published_at)[:10], 'source': r.source, 'media_type': r.media_type,
                            'title': r.title, 'url': r.url, 'project_now': nn(r.project), 'student_project': nn(r.student_project),
                            'reason': r.reason, 'decision': None} for r in rq.sort_values('published_at').itertuples()]
    lv = posts[posts.origin == 'live'].merge(f[['post_id', 'project', 'student_project', 'student_prob', 'label_source']], on='post_id', how='left')
    out['live'] = [{'id': r.post_id, 'date': str(r.published_at)[:10], 'source': r.source, 'url': r.url, 'title': r.title,
                    'project_hint': nn(r.project), 'student_project': nn(r.student_project), 'student_prob': nn(r.student_prob),
                    'in_wide_net': bool(pd.notna(r.label_source)), 'verified': False}
                   for r in lv.sort_values('published_at', ascending=False).itertuples()]
    p = os.path.join(EXPORT, 'data.json')
    jdump(out, p)
    log('export', f"{p}: {len(out['posts']):,} posts, {len(out['live'])} live items, status={status}, {os.path.getsize(p) / 1e6:.1f} MB")
    return out


if __name__ == '__main__':
    run()
