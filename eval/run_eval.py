"""One command for every number on the trust slide.

Run:  python -I -X utf8 eval/run_eval.py [--preds path/to/model_labels.jsonl --preds-name local_model] [--B 2000]

Reads
  scripts/pilot/sample.jsonl + labels_{haiku,sonnet_a,sonnet_b}.jsonl   (3 AI labellers, 240 posts)
  eval/gold/labels_<human>.csv                                           (label tool output, if any)
  eval/gold/labels_adjudicated.csv                                       (joint decisions on human disagreements, optional)
  --preds: any model's labels in contract/pilot format (optional, e.g. the local model)
Writes
  eval/results/metrics.json     every number, with 95% intervals and n
  eval/results/tables.md        the same, readable
  eval/results/human_disagreements.csv   rows where the humans disagree (for adjudication)
Every interval is a 95% paired percentile bootstrap over posts unless it says Wilson.
"""
import argparse
import csv
import json
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evallib import metrics as M  # noqa: E402
from evallib import calibration as CAL  # noqa: E402
from evallib import prevalence as PV  # noqa: E402
from evallib import io as IO  # noqa: E402
from evallib.io import (load_sample, load_pilot_ai, load_labels, keyword_baseline, stance4, to_pilot_ids,  # noqa: E402
                        RELEVANT, STANCE4)
from evallib.regression import load_cases, check_model, check_dedup  # noqa: E402
from evallib.dedup import cluster  # noqa: E402

MD = []


def md(s=''):
    MD.append(s)


def f2(x):
    return 'n/a' if x is None else f'{x:.2f}'


def ci(d):
    if d is None or d.get('value') is None:
        return 'n/a'
    if d.get('lo') is None:
        return f2(d['value'])
    return f"{d['value']:.2f} [{d['lo']:.2f}, {d['hi']:.2f}]"


def kappa_stat(a, b):
    return M.cohen_kappa(a, b)


def rel(p):
    return None if p is None else p in RELEVANT


def compare(ref, pred, pids, B, seed=0, stance_labels=STANCE4):
    """All metrics of pred against ref on the given pids. ref/pred: {pid: rec}."""
    pids = [p for p in pids if p in ref and p in pred and ref[p].get('project') and pred[p].get('project')]
    out = {'n': len(pids)}
    rp = [ref[p]['project'] for p in pids]
    pp = [pred[p]['project'] for p in pids]
    out['project_accuracy'] = M.bootstrap(M.accuracy, rp, pp, B=B, seed=seed)
    out['project_kappa'] = M.bootstrap(kappa_stat, rp, pp, B=B, seed=seed)
    rr = [rel(x) for x in rp]
    pr = [rel(x) for x in pp]
    out['relevance'] = M.binary_prf(rr, pr)
    out['relevance_precision'] = M.bootstrap(lambda a, b: M.binary_prf(a, b)['precision'], rr, pr, B=B, seed=seed)
    out['relevance_recall'] = M.bootstrap(lambda a, b: M.binary_prf(a, b)['recall'], rr, pr, B=B, seed=seed)
    # stance on posts the reference calls relevant
    sp = [p for p in pids if ref[p]['project'] in RELEVANT and ref[p].get('stance') and pred[p].get('stance')]
    rs = [stance4(ref[p]['stance']) for p in sp]
    ps = [stance4(pred[p]['stance']) if pred[p]['project'] in RELEVANT else 'other' for p in sp]
    out['stance_n'] = len(sp)
    if sp:
        out['stance_accuracy'] = M.bootstrap(M.accuracy, rs, ps, B=B, seed=seed)
        out['stance_kappa'] = M.bootstrap(kappa_stat, rs, ps, B=B, seed=seed)
        out['stance_macro_f1'] = M.bootstrap(lambda a, b: M.macro_f1(a, b, stance_labels), rs, ps, B=B, seed=seed)
        out['stance_per_class'] = M.per_class(rs, ps, stance_labels)
        labs, cm = M.confusion(rs, ps, stance_labels)
        out['stance_confusion'] = {'rows_reference': labs, 'cols_prediction': labs, 'matrix': cm.tolist()}
        # opinion-bearing = reference says support or oppose
        ob = [(a, b) for a, b in zip(rs, ps) if a in ('support', 'oppose')]
        out['opinion_bearing_n'] = len(ob)
        out['opinion_bearing_exact'] = M.wilson(sum(a == b for a, b in ob), len(ob))
        out['opinion_flipped'] = sum(1 for a, b in ob if {a, b} == {'support', 'oppose'})
    vp = [p for p in pids if ref[p].get('voice') and pred[p].get('voice')]
    if vp:
        out['voice_kappa'] = M.bootstrap(kappa_stat, [ref[p]['voice'] for p in vp], [pred[p]['voice'] for p in vp],
                                         B=B, seed=seed)
    return out


def md_compare(title, c):
    md(f'**{title}** (n = {c["n"]}; stance on {c.get("stance_n", 0)} relevant posts)')
    md('')
    md('| Metric | Value [95% CI] |')
    md('|---|---|')
    md(f'| Project accuracy | {ci(c["project_accuracy"])} |')
    md(f'| Project kappa | {ci(c["project_kappa"])} |')
    md(f'| Relevance precision | {ci(c["relevance_precision"])} |')
    md(f'| Relevance recall | {ci(c["relevance_recall"])} |')
    if c.get('stance_n'):
        md(f'| Stance accuracy (4 classes) | {ci(c["stance_accuracy"])} |')
        md(f'| Stance kappa | {ci(c["stance_kappa"])} |')
        md(f'| Stance macro-F1 | {ci(c["stance_macro_f1"])} |')
        ob = c['opinion_bearing_exact']
        md(f'| Support/oppose posts labelled the same (Wilson) | {ci(ob)} ({ob.get("k", 0)}/{ob["n"]}), '
           f'support<->oppose flips: {c["opinion_flipped"]} |')
    if c.get('voice_kappa'):
        md(f'| Voice kappa | {ci(c["voice_kappa"])} |')
    md('')
    if c.get('stance_n'):
        cm = c['stance_confusion']
        md('Stance confusion (rows = reference, columns = prediction):')
        md('')
        md('| ref \\ pred | ' + ' | '.join(cm['cols_prediction']) + ' |')
        md('|---' * (len(cm['cols_prediction']) + 1) + '|')
        for lab, row in zip(cm['rows_reference'], cm['matrix']):
            md(f'| {lab} | ' + ' | '.join(str(x) for x in row) + ' |')
        md('')
        md('Per class: ' + '; '.join(f'{k} P {v["precision"]:.2f} R {v["recall"]:.2f} F1 {v["f1"]:.2f} (n {v["support"]})'
                                     for k, v in c['stance_per_class'].items()))
        md('')


def majority_labels(label_sets, pids, fields=('project', 'stance', 'voice')):
    out = {}
    for p in pids:
        rs = [L[p] for L in label_sets if p in L]
        if not rs:
            continue
        r = {f: M.majority([x.get(f) for x in rs]) for f in fields}
        r = {f: (None if v == 'TIE' else v) for f, v in r.items()}
        r['n_votes'] = len(rs)
        out[p] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preds', action='append', default=[], help='extra model label file (jsonl/csv), repeatable')
    ap.add_argument('--preds-name', action='append', default=[])
    ap.add_argument('--B', type=int, default=2000)
    ap.add_argument('--gold-dir', default=None, help='default eval/gold (use another folder for dry runs)')
    ap.add_argument('--results-dir', default=None, help='default eval/results')
    a = ap.parse_args()
    B = a.B
    if a.gold_dir:
        IO.GOLD = a.gold_dir
    RESULTS = a.results_dir or IO.RESULTS
    os.makedirs(RESULTS, exist_ok=True)
    S = load_sample()
    A = load_pilot_ai()
    names = sorted(A)
    H, ADJ = IO.load_human()
    extra = {}
    for i, p in enumerate(a.preds):
        nm = a.preds_name[i] if i < len(a.preds_name) else os.path.splitext(os.path.basename(p))[0]
        extra[nm] = to_pilot_ids(load_labels(p))   # contract post_id -> pilot pid where possible
    KWB = {p: {'project': keyword_baseline(S[p]['text']), 'stance': None, 'voice': None} for p in S}
    pids = sorted(S)
    R = {'generated': datetime.now().isoformat(timespec='seconds'), 'bootstrap_B': B,
         'labellers_ai': names, 'labellers_human': sorted(H), 'adjudicated': bool(ADJ), 'extra_models': sorted(extra),
         'note': 'pilot sample is stratified (70 HN, 50 Bonn, 40 Paris, 40 IPAI, 40 hard negatives): '
                 'shares are within-sample, not population shares'}

    md('# Evaluation results')
    md('')
    md(f'Generated {R["generated"]} by `eval/run_eval.py`. 95% intervals: paired bootstrap over posts (B = {B}) '
       'unless marked Wilson. Pilot sample = 240 stratified posts, so shares are within-sample.')
    md('')
    md(f'AI labellers: {names}. Human labellers: {sorted(H) or "none yet"}. Extra models: {sorted(extra) or "none"}.')
    md('')

    # ---------- 1. AI vs AI ----------
    md('## 1. AI vs AI agreement (consistency, not accuracy)')
    md('')
    md('| Pair | n | Project kappa | Relevant kappa | Stance kappa (all) | Stance kappa (both say relevant) | Voice kappa |')
    md('|---|---|---|---|---|---|---|')
    sec = {}
    for x, y in combinations(names, 2):
        c = sorted(set(A[x]) & set(A[y]))
        g = lambda L, f: [L[p][f] for p in c]
        both_rel = [p for p in c if A[x][p]['project'] in RELEVANT and A[y][p]['project'] in RELEVANT]
        d = {'n': len(c),
             'project': M.bootstrap(kappa_stat, g(A[x], 'project'), g(A[y], 'project'), B=B),
             'relevant': M.bootstrap(kappa_stat, [rel(v) for v in g(A[x], 'project')], [rel(v) for v in g(A[y], 'project')], B=B),
             'stance_all': M.bootstrap(kappa_stat, g(A[x], 'stance'), g(A[y], 'stance'), B=B),
             'stance_relevant': M.bootstrap(kappa_stat, [A[x][p]['stance'] for p in both_rel],
                                            [A[y][p]['stance'] for p in both_rel], B=B),
             'voice': M.bootstrap(kappa_stat, g(A[x], 'voice'), g(A[y], 'voice'), B=B)}
        sec[f'{x}__{y}'] = d
        md(f'| {x} vs {y} | {d["n"]} | {ci(d["project"])} | {ci(d["relevant"])} | {ci(d["stance_all"])} | '
           f'{ci(d["stance_relevant"])} (n {d["stance_relevant"]["n"]}) | {ci(d["voice"])} |')
    alpha = {}
    for f in ('project', 'stance', 'voice'):
        units = [[A[n][p][f] if p in A[n] else None for n in names] for p in pids]
        alpha[f] = M.bootstrap(lambda u: M.krippendorff_alpha_nominal(u), units, B=min(B, 1000))
    sec['krippendorff_alpha'] = alpha
    R['ai_vs_ai'] = sec
    md('')
    md('Krippendorff alpha, all 3: ' + ', '.join(f'{f} {ci(v)}' for f, v in alpha.items()))
    md('')
    md('Note: the stance kappa "all" includes irrelevant posts where stance is unclear by rule, which inflates it. '
       'The "both say relevant" column is the honest stance number.')
    md('')

    # ---------- 2. Leave one labeller out ----------
    md('## 2. Leave one labeller out (each AI vs the agreed label of the other two)')
    md('')
    md('Reference = label where the other two AI labellers agree; posts where they split are dropped from the reference. '
       'This tells us whether one model is an outlier. It is still AI vs AI.')
    md('')
    loo = {}
    for x in names:
        others = [A[n] for n in names if n != x]
        ref = {}
        for p in pids:
            r = {}
            for f in ('project', 'stance', 'voice'):
                v = {o[p][f] for o in others}
                r[f] = v.pop() if len(v) == 1 else None
            if r['project']:
                ref[p] = r
        c = compare(ref, A[x], pids, B)
        loo[x] = c
        md_compare(f'{x} vs agreed label of the other two', c)
    R['leave_one_out'] = loo

    # ---------- consensus ----------
    CONS = majority_labels([A[n] for n in names], pids)
    for p, r in CONS.items():
        vals = [A[n][p]['stance'] for n in names]
        r['stance_votes'] = Counter(vals)

    # ---------- 3. Keyword baseline ----------
    md('## 3. Keyword baseline vs 3-AI consensus (relevance)')
    md('')
    kb = compare({p: r for p, r in CONS.items() if r['project']}, KWB, pids, B)
    kb = {k: v for k, v in kb.items() if not k.startswith('stance') and not k.startswith('voice') and not k.startswith('opinion')}
    R['keyword_vs_consensus'] = kb
    md(f'n = {kb["n"]}: precision {ci(kb["relevance_precision"])}, recall {ci(kb["relevance_recall"])}, '
       f'project accuracy {ci(kb["project_accuracy"])}. Counts: {kb["relevance"]}.')
    md('')
    md('The sample over-represents real candidates (200 of 240 are from candidate sets), so on the full 39,361 records '
       'keyword precision will be lower. Measure it on a random sample of keyword hits before quoting a full-data number.')
    md('')

    # ---------- 4. Vendor sentiment ----------
    md('## 4. Vendor sentiment vs 3-AI consensus stance (relevant posts)')
    md('')
    mp = {1: 'support', -1: 'oppose', 0: 'neutral_informative'}
    relp = [p for p in pids if CONS[p]['project'] in RELEVANT and CONS[p]['stance']]
    sc = [p for p in relp if S[p]['vendor_sentiment'] in mp]
    k = sum(mp[S[p]['vendor_sentiment']] == CONS[p]['stance'] for p in sc)
    vend = {'match': M.wilson(k, len(sc)), 'unscored': sum(S[p]['vendor_sentiment'] == -99 for p in relp),
            'relevant_n': len(relp),
            'positive_but_neutral': sum(1 for p in sc if S[p]['vendor_sentiment'] == 1 and CONS[p]['stance'] == 'neutral_informative')}
    R['vendor_vs_consensus'] = vend
    md(f'Vendor score read as stance (1 = support, 0 = neutral, -1 = oppose) matches the consensus in '
       f'{k}/{len(sc)} = {ci(vend["match"])} (Wilson). {vend["positive_but_neutral"]} posts scored positive are neutral reports. '
       f'{vend["unscored"]}/{len(relp)} relevant posts have no score.')
    md('')

    # ---------- 5. Consensus stance counts ----------
    md('## 5. Stance counts per project (3-AI consensus, within the stratified sample)')
    md('')
    md('| Project | n | Support | Oppose | Neutral | Mixed/unclear | Oppose share (Wilson) |')
    md('|---|---|---|---|---|---|---|')
    shares = {}
    for proj in sorted(RELEVANT):
        ps_ = [p for p in pids if CONS[p]['project'] == proj and CONS[p]['stance']]
        c4 = Counter(stance4(CONS[p]['stance']) for p in ps_)
        shares[proj] = {'n': len(ps_), 'counts': dict(c4),
                        'support': M.wilson(c4['support'], len(ps_)), 'oppose': M.wilson(c4['oppose'], len(ps_))}
        md(f'| {proj} | {len(ps_)} | {c4["support"]} | {c4["oppose"]} | {c4["neutral_informative"]} | {c4["other"]} | '
           f'{ci(shares[proj]["oppose"])} |')
    hc = [p for p in pids if CONS[p]['project'] == 'heilbronn_cablecar' and CONS[p]['voice'] == 'citizen' and CONS[p]['stance']]
    c4 = Counter(stance4(CONS[p]['stance']) for p in hc)
    shares['heilbronn_citizen_voice'] = {'n': len(hc), 'counts': dict(c4)}
    R['consensus_stance'] = shares
    md('')
    md(f'Heilbronn posts with consensus voice = citizen in this sample: n = {len(hc)}, {dict(c4)}. '
       'With n this small every share has an interval of roughly plus or minus 20 to 35 points (see section 10).')
    md('')

    # ---------- 6. Vote calibration and abstention (AI proxy) ----------
    md('## 6. Voting with abstention and vote-share calibration (AI proxy, leave one out)')
    md('')
    md('For each held-out AI labeller: the other two vote. Confidence = share of the two votes for the chosen label '
       '(1.0 = they agree, 0.5 = split). "Correct" = the held-out labeller gives the same label. '
       'This is AI vs AI; the human version is in section 8.')
    md('')
    calib = {}
    for fld in ('project', 'stance'):
        conf, corr = [], []
        for x in names:
            others = [n for n in names if n != x]
            for p in pids:
                if fld == 'stance' and CONS[p]['project'] not in RELEVANT:
                    continue
                lab, share = CAL.vote_confidence([A[o][p][fld] for o in others])
                conf.append(share)
                corr.append(lab == A[x][p][fld])
        e, rows = CAL.ece_by_levels(conf, corr)
        calib[fld] = {'ece': e, 'levels': rows}
        md(f'- {fld}: ' + '; '.join(f'when the two {"agree" if r["conf"] == 1 else "split"} (n {r["n"]}) the third matches '
                                   f'{r["accuracy"]:.2f}' for r in rows) + f'. ECE {e:.3f}.')
    # abstention: 3-way unanimity
    abst = {}
    for fld in ('project', 'stance'):
        ps_ = pids if fld == 'project' else [p for p in pids if CONS[p]['project'] in RELEVANT]
        un = [p for p in ps_ if len({A[n][p][fld] for n in names}) == 1]
        abst[fld] = {'n': len(ps_), 'unanimous': len(un), 'coverage': M.wilson(len(un), len(ps_))}
        md(f'- Abstain unless all 3 agree, {fld}: coverage {len(un)}/{len(ps_)} = {ci(abst[fld]["coverage"])}. '
           'Accuracy on the covered posts needs human labels (section 8).')
    R['vote_calibration_ai_proxy'] = calib
    R['abstention_ai'] = abst
    md('')

    # ---------- 7. Prevalence correction on real data (AI proxy) ----------
    md('## 7. Prevalence correction on real pilot data (proxy truth)')
    md('')
    md('Set-up with a known answer: pretend haiku is the deployed model and sonnet_a is the truth. '
       'Split the relevant posts at random: half is the "gold set" (both labels known), half is "unlabelled" (only haiku used). '
       'We know sonnet_a on the unlabelled half, so we can see which estimate lands closer. Repeated over 200 random splits.')
    md('')
    rp = [p for p in pids if CONS[p]['project'] in RELEVANT]
    truth_lab = {p: stance4(A['sonnet_a'][p]['stance']) for p in rp}
    model_lab = {p: stance4(A['haiku'][p]['stance']) if A['haiku'][p]['project'] in RELEVANT else 'other' for p in rp}
    errs = defaultdict(list)
    cover = defaultdict(list)
    rng = random.Random(7)
    first = None
    for it in range(200):
        sh = rp[:]
        rng.shuffle(sh)
        g, u = sh[:len(sh) // 2], sh[len(sh) // 2:]
        gr, gp, up = [truth_lab[p] for p in g], [model_lab[p] for p in g], [model_lab[p] for p in u]
        true_u = PV.cc([truth_lab[p] for p in u], STANCE4)
        ccv = PV.cc(up, STANCE4)
        accv, info = PV.acc(gr, gp, up, STANCE4)
        ppiv = PV.ppi(gr, gp, up, STANCE4)
        for l in STANCE4:
            errs['cc'].append(abs(ccv[l] - true_u[l]))
            errs['acc'].append(abs(accv[l] - true_u[l]))
            errs['ppi'].append(abs(ppiv[l]['value'] - true_u[l]))
            cover['ppi'].append(ppiv[l]['lo'] <= true_u[l] <= ppiv[l]['hi'])
        if it == 0:
            accb, _ = PV.acc_bootstrap(gr, gp, up, STANCE4, B=300, seed=1)
            first = {'n_gold': len(g), 'n_unlabelled': len(u), 'truth': true_u, 'cc': ccv, 'acc': accb, 'ppi': ppiv,
                     'cond_M': info['cond_M']}
    pv = {'first_split': first, 'mean_abs_error': {k: float(np.mean(v)) for k, v in errs.items()},
          'ppi_interval_coverage': float(np.mean(cover['ppi'])), 'splits': 200}
    R['prevalence_proxy'] = pv
    md('| Class | Proxy truth | Raw count (CC) | ACC [95% CI] | PPI [95% CI] |')
    md('|---|---|---|---|---|')
    for l in STANCE4:
        md(f'| {l} | {first["truth"][l]:.2f} | {first["cc"][l]:.2f} | {ci(first["acc"][l])} | {ci(first["ppi"][l])} |')
    md('')
    md(f'Over 200 splits, mean absolute error per class share: CC {pv["mean_abs_error"]["cc"]:.3f}, '
       f'ACC {pv["mean_abs_error"]["acc"]:.3f}, PPI {pv["mean_abs_error"]["ppi"]:.3f}. '
       f'PPI 95% intervals contained the proxy truth {pv["ppi_interval_coverage"]:.0%} of the time.')
    md('')
    md('Read this carefully: the two models disagree little, so the correction has little to fix here. '
       'It shows the code runs on real data and that the intervals are honest; the real test is with human gold.')
    md('')

    # ---------- 8. Humans ----------
    md('## 8. Human labels')
    md('')
    hum = {}
    if not H:
        md('**Pending.** No human labels in `eval/gold/` yet. Start the label tool (see `eval/README.md`).')
        md('')
    else:
        for n, L in H.items():
            md(f'- {n}: {len(L)} posts labelled')
        md('')
        hh = {}
        for x, y in combinations(sorted(H), 2):
            c = sorted(set(H[x]) & set(H[y]))
            d = {'n': len(c)}
            for f in ('project', 'stance', 'voice'):
                d[f] = M.bootstrap(kappa_stat, [H[x][p][f] for p in c], [H[y][p][f] for p in c], B=B)
            both_rel = [p for p in c if H[x][p]['project'] in RELEVANT and H[y][p]['project'] in RELEVANT]
            d['stance_relevant'] = M.bootstrap(kappa_stat, [stance4(H[x][p]['stance']) for p in both_rel],
                                               [stance4(H[y][p]['stance']) for p in both_rel], B=B)
            hh[f'{x}__{y}'] = d
            md(f'**Human vs human, {x} vs {y}** (n = {d["n"]}): project kappa {ci(d["project"])}, '
               f'stance kappa on relevant (4 classes) {ci(d["stance_relevant"])} (n {d["stance_relevant"]["n"]}), '
               f'voice kappa {ci(d["voice"])}.')
        hum['human_vs_human'] = hh
        md('')
        # gold = adjudicated, else agreement, else single label
        gold, dis = {}, []
        allp = sorted(set().union(*[set(L) for L in H.values()]))
        for p in allp:
            rs = [H[n][p] for n in H if p in H[n]]
            r = {}
            for f in ('project', 'stance', 'voice'):
                vals = {x.get(f) for x in rs}
                r[f] = vals.pop() if len(vals) == 1 else None
            if ADJ and p in ADJ:
                gold[p] = dict(ADJ[p], source='adjudicated')
            elif r['project'] and r['stance']:
                gold[p] = dict(r, source='agreed' if len(rs) > 1 else 'single')
            else:
                dis.append((p, rs))
        with open(os.path.join(RESULTS, 'human_disagreements.csv'), 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(['pid', 'text'] + [f'{n}_{fld}' for n in sorted(H) for fld in ('project', 'stance', 'voice')] +
                       ['project', 'stance', 'voice', 'arguments'])
            for p, _ in dis:
                w.writerow([p, S.get(p, {}).get('text', '')] +
                           [H[n].get(p, {}).get(fld, '') for n in sorted(H) for fld in ('project', 'stance', 'voice')] +
                           ['', '', '', ''])
        src = Counter(g['source'] for g in gold.values())
        hum['gold'] = {'n': len(gold), 'by_source': dict(src), 'unresolved_disagreements': len(dis)}
        md(f'Gold set: {len(gold)} posts ({dict(src)}); {len(dis)} human disagreements unresolved, written to '
           '`eval/results/human_disagreements.csv`. Fill the last 4 columns together, save as '
           '`eval/gold/labels_adjudicated.csv` (columns pid, project, stance, voice, arguments) and re-run.')
        if src.get('agreed') and not ADJ:
            md('**Warning:** without adjudication the gold set keeps only posts where the humans agree. Those are the '
               'easier posts, so the AI-vs-human numbers below are optimistic until the disagreements are adjudicated.')
        md('')
        gp = [p for p in gold if p in S]
        hum['gold_in_pilot_sample'] = len(gp)
        vs = {}
        sets = {n: A[n] for n in names}
        sets['ai_majority_3'] = CONS
        sets.update(extra)
        for n, L in sets.items():
            c = compare(gold, L, sorted(gold), B)
            vs[n] = c
            md_compare(f'{n} vs human gold', c)
        kbh = compare(gold, KWB, gp, B)
        vs['keyword_baseline'] = {k: v for k, v in kbh.items() if k.startswith(('n', 'project', 'relevance'))}
        md(f'Keyword baseline vs human gold: relevance precision {ci(kbh["relevance_precision"])}, '
           f'recall {ci(kbh["relevance_recall"])} (n {kbh["n"]}).')
        md('')
        hum['vs_gold'] = vs
        # vendor vs human
        hs = [p for p in gp if gold[p]['project'] in RELEVANT and S[p]['vendor_sentiment'] in mp]
        kk = sum(mp[S[p]['vendor_sentiment']] == gold[p]['stance'] for p in hs)
        hum['vendor_vs_human'] = M.wilson(kk, len(hs))
        md(f'Vendor sentiment as stance vs human gold: {kk}/{len(hs)} = {ci(hum["vendor_vs_human"])} (Wilson).')
        md('')
        # vote share calibration + abstention vs human
        cal = {}
        for fld in ('project', 'stance'):
            conf, corr, una = [], [], []
            for p in gp:
                if fld == 'stance' and gold[p]['project'] not in RELEVANT:
                    continue
                lab, share = CAL.vote_confidence([A[n][p][fld] for n in names])
                conf.append(share)
                corr.append(lab == gold[p][fld])
            if conf:
                e, rows = CAL.ece_by_levels(conf, corr)
                cov = [c == 1.0 for c in conf]
                acc_cov = [k for k, c in zip(corr, cov) if c]
                cal[fld] = {'ece': e, 'levels': rows, 'coverage_unanimous': M.wilson(sum(cov), len(cov)),
                            'accuracy_when_unanimous': M.wilson(sum(acc_cov), len(acc_cov)),
                            'accuracy_all': M.wilson(sum(corr), len(corr))}
                md(f'- {fld}, 3-AI vote vs human: ' + '; '.join(f'vote share {r["conf"]:.2f}: right {r["accuracy"]:.2f} '
                                                                f'(n {r["n"]})' for r in rows) +
                   f'. ECE {e:.3f}. Abstain unless unanimous: coverage {ci(cal[fld]["coverage_unanimous"])}, '
                   f'accuracy on covered {ci(cal[fld]["accuracy_when_unanimous"])} vs all {ci(cal[fld]["accuracy_all"])}.')
        hum['vote_calibration_vs_human'] = cal
        md('')
        # human labels on the regression suite = does the suite match human judgement?
        cases = load_cases()
        for n, L in H.items():
            out, summ = check_model(cases, L)
            hum.setdefault('suite_vs_humans', {})[n] = {'summary': summ, 'fails': [r for r in out if r['status'] == 'fail']}
            md(f'- Regression suite checked against {n}\'s own labels: '
               + ', '.join(f'{k} {v["pass"]}/{v["pass"] + v["fail"]}' for k, v in summ.items() if v['pass'] + v['fail']))
        md('')
        # prevalence-corrected stance shares for each extra (pipeline) model: M from gold, q from all its predictions
        prev = {}
        for n_, L in extra.items():
            g_ = [p for p in gold if p in L and gold[p]['project'] in RELEVANT and gold[p].get('stance')]
            if len(g_) < 30:
                prev[n_] = {'status': f'only {len(g_)} gold posts overlap; need 30+'}
                continue
            gr = [stance4(gold[p]['stance']) for p in g_]
            gpred = [stance4(L[p]['stance']) if L[p]['project'] in RELEVANT and L[p].get('stance') else 'other' for p in g_]
            prev[n_] = {'n_gold': len(g_)}
            md(f'Prevalence-corrected stance shares, {n_} (M from {len(g_)} gold posts; ACC assumes P(pred|true) is the same '
               'off the gold set; PPI also assumes the gold set is a random sample):')
            md('')
            md('| Project | n predicted | Class | Raw (CC) | ACC [95% CI] | PPI [95% CI] |')
            md('|---|---|---|---|---|---|')
            for proj in sorted(RELEVANT):
                up = [stance4(r['stance']) for r in L.values() if r['project'] == proj and r.get('stance')]
                if len(up) < 10:
                    continue
                ccv = PV.cc(up, STANCE4)
                accb, info = PV.acc_bootstrap(gr, gpred, up, STANCE4, B=min(B, 500), seed=2)
                ppiv = PV.ppi(gr, gpred, up, STANCE4)
                prev[n_][proj] = {'n': len(up), 'cc': ccv, 'acc': accb, 'ppi': ppiv, 'cond_M': info['cond_M']}
                for l in ('support', 'oppose'):
                    md(f'| {proj} | {len(up)} | {l} | {ccv[l]:.2f} | {ci(accb[l])} | {ci(ppiv[l])} |')
            md('')
        hum['prevalence_corrected'] = prev
        # Heilbronn census from human gold
        hn = [p for p in gold if gold[p]['project'] == 'heilbronn_cablecar']
        cz = [p for p in hn if gold[p].get('voice') == 'citizen']
        hum['heilbronn_human'] = {'n': len(hn), 'stance': dict(Counter(stance4(gold[p]['stance']) for p in hn)),
                                  'citizen_n': len(cz), 'citizen_stance': dict(Counter(stance4(gold[p]['stance']) for p in cz))}
        for lab in ('support', 'oppose'):
            hum['heilbronn_human'][f'citizen_{lab}_share'] = M.wilson(sum(stance4(gold[p]['stance']) == lab for p in cz), len(cz))
        md(f'Heilbronn posts in human gold: {len(hn)}, stance {hum["heilbronn_human"]["stance"]}. Citizen voices: '
           f'{len(cz)}, stance {hum["heilbronn_human"]["citizen_stance"]}, oppose share '
           f'{ci(hum["heilbronn_human"]["citizen_oppose_share"])} (Wilson).')
        md('')
    R['human'] = hum

    # ---------- 9. Regression suite ----------
    md('## 9. Falsification regression suite (`eval/tests/regression_cases.jsonl`)')
    md('')
    cases = load_cases()
    reg = {}
    sets = {n: A[n] for n in names}
    sets['ai_majority_3'] = CONS
    sets['keyword_baseline'] = KWB
    sets.update(extra)
    md('| Model | ' + ' | '.join(sorted({c['rule'] for c in cases})) + ' | failures |')
    md('|---' * (len({c['rule'] for c in cases}) + 2) + '|')
    for n, L in sets.items():
        out, summ = check_model(cases, L)
        fails = [r for r in out if r['status'] == 'fail']
        reg[n] = {'summary': summ, 'fails': fails}
        md(f'| {n} | ' + ' | '.join(f'{summ[r]["pass"]}/{summ[r]["pass"] + summ[r]["fail"]}'
                                    + (f' (+{summ[r]["missing"] + summ[r]["n/a"]} not checkable)' if summ[r]['missing'] + summ[r]['n/a'] else '')
                                    for r in sorted(summ)) + ' | ' + ('; '.join(f'{x["case_id"]}: {x["reason"]}' for x in fails) or 'none') + ' |')
    dd = check_dedup(cases, cluster)
    reg['reference_dedup'] = dd
    R['regression'] = reg
    md('')
    md(f'Reference dedup (5-word shingles, Jaccard 0.8): {sum(d["status"] == "pass" for d in dd)}/{len(dd)} cases pass.')
    md('')
    md('Cases were picked by Claude from the data while seeing the AI labels, so they are known hard spots, not a random '
       'sample. A pass rate here is not an accuracy. Humans confirm the expected labels via section 8.')
    md('')

    # ---------- 10. Sample size ----------
    md('## 10. Sample size: what n gives what interval')
    md('')
    tab = M.sample_size_table()
    R['sample_size'] = tab
    md('| n | p = 0.5: half-width / Wilson | p = 0.8 | p = 0.9 |')
    md('|---|---|---|---|')
    for r in tab:
        md(f'| {r["n"]} | ' + ' | '.join(f'+/-{r[k]["normal_half_width"]:.2f} / [{r[k]["wilson"][0]:.2f}, {r[k]["wilson"][1]:.2f}]'
                                         for k in ('p=0.5', 'p=0.8', 'p=0.9')) + ' |')
    md('')

    # ---------- summary for app/ (keys asked for in app/DATA_SCHEMA_PROPOSAL.md) and contract metrics rows ----------
    vsg = hum.get('vs_gold', {}).get('ai_majority_3')
    R['status'] = 'human_checked' if vsg else 'pending_human_labels'
    R['n_gold'] = hum.get('gold', {}).get('n', 0)
    if vsg and vsg.get('stance_n'):
        R['stance'] = {'reference': 'human_gold', 'n': vsg['stance_n'], 'agreement': vsg['stance_accuracy']['value'],
                       'kappa': vsg['stance_kappa']['value'], 'macro_f1': vsg['stance_macro_f1']['value'],
                       'ci': {k: [vsg[k]['lo'], vsg[k]['hi']] for k in ('stance_accuracy', 'stance_kappa', 'stance_macro_f1')}}
        R['relevance'] = {'reference': 'human_gold', 'n': vsg['n'], 'precision': vsg['relevance']['precision'],
                          'recall': vsg['relevance']['recall']}
    else:
        pk = [v['stance_relevant']['value'] for k_, v in R['ai_vs_ai'].items() if k_ != 'krippendorff_alpha']
        R['stance'] = {'reference': 'AI vs AI, pairwise kappa on posts both call relevant (no human labels yet)',
                       'kappa_range': [min(pk), max(pk)], 'agreement': None, 'kappa': None}
        R['relevance'] = {'reference': '3-AI consensus (no human labels yet)',
                          'keyword_precision': kb['relevance']['precision'], 'keyword_recall': kb['relevance']['recall'],
                          'precision': None, 'recall': None}
    R['by_project'] = {k: {'n': v['n'], 'counts': v['counts']} for k, v in shares.items()}
    now = R['generated']
    rows = []

    def row(mid, name, d, method, n=None, project=None, voice=None):
        if d is None or d.get('value') is None:
            return
        rows.append({'metric_id': mid, 'project': project, 'voice': voice, 'name': name, 'value': d['value'],
                     'ci_low': d.get('lo'), 'ci_high': d.get('hi'), 'n': n if n is not None else d.get('n'),
                     'method': method, 'source_run_ids': 'pilot_haiku;pilot_sonnet_a;pilot_sonnet_b', 'computed_at': now})
    for pair, d in R['ai_vs_ai'].items():
        if pair == 'krippendorff_alpha':
            continue
        row(f'agreement.ai_ai.{pair}.stance_relevant', f'Stance kappa {pair} (AI vs AI)', d['stance_relevant'], 'kappa')
        row(f'agreement.ai_ai.{pair}.project', f'Project kappa {pair} (AI vs AI)', d['project'], 'kappa')
    for f_, d in R['ai_vs_ai']['krippendorff_alpha'].items():
        row(f'agreement.ai_ai.alpha.{f_}', f'Krippendorff alpha {f_}, 3 AI labellers', d, 'bootstrap')
    row('baseline.keyword.precision', 'Keyword relevance precision vs 3-AI consensus', kb['relevance_precision'], 'bootstrap')
    row('baseline.keyword.recall', 'Keyword relevance recall vs 3-AI consensus', kb['relevance_recall'], 'bootstrap')
    row('vendor.match_stance', 'Vendor sentiment read as stance, match with consensus', vend['match'], 'wilson')
    for n_, c in hum.get('vs_gold', {}).items():
        if c.get('stance_macro_f1'):
            row(f'accuracy.human.{n_}.stance_macro_f1', f'Stance macro-F1, {n_} vs human gold', c['stance_macro_f1'], 'bootstrap', c['stance_n'])
            row(f'accuracy.human.{n_}.stance_kappa', f'Stance kappa, {n_} vs human gold', c['stance_kappa'], 'kappa', c['stance_n'])
        if c.get('relevance_precision'):
            row(f'accuracy.human.{n_}.relevance_precision', f'Relevance precision, {n_} vs human gold', c['relevance_precision'], 'bootstrap')
    for pair, d in hum.get('human_vs_human', {}).items():
        row(f'agreement.human_human.{pair}.stance_relevant', 'Stance kappa human vs human', d['stance_relevant'], 'kappa')
    R['metrics_rows'] = rows

    with open(os.path.join(RESULTS, 'metrics.json'), 'w', encoding='utf-8') as f:
        json.dump(R, f, ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
    with open(os.path.join(RESULTS, 'tables.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(MD) + '\n')
    print('\n'.join(MD))
    print(f'\nwrote {os.path.join(RESULTS, "metrics.json")} and tables.md ({R["status"]})')


if __name__ == '__main__':
    main()
