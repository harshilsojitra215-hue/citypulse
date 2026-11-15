"""Build the falsification regression suite: eval/tests/regression_cases.jsonl.

Every case is a real post from the data (pilot sample pid, or a record from the full export with a new id F-xx).
Texts are the masked snippets the labellers see (authors, handles, URLs replaced). No author names are stored.
Run: python -I -X utf8 eval/build_regression_cases.py
"""
import json
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evallib.io import load_sample, ROOT  # noqa: E402
from evallib.textprep import snippet  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests', 'regression_cases.jsonl')
NOT_HN = {'field': 'project', 'not_in': ['heilbronn_cablecar']}
IRREL = {'field': 'project', 'in': ['irrelevant']}
HN_NEUTRAL = [{'field': 'project', 'in': ['heilbronn_cablecar']}, {'field': 'stance', 'in': ['neutral_informative']}]
NOT_HN_OPPOSE = {'not_both': {'project': 'heilbronn_cablecar', 'stance': 'oppose'}}

# (rule, pid, expect, why)
PILOT_CASES = [
    # R1 ski, mountain, tourist and playground lifts are irrelevant (codebook section 1)
    ('R1_ski_lift_irrelevant', 'P046', [IRREL], 'family holiday tips in the Alps'),
    ('R1_ski_lift_irrelevant', 'P083', [IRREL], 'travel article, Meran'),
    ('R1_ski_lift_irrelevant', 'P143', [IRREL], 'top 10 sights in Bavaria, Zugspitze'),
    ('R1_ski_lift_irrelevant', 'P161', [IRREL], 'new ski-area lift in a protected zone (hard: political tone)'),
    ('R1_ski_lift_irrelevant', 'P189', [IRREL], 'train trip to Garmisch, Zugspitzbahn'),
    ('R1_ski_lift_irrelevant', 'P192', [IRREL], 'mountain lift moved by helicopter'),
    ('R1_ski_lift_irrelevant', 'P212', [IRREL], 'trade magazine: new lifts in Valais ski areas'),
    ('R1_ski_lift_irrelevant', 'P233', [IRREL], 'forum: Kampenwand mountain lift'),
    ('R1_ski_lift_irrelevant', 'P063', [IRREL], 'playground "Seilbahn" in Neckarsulm, in the Heilbronn paper (hard: local)'),
    ('R1_ski_lift_irrelevant', 'P122', [IRREL], 'tourist cable car Puerto Plata'),
    # R2 a news report of a council decision is neutral, not support (codebook stance rule 1)
    ('R2_council_report_neutral', 'P149', HN_NEUTRAL, '"Heilbronn sagt Ja zur Seilbahn-Idee" (the codebook example)'),
    ('R2_council_report_neutral', 'P019', HN_NEUTRAL, 'microblog sharing the same headline'),
    ('R2_council_report_neutral', 'P018', HN_NEUTRAL, 'Baubeschluss could come'),
    ('R2_council_report_neutral', 'P162', HN_NEUTRAL, 'paywall stub: Gemeinderat treibt Millionenprojekt voran'),
    ('R2_council_report_neutral', 'P183', HN_NEUTRAL, 'council approved deeper planning (hard: "Chancen stehen sehr gut")'),
    ('R2_council_report_neutral', 'P156', HN_NEUTRAL, 'council discusses plans, asks what speaks for and against'),
    # R3 an accident story in another place is not opposition to Heilbronn
    ('R3_accident_elsewhere_not_hn', 'P021', [NOT_HN, NOT_HN_OPPOSE], 'fatal cable car accident, Monte Faito, Italy'),
    ('R3_accident_elsewhere_not_hn', 'P224', [NOT_HN, NOT_HN_OPPOSE], 'same story, second copy'),
    ('R3_accident_elsewhere_not_hn', 'P191', [NOT_HN, NOT_HN_OPPOSE], 'gondolas crashed into stations, Italian Alps'),
    # R5 an IPAI post with no cable car claim gets no cable car project or stance
    ('R5_ipai_without_cablecar', 'P049', [NOT_HN], 'IPAI-city link "must succeed", paywall stub, no cable car word'),
    ('R5_ipai_without_cablecar', 'P029', [NOT_HN], 'construction firm builds the AI park'),
    ('R5_ipai_without_cablecar', 'P032', [NOT_HN], 'construction sign for the park'),
    ('R5_ipai_without_cablecar', 'P079', [NOT_HN], 'chancellor at the foundation stone'),
    ('R5_ipai_without_cablecar', 'P118', [NOT_HN], 'groundbreaking video'),
    ('R5_ipai_without_cablecar', 'P201', [NOT_HN], 'IPAI foundation plans'),
    ('R5_ipai_without_cablecar', 'P203', [NOT_HN], 'why Heilbronn builds a district for AI'),
    ('R5_ipai_without_cablecar', 'P148', [NOT_HN], 'citizen comment praising IPAI, no cable car'),
]

# R4 syndicated copies count once (dedup) and get the same labels (consistency)
DEDUP_CASES = [
    ('R4_syndicated_count_once', ['P021', 'P224'], 'same', 'accident story, two copies'),
    ('R4_syndicated_count_once', ['P096', 'P116', 'P150'], 'same', '"Stadt plant BW erste Nahverkehrs-Seilbahn", three outlets'),
    ('R4_syndicated_count_once', ['P149', 'P183'], 'different', 'two different articles about the same council vote'),
    ('R4_syndicated_count_once', ['P018', 'P096'], 'different', 'two different articles on the plan'),
]

# Cases from the full export (no pilot labels yet; any model that labels them is checked)
FULL_CASES = [
    ('R3_accident_elsewhere_not_hn', r'^Nach Unglück in Lissabon', [NOT_HN, NOT_HN_OPPOSE],
     'Heilbronn paper: after Lisbon accident, how safe are funiculars in Künzelsau and Stuttgart'),
    ('R3_accident_elsewhere_not_hn', r'^Als eine ganze deutsche Schulklasse', [IRREL],
     '1954 Dachstein disaster of a Heilbronn school class (negative, says Heilbronn, not the cable car)'),
    # Not used: heilbronn.de "Gemeinderat beschließt Vorplanung" is the city speaking for itself with a quote in
    # favour, so codebook rule 3 allows support. A test must have one defensible answer.
]


def main():
    S = load_sample()
    import csv
    from evallib.io import PILOT
    with open(os.path.join(PILOT, 'sample_key.csv'), encoding='utf-8-sig') as f:
        key = {r['pid']: r['mention_id'] for r in csv.DictReader(f)}
    rows = []
    for rule, pid, expect, why in PILOT_CASES:
        s = S[pid]
        rows.append({'case_id': f'{rule}:{pid}', 'rule': rule, 'pid': pid, 'post_id': key[pid], 'source': 'pilot_sample',
                     'date': s['date'], 'media_type': s['media_type'], 'text': s['text'], 'expect': expect, 'why': why})
    for rule, members, mode, why in DEDUP_CASES:
        rows.append({'case_id': f'{rule}:{"+".join(members)}', 'rule': rule, 'members': members,
                     'member_post_ids': [key[p] for p in members], 'dedup': mode,
                     'texts': [S[p]['text'] for p in members], 'source': 'pilot_sample', 'why': why,
                     'expect': [{'consistent_labels': ['project', 'stance']}] if mode == 'same' else []})
    df = pd.read_pickle(os.path.join(ROOT, 'scripts', 'deep_stadt', 'df2.pkl'))
    for i, (rule, title_re, expect, why) in enumerate(FULL_CASES, 1):
        m = df[df.title.fillna('').str.contains(title_re, regex=True)]
        if m.empty:
            print('NOT FOUND', title_re)
            continue
        r = m.sort_values('published_at').iloc[0]
        pid = f'F{i:02d}'
        rows.append({'case_id': f'{rule}:{pid}', 'rule': rule, 'pid': pid, 'post_id': r['mention_id'],
                     'source': 'full_export', 'date': str(pd.Timestamp(r['published_at']).date()),
                     'media_type': r['media_type_name'], 'text': snippet(r), 'expect': expect, 'why': why})
    with open(OUT, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    from collections import Counter
    print('wrote', OUT, len(rows), 'cases', dict(Counter(r['rule'] for r in rows)))


if __name__ == '__main__':
    main()
