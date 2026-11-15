"""Score the edited-post test: does the labeller follow each edit the way the codebook rule says it must?

For edits of real posts, the expected label is computed from the SAME labeller's own label on the original
post (pilot labels_<run>.jsonl; for the majority, the 3-run majority). So no human truth is needed.
Run: python -I -X utf8 eval/robustness/score_edits.py
Writes eval/results/robustness.json and eval/results/robustness.md.
"""
import glob
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
from evallib.io import load_labels, load_pilot_ai, norm  # noqa: E402
from evallib.metrics import majority, wilson  # noqa: E402

RESULTS = os.path.join(EVAL, 'results')
DIRECTIONAL = {'E2_quoted_in_report', 'E3_cost_but', 'T1_flip_pair', 'T2_angry_support', 'T3_calm_oppose',
               'T4_council_report', 'T5_reported_opposition', 'T6_neutral_question', 'T7_mixed', 'T8_irrelevant_lift'}
PLAIN = {
    'E1_project_swap': 'Heilbronn and Bonn swapped in the text: project must swap, stance must stay',
    'E2_quoted_in_report': 'opinion post quoted inside a neutral news report: must become neutral',
    'E3_cost_but': 'support post + "good idea, but far too expensive": must become mixed',
    'E4_tone_caps': '"WICHTIG!!!" added: nothing may change',
    'E5_sidebar': 'link list naming Heilbronn appended: nothing may change',
    'E6_numbers': 'amounts changed (157 -> 164 Millionen): nothing may change',
    'T1_flip_pair': 'written pairs, one phrase flips for/against',
    'T2_angry_support': 'angry words but wants it built: support',
    'T3_calm_oppose': 'calm, friendly words but wants it stopped: oppose',
    'T4_council_report': 'report of a council decision: neutral',
    'T5_reported_opposition': 'news reports a group demanding a stop: neutral',
    'T6_neutral_question': 'neutral question ("where will cars park?"): neutral',
    'T7_mixed': 'idea good, cost too high: mixed',
    'T8_irrelevant_lift': 'ski or playground lift: irrelevant',
}


def load_runs():
    runs = defaultdict(dict)
    for f in glob.glob(os.path.join(HERE, 'labels', '*_batch*.jsonl')):
        name = re.sub(r'_batch\d+\.jsonl$', '', os.path.basename(f))
        runs[name].update(load_labels(f))
    return dict(runs)


def check(item, lab, own):
    """Return (pass_all, pass_stance, reason). own = this labeller's label on the seed post (or None)."""
    if lab is None:
        return None, None, 'missing'
    ok_all, ok_st, why = True, True, []
    for e in item['expect']:
        f = e.get('field', 'project')
        if e['type'] == 'is':
            good = lab.get(f) == e['value']
            exp = e['value']
        elif e['type'] == 'same_as_own':
            if own is None:
                return None, None, 'no seed label'
            good = lab.get(f) == own.get(f)
            exp = own.get(f)
        elif e['type'] == 'swap_project':
            if own is None or own.get('project') != e['from']:
                return None, None, 'seed label differs'
            good = lab.get('project') == e['to']
            exp = e['to']
        else:
            raise ValueError(e)
        if not good:
            ok_all = False
            why.append(f'{f}: got {lab.get(f)}, expected {exp}')
            if f == 'stance':
                ok_st = False
    return ok_all, ok_st, '; '.join(why)


def main():
    key = [json.loads(l) for l in open(os.path.join(HERE, '_answer_key', 'edits_key.jsonl'), encoding='utf-8')]
    runs = load_runs()
    if not runs:
        sys.exit('no labels in eval/robustness/labels/ yet')
    pilot = load_pilot_ai()
    names = sorted(runs)
    pids = [k['pid'] for k in key]
    maj = {p: {f: (lambda v: None if v == 'TIE' else v)(majority([runs[n].get(p, {}).get(f) for n in names]))
               for f in ('project', 'stance')} for p in pids if any(p in runs[n] for n in names)}
    pmaj = {p: {f: (lambda v: None if v == 'TIE' else v)(majority([pilot[n][p][f] for n in pilot]))
                for f in ('project', 'stance')} for p in pilot['haiku']}
    sets = {n: (runs[n], pilot.get(n, {})) for n in names}
    sets['majority_3'] = (maj, pmaj)
    out = {'n_items': len(key), 'runs': {n: len(runs[n]) for n in names}, 'by_model': {}}
    md = ['# Edited-post test (answers fixed by the edit)', '',
          f'{len(key)} items: edits of real pilot posts where all 3 AI labellers agreed, plus written templates. '
          'For real-post edits the expected label comes from the same labeller\'s own label on the original post plus '
          'one codebook rule. Blind labelling runs: ' + ', '.join(f'{n} ({len(runs[n])} labels)' for n in names) +
          '. Intervals: Wilson 95%.', '']
    for n, (L, own) in sets.items():
        fam = defaultdict(lambda: {'n': 0, 'ok': 0, 'ok_stance': 0, 'fails': []})
        for it in key:
            o = own.get(it['seed']) if it['seed'] else None
            a, s, why = check(it, L.get(it['pid']), o)
            if a is None:
                continue
            d = fam[it['family']]
            d['n'] += 1
            d['ok'] += a
            d['ok_stance'] += s
            if not a:
                d['fails'].append({'pid': it['pid'], 'seed': it['seed'], 'why': why})
        res = {}
        for f_, d in sorted(fam.items()):
            res[f_] = {'n': d['n'], 'pass': wilson(d['ok'], d['n']), 'stance_pass': wilson(d['ok_stance'], d['n']),
                       'fails': d['fails']}
        groups = {'directional (must change)': [f for f in res if f in DIRECTIONAL],
                  'invariance (must not change)': [f for f in res if f not in DIRECTIONAL]}
        for g, fs in groups.items():
            k_ = sum(fam[f]['ok'] for f in fs)
            n_ = sum(fam[f]['n'] for f in fs)
            res[g] = {'n': n_, 'pass': wilson(k_, n_)}
        k_ = sum(fam[f]['ok'] for f in fam)
        n_ = sum(fam[f]['n'] for f in fam)
        res['all'] = {'n': n_, 'pass': wilson(k_, n_)}
        out['by_model'][n] = res
    # table: families x models
    models = list(sets)
    md.append('| Test | What it checks | ' + ' | '.join(models) + ' |')
    md.append('|---' * (len(models) + 2) + '|')
    fams = sorted({f for m in models for f in out['by_model'][m] if f in PLAIN})

    def cell(d):
        p = d['pass']
        return f"{p['k']}/{p['n']} ({p['value']:.0%}, {p['lo']:.0%} to {p['hi']:.0%})" if p['n'] else 'n/a'
    for f_ in fams + ['directional (must change)', 'invariance (must not change)', 'all']:
        md.append(f'| {f_} | {PLAIN.get(f_, "")} | ' + ' | '.join(cell(out['by_model'][m][f_]) if f_ in out['by_model'][m] else 'n/a'
                                                                for m in models) + ' |')
    md += ['', '## Failures of the 3-run majority (what the system would publish)', '']
    for f_ in fams:
        for x in out['by_model']['majority_3'][f_]['fails']:
            md.append(f'- {f_} {x["pid"]} (seed {x["seed"]}): {x["why"]}')
    md += ['', 'Known test-design issues (found after scoring, kept visible): (1) E2 extends codebook stance rule 1, which '
           'names "a quote of a politician", to a long citizen opinion quoted inside a news item. The codebook does not '
           'say this case explicitly, so E2 failures show a codebook gap, not only model errors. (2) Some E1 swaps create '
           'impossible text (Bonn inside "Baden-Württembergs erste Nahverkehrs-Seilbahn", seeds P096, P116, P150), so a '
           'few haiku E1 misses are partly the edit\'s fault.', '',
           'Limits: the edits and templates were written by Claude with the codebook open, so they test whether the '
           'labeller follows the codebook rules, not whether the rules match how people read real posts. Edited text is '
           'cleaner than real language. Seeds are posts all 3 AI runs agreed on (easier posts).', '']
    os.makedirs(RESULTS, exist_ok=True)
    json.dump(out, open(os.path.join(RESULTS, 'robustness.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    open(os.path.join(RESULTS, 'robustness.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    print('\n'.join(md))


if __name__ == '__main__':
    main()
