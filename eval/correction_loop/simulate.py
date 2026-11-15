"""Feasibility study: can a few staff corrections per visit train the local model and measure accuracy?

SIMULATION. There are no real staff corrections. The "staff answer" is the 3-run AI consensus on the 240-post
pilot (scripts/pilot/), the same reference the local benchmark used. So "agreement with staff" below means
agreement with that consensus. Real staff may disagree with the AI; that is exactly what the real loop would measure.

Set-up (mirrors scripts/localbench/ so numbers are comparable; the team's real models in pipeline/ are not touched):
  relevance: relevant vs irrelevant, e5-base embeddings (cached) + logistic regression (C=10, balanced)
  stance:    support / oppose / neutral on relevant posts, TF-IDF word+char + logistic regression (same settings)
Each repeat: hold out 30% of posts as a fixed test set (stratified), the other 70% are the pool staff could see.
Start from a seed of 10 random corrections, then add corrections in rounds of 5. After each round, refit and
measure Cohen's kappa against the consensus on the test set. Three ways to choose what staff see:
  random            any post from the pool
  least_confident   the posts the local model is least sure about (1 - max probability)
  llm_disagreement  posts where the 3 AI runs did not agree first, then least confident
Reference line ("LLM level"): each AI run vs the agreed label of the other two runs, on the same test posts.
Run: python -I -X utf8 eval/correction_loop/simulate.py
Writes eval/results/correction_loop.json and .md
"""
import json
import os
import sys
import warnings
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.pipeline import make_pipeline, make_union

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
ROOT = os.path.dirname(EVAL)
sys.path.insert(0, EVAL)
from evallib.io import load_pilot_ai, load_sample, RELEVANT  # noqa: E402
from evallib.metrics import cohen_kappa, wilson, majority  # noqa: E402

REPEATS = 30
SEED_N = 10
STEP = 5
STRATS = ['random', 'least_confident', 'llm_disagreement']
STANCE3 = ['support', 'oppose', 'neutral_informative']


def load():
    S = load_sample()
    A = load_pilot_ai()
    names = sorted(A)
    pids = sorted(S)
    text = [S[p]['text'] for p in pids]
    emb = np.load(os.path.join(ROOT, 'scripts', 'localbench', 'cache', 'emb_e5base.npy'))
    assert emb.shape[0] == len(pids)
    tasks = {}
    rel_y, rel_ix, st_y, st_ix, rel_split, st_split, runs_rel, runs_st = [], [], [], [], [], [], [], []
    for i, p in enumerate(pids):
        projs = [A[n][p]['project'] for n in names]
        relv = ['relevant' if x in RELEVANT else 'irrelevant' for x in projs]
        c = majority(relv)
        if c not in (None, 'TIE'):
            rel_ix.append(i)
            rel_y.append(c)
            rel_split.append(len(set(relv)) > 1)
            runs_rel.append(relv)
        stv = [A[n][p]['stance'] for n in names]
        cp = majority(projs)
        cs = majority(stv)
        if cp in RELEVANT and cs in STANCE3:
            st_ix.append(i)
            st_y.append(cs)
            st_split.append(len(set(stv)) > 1)
            runs_st.append(stv)
    tasks['relevance'] = dict(ix=np.array(rel_ix), y=np.array(rel_y), split=np.array(rel_split), runs=runs_rel,
                              feat='e5base')
    tasks['stance'] = dict(ix=np.array(st_ix), y=np.array(st_y), split=np.array(st_split), runs=runs_st, feat='tfidf')
    return tasks, text, emb


def model(feat):
    if feat == 'tfidf':
        return make_pipeline(make_union(TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, lowercase=True),
                                        TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 5), sublinear_tf=True,
                                                        min_df=2)),
                             LogisticRegression(C=10, class_weight='balanced', max_iter=3000))
    return LogisticRegression(C=10, class_weight='balanced', max_iter=3000)


def X(task, rows, text, emb):
    ix = task['ix'][rows]
    return [text[i] for i in ix] if task['feat'] == 'tfidf' else emb[ix]


def llm_level(task, test_rows):
    """Mean over the 3 runs of kappa(run, agreed label of the other two) on the test rows."""
    ks = []
    for j in range(3):
        ref, pred = [], []
        for r in test_rows:
            v = task['runs'][r]
            others = [v[k] for k in range(3) if k != j]
            if others[0] == others[1]:
                ref.append(others[0])
                pred.append(v[j])
        k = cohen_kappa(ref, pred)
        if k is not None:
            ks.append(k)
    return float(np.mean(ks)) if ks else None


def run_task(name, task, text, emb):
    y = task['y']
    n = len(y)
    sss = StratifiedShuffleSplit(n_splits=REPEATS, test_size=0.3, random_state=7)
    curves = {s: {} for s in STRATS}
    shown_acc = {s: {} for s in STRATS}       # local model accuracy on the posts staff are shown (before correction)
    llm = []
    for rep, (pool, test) in enumerate(sss.split(np.zeros(n), y)):
        llm.append(llm_level(task, test))
        rng = np.random.default_rng(100 + rep)
        seed = list(rng.choice(pool, SEED_N, replace=False))
        while len(set(y[seed])) < 2:
            seed = list(rng.choice(pool, SEED_N, replace=False))
        for strat in STRATS:
            lab = list(seed)
            rest = [i for i in pool if i not in set(lab)]
            r2 = np.random.default_rng(1000 + rep)
            while True:
                m = model(task['feat']).fit(X(task, lab, text, emb), y[lab])
                k = cohen_kappa(list(y[test]), list(m.predict(X(task, test, text, emb))))
                curves[strat].setdefault(len(lab), []).append(k if k is not None else 0.0)
                if not rest:
                    break
                take = min(STEP, len(rest))
                if strat == 'random':
                    pick = list(r2.choice(rest, take, replace=False))
                else:
                    pr = m.predict_proba(X(task, rest, text, emb))
                    unc = 1 - pr.max(axis=1)
                    if strat == 'llm_disagreement':
                        unc = unc + 10 * task['split'][rest]     # AI-split posts first, then least confident
                    pick = [rest[i] for i in np.argsort(-unc)[:take]]
                pred = m.predict(X(task, pick, text, emb))
                shown_acc[strat].setdefault(len(lab), []).append(float(np.mean(pred == y[pick])))
                lab += pick
                rest = [i for i in rest if i not in set(pick)]
    # full-pool reference (all corrections used)
    out = {'n_posts': int(n), 'pool_size': int(round(n * 0.7)), 'class_counts': dict(Counter(y.tolist())),
           'ai_split_posts': int(task['split'].sum()), 'llm_level_kappa': float(np.mean([v for v in llm if v is not None])),
           'repeats': REPEATS, 'curves': {}, 'shown_accuracy': {}}
    for s in STRATS:
        out['curves'][s] = {int(k): {'mean': float(np.mean(v)), 'p10': float(np.percentile(v, 10)),
                                     'p90': float(np.percentile(v, 90))} for k, v in sorted(curves[s].items())}
        out['shown_accuracy'][s] = {int(k): float(np.mean(v)) for k, v in sorted(shown_acc[s].items())}
    return out


def first_reach(curve, target):
    for k, v in sorted(curve.items()):
        if v['mean'] >= target:
            return k
    return None


def main():
    tasks, text, emb = load()
    R = {'note': 'SIMULATION: staff answers = 3-run AI consensus on the 240-post pilot', 'tasks': {}}
    md = ['# Correction loop: simulated staff corrections (feasibility)', '',
          '**Simulation.** "Staff answer" = the 3-run AI consensus on the 240 pilot posts. No real staff were involved. '
          f'{REPEATS} repeats; each holds out 30% of posts as a test set; seed of {SEED_N} corrections, then rounds of '
          f'{STEP}. Kappa vs consensus on the test set; mean with the 10th to 90th percentile across repeats.', '']
    for name, task in tasks.items():
        r = run_task(name, task, text, emb)
        R['tasks'][name] = r
        llm = r['llm_level_kappa']
        md += [f'## {name} (local model: {"e5-base + LR" if task["feat"] == "e5base" else "TF-IDF + LR"})', '',
               f'{r["n_posts"]} posts, pool {r["pool_size"]}, classes {r["class_counts"]}, AI runs split on '
               f'{r["ai_split_posts"]}. LLM level (each AI run vs the other two, same test posts): kappa {llm:.2f}.', '',
               '| Corrections | ' + ' | '.join(STRATS) + ' |', '|---' * (len(STRATS) + 1) + '|']
        ks = sorted(r['curves']['random'])
        show = [k for k in ks if k in (10, 15, 20, 30, 40, 50, 60, 80, 100, 120, 140, 160) or k == ks[-1]]
        for k in show:
            md.append(f'| {k} | ' + ' | '.join(
                f"{r['curves'][s][k]['mean']:.2f} ({r['curves'][s][k]['p10']:.2f} to {r['curves'][s][k]['p90']:.2f})"
                if k in r['curves'][s] else 'n/a' for s in STRATS) + ' |')
        best_end = max(r['curves'][s][ks[-1]]['mean'] for s in STRATS)
        r['reach'] = {}
        for s in STRATS:
            r['reach'][s] = {f'{f:.0%}_of_llm': first_reach(r['curves'][s], f * llm) for f in (0.8, 0.9, 1.0)}
        md += ['', 'Corrections needed to reach a share of the LLM level (mean curve): ' + '; '.join(
            f'{s}: 80% at {r["reach"][s]["80%_of_llm"]}, 90% at {r["reach"][s]["90%_of_llm"]}, 100% at {r["reach"][s]["100%_of_llm"]}'
            for s in STRATS) + '. "None" = not reached with the whole pool.', '',
               'How wrong the local model looks on the posts staff are shown (mean accuracy on the shown batch, at 20 and 60 '
               'corrections): ' + '; '.join(
                   f'{s}: {r["shown_accuracy"][s].get(20, float("nan")):.2f} / {r["shown_accuracy"][s].get(60, float("nan")):.2f}'
                   for s in STRATS) + '. Actively chosen posts are the hard ones, so their error rate is NOT the model\'s '
               'accuracy; only randomly chosen checks estimate accuracy.', '']
    md += ['## Accuracy estimate from random checks (Wilson 95%, if the system is right 85% of the time)', '',
           '| Random checks | Interval | Visits at 1 random check per visit |', '|---|---|---|']
    R['estimate_table'] = []
    for n in (10, 20, 30, 50, 80, 100, 150):
        w = wilson(round(0.85 * n), n)
        R['estimate_table'].append({'n': n, 'lo': w['lo'], 'hi': w['hi']})
        md.append(f'| {n} | {w["lo"]:.0%} to {w["hi"]:.0%} (+/- {(w["hi"] - w["lo"]) / 2:.0%}) | {n} |')
    os.makedirs(os.path.join(EVAL, 'results'), exist_ok=True)
    json.dump(R, open(os.path.join(EVAL, 'results', 'correction_loop.json'), 'w', encoding='utf-8'), indent=1)
    open(os.path.join(EVAL, 'results', 'correction_loop.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    print('\n'.join(md))


if __name__ == '__main__':
    main()
