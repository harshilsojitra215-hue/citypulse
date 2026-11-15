"""Stage 9: FAQ claim matching. Where does the city's own communication not reach people?

The official FAQ (reference/faq_heilbronn.json) is the city's position. It never decides stance.
It is used for two things:
1. concern_answered: a Heilbronn post raises a concern the FAQ already answers
   (e.g. "where will cars park?" while the FAQ talks about park-and-ride). Rule: any concern pattern
   of that FAQ item matches the post's snippet.
2. figure_differs: a post states a number for an official figure that is outside the official range
   (e.g. a cost other than 157 million EUR), published on or after the date the official figure
   became public (`valid_from`). An older estimate is not a wrong claim.

Both are candidates for a human check (`checked` stays null). Rules are transparent and editable;
an embedding matcher can replace them later (method 'embedding_v1').
"""
import json
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import log, path, read_table, write_table  # noqa: E402

WORDNUM = {'vier': 4, 'fünf': 5, 'sechs': 6, 'sieben': 7, 'acht': 8}


def to_num(s):
    s = s.strip().lower()
    if s in WORDNUM:
        return float(WORDNUM[s])
    s = s.replace('.', '') if re.fullmatch(r'\d{1,3}(\.\d{3})+', s) else s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def load_faq():
    d = json.load(open(path('faq'), encoding='utf-8'))
    items = pd.DataFrame(d['items'])
    items['official_figures'] = None
    return d, items


def run():
    d, items = load_faq()
    figs = d['official_figures']
    f = read_table('labels_final')
    c = read_table('candidates')[['post_id', 'snippet']]
    p = read_table('posts', columns=['post_id', 'published_at', 'title', 'text'])
    hn = f[(f.project == 'heilbronn_cablecar') & (f.label_source != 'wide_net')].merge(p, on='post_id').merge(c, on='post_id', how='left')
    hn['x'] = hn.snippet.fillna(hn.title + ' | ' + hn.text.str[:600]).str.lower()
    rows = []
    for r in hn.itertuples():
        for it in d['items']:
            for pat in it['concern_patterns']:
                m = re.search(pat, r.x)
                if m:
                    lo, hi = max(0, m.start() - 90), m.end() + 90
                    rows.append({'post_id': r.post_id, 'faq_id': it['faq_id'], 'match_type': 'concern_answered', 'score': 1.0,
                                 'post_value': None, 'official_value': None, 'matched_text': r.x[lo:hi], 'method': 'rules_v1', 'checked': None})
                    break
        for fg in figs:
            if fg.get('valid_from') and str(r.published_at)[:10] < fg['valid_from']:
                continue
            if not isinstance(fg['value'], (int, float)):
                continue
            for m in re.finditer(fg['regex'], r.x):
                ctx = r.x[max(0, m.start() - 70):m.end() + 30]
                if not re.search(fg['context'], ctx):
                    continue
                v = to_num(m.group(1))
                if v is None:
                    continue
                if fg['figure_id'] == 'cost_invest' and re.search(r'förder|planungsmittel|planungsgeld|zuschuss|paris|bonn|stuttgart|stadtbahn', ctx):
                    continue  # another money amount or another project, not the investment cost
                ok = fg['accept_min'] <= v <= fg['accept_max']
                if not ok:
                    rows.append({'post_id': r.post_id, 'faq_id': next((i['faq_id'] for i in d['items'] if fg['figure_id'].split('_')[0] in i['faq_id']), fg['figure_id']),
                                 'match_type': 'figure_differs', 'score': 0.5, 'post_value': m.group(0).strip(),
                                 'official_value': f"{fg['value']} {fg['unit']}", 'matched_text': ctx, 'method': 'rules_v1', 'checked': None,
                                 'figure_id': fg['figure_id']})
    mt = pd.DataFrame(rows, columns=['post_id', 'faq_id', 'match_type', 'score', 'post_value', 'official_value', 'matched_text', 'method', 'checked', 'figure_id'])
    mt['checked'] = mt['checked'].astype('boolean')
    faq = items[['faq_id', 'project', 'question', 'question_en', 'answer_summary', 'topic', 'argument_code', 'source_url', 'date_seen']].copy()
    faq['official_figures'] = json.dumps(figs, ensure_ascii=False)
    write_table('faq', faq)
    write_table('faq_matches', mt)
    by = mt[mt.match_type == 'concern_answered'].faq_id.value_counts().to_dict()
    log('faq', f"{len(hn)} Heilbronn posts checked; concern matches {by}; figure_differs {int((mt.match_type == 'figure_differs').sum())}")
    return mt


if __name__ == '__main__':
    run()
