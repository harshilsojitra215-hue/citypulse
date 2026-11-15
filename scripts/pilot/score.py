"""Score labeler reliability for the cable-car pilot.

Usage (python -I -X utf8 score.py [options]):
  python -I -X utf8 score.py                      # all labels_*.jsonl in this folder (except labels_human)
  python -I -X utf8 score.py --dir DIR            # other folder (needs sample.jsonl or --sample)
  python -I -X utf8 score.py --gold labels_human.jsonl   # also score against human gold
  python -I -X utf8 score.py --human-csv human_review.csv  # convert filled CSV to labels_human.jsonl first

Label line: {"pid","project","stance","arguments":[...],"voice","evidence"}
Writes disagreements.csv and score_report.txt into --dir. No third-party packages.
"""
import argparse, csv, glob, json, os, re, sys
from collections import Counter, defaultdict
from itertools import combinations

FIELDS = ['project', 'stance', 'voice']
ARGS = ['cost', 'climate_environment', 'traffic_mobility', 'noise_privacy_overflight', 'cityscape_design',
        'safety_technology', 'ipai_who_benefits', 'process_participation', 'tourism_image', 'other']
RELEVANT = {'heilbronn_cablecar', 'bonn_cablecar', 'paris_c1', 'ipai'}
OUT = []


def say(s=''):
    OUT.append(s); print(s)


def load_jsonl(p):
    d = {}
    with open(p, encoding='utf-8') as f:
        for l in f:
            l = l.strip()
            if l:
                r = json.loads(l); d[r['pid']] = r
    return d


def norm(v):
    return str(v).strip().lower() if v not in (None, '') else None


def kappa(a, b):
    """Cohen's kappa for two aligned lists of labels"""
    n = len(a)
    if n == 0: return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if pe == 1: return None  # undefined (no variation)
    return (po - pe) / (1 - pe)


def krippendorff_nominal(units):
    """units: list of lists of labels (None dropped), one list per item. Nominal alpha."""
    units = [[v for v in u if v is not None] for u in units]
    units = [u for u in units if len(u) >= 2]
    if not units: return None
    o = Counter(); n = 0
    for u in units:
        m = len(u)
        for i, x in enumerate(u):
            for j, y in enumerate(u):
                if i != j: o[(x, y)] += 1 / (m - 1)
        n += m
    nc = Counter()
    for (x, y), v in o.items(): nc[x] += v
    do = sum(v for (x, y), v in o.items() if x != y)
    de = sum(nc[x] * nc[y] for x in nc for y in nc if x != y) / (n - 1)
    return 1 - do / de if de else 1.0


def fmt(x): return 'n/a' if x is None else f'{x:.2f}'


def args_set(r):
    a = r.get('arguments') or []
    if isinstance(a, str): a = re.split(r'[;,|]', a)
    return {norm(x) for x in a if norm(x)}


def majority(vals):
    c = Counter(v for v in vals if v is not None)
    if not c: return None
    (top, n), *rest = c.most_common()
    if rest and rest[0][1] == n: return 'TIE'
    return top


def human_csv_to_jsonl(csv_path, out_path):
    n = 0
    with open(csv_path, encoding='utf-8-sig', newline='') as f, open(out_path, 'w', encoding='utf-8') as g:
        for r in csv.DictReader(f):
            if not (r.get('project') or '').strip(): continue
            a = [x.strip() for x in re.split(r'[;,|]', r.get('arguments') or '') if x.strip()]
            g.write(json.dumps({'pid': r['pid'], 'project': r['project'].strip(), 'stance': (r.get('stance') or '').strip(),
                                'arguments': a, 'voice': (r.get('voice') or '').strip(),
                                'evidence': (r.get('evidence') or '').strip()}, ensure_ascii=False) + '\n')
            n += 1
    print(f'wrote {out_path}: {n} human labels')


# Simple keyword baseline: "does a Seilbahn-type word occur near a project word"
KW = r'seilbahn|gondel|kabinenbahn|cable car|téléphérique|telepherique|câble|schwebebahn'
PROJ_KW = {'heilbronn_cablecar': r'heilbronn', 'bonn_cablecar': r'bonn|venusberg', 'paris_c1': r'c1\b|créteil|creteil|paris|val-de-marne',
           'ipai': r'\bipai\b|ki-park|innovation park'}


def baseline(text):
    t = text.lower()
    if re.search(r'\bipai\b|ki-park|innovation park', t): ipai = True
    else: ipai = False
    found = []
    for m in re.finditer(KW, t):
        seg = t[max(0, m.start() - 300):m.end() + 300]
        for p in ('heilbronn_cablecar', 'bonn_cablecar', 'paris_c1'):
            if re.search(PROJ_KW[p], seg): found.append(p)
    if found: return Counter(found).most_common(1)[0][0]
    return 'ipai' if ipai else 'irrelevant'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument('--sample', default=None)
    ap.add_argument('--gold', default=None, help='human gold file (default: labels_human.jsonl if present)')
    ap.add_argument('--human-csv', default=None)
    a = ap.parse_args()
    D = a.dir
    if a.human_csv:
        human_csv_to_jsonl(os.path.join(D, a.human_csv) if not os.path.isabs(a.human_csv) else a.human_csv,
                           os.path.join(D, 'labels_human.jsonl'))
    gp = a.gold or os.path.join(D, 'labels_human.jsonl')
    gp = gp if os.path.isabs(gp) or os.path.exists(gp) else os.path.join(D, gp)
    gold = load_jsonl(gp) if os.path.exists(gp) else None
    sp = a.sample or os.path.join(D, 'sample.jsonl')
    S = load_jsonl(sp)
    files = sorted(f for f in glob.glob(os.path.join(D, 'labels_*.jsonl')) if os.path.basename(f) != 'labels_human.jsonl'
                   and os.path.abspath(f) != os.path.abspath(gp))
    if len(files) < 1:
        sys.exit('no labels_<name>.jsonl found')
    L = {re.sub(r'^labels_|\.jsonl$', '', os.path.basename(f)): load_jsonl(f) for f in files}
    names = sorted(L)
    say(f'Labelers: {names}  | sample: {len(S)} posts | gold: {"yes (%d)" % len(gold) if gold else "no"}')
    for n in names: say(f'  {n}: {len(L[n])} labelled, {len(set(L[n]) - set(S))} pids not in sample')
    strat = lambda pid: S.get(pid, {}).get('project_hint', '?').split('_')[0]

    # 1. pairwise agreement
    say('\n== 1. Pairwise agreement (per field) ==')
    if len(names) < 2:
        say('only one labeler: skipping pairwise')
    for x, y in combinations(names, 2):
        common = sorted(set(L[x]) & set(L[y]))
        say(f'-- {x} vs {y} (n={len(common)})')
        for fld in FIELDS:
            va = [norm(L[x][p].get(fld)) for p in common]; vb = [norm(L[y][p].get(fld)) for p in common]
            ag = sum(i == j for i, j in zip(va, vb)) / max(1, len(common))
            say(f'   {fld:8s} agreement {ag:.2f}  kappa {fmt(kappa(va, vb))}')
        # relevance as a binary field
        ra = [L[x][p].get('project') in RELEVANT for p in common]; rb = [L[y][p].get('project') in RELEVANT for p in common]
        say(f'   relevant(4 projects) agreement {sum(i == j for i, j in zip(ra, rb)) / max(1, len(common)):.2f}  kappa {fmt(kappa(ra, rb))}')
        # arguments: per-code kappa + mean Jaccard
        js = []
        for p in common:
            u = args_set(L[x][p]) | args_set(L[y][p])
            js.append(1.0 if not u else len(args_set(L[x][p]) & args_set(L[y][p])) / len(u))
        say(f'   arguments mean Jaccard {sum(js) / max(1, len(js)):.2f}; per-code kappa: ' + ', '.join(
            f'{c}={fmt(kappa([c in args_set(L[x][p]) for p in common], [c in args_set(L[y][p]) for p in common]))}' for c in ARGS))
    if len(names) >= 2:
        say('\nKrippendorff alpha (nominal, all labelers)')
        pids = sorted(set.union(*[set(L[n]) for n in names]))
        for fld in FIELDS:
            say(f'   {fld:8s} {fmt(krippendorff_nominal([[norm(L[n][p].get(fld)) if p in L[n] else None for n in names] for p in pids]))}')

    # consensus
    pids_all = sorted(set.union(*[set(L[n]) for n in names]))
    cons = {}
    for p in pids_all:
        rs = [L[n][p] for n in names if p in L[n]]
        c = {f: majority([norm(r.get(f)) for r in rs]) for f in FIELDS}
        c['n'] = len(rs)
        cs = Counter(x for r in rs for x in args_set(r))
        c['arguments'] = {k for k, v in cs.items() if v > len(rs) / 2}
        cons[p] = c
    ties = sum(1 for c in cons.values() if 'TIE' in (c['project'], c['stance']))
    say(f'\nConsensus = majority over {len(names)} labelers; project/stance ties (excluded below): {ties}')

    # 2. baseline relevance vs consensus
    def prf(pairs):
        tp = sum(1 for g, p in pairs if g and p); fp = sum(1 for g, p in pairs if not g and p)
        fn = sum(1 for g, p in pairs if g and not p); tn = sum(1 for g, p in pairs if not g and not p)
        pr = tp / (tp + fp) if tp + fp else None; rc = tp / (tp + fn) if tp + fn else None
        return tp, fp, fn, tn, pr, rc
    say('\n== 2. Keyword baseline vs label consensus (relevance to the 4 projects) ==')
    pairs = [(cons[p]['project'] in RELEVANT, baseline(S[p]['text']) in RELEVANT) for p in cons
             if p in S and cons[p]['project'] not in (None, 'TIE')]
    tp, fp, fn, tn, pr, rc = prf(pairs)
    say(f'n={len(pairs)}  TP={tp} FP={fp} FN={fn} TN={tn}  precision {fmt(pr)}  recall {fmt(rc)}')
    ok = [(cons[p]['project'], baseline(S[p]['text'])) for p in cons if p in S and cons[p]['project'] in RELEVANT]
    say(f'baseline picks the right project among truly relevant posts: {sum(g == b for g, b in ok)}/{len(ok)}')

    # 3. vendor sentiment vs consensus stance
    say('\n== 3. Vendor sentiment vs consensus stance (relevant posts only) ==')
    rel = [p for p in cons if p in S and cons[p]['project'] in RELEVANT and cons[p]['stance'] not in (None, 'TIE')]
    stances = ['support', 'oppose', 'neutral_informative', 'mixed', 'unclear']
    sent_lab = {1: 'pos(1)', 0: 'neu(0)', -1: 'neg(-1)', -99: 'unscored(-99)'}
    tab = defaultdict(Counter)
    for p in rel: tab[sent_lab.get(S[p]['vendor_sentiment'], str(S[p]['vendor_sentiment']))][cons[p]['stance']] += 1
    say('sentiment \\ stance      ' + ''.join(f'{s[:9]:>11s}' for s in stances) + '      total')
    for k in sent_lab.values():
        if k in tab: say(f'{k:20s}' + ''.join(f'{tab[k][s]:11d}' for s in stances) + f'{sum(tab[k].values()):11d}')
    neg = [p for p in rel if S[p]['vendor_sentiment'] == -1]
    pos = [p for p in rel if S[p]['vendor_sentiment'] == 1]
    say(f'negative sentiment with support stance: {sum(cons[p]["stance"] == "support" for p in neg)}/{len(neg)}')
    say(f'positive sentiment with oppose stance:  {sum(cons[p]["stance"] == "oppose" for p in pos)}/{len(pos)}')
    say(f'unscored (-99) among relevant posts: {sum(S[p]["vendor_sentiment"] == -99 for p in rel)}/{len(rel)}')
    # crude mapping agreement: pos->support, neg->oppose, 0->neutral on posts with a polar/neutral consensus
    mp = {1: 'support', -1: 'oppose', 0: 'neutral_informative'}
    sc = [p for p in rel if S[p]['vendor_sentiment'] in mp]
    say(f'vendor-as-stance (1=support, -1=oppose, 0=neutral) matches consensus: {sum(mp[S[p]["vendor_sentiment"]] == cons[p]["stance"] for p in sc)}/{len(sc)}')

    # 4. per-stratum disagreement
    say('\n== 4. Per-stratum disagreement (share of posts where labelers are not unanimous) ==')
    by = defaultdict(lambda: [0, Counter()])
    for p in cons:
        rs = [L[n][p] for n in names if p in L[n]]
        if len(rs) < 2: continue
        s = S[p]['project_hint'] if p in S else '?'
        by[s][0] += 1
        for f in FIELDS:
            if len({norm(r.get(f)) for r in rs}) > 1: by[s][1][f] += 1
        if len({frozenset(args_set(r)) for r in rs}) > 1: by[s][1]['arguments'] += 1
    say(f'{"stratum":24s}{"n":>4s}' + ''.join(f'{f:>11s}' for f in FIELDS + ['arguments']))
    for s in sorted(by):
        n, c = by[s]
        say(f'{s:24s}{n:4d}' + ''.join(f'{c[f] / n:11.2f}' for f in FIELDS + ['arguments']))

    # disagreements.csv
    dpath = os.path.join(D, 'disagreements.csv'); nd = 0
    with open(dpath, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['pid', 'stratum', 'fields_in_disagreement', 'vendor_sentiment', 'text'] +
                   [f'{n}_{c}' for n in names for c in ['project', 'stance', 'voice', 'arguments']] +
                   (['gold_project', 'gold_stance', 'gold_voice'] if gold else []))
        for p in sorted(cons):
            rs = {n: L[n][p] for n in names if p in L[n]}
            if len(rs) < 2: continue
            dis = [f for f in FIELDS if len({norm(r.get(f)) for r in rs.values()}) > 1]
            if len({frozenset(args_set(r)) for r in rs.values()}) > 1: dis.append('arguments')
            if not dis: continue
            nd += 1
            row = [p, S.get(p, {}).get('project_hint', '?'), '+'.join(dis), S.get(p, {}).get('vendor_sentiment', ''),
                   S.get(p, {}).get('text', '').replace('\n', ' ')]
            for n in names:
                r = rs.get(n, {})
                row += [r.get('project', ''), r.get('stance', ''), r.get('voice', ''), ';'.join(sorted(args_set(r)))]
            if gold:
                g = gold.get(p, {}); row += [g.get('project', ''), g.get('stance', ''), g.get('voice', '')]
            w.writerow(row)
    say(f'\nwrote {dpath}: {nd} posts with at least one disagreement')

    # 5. gold mode
    if gold:
        say('\n== 5. Against human gold (labels_human.jsonl) ==')
        gp_ = [p for p in gold if p in S]
        say(f'gold posts in sample: {len(gp_)}')
        for n in names + ['consensus']:
            if n == 'consensus':
                pred = {p: cons[p] for p in gp_ if p in cons}
            else:
                pred = {p: {f: norm(L[n][p].get(f)) for f in FIELDS} for p in gp_ if p in L[n]}
            c = [p for p in pred if p in gold]
            if not c: continue
            line = []
            for f in FIELDS:
                va = [norm(gold[p].get(f)) for p in c]; vb = [pred[p][f] for p in c]
                line.append(f'{f} acc {sum(i == j for i, j in zip(va, vb)) / len(c):.2f} k {fmt(kappa(va, vb))}')
            say(f'  {n:12s} n={len(c)}  ' + ' | '.join(line))
        c = [p for p in gp_ if norm(gold[p].get('project'))]
        # baseline and vendor vs gold
        pr_ = [(norm(gold[p]['project']) in RELEVANT, baseline(S[p]['text']) in RELEVANT) for p in c]
        tp, fp, fn, tn, pr, rc = prf(pr_)
        say(f'  keyword baseline relevance vs gold: precision {fmt(pr)} recall {fmt(rc)} (TP={tp} FP={fp} FN={fn} TN={tn})')
        sc = [p for p in c if norm(gold[p]['project']) in RELEVANT and S[p]['vendor_sentiment'] in mp]
        say(f'  vendor-as-stance matches gold: {sum(mp[S[p]["vendor_sentiment"]] == norm(gold[p].get("stance")) for p in sc)}/{len(sc)}')
        negs = [p for p in sc if S[p]['vendor_sentiment'] == -1]
        say(f'  gold: negative vendor sentiment with support stance: {sum(norm(gold[p].get("stance")) == "support" for p in negs)}/{len(negs)}')
        # evidence quote length check
        long = [p for n in names for p, r in L[n].items() if len((r.get('evidence') or '').split()) > 15]
        say(f'  evidence quotes longer than 15 words (all labelers): {len(long)}')

    with open(os.path.join(D, 'score_report.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(OUT) + '\n')


if __name__ == '__main__':
    main()
