"""External check: can our labeller read a side when the AUTHOR told us their side? (X-Stance)

X-Stance (Vamvas and Sennrich 2020, University of Zurich): Swiss election candidates answered yes/no policy
questions and wrote a comment explaining their answer. Label = the candidate's own answer (FAVOR / AGAINST),
so the truth comes from the author, not from an annotator. Licence CC BY-NC 4.0: we use it for evaluation only,
the data stays in eval/external/ and is never redistributed or put in the app.

Steps:
  python -I -X utf8 eval/xstance/xstance.py prepare   # needs eval/external/xstance/xstance-data-v1.0.zip
  (label eval/xstance/batch_*_blind.jsonl with the codebook stance rules, see PROMPT below)
  python -I -X utf8 eval/xstance/xstance.py score
Sample: test split, topic "Infrastructure & Environment" (closest to our domain), German and French,
50 FAVOR + 50 AGAINST per language (balanced, seed fixed) = 200 comments.
Mapping: support = FAVOR, oppose = AGAINST. neutral_informative / mixed / unclear = "no side": wrong for
accuracy, and reported separately (every X-Stance comment has a side, so "no side" is over-caution).
"""
import glob
import json
import os
import random
import sys
import zipfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
from evallib.io import load_labels  # noqa: E402
from evallib.metrics import bootstrap, cohen_kappa, macro_f1, accuracy, wilson, majority  # noqa: E402

ZIP = os.path.join(EVAL, 'external', 'xstance', 'xstance-data-v1.0.zip')
KEY = os.path.join(HERE, '_answer_key', 'xstance_key.jsonl')
SEED = 20261115
PER = 50
FRAME = {'de': 'Frage: {q}\n\nKommentar: {c}', 'fr': 'Question : {q}\n\nCommentaire : {c}'}


def read_split(name):
    with zipfile.ZipFile(ZIP) as z:
        member = [m for m in z.namelist() if m.endswith(name)][0]
        with z.open(member) as f:
            return [json.loads(l) for l in f.read().decode('utf-8').splitlines() if l.strip()]


def prepare():
    if not os.path.exists(ZIP):
        sys.exit(f'missing {ZIP}: download needs Harshil\'s yes (6.4 MB, github.com/ZurichNLP/xstance)')
    rows = read_split('test.jsonl')
    print('fields:', sorted(rows[0]))
    print('topics:', Counter(r.get('topic') for r in rows).most_common(15))
    rng = random.Random(SEED)
    pick = []
    for lang in ('de', 'fr'):
        pool = [r for r in rows if r.get('language') == lang and 'nfrastruct' in str(r.get('topic', ''))]
        for lab in ('FAVOR', 'AGAINST'):
            sub = [r for r in pool if r.get('label') == lab]
            rng.shuffle(sub)
            pick += sub[:PER]
            print(lang, lab, 'pool', len(sub), 'took', min(PER, len(sub)))
    rng.shuffle(pick)
    os.makedirs(os.path.dirname(KEY), exist_ok=True)
    with open(KEY, 'w', encoding='utf-8') as f:
        for i, r in enumerate(pick, 1):
            f.write(json.dumps({'pid': f'X{i:03d}', 'language': r['language'], 'label': r['label'],
                                'question_id': r.get('question_id'), 'topic': r.get('topic'),
                                'test_set': r.get('test_set')}, ensure_ascii=False) + '\n')
    half = (len(pick) + 1) // 2
    for k, chunk in enumerate([pick[:half], pick[half:]], 1):
        with open(os.path.join(HERE, f'batch_{k}_blind.jsonl'), 'w', encoding='utf-8') as f:
            for j, r in enumerate(chunk):
                pid = f'X{(k - 1) * half + j + 1:03d}'
                f.write(json.dumps({'pid': pid, 'text': FRAME[r['language']].format(q=r['question'], c=r['comment'])},
                                   ensure_ascii=False) + '\n')
    print('wrote', len(pick), 'items (no author fields kept)')


def side(s):
    return {'support': 'FAVOR', 'oppose': 'AGAINST'}.get(s, 'NO_SIDE')


def score():
    key = {json.loads(l)['pid']: json.loads(l) for l in open(KEY, encoding='utf-8')}
    runs = defaultdict(dict)
    for f in glob.glob(os.path.join(HERE, 'labels', '*_batch*.jsonl')):
        n = os.path.basename(f).split('_batch')[0]
        for p, r in load_labels_stance(f).items():
            runs[n][p] = r
    if not runs:
        sys.exit('no labels in eval/xstance/labels/ yet')
    names = sorted(runs)
    runs['majority_3'] = {p: (lambda v: None if v == 'TIE' else v)(majority([runs[n].get(p) for n in names]))
                          for p in key}
    out = {'n_items': len(key), 'runs': {n: len(runs[n]) for n in names}, 'by_model': {}}
    md = ['# X-Stance check (truth = the author\'s own answer)', '',
          'Swiss candidates\' comments on "Infrastructure & Environment" questions, test split, 50 FAVOR + 50 AGAINST '
          'per language. Our labeller read "question + comment" and used the codebook stance definitions with the '
          'question\'s proposal as the target. Licence CC BY-NC 4.0, evaluation only. Intervals: bootstrap 95% '
          '(accuracy, kappa, macro-F1), Wilson (no-side rate).', '',
          '| Model | Language | n | Accuracy | Kappa | Macro-F1 (favor/against) | Said "no side" | Swapped sides |',
          '|---|---|---|---|---|---|---|---|']
    for n in names + ['majority_3']:
        out['by_model'][n] = {}
        for lang in ('de', 'fr', 'all'):
            ps = [p for p in key if (lang == 'all' or key[p]['language'] == lang) and runs[n].get(p) is not None]
            ref = [key[p]['label'] for p in ps]
            pred = [side(runs[n][p]) for p in ps]
            acc = bootstrap(accuracy, ref, pred, B=2000)
            kap = bootstrap(cohen_kappa, ref, pred, B=2000)
            mf1 = bootstrap(lambda a, b: macro_f1(a, b, ['FAVOR', 'AGAINST', 'NO_SIDE']), ref, pred, B=2000)
            ns = wilson(sum(x == 'NO_SIDE' for x in pred), len(pred))
            swaps = sum(1 for a, b in zip(ref, pred) if b != 'NO_SIDE' and a != b)
            out['by_model'][n][lang] = {'n': len(ps), 'accuracy': acc, 'kappa': kap, 'macro_f1': mf1,
                                        'no_side': ns, 'swapped': swaps,
                                        'accuracy_when_side_given': wilson(sum(a == b for a, b in zip(ref, pred) if b != 'NO_SIDE'),
                                                                           sum(1 for b in pred if b != 'NO_SIDE'))}
            f = lambda d: f"{d['value']:.2f} [{d['lo']:.2f}, {d['hi']:.2f}]" if d.get('lo') is not None else 'n/a'
            md.append(f'| {n} | {lang} | {len(ps)} | {f(acc)} | {f(kap)} | {f(mf1)} | {ns["k"]} ({ns["value"]:.0%}) | {swaps} |')
    md += ['', 'What this shows: whether the labeller reads the side an author really took, in German and French. '
           'What it does not show: the neutral class (X-Stance has none), cable car or news text, or how people read '
           'our posts. The models may have seen X-Stance during training.', '']
    os.makedirs(os.path.join(EVAL, 'results'), exist_ok=True)
    json.dump(out, open(os.path.join(EVAL, 'results', 'xstance.json'), 'w', encoding='utf-8'), indent=1)
    open(os.path.join(EVAL, 'results', 'xstance.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    print('\n'.join(md))


def load_labels_stance(path):
    d = {}
    for l in open(path, encoding='utf-8'):
        if l.strip():
            r = json.loads(l)
            if r.get('pid'):
                d[r['pid']] = (r.get('stance') or '').strip().lower() or None
    return d


PROMPT = """You are a careful annotator.
1. Read C:\\Users\\Harshil\\Desktop\\win\\eval\\label_tool\\codebook_v1.md, section 2 (stance) and its boundary rules.
2. Read {BATCH}. Each line: pid and text = a policy QUESTION and a COMMENT written by one person.
3. For each line, decide the stance of the COMMENT toward the proposal in the QUESTION, using exactly the codebook
   stance values and definitions (support, oppose, neutral_informative, mixed, unclear). Treat the proposal in the
   question as "the project". Judge only the text. Read each item yourself; do not write code to label.
4. Do NOT open any other file (no answer keys, no other labels).
5. Write with the Write tool to {OUT}, one line per item: {{"pid":"X001","stance":"...","evidence":"<=15 words verbatim"}}
6. Reply with only the number of lines written."""

if __name__ == '__main__':
    {'prepare': prepare, 'score': score}[sys.argv[1] if len(sys.argv) > 1 else 'prepare']()
