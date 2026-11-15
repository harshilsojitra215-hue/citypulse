"""Edited-post test set: the right answer is fixed by the edit, not by a person or a model.

Two kinds of items:
1. Edits of real pilot posts where all three AI labellers agreed (seeds). The expected label after the edit is
   computed from the model's OWN label on the original post plus one codebook rule, so no human truth is needed:
     E1 project_swap     Heilbronn <-> Bonn in the text         project swaps, stance unchanged     (project definitions)
     E2 quoted_in_report opinion post quoted inside a neutral news report -> neutral_informative  (stance rule 1)
     E3 cost_but         support post + "the idea is good, but the cost is far too high" -> mixed (stance rule 5)
     E4 tone_caps        "WICHTIG!!!" prefix, "!!!" suffix          unchanged (stance is attitude, not mood)
     E5 sidebar          appended link list that names Heilbronn once   unchanged (section 1: passing mention)
     E6 numbers          every figure changed                       unchanged (a figure is not a position)
2. Written templates (DE for Heilbronn and Bonn, FR for Paris) whose label follows from one codebook rule each,
   including minimal flip pairs that differ in one phrase (for/against, build/stop).

Written by Claude (eval session); the expected labels are rule-forced and listed with the rule. Run:
  python -I -X utf8 eval/robustness/build_edits.py
Writes eval/robustness/_answer_key/edits_key.jsonl (with answers) and batch_<k>_blind.jsonl (pid, date, media_type, text only).
"""
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from evallib.io import load_pilot_ai, load_sample, RELEVANT  # noqa: E402

SEED = 20261115
rng = random.Random(SEED)

SIDEBAR = ('\n\nWeitere Artikel: Wetter am Wochenende | Heilbronn: Baustelle in der Innenstadt | '
           'Sport: Ergebnisse vom Samstag | Newsletter abonnieren')
COST_BUT = {'de': ' Die Idee ist gut, aber die Kosten sind viel zu hoch.',
            'fr': " L'idée est bonne, mais le coût est beaucoup trop élevé."}
REPORT = {'de': ('Reaktionen im Netz: Die Pläne werden online diskutiert. Ein Nutzer schrieb dazu: „{t}“ '
                 'Die Stadt will die Planung im kommenden Jahr fortsetzen, wie ein Sprecher mitteilte.'),
          'fr': ('Réactions en ligne : le projet fait débat sur les réseaux. Un internaute a écrit : « {t} » '
                 "Selon un porte-parole, l'exploitation continue normalement.")}
PLACE_BLOCK = r'ipai|ki-park|innovationspark|neckar|venusberg|rhein|beuel|ramersdorf|regierungsviertel|experimenta|' \
              r'friedrichshall|löwenstein|stimme|mergel|südliches kreuz|hbf'


def lang(text):
    return 'fr' if re.search(r"\b(le|la|les|des|est|une|du)\b", text.lower()) and \
        not re.search(r'\b(der|die|und|das|nicht)\b', text.lower()) else 'de'


def short(text, n=420):
    return text if len(text) <= n else text[:n].rsplit(' ', 1)[0] + ' ...'


AMOUNT = (r'(\d+(?:[.,]\d+)?)(\s?(?:Millionen|Milliarden|Mio\.?|Mrd\.?|Euro|€|km|Kilometer|Meter|Prozent|%|Stationen|'
          r'Kabinen|Fahrgäste|Minuten|millions?|milliards?|euros?|kilomètres?|mètres|minutes|voyageurs|cabines|stations))')


def change_numbers(text):
    """Change only amounts (157 Millionen -> 164 Millionen), never dates, times or ids."""
    def f(m):
        v = m.group(1)
        new = str(int(v) + 7) if v.isdigit() else str(round(float(v.replace(',', '.')) + 7, 1)).replace('.', ',')
        return new + m.group(2)
    return re.sub(AMOUNT, f, text)


PAYWALL = r'Testabo|Zugang freischalten|Abo-Shop|Artikel merken'


def quotable(text):
    """Headline only for paywall stubs; otherwise the first 420 characters."""
    if re.search(PAYWALL, text):
        return text.split('\n')[0].strip()
    return short(text).replace('\n', ' ')


def swap_city(text):
    t = re.sub(r'Heilbronner', '§BNR§', text)
    t = re.sub(r'Heilbronn', '§BN§', t)
    t = re.sub(r'Bonner', 'Heilbronner', t)
    t = re.sub(r'\bBonn\b', 'Heilbronn', t)
    return t.replace('§BNR§', 'Bonner').replace('§BN§', 'Bonn')


def same(field):
    return {'type': 'same_as_own', 'field': field}


def main():
    S = load_sample()
    A = load_pilot_ai()
    names = sorted(A)
    seeds = {}
    for p in S:
        ls = [A[k][p] for k in names]
        if len({l['project'] for l in ls}) == 1 and len({l['stance'] for l in ls}) == 1 and ls[0]['project'] in RELEVANT:
            seeds[p] = ls[0]
    opinion = [p for p in seeds if seeds[p]['stance'] in ('support', 'oppose')]
    neutral = [p for p in seeds if seeds[p]['stance'] == 'neutral_informative']
    items = []

    def add(family, rule, text, expect, seed=None, media='News', date='2026-01-15'):
        items.append({'family': family, 'rule': rule, 'seed': seed, 'text': text, 'expect': expect,
                      'media_type': media, 'date': date})

    for p in sorted(seeds):
        s = S[p]
        t = s['text']
        lg = lang(t)
        st = seeds[p]
        # E1 project swap: Heilbronn or Bonn posts with no other place cue
        if st['project'] in ('heilbronn_cablecar', 'bonn_cablecar') and not re.search(PLACE_BLOCK, t, re.I) \
                and re.search(r'Heilbronn|\bBonn\b', t):
            to = 'bonn_cablecar' if st['project'] == 'heilbronn_cablecar' else 'heilbronn_cablecar'
            add('E1_project_swap', 'project definitions', swap_city(t),
                [{'type': 'swap_project', 'from': st['project'], 'to': to}, same('stance')], p, s['media_type'], s['date'])
        if p in opinion:
            add('E2_quoted_in_report', 'stance rule 1 (outlet only reports)', REPORT[lg].format(t=quotable(t)),
                [same('project'), {'type': 'is', 'field': 'stance', 'value': 'neutral_informative'}], p, 'News', s['date'])
            if st['stance'] == 'support':
                add('E3_cost_but', 'stance rule 5 (good idea, criticism of cost only)', t.rstrip() + COST_BUT[lg],
                    [same('project'), {'type': 'is', 'field': 'stance', 'value': 'mixed'}], p, s['media_type'], s['date'])
            add('E4_tone_caps', 'stance is attitude, not mood', 'WICHTIG!!! ' + t.rstrip() + ' !!!',
                [same('project'), same('stance')], p, s['media_type'], s['date'])
    for p in rng.sample(sorted(opinion), min(12, len(opinion))) + rng.sample(sorted(neutral), 18):
        s = S[p]
        add('E5_sidebar', 'section 1: a passing mention in a link list does not count', s['text'].rstrip() + SIDEBAR,
            [same('project'), same('stance')], p, s['media_type'], s['date'])
    numeric = [p for p in sorted(seeds) if change_numbers(S[p]['text']) != S[p]['text']]
    for p in rng.sample(numeric, min(20, len(numeric))):
        s = S[p]
        add('E6_numbers', 'a changed figure is not a changed position', change_numbers(s['text']),
            [same('project'), same('stance')], p, s['media_type'], s['date'])

    # ---------- templates (absolute expected labels) ----------
    def T(family, rule, text, project, stance, media):
        add(family, rule, text, [{'type': 'is', 'field': 'project', 'value': project},
                                 {'type': 'is', 'field': 'stance', 'value': stance}], None, media)
    de = [('Heilbronn', 'heilbronn_cablecar'), ('Bonn', 'bonn_cablecar')]
    for city, proj in de:
        # flip pairs: same sentence, one phrase changes the side
        pairs = [
            (f'Ich bin klar für die Seilbahn in {city}. Wir brauchen sie, damit die Busse entlastet werden.',
             f'Ich bin klar gegen die Seilbahn in {city}. Wir brauchen sie nicht, die Busse reichen völlig.'),
            (f'Baut endlich die Seilbahn in {city}! Das ist genau das, was die Stadt braucht.',
             f'Stoppt endlich die Seilbahn in {city}! Das ist genau das, was die Stadt nicht braucht.'),
            (f'Die Seilbahn in {city} ist jeden Euro wert, ein echter Gewinn für alle Pendler.',
             f'Die Seilbahn in {city} ist keinen Euro wert, ein echter Verlust für alle Steuerzahler.'),
        ]
        for i, (sup, opp) in enumerate(pairs):
            T(f'T1_flip_pair', 'stance definitions (support vs oppose)', sup, proj, 'support', 'YouTube Comments')
            T(f'T1_flip_pair', 'stance definitions (support vs oppose)', opp, proj, 'oppose', 'YouTube Comments')
        T('T2_angry_support', 'stance rule 2 (angry words, wants it built)',
          f'Der Bus ist jeden Morgen hoffnungslos überfüllt, es ist eine Zumutung. Wir brauchen die Seilbahn in {city} jetzt, nicht erst in zehn Jahren!',
          proj, 'support', 'Comments')
        T('T3_calm_oppose', 'stance rule 2 (calm words, wants it stopped)',
          f'Eine schöne Idee, die Seilbahn in {city}. Trotzdem sollte die Stadt das Projekt beenden und das Geld lieber in Ärzte und Schulen stecken.',
          proj, 'oppose', 'Comments')
        T('T4_council_report', 'stance rule 1 (report of a decision)',
          f'Der Gemeinderat in {city} hat am Donnerstag mit großer Mehrheit beschlossen, die Planung der Seilbahn fortzusetzen. Die Kosten werden auf einen dreistelligen Millionenbetrag geschätzt.',
          proj, 'neutral_informative', 'News')
        T('T5_reported_opposition', 'stance rule 1 (outlet reports a quote)',
          f'Die Fraktion im Rat fordert den Stopp der Seilbahn in {city}. „Das Projekt ist zu teuer“, sagte ihr Sprecher am Montag. Die Verwaltung will die Kritik prüfen.',
          proj, 'neutral_informative', 'News')
        T('T6_neutral_question', 'stance rule 4 (neutral question)',
          f'Wo sollen eigentlich die Autos parken, wenn die Seilbahn in {city} fertig ist? Weiß das jemand?',
          proj, 'neutral_informative', 'Comments')
        T('T7_mixed', 'stance rule 5 (idea good, cost not)',
          f'Grundsätzlich finde ich die Seilbahn in {city} eine gute Sache. Aber die Kosten laufen aus dem Ruder, so geht das nicht.',
          proj, 'mixed', 'Comments')
    fr = [
        ('T1_flip_pair', 'stance definitions (support vs oppose)', "Le téléphérique Câble C1 à Créteil, c'est une vraie réussite. Il faut le garder et en construire d'autres.", 'support', 'Comments'),
        ('T1_flip_pair', 'stance definitions (support vs oppose)', "Le téléphérique Câble C1 à Créteil, c'est un vrai échec. Il faut l'arrêter et ne plus en construire.", 'oppose', 'Comments'),
        ('T2_angry_support', 'stance rule 2 (angry words, wants it built)', "Ras-le-bol des bus bondés tous les matins ! Le Câble C1 est la seule bonne nouvelle depuis des années, qu'on en fasse d'autres !", 'support', 'Comments'),
        ('T3_calm_oppose', 'stance rule 2 (calm words, wants it stopped)', "Le Câble C1 est joli à regarder. Mais l'argent aurait été mieux utilisé pour les hôpitaux ; il faudrait arrêter ce genre de projet.", 'oppose', 'Comments'),
        ('T4_council_report', 'stance rule 1 (report of a decision)', "Île-de-France Mobilités a annoncé mardi que le Câble C1 transporte en moyenne plusieurs milliers de voyageurs par jour depuis son ouverture.", 'neutral_informative', 'News'),
        ('T5_reported_opposition', 'stance rule 1 (outlet reports a quote)', "Une association de riverains critique le Câble C1. « Les cabines passent au-dessus de nos jardins », a déclaré sa présidente. La région dit étudier la question.", 'neutral_informative', 'News'),
        ('T6_neutral_question', 'stance rule 4 (neutral question)', "Quelqu'un sait si le Câble C1 fonctionne quand il y a beaucoup de vent ?", 'neutral_informative', 'Comments'),
        ('T7_mixed', 'stance rule 5 (idea good, cost not)', "J'aime bien l'idée du Câble C1, mais le coût du projet est franchement excessif.", 'mixed', 'Comments'),
    ]
    for fam, rule, text, stance, media in fr:
        T(fam, rule, text, 'paris_c1', stance, media)
    for text in ['Die Seilbahn auf die Zugspitze fährt ab Montag wieder. Für Familien gibt es ermäßigte Tickets.',
                 'Auf dem neuen Spielplatz in Heilbronn-Böckingen gibt es eine lange Seilbahn für Kinder. Die Eltern sind begeistert.',
                 'Wegen Sturm stand die Seilbahn am Feldberg den ganzen Tag still. Skifahrer mussten warten.']:
        T('T8_irrelevant_lift', 'section 1 (ski, tourist, playground lifts are irrelevant)', text, 'irrelevant', 'unclear', 'News')

    rng.shuffle(items)
    for i, it in enumerate(items, 1):
        it['pid'] = f'E{i:03d}'
    with open(os.path.join(HERE, '_answer_key', 'edits_key.jsonl'), 'w', encoding='utf-8') as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + '\n')
    half = (len(items) + 1) // 2
    for k, chunk in enumerate([items[:half], items[half:]], 1):
        with open(os.path.join(HERE, f'batch_{k}_blind.jsonl'), 'w', encoding='utf-8') as f:
            for it in chunk:
                f.write(json.dumps({x: it[x] for x in ('pid', 'date', 'media_type', 'text')}, ensure_ascii=False) + '\n')
    from collections import Counter
    print(len(items), 'items', dict(sorted(Counter(i['family'] for i in items).items())))


if __name__ == '__main__':
    main()
