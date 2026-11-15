"""Build the human labelling task files in eval/gold/.

Tier 1 (both label, about 40 min each): the 60 blind rows of scripts/pilot/human_review.csv.
        -> human vs human kappa, AI vs human, vendor vs human, vote calibration.
Tier 2 (both label, about 10 min each): Heilbronn citizen voices not already in tier 1.
        -> the only "what residents say" number, double-labelled, as a census.
Tier 3 (split A / B, about 35 min each): every other Heilbronn record, syndicated copies labelled once.
        -> human census of Heilbronn stance (no sampling error) and a bigger gold set for ACC.

Task CSV columns: pid (= export mention_id, the contract join key post_id), ref (short id shown on screen:
P### = pilot sample, H### = other Heilbronn record), tier, date, media_type, text.
No vendor sentiment, no AI labels, no authors. eval/gold/task_key.csv maps ref -> mention_id, url, source.
Labellers are pseudonyms: a = Harshil, b = the team (pipeline/CONTRACT.md: never names in tables).
Run: python -I -X utf8 eval/build_gold_tasks.py
"""
import csv
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evallib.io import load_sample, PILOT, ROOT, GOLD  # noqa: E402
from evallib.textprep import snippet  # noqa: E402

CITIZEN = 'citizen/forum/comment/personal blog'


def write(path, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['pid', 'ref', 'tier', 'date', 'media_type', 'text'])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in w.fieldnames})


def main():
    os.makedirs(GOLD, exist_ok=True)
    S = load_sample()
    key = {r['pid']: r for r in csv.DictReader(open(os.path.join(PILOT, 'sample_key.csv'), encoding='utf-8-sig'))}
    hr = [r['pid'] for r in csv.DictReader(open(os.path.join(PILOT, 'human_review.csv'), encoding='utf-8-sig'))]
    mid2pid = {v['mention_id']: p for p, v in key.items()}

    t1 = [{'pid': key[p]['mention_id'], 'ref': p, 'tier': 1, 'date': S[p]['date'], 'media_type': S[p]['media_type'], 'text': S[p]['text']} for p in hr]
    keyrows = [{'ref': p, 'tier': 1, 'mention_id': key[p]['mention_id'], 'url': key[p]['url'],
                'source': key[p]['source_name'], 'copy_of': ''} for p in hr]

    hn = pd.read_pickle(os.path.join(ROOT, 'scripts', 'deep_stadt', 'hn_final.pkl')).sort_values('ts')
    in_t1 = {key[p]['mention_id'] for p in hr}
    hn = hn[~hn.mention_id.isin(in_t1)]
    # syndicated copies: same normalised title (ignoring site suffix) and same first 200 content characters
    nt = hn.title.fillna('').str.lower().str.replace(r'\s[-|–]\s[^-|–]{2,40}$', '', regex=True)
    nt = nt.str.replace(r'\W+', ' ', regex=True).str.strip()
    hn = hn.assign(_nt=nt)
    first = {}
    t2, t3 = [], []
    n = 0
    for _, r in hn.iterrows():
        k = r['_nt'] if len(r['_nt']) > 15 else None
        if k and k in first:
            keyrows.append({'ref': '', 'tier': 'copy', 'mention_id': r['mention_id'], 'url': r['url'],
                            'source': r['source_name'], 'copy_of': first[k]})
            continue
        # reuse the pilot id when the record is in the pilot sample (so AI labels line up)
        pid = mid2pid.get(r['mention_id'])
        if not pid:
            n += 1
            pid = f'H{n:03d}'
        if k:
            first[k] = pid
        row = {'pid': r['mention_id'], 'ref': pid, 'date': str(r['ts'].date()), 'media_type': r['media_type_name'],
               'text': S[pid]['text'] if pid in S else snippet(r)}
        if r['voice'] == CITIZEN:
            row['tier'] = 2
            t2.append(row)
        else:
            row['tier'] = 3
            t3.append(row)
        keyrows.append({'ref': pid, 'tier': row['tier'], 'mention_id': r['mention_id'], 'url': r['url'],
                        'source': r['source_name'], 'copy_of': ''})
    a, b = t3[0::2], t3[1::2]
    for r in a:
        r['tier'] = '3A'
    for r in b:
        r['tier'] = '3B'
    write(os.path.join(GOLD, 'tasks_tier1_both.csv'), t1)
    write(os.path.join(GOLD, 'tasks_tier2_both_hn_citizens.csv'), t2)
    write(os.path.join(GOLD, 'tasks_tier3A.csv'), a)
    write(os.path.join(GOLD, 'tasks_tier3B.csv'), b)
    in_a = {x['ref'] for x in a}
    for r in keyrows:
        if r['tier'] == 3:
            r['tier'] = '3A' if r['ref'] in in_a else '3B'
    with open(os.path.join(GOLD, 'task_key.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['ref', 'tier', 'mention_id', 'url', 'source', 'copy_of'])
        w.writeheader()
        w.writerows(keyrows)
    copies = sum(1 for r in keyrows if r['tier'] == 'copy')
    print(f'tier1 {len(t1)} | tier2 {len(t2)} | tier3A {len(a)} | tier3B {len(b)} | syndicated copies skipped {copies}')
    print(f'Heilbronn records covered: tier1 HN {len(in_t1 & set(pd.read_pickle(os.path.join(ROOT, "scripts", "deep_stadt", "hn_final.pkl")).mention_id))}'
          f' + tier2 {len(t2)} + tier3 {len(t3)} + copies {copies}')


if __name__ == '__main__':
    main()
