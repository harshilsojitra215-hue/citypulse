"""Shared pieces: config, project matching, polite HTTP, item, store.

Standard library plus PyYAML. Nothing here logs in, solves challenges, rotates agents or hides who we are.
"""
import datetime as dt
import hashlib
import html
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTC = dt.timezone.utc


# ---------------------------------------------------------------- config
def load_config(path=None):
    with open(path or os.path.join(ROOT, 'projects.yaml'), encoding='utf-8') as f:
        return yaml.safe_load(f)


NEAR = 100                                         # radar gate: cable word and place word at most this many characters apart
FRAG_SPLIT = re.compile(r'\s*(?:\.\.\.|\u2026|\n|\u2022|\*\*)\s*|(?<=[a-z\u00e4\u00f6\u00fc\u00df)"][.!?])\s+(?=[A-Z\u00c4\u00d6\u00dc0-9])')   # also sentence ends (not after a digit: '27. Juli')


class Project:
    def __init__(self, pid, cfg):
        self.id = pid
        self.cfg = cfg
        self.name = cfg['name']
        self.city = cfg['city']
        self.group = cfg.get('comparison_group')
        kw = cfg.get('keywords', {})
        self.keywords = [k for ks in kw.values() for k in ks]
        self.specific = cfg.get('specific', [])
        self.place_words = cfg.get('place_words', [])
        self.queries = cfg.get('queries', {})          # {lang: [q, ...]}
        self.hashtags = cfg.get('hashtags', [])
        self.oparl_terms = cfg.get('oparl_terms', [])
        self.negative_words = cfg.get('negative_words', [])      # block the generic keyword + place match (ski lifts, Alpine cable cars); a specific phrase still counts
        self._spec = self._rx(self.specific)
        self._kw = self._rx(self.keywords)
        self._place = self._rx(self.place_words)
        self._neg = self._rx(self.negative_words)

    @staticmethod
    def _rx(words):
        if not words:
            return None
        return re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(w) for w in words) + r')(?!\w)', re.I)

    def matches(self, text):
        """A specific phrase alone, or a generic keyword together with a place word."""
        if not text:
            return False
        if self._spec and self._spec.search(text):
            return True
        if self._neg and self._neg.search(text):
            return False
        return bool(self._kw and self._place and self._kw.search(text) and self._place.search(text))

    def relevance(self, title, snippet=''):
        """Radar gate on title + snippet: 'strong' | 'weak' | 'none'. Same word lists as matches(), stricter on where the words sit.
        strong: a specific phrase, or a cable word AND a place word in the SAME fragment of the text, at most NEAR characters apart
                (search snippets are glued together from separate page fragments joined by '...': two words in different fragments are not one sentence).
        weak:   only one of the two, or both but far apart / in different fragments.
        none:   neither, or a negative word (ski lift, Alps) without a specific phrase."""
        frags = [title or ''] + [f for f in FRAG_SPLIT.split(snippet or '') if f.strip()]
        if self._spec and any(self._spec.search(f) for f in frags):
            return 'strong'
        whole = ' '.join(frags)
        if self._neg and self._neg.search(whole):
            return 'none'
        if not (self._kw and self._place):
            return 'weak' if (self._kw and self._kw.search(whole)) or (self._place and self._place.search(whole)) else 'none'
        for f in frags:
            ks = [m.span() for m in self._kw.finditer(f)]
            ps = [m.span() for m in self._place.finditer(f)]
            if any(max(0, b0 - a1, a0 - b1) <= NEAR for a0, a1 in ks for b0, b1 in ps):
                return 'strong'
        return 'weak' if self._kw.search(whole) or self._place.search(whole) else 'none'

    def cable_word(self, text):
        """First generic or specific word of this project found in `text` (None if none): the word a site-scoped query must keep."""
        m = (self._kw and self._kw.search(text or '')) or (self._spec and self._spec.search(text or ''))
        return m.group(0) if m else None

    def site_query(self):
        """Query for site-scoped discovery: a quoted specific phrase that holds the cable word and the city ("Seilbahn Heilbronn")."""
        base = next((x for x in self.specific if self.city.lower()[:6] in x.lower() and self.cable_word(x)), None) \
            or (self.specific[0] if self.specific else '')
        return f'"{base}"' if base else ''

    def matches_terms(self, text, terms):
        return bool(text) and any(re.search(r'(?<!\w)' + re.escape(t), text, re.I) for t in terms)


def load_projects(cfg, only=None):
    return [Project(k, v) for k, v in cfg['projects'].items() if not only or k in only]


# ---------------------------------------------------------------- text helpers
def strip_html(s):
    s = html.unescape(s or '')
    s = re.sub(r'<(br|/p)\s*/?>', ' ', s, flags=re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def mask_handles(s):
    """Social text: replace @mentions so no handle is stored through the text."""
    return re.sub(r'(?<![\w/])@[\w.\-]+(?:@[\w.\-]+)?', '@[USER]', s or '')


FIRST_NAMES = frozenset('''
alexander andreas anna anne annika antje barbara bernd birgit björn bjoern brigitte carsten christian christina christoph claudia daniel david
dieter dirk eva florian frank franziska gabriele georg gerhard hans heike heinz helmut holger ingrid jan jana jens jessica joachim jochen johannes
jörg joerg jonas julia jürgen juergen karin karl katharina kerstin klaus lars laura lena lisa lukas manuel marco marcus maria marie marina markus
martin matthias melanie michael michaela monika nadine nicole niklas nils norbert oliver patrick paul peter petra philipp ralf rainer reinhard
renate robert sabine sandra sarah sebastian silke simon sonja stefan stefanie steffen susanne sven tanja thomas thorsten tim tobias tom ulrich
ulla ute uwe vera werner wolfgang harry
alain alexandre amélie amelie antoine arnaud audrey benoît benoit bernard camille catherine cédric cedric céline celine christophe claire
clément clement denis émilie emilie étienne etienne fabien florence françois francois frédéric frederic gérard gerard guillaume hélène helene
jacques jean jérôme jerome julien laurent léa lea louis lucas ludovic manon marc margaux mathieu maxime michel nathalie nicolas olivier pascal
patrice philippe pierre rémi remi romain sébastien sylvie thibault thierry valérie valerie vincent virginie xavier yann yves
ahmed ali ayse emre fatma hasan mehmet mustafa murat ozan zeynep john james mary jennifer emma sophie
timon adrian albert alessandro alexandra alina andrea angelika anja annette arthur astrid axel bastian beate benedikt benjamin bettina bianca bruno
carina carolin caroline cathrin charlotte christa christel christine conny constantin cornelia dagmar daniela dennis detlef dietmar dominik
doris edeltraud egon elena elias elisabeth elke ella emil emily erik erika ernst esther ewald fabian felix ferdinand finn frederik friedrich
fritz gabi gerd gisela gregor gudrun guido gunnar günter guenter günther gustav hannah hannelore harald hartmut heidi heiko heinrich helga
helene henrik henning herbert hermann hildegard horst hubert ilse ina inge ingo irene iris isabel isabell jakob jasmin jennifer jeremias
jessika johanna josef joseph judith jule julian justus kai karsten katja katrin kevin kim kirsten konrad konstantin kristin lea leon leonie
leni linda lina lothar louisa lucia ludwig luise luisa lutz maik malte mandy manfred manuela mareike mario marion marius marlene mathias
maximilian mia michel miriam mirjam moritz natalie nadja nina noah norman ole oskar otto pascal paula pauline rafael ralph regina reiner
rene rené richard rita robin roland rolf rosemarie rudolf ruth sabrina sascha silvia simone stephan stephanie susann svenja sylvia tamara
theo theresa thilo til till timo tina tino torsten ulf ulrike ursula valentin verena viktor viola walter waltraud wilhelm willi willy
wolfram yvonne
adèle agnès alice anaïs aurélie baptiste bastien caroline cécile chantal charles chloé clémence colette damien delphine didier dominique
édouard eric éric eugène fanny gaëlle geraldine géraldine gilles grégoire hugo inès isabelle jacqueline jeanne joël josé josiane karine
laetitia laure lionel lucie lucien marcel marianne mathilde mélanie mickaël muriel nadia noémie odile pauline raphaël régis roger sandrine
serge simone solène stéphane sylvain thomas timothée yannick yvette
abdul abdullah amir aylin burak cem deniz elif emine hakan hüseyin ibrahim kemal leyla mahmut mehdi merve mohamed mohammed muhammad omar
osman rachid samir selin serkan sinan tarek yasin youssef yusuf burim
aleksandra anastasia anastasiia bartek bartosz danuta dorota ewa gilmar irina joanna kasia katarzyna krzysztof magdalena marek marta
natalia olga piotr radoslawa tomasz vitan wojciech dmitri igor ivan sergei svetlana tatiana
alessandra antonio carlo chiara francesca giovanni giulia giuseppe luca lorenzo marco matteo paolo sara stefano
anthony brian chris christopher david emily george jack jessica kate kevin matthew michelle nick oliver rachel ryan sam sarah steve
'''.split())
_CAP = r"[A-ZÄÖÜÉÈÀ][\wäöüéèàçß]+"
_TOKEN = re.compile(r"(?<![\w-])" + _CAP + r"(?:-" + _CAP + r")?(?![\w-])")
_GAP = re.compile(r"\s+(?:(?:von|van|de|du|le|la|zu|der|dem)\s+){0,2}")


def _mask_names(s):
    toks = list(_TOKEN.finditer(s))
    out, last, i = [], 0, 0
    while i < len(toks) - 1:
        a, b = toks[i], toks[i + 1]
        if a.group(0).split('-')[0].lower() in FIRST_NAMES and _GAP.fullmatch(s[a.end():b.start()]) \
                and not _INSTITUTION.match(s, b.end()):
            out += [s[last:a.start()], '[USER]']
            last, i = b.end(), i + 2
            # longer names: "Abdul Matin Sheikh Maheen" (at most 2 more capitalised words, never a place or a sentence word)
            for _ in range(2):
                if i < len(toks) and re.fullmatch(r' ', s[last:toks[i].start()]) and toks[i].group(0).lower() not in _NOT_A_PERSON \
                        and toks[i].group(0).lower() not in _NOT_A_NAME_START:
                    last, i = toks[i].end(), i + 1
        else:
            i += 1
    s = ''.join(out) + s[last:]
    # a listed first name alone after a greeting: "Hallo Adrian!", "Merci Camille"
    return _GREETING.sub(lambda m: f'{m.group(1)} [USER]' if m.group(2).lower() in FIRST_NAMES else m.group(0), s)


# a name that is part of an institution's name stays: "Dieter Schwarz Stiftung", "Robert-Bosch-Krankenhaus", "Museum Ludwig"
_INSTITUTION = re.compile(r"[\s-]+(?:Stiftung|Foundation|Fondation|Krankenhaus\w*|Klinik\w*|Straße|Strasse|Platz|Allee|Schule|Gymnasium|"
                          r"Universität|Hochschule|Institut|Halle|Haus|Museum|Preis|Arena|Center|Centre|Zentrum|Park|Brücke|Weg|Ring|Campus|"
                          r"Gruppe|Group|GmbH|AG|Verlag|Realschule|Gesamtschule)(?![\wäöü])")
_GREETING = re.compile(r"\b(Hallo|Hello|Hi|Hey|Danke|Thanks|Thank you|Merci|Bonjour|Salut|Liebe|Lieber)\s+([A-ZÄÖÜÉ][\wäöüéèàçß]+)(?![\w-])")
_HANDLE = re.compile(r'(?<![\w/])@[\w.\-\\]+(?:@[\w.\-\\]+)?')
_EMAIL = re.compile(r'[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)*\.[A-Za-z]{2,}')
# "Timon Höfer and [USER]", "[USER] und Anna Weber": a name joined to an already masked name is a person too
_WITH_MASKED = re.compile(r"(?<![\w-])" + _CAP + r"(?:\s+" + _CAP + r"){1,2}(?=\s+(?:and|und|et|&)\s+\[USER\])|(?<=\[USER\] and )"
                          + _CAP + r"(?:\s+" + _CAP + r"){1,2}|(?<=\[USER\] und )" + _CAP + r"(?:\s+" + _CAP + r"){1,2}")
# an account name at the start of an Instagram caption: "xl2\_gmbh 🤖 XL2 Innovation Bites" (needs _ . or a digit to look like a handle)
_LEADING_HANDLE = re.compile(r"^(?=[a-z0-9_.\\]*[_.\d])[a-z0-9_.\\]{3,30}(?=\s)")
# comment threads in social snippets: "... 1w 1 View 1 reply Willy van der Linden Heel leuk ..." or "[...] Tan Ya Es sollen ..."
# The commenter's name stands right after a thread boundary (age stamp, reply counter, '[...]', 'Top fan'), so the first name-like
# words after each boundary are masked, but only in a snippet that is a comment thread (it has an age stamp or a reply counter).
_THREAD = re.compile(r'(?i)\bview (?:all )?\d+ repl|\btop fan\b|(?<![\w:])\d{1,2}[dwh] \d{1,4}\b|(?<![\w:])\d{1,2}w\b')
_BOUNDARY = r"(?:\[\.\.\.\]|(?i:view (?:all )?\d+ repl(?:y|ies)|top fan)|(?<![\w:])\d{1,2}[dwh](?: \d{1,4})?(?![\w:])|\bImage \d{1,3}:?)"
_NAME_W = r"(?:[A-ZÄÖÜÉÈÀÇŁŚŻ][\wäöüéèàçßłśżąęńó'’.-]*|van|von|der|den|dos|del|de|da|el|al|bin|ibn)(?![\w'’])"
_COMMENT_HEAD = re.compile(_BOUNDARY + r"(\s+)((?:[a-zäöü]{1,2}\s+(?=[A-Z]))?" + _NAME_W + r"(?:\s+" + _NAME_W + r"){0,3})")
# photo credits in video descriptions: "CC BY 4.0: Bundesverfassungsgericht Karlsruhe – Asmodea Oaktree; Das deutsche Eck – Flyerx."
_CREDIT = re.compile(r"(\s[–—]\s)([^;\[\]–—:]{2,40}?)(?=\s*;|\s*\[\.\.\.\]|\.(?:\s|$)|$)")
_NOT_A_NAME_START = frozenset('''
die der das des den dem ein eine es ich wir ihr sie er du man und aber oder doch ja nein genau warum wie was wenn weil wo wer
the a an i we you it this that why how what when yes no and but le la les un une je nous vous il elle on et mais oui non pourquoi
seilbahn heilbronn koblenz köln bonn paris wuppertal ipai câble cable bravo
'''.split())


def _comment_sub(m):
    words = m.group(2).split()
    if words[0].lower().strip("'’.") in _NOT_A_NAME_START or _is_place(m.group(2)):
        return m.group(0)
    return m.group(0)[:m.start(2) - m.start(0)] + '[USER]'


def _mask_comment_heads(s):
    return _COMMENT_HEAD.sub(_comment_sub, s) if _THREAD.search(s) else s


# tag lists: "[USER], [USER], Kristin Seyboth, [USER], Timo Gessmann, Dr. Benjamin [USER]" (a comma list that already holds a masked
# name is a list of people, so every name-like item in it is masked)
_TAG_ITEM = r"(?:(?:Dr|Prof|PhD)\.?\s+)*(?:\[USER\]|[A-ZÄÖÜÉ][\wäöüéèàçß'’-]+(?:\s+(?:\[USER\]|[A-ZÄÖÜÉ][\wäöüéèàçß'’-]+)){0,3})"
_TAG_LIST = re.compile(r"(?<![\w])" + _TAG_ITEM + r"(?:,\s*" + _TAG_ITEM + r"){2,}")


def _tag_sub(m):
    if '[USER]' not in m.group(0):
        return m.group(0)
    return re.sub(r'[^,]+', lambda x: (' ' if x.group(0).startswith(' ') else '') + '[USER]', m.group(0))


# bylines in news and official text: "von Frank Wittmer", "par Jean Dupont", "Autor: Anna Schmidt" (first name from the list)
_BYLINE = re.compile(r"\b(von|by|par|Von|By|Par|Autor(?:in)?:|Text:)\s+(" + _CAP + r")(\s+" + _CAP + r"(?:-" + _CAP + r")?)")
_PHOTO_BY = re.compile(r'(?i)\b(photo|video|reel|post)s? (?:by|from|von|de) [^(@\n|:]{1,60}?\s*(?:\(\s*@[\w.\-]+\s*\))?'
                       r'(?=\s*[|:\u2013\u00b7]|\s*-\s|$|\s*\.\.\.|\s+(?:on|am|le) (?:[A-Z][a-z]+ \d|\d))')
# social page headers from search snippets: "Reyad in Germany's Post Reyad in Germany Friday, ..." (owner, "'s post", owner again)
_PAGE_HEADER = re.compile(r"(?:^|(?<=\s))([^\s'\u2019][^'\u2019\n\u00b7|]{0,80}?)['\u2019]s [Pp]ost \1(?=\s)")
_OWNER_POST = re.compile(r"(?:^|(?<=[\s\]\u00b7|]))[^'\u2019\n\u00b7|\]\[]{1,60}?['\u2019]s [Pp]ost\b")
# search titles of profile pages: "Elisabeth Messner on Reels - Facebook", "#autumn #stuttgart | Jakob Maier - Facebook"
_PROFILE_TITLE = re.compile(r"(^|\|\s*)([^|#@\n]{2,60}?)(?: on Reels)? - (Facebook|Instagram|LinkedIn|TikTok|X|Threads|YouTube)\s*$")
# X display name glued to its handle: "So Janu@Janu2So Nov 13"
_GLUED_HANDLE = re.compile(r"(?:[A-ZÄÖÜÉ][\w'’.-]*\s+){0,3}[\w.'’-]*(?<=\w)@[A-Za-z0-9_\\]{2,}")
_PROFILE_PIC = re.compile(r"(?<![\w@])[\w.\-]{2,40}['\u2019]s profil(?:e picture|e|\u2026)?")
_AUTHOR_ON = re.compile(r'^(.{1,70}?) (on|sur|auf) (X|Instagram|Facebook|TikTok|Threads|LinkedIn|Reddit)\b')


# "<Name> shared this", "<Name>'s post", "<Name> hat geteilt": the words around the name give it away, so no name list is needed.
# At least two name words ('Burim Sopaj'), never a place, project or organisation word (stoplist below).
_NAME_SEQ = r"(?:" + _CAP + r"(?:-" + _CAP + r")?)(?:\s+(?:(?:von|van|de|du|le|la|zu|der|dem)\s+)?" + _CAP + r"(?:-" + _CAP + r")?){1,3}"
_ACTOR = re.compile(r"(?<![\w-])" + _NAME_SEQ + r"(?=\s+(?:shared|reposted|posted|liked) this(?=\s*[\]\)|.,:;·•–-]|\s*$|\s+(?:post|update|article|link)\b)"
                    r"|['’]s\s+(?:[Pp]ost|[Bb]eitrag|[Aa]ctivity|[Pp]rofile)\b|\s+(?:hat|haben)\s+(?:das\s+|einen\s+Beitrag\s+)?"
                    r"(?:geteilt|gepostet|kommentiert|repostet)\b|\s+a\s+(?:partagé|publié|commenté)\b)")
_NOT_A_PERSON = frozenset('''
heilbronn bonn paris koblenz köln koeln berlin hamburg münchen muenchen stuttgart wuppertal bochum herne ludwigshafen créteil creteil
seilbahn seilbahnen câble cable urbane stadt city ville gemeinderat rathaus mairie ipai neckar neckarturm group gmbh ag se kg ug sas sarl
university universität hochschule tum hhn swr stimme zeitung news verlag media innovation park partner team official offizielle
'''.split())


def _is_place(text):
    return any(w in _NOT_A_PERSON or w.endswith('stadt') for w in re.findall(r'[\wäöüéèàçß]+', text.lower()))


def _actor_sub(m):
    return m.group(0) if _is_place(m.group(0)) else '[USER]'
# page furniture that search snippets drag in: markdown residue, empty links, login and cookie prompts
_JUNK = [
    (re.compile(r'!\[[^\]]*\]\([^)\s]*\)'), ' '),                     # markdown image
    (re.compile(r'\[\s*\]\([^)\s]*\)'), ' '),                         # empty link (a link never contains spaces)
    (re.compile(r'\[\s*\]\(?'), ' '),                                 # empty link cut off by the snippet end
    (re.compile(r'\[([^\]]{1,200})\]\((?:https?:|/)[^)\s]*\)'), r'\1'), # markdown link -> its text
    (re.compile(r'(?m)(^|\s)#{1,6}\s+'), r'\1'),                      # markdown heading marks
    (re.compile(r'\*\*|__'), ''),                                     # bold marks
    (re.compile(r'(?i)\b(?:log ?in|sign ?in|sign ?up|create new account|forgot(?:ten)? (?:account|password)\??|join now|'
                r'accept (?:all )?cookies|cookie settings|skip to (?:main )?content|enable javascript|anmelden|registrieren|'
                r'zum inhalt springen|alle cookies akzeptieren|se connecter|s[\'’]inscrire|mot de passe oublié|'
                r'logáil isteach|dearmad déanta agat ar do chuntas\??|you are currently viewing|menü schließen|'
                r'cookie-einstellungen|cookie-instellingen|accepteer (?:analytics-)?cookies(?: om deze content te kunnen bekijken)?|(?:springe |direkt )?(?:zur|zum) (?:navigation|inhalt|playerleiste|fußzeile|suche)|'
                r'zurück zur startseite(?: der \w+)?)(?![\w-])[.?!:]?'), ' '),
    # image captions and alt texts: 'Image 3:', 'Image en Une:', 'May be an image of map, poster and text.'
    (re.compile(r'(?i)\bmay be an image of [^.·|]{0,120}\.?'), ' '),
    (re.compile(r'(?<![A-Z])Image(?: \d{1,3}| en [Uu]ne)(?!\d):?'), ' '),
    (re.compile(r'(?i)\bskip (?:to )?navigation\b'), ' '),
    # Wikipedia template code that full-text search returns: '"lieu inter2":{"wt":"..."}', '{{...}}', '[[a|b]]', "''"
    (re.compile(r'"[^"{}]{1,60}":\{"wt":"(?:[^"\\]|\\.)*"\},?'), ' '),
    (re.compile(r'\{\{[^{}]{0,400}\}\}'), ' '),
    (re.compile(r'\{\{[^{}]{0,400}\}\}'), ' '),                       # twice for one level of nesting
    (re.compile(r'\[\[(?:[^\]|]{0,120}\|)?([^\]]{0,120})\]\]'), r'\1'),
    (re.compile(r'\[https?://\S+ ([^\]]{1,200})\]'), r'\1'),
    (re.compile(r"''+"), ''),
    (re.compile(r'(?:^|\s)"\},?(?=\s|$)|\{"wt":"|\|\s*url=\S+'), ' '),
    # markdown tables: '| a | b |' cells to ' · ', '|---|---|' rows dropped
    (re.compile(r'\|?(?:\s*:?-{3,}:?\s*\|)+'), ' '),
    (re.compile(r'(?:\s*\|){2,}\s*'), ' · '),
    # leftover HTML class attributes: 'img:first-child]:pt-0 data-[size=sm]:gap-4 ... hover:-translate-y-1">' (from the first
    # class-like token to the closing '">')
    (re.compile(r'\S*(?:\]:|:\[|data-\[)\S*[^"<>]{0,400}?"\s*>'), ' '),
    # platform and news-site interface text that search snippets drag in
    (re.compile(r'(?i)(?:post\s+)?log ?in\s*sign ?up(?:\s+post)?'), ' '),
    (re.compile(r"(?i)never miss a post from \S+ for \w+ to stay in the loop\.?|by continuing, you agree to \w+['’]s terms of use and "
                r"privacy policy\.?|no comments yet\.? start the conversation\.?|to like or comment\.?|view profile for|report this post|"
                r"\bsee more\b|\bview (?:all )?\d+ repl(?:y|ies)\b|\btop fan\b|\bGIFGIPHY\b|(?:more )?posts? by \[USER\] on|"
                r"(?:\[USER\]['’]s profile\s*)+"), ' '),
    (re.compile(r"(?i)drucken merken zur merkliste|erfolgreich kopiert!?|jetzt den vollen zugang freischalten:?|testabo|neukundenangebot!?|"
                r"danach nur \d+,\d+ ?€ mtl\.?|regional\. exklusiv\. aktuell\.|stimme\+ (?:testen|logo)|e-paper newsletter(?: jobs trauer)?|"
                r"\bmenü\b|startseite\s*›(?:\s*[^›]{1,40}›)*|(?:\d\.\s+)?startseite(?:\s+\d\.\s+[^\d.]{1,40}?(?=\s+\d\.|$))*|"
                r"retrieved from \"?\s*https?://\S+|category:pages using[^.]{0,80}|\"\}\}'/>|\},\"i\":\d+\}\}\]\}'>"), ' '),
]


def clean_text(s):
    """Remove page furniture (markdown residue, empty links, login and cookie prompts) from snippets and page text."""
    s = s or ''
    for rx, rep in _JUNK:
        s = rx.sub(rep, s)
    s = re.sub(r'\s+([,.;:!?])', r'\1', s)
    return re.sub(r'\s{2,}', ' ', s).strip(' -|·')


_LI_SLUG = re.compile(r'(/posts/|linkedin\.com/in/|linkedin\.com/pub/)[A-Za-z0-9%\-.]+?(?=_|/|\?|\s|$|[)\]"\'])')


def mask_private(s, names=False, platform_post=False):
    """Output masking for people: @handles become [USER]; with names=True also 'Firstname Lastname' (first name from a built-in list, so
    'Stadt Heilbronn' stays). platform_post=True also masks the author part of 'Photo by <author>' and '<author> on X:' (search-engine titles of
    social posts). Always: a name directly before 'shared this', "'s post", 'hat geteilt' and the like, whatever the name.
    A best-effort filter, not proof of anonymity: a name in other positions and not in the list passes."""
    s = s or ''
    if platform_post:                         # before the name rules, so the repeated owner name is still whole
        s = _PAGE_HEADER.sub(lambda m: m.group(0) if _is_place(m.group(1)) else '', s)
        s = _OWNER_POST.sub(lambda m: m.group(0) if _is_place(m.group(0)) else "[USER]'s post", s)
        s = _PROFILE_PIC.sub("[USER]'s profile", s)
        s = _PROFILE_TITLE.sub(lambda m: m.group(0) if _is_place(m.group(2)) else f'{m.group(1)}[USER] - {m.group(3)}', s)
        s = _GLUED_HANDLE.sub(lambda m: m.group(0) if _is_place(m.group(0)) else '[USER]', s)
        s = _LEADING_HANDLE.sub('[USER]', s)
    s = _ACTOR.sub(_actor_sub, s)
    if platform_post:
        s = _PHOTO_BY.sub(lambda m: f'{m.group(1)} by [USER]', s)
        s = _AUTHOR_ON.sub(lambda m: f'[USER] {m.group(2)} {m.group(3)}', s)
    s = _EMAIL.sub('[EMAIL]', s)
    s = _LI_SLUG.sub(r'\1[USER]', s)          # LinkedIn link slugs carry the author's name (15 Nov audit: /posts/<name-id>_...)
    s = _HANDLE.sub('[USER]', s)
    s = _BYLINE.sub(lambda m: f'{m.group(1)} [USER]' if m.group(2).lower() in FIRST_NAMES else m.group(0), s)
    if platform_post or names:
        s = _mask_comment_heads(s)
        if 'CC BY' in s or 'CC0' in s:
            s = _CREDIT.sub(lambda m: m.group(0) if _is_place(m.group(2)) else f'{m.group(1)}[USER]', s)
    if names:
        s = _mask_names(s)
    s = _TAG_LIST.sub(_tag_sub, s)
    s = _WITH_MASKED.sub(lambda m: m.group(0) if _is_place(m.group(0)) else '[USER]', s)
    return s


PEOPLE_KINDS = ('web', 'social_link', 'social_post', 'forum', 'blog', 'video', 'video_comment')


def mask_for_kind(kind, s):
    """Handles are masked for every kind; person names only where residents or private sites talk (not in news, official or council text)."""
    return mask_private(clean_text(s), names=kind in PEOPLE_KINDS, platform_post=kind == 'social_link')


TRACKING = re.compile(r'^(utm_|fbclid|gclid|mc_|ref$|ref_)', re.I)


def canonical_url(u):
    p = urllib.parse.urlsplit((u or '').strip())
    host = p.netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    if host.endswith('news.google.com'):      # the redirect token is the identity, keep the query as is
        q = p.query
    else:
        q = urllib.parse.urlencode([(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not TRACKING.match(k)])
    path = p.path.rstrip('/') or '/'
    return urllib.parse.urlunsplit((p.scheme.lower() or 'https', host, path, q, ''))


def title_key(title):
    t = re.sub(r'\W+', ' ', (title or '').lower()).strip()
    return hashlib.sha1(t.encode()).hexdigest()[:16] if len(t) > 15 else ''


def salt():
    """Local random salt for hashing author ids. Lives in data/.author_salt, never exported."""
    if os.environ.get('LIVE_AUTHOR_SALT'):
        return os.environ['LIVE_AUTHOR_SALT']
    p = os.path.join(ROOT, 'data', '.author_salt')
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            f.write(hashlib.sha256(os.urandom(32)).hexdigest())
    with open(p) as f:
        return f.read().strip()


def author_hash(platform, ident):
    return hashlib.sha256(f'{salt()}|{platform}|{ident}'.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- polite http
class HttpError(Exception):
    def __init__(self, status, msg, body=''):
        super().__init__(msg)
        self.status = status
        self.body = body          # first 600 chars of the error response (API error reasons), never the request


class SkipSource(Exception):
    """Raised by an adapter that cannot run (no key, quota used up). Not a failure: the run receipt lists it as skipped."""


_ENV = {}


def get_env(name):
    """Environment variable first, then live/.env (KEY=VALUE lines). The value is returned, never printed or logged."""
    v = os.environ.get(name)
    if v:
        return v.strip()
    if not _ENV:
        p = os.path.join(ROOT, '.env')
        if os.path.exists(p):
            with open(p, encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, _, val = line.partition('=')
                        _ENV[k.strip()] = val.strip().strip('"').strip("'")
        _ENV['__loaded__'] = '1'
    return (_ENV.get(name) or '').strip()


class Http:
    def __init__(self, user_agent, min_interval=1.5, timeout=30, retries=2):
        self.ua = user_agent
        self.min_interval = min_interval
        self.timeout = timeout
        self.default_retries = retries
        self._last = {}
        self._robots = {}

    def _wait(self, host, interval):
        gap = time.time() - self._last.get(host, 0)
        if gap < interval:
            time.sleep(interval - gap)
        self._last[host] = time.time()

    def robots_ok(self, url):
        p = urllib.parse.urlsplit(url)
        base = f'{p.scheme}://{p.netloc}'
        rp = self._robots.get(base)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                req = urllib.request.Request(base + '/robots.txt', headers={'User-Agent': self.ua})
                rp.parse(urllib.request.urlopen(req, timeout=min(15, self.timeout)).read().decode('utf-8', 'replace').splitlines())
            except Exception:
                rp = False          # no readable robots.txt: allowed
            self._robots[base] = rp
        return True if rp is False else rp.can_fetch(self.ua, url)

    def get(self, url, params=None, interval=None, robots=True, retries=None, accept=None, headers=None, max_bytes=None):
        """GET -> (bytes, content_type). Honours robots.txt (unless robots=False), spaces requests per host,
        backs off on 429/503. Raises HttpError with .status."""
        retries = self.default_retries if retries is None else retries
        if params:
            url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
        if url.startswith('file://'):      # local test copies only (pagewatch tests); never used for live sources
            with open(urllib.request.url2pathname(urllib.parse.urlsplit(url).path), 'rb') as f:
                return f.read(), 'text/html'
        if robots and not self.robots_ok(url):
            raise HttpError(0, 'robots.txt disallows ' + url)
        host = urllib.parse.urlsplit(url).netloc
        wait429 = 12
        for attempt in range(retries + 1):
            self._wait(host, interval or self.min_interval)
            req = urllib.request.Request(url, headers={'User-Agent': self.ua, 'Accept': accept or '*/*', **(headers or {})})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return (r.read(max_bytes) if max_bytes else r.read()), r.headers.get('Content-Type', '')
            except urllib.error.HTTPError as e:
                if e.code in (429, 503) and attempt < retries:
                    time.sleep(wait429)
                    wait429 *= 2
                    continue
                try:
                    body = e.read(600).decode('utf-8', 'replace')
                except Exception:
                    body = ''
                raise HttpError(e.code, f'HTTP {e.code} {url.split("?")[0]}', body)
            except Exception as e:
                if attempt < retries:
                    time.sleep(3)
                    continue
                raise HttpError(-1, f'{type(e).__name__}: {e}')

    def post_json(self, url, payload, headers=None, interval=None, retries=None):
        """POST a JSON body, return parsed JSON. For documented APIs with a key in a header. Same pacing and back-off as get().
        429 and 503 are retried after a pause; other errors (402, 432, 433: credits or plan limit) are raised at once with .status."""
        retries = self.default_retries if retries is None else retries
        host = urllib.parse.urlsplit(url).netloc
        data = json.dumps(payload).encode('utf-8')
        wait429 = 8
        for attempt in range(retries + 1):
            self._wait(host, interval or self.min_interval)
            req = urllib.request.Request(url, data=data, method='POST', headers={
                'User-Agent': self.ua, 'Accept': 'application/json', 'Content-Type': 'application/json', **(headers or {})})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode('utf-8'))
            except urllib.error.HTTPError as e:
                if e.code in (429, 503) and attempt < retries:
                    time.sleep(wait429)
                    wait429 *= 2
                    continue
                try:
                    body = e.read(600).decode('utf-8', 'replace')
                except Exception:
                    body = ''
                raise HttpError(e.code, f'HTTP {e.code} {url.split("?")[0]}', body)
            except json.JSONDecodeError:
                raise HttpError(-2, 'not JSON from ' + url.split('?')[0])
            except Exception as e:
                if attempt < retries:
                    time.sleep(3)
                    continue
                raise HttpError(-1, f'{type(e).__name__}: {e}')

    def json(self, url, **kw):
        body, _ = self.get(url, **kw)
        try:
            return json.loads(body.decode('utf-8'))
        except Exception:
            head = body[:4000].decode('utf-8', 'replace')
            if 'altcha' in head.lower() or '<html' in head.lower():
                raise HttpError(403, 'gated: HTML challenge page instead of JSON (not bypassed)')
            raise HttpError(-2, 'not JSON: ' + head[:80].replace('\n', ' '))


# ---------------------------------------------------------------- item and adapter base
class Item:
    def __init__(self, source, project, url, title, text, published_at, source_name, language=None, country=None,
                 media_type='News', author_hash=None, engagements=0, source_terms='', query='', title_hit=True, kind=None, modified_at=None,
                 version_id=None, text_scope=None, date_known=True, radar_match=None):
        self.source, self.project, self.url = source, project, url
        self.title, self.text = (title or '').strip(), (text or title or '').strip()
        self.published_at = published_at
        self.source_name, self.language, self.country = source_name, language, country
        self.media_type, self.author_hash, self.engagements = media_type, author_hash, engagements
        self.source_terms, self.query, self.title_hit = source_terms, query, title_hit
        self.kind, self.modified_at, self.version_id = kind, modified_at, version_id
        self.text_scope, self.date_known = text_scope, date_known    # text_scope: 'full' or 'snippet'; date_known False: published_at is our retrieval time
        self.radar_match = radar_match                              # strong | weak | none, set by the adapter or run_collect
        self.retrieved_at = dt.datetime.now(UTC)

    def content_hash(self):
        return hashlib.sha1(f'{self.title}\n{self.text}'.encode()).hexdigest()[:16]


class Adapter:
    """fetch(project, since) -> list[Item]. `since` is an aware UTC datetime. Raise on hard failure."""
    name = 'base'
    source_terms = ''

    def __init__(self, cfg, http):
        self.cfg = cfg
        self.http = http
        self.interval = cfg.get('min_interval_s', 1.5)

    def fetch(self, project, since):
        raise NotImplementedError


# ---------------------------------------------------------------- store
DEFAULT_KIND = {'rss': 'article', 'oparl': 'council_paper', 'gdelt': 'article', 'gnews': 'article',
                'bluesky': 'social_post', 'mastodon': 'social_post', 'pagewatch': 'official_page_change',
                'exa': 'web', 'tavily': 'web', 'youtube': 'video'}
DATASET_EDGE = '2026-10-27T12:29:00+0000'     # last record of the city's historical export (same as pipeline/config.toml)


class Store:
    """SQLite. Key = sha1(canonical url [+ version id]). One row per record in `items` (the latest version).
    Append-only tables: `item_versions` (every version of a record, version 1 at first sight) and `sightings` (every time a
    source returned the record in a run: same article from two sources = one record, two sightings).
    A second article with the same headline from the same outlet (another source adapter, other URL) is stored but flagged dup_of.
    Dates kept apart: published_at (source date), modified_at (source says it changed), first_seen (= discovered_at, never changes),
    last_changed_at (when we saw a new version), retrieved_at (last time we saw it). ingested_at belongs to the pipeline."""

    COLS = ['key', 'mention_id', 'url', 'canonical_url', 'content_hash', 'title_key', 'dup_of', 'source', 'projects', 'title',
            'text', 'published_at', 'source_name', 'language', 'country', 'media_type', 'author_hash', 'engagements',
            'source_terms', 'retrieved_at', 'first_seen', 'query', 'title_hit', 'kind', 'modified_at',
            'version_no', 'first_run_id', 'last_changed_at', 'last_changed_run_id', 'text_scope', 'date_known', 'radar_match']

    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        self.db = sqlite3.connect(path)
        self.run_id = None
        self.db.execute('''CREATE TABLE IF NOT EXISTS items(
            key TEXT PRIMARY KEY, mention_id TEXT, url TEXT, canonical_url TEXT, content_hash TEXT, title_key TEXT,
            dup_of TEXT, source TEXT, projects TEXT, title TEXT, text TEXT, published_at TEXT, source_name TEXT,
            language TEXT, country TEXT, media_type TEXT, author_hash TEXT, engagements INTEGER,
            source_terms TEXT, retrieved_at TEXT, first_seen TEXT, query TEXT)''')
        for col, typ in (('title_hit', 'INTEGER DEFAULT 1'), ('kind', 'TEXT'), ('modified_at', 'TEXT'), ('version_no', 'INTEGER DEFAULT 1'),
                         ('first_run_id', 'TEXT'), ('last_changed_at', 'TEXT'), ('last_changed_run_id', 'TEXT'),
                         ('text_scope', 'TEXT'), ('date_known', 'INTEGER DEFAULT 1'), ('radar_match', 'TEXT'),
                         ('date_source', 'TEXT')):   # date_source: where a recovered date came from (collector/dates.py); NULL = the source gave it
            try:
                self.db.execute(f'ALTER TABLE items ADD COLUMN {col} {typ}')
            except sqlite3.OperationalError:
                pass
        # an earlier prototype of item_versions had another layout; it was empty in every store, so replace it
        cols = [r[1] for r in self.db.execute('PRAGMA table_info(item_versions)')]
        if cols and 'version_no' not in cols:
            if self.db.execute('SELECT count(*) FROM item_versions').fetchone()[0]:
                self.db.execute('ALTER TABLE item_versions RENAME TO item_versions_prototype')
            else:
                self.db.execute('DROP TABLE item_versions')
        self.db.execute('''CREATE TABLE IF NOT EXISTS item_versions(
            key TEXT, version_no INTEGER, content_hash TEXT, title TEXT, text TEXT, seen_at TEXT, run_id TEXT,
            PRIMARY KEY (key, version_no))''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS sightings(
            key TEXT, source TEXT, project TEXT, query TEXT, seen_at TEXT, run_id TEXT)''')
        self.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_sight ON sightings(key, source, project, run_id)')
        self.db.execute('''CREATE TABLE IF NOT EXISTS page_snapshots(
            page_id TEXT, fetched_at TEXT, url TEXT, content_hash TEXT, text TEXT)''')
        # rows stored before these columns existed
        for src, kind in DEFAULT_KIND.items():
            self.db.execute('UPDATE items SET kind=? WHERE kind IS NULL AND source=?', (kind, src))
        self.db.execute("UPDATE items SET kind='official_news' WHERE kind='article' AND source='rss' AND media_type='Other'")
        self.db.execute('UPDATE items SET version_no=1 WHERE version_no IS NULL')
        self.db.execute('UPDATE items SET last_changed_at=first_seen WHERE last_changed_at IS NULL')
        self.db.execute('''INSERT OR IGNORE INTO item_versions(key, version_no, content_hash, title, text, seen_at, run_id)
                           SELECT key, 1, content_hash, title, text, first_seen, first_run_id FROM items''')
        self.db.execute('CREATE INDEX IF NOT EXISTS ix_tk ON items(title_key)')
        self.db.commit()
        self.reset_run()

    # per-run bookkeeping for the receipt (distinct keys, so an item found for two projects counts once)
    def reset_run(self, run_id=None):
        self.run_id = run_id
        self.run = {'new': set(), 'updated': set(), 'seen': set(), 'dup': set(), 'sightings': 0}

    PURGED = '[removed after 30 days: YouTube API terms]'

    def purge_api_text(self, source='youtube', days=30, now=None):
        """YouTube API Services terms: API data may be stored at most 30 days unless refreshed. An item seen again by a
        new search gets a fresh retrieved_at and is kept. Older ones lose title and text (also in item_versions); the
        link, dates, hash and our labels stay. Returns the number of items purged in this call."""
        now = now or dt.datetime.now(dt.timezone.utc)
        cut = (now - dt.timedelta(days=days)).isoformat(timespec='seconds')
        keys = [r[0] for r in self.db.execute('SELECT key FROM items WHERE source = ? AND retrieved_at < ? AND title != ?',
                                              (source, cut, self.PURGED))]
        for k in keys:
            self.db.execute('UPDATE items SET title = ?, text = ? WHERE key = ?', (self.PURGED, self.PURGED, k))
            self.db.execute('UPDATE item_versions SET title = ?, text = ? WHERE key = ?', (self.PURGED, self.PURGED, k))
        self.db.commit()
        return len(keys)

    def upsert(self, it):
        canon = canonical_url(it.url)
        key = hashlib.sha1((canon + ('|' + it.version_id if it.version_id else '')).encode()).hexdigest()
        ch = it.content_hash()
        row = self.db.execute('SELECT content_hash, projects, version_no FROM items WHERE key=?', (key,)).fetchone()
        now = it.retrieved_at.isoformat(timespec='seconds')
        cur = self.db.execute('INSERT OR IGNORE INTO sightings VALUES (?,?,?,?,?,?)',
                              (key, it.source, it.project, it.query, now, self.run_id))
        self.run['sightings'] += cur.rowcount
        if row:
            projects = set(row[1].split(',')) | {it.project}
            if it.text_scope == 'snippet':
                # A search snippet is an excerpt the search service picks for each query, not the page itself. A different
                # snippet for the same link is not an edit (15 Nov: 79 false "versions" came from this). Keep the first
                # snippet, record the sighting, and keep the strongest radar match seen.
                rank = {'strong': 3, 'weak': 2, 'none': 1}
                old = self.db.execute('SELECT radar_match FROM items WHERE key=?', (key,)).fetchone()[0]
                best = it.radar_match if rank.get(it.radar_match, 0) > rank.get(old, 0) else old
                self.db.execute('UPDATE items SET projects=?, retrieved_at=?, radar_match=? WHERE key=?',
                                (','.join(sorted(projects)), now, best, key))
                self.run['seen'].add(key)
                return 'seen'
            if row[0] != ch:
                v = (row[2] or 1) + 1
                self.db.execute('INSERT INTO item_versions VALUES (?,?,?,?,?,?,?)', (key, v, ch, it.title, it.text, now, self.run_id))
                self.db.execute('UPDATE items SET projects=?, retrieved_at=?, content_hash=?, title=?, text=?, engagements=?, '
                                'version_no=?, last_changed_at=?, last_changed_run_id=? WHERE key=?',
                                (','.join(sorted(projects)), now, ch, it.title, it.text, it.engagements, v, now, self.run_id, key))
                self.run['updated'].add(key)
                return 'updated'
            self.db.execute('UPDATE items SET projects=?, retrieved_at=? WHERE key=?', (','.join(sorted(projects)), now, key))
            self.run['seen'].add(key)
            return 'seen'
        tk = title_key(it.title)
        dup = None
        if tk:
            d = self.db.execute('SELECT key FROM items WHERE title_key=? AND dup_of IS NULL AND source_name=?',
                                (tk, it.source_name)).fetchone()
            dup = d[0] if d else None
        pub = it.published_at.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S+0000')
        mod = it.modified_at.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S+0000') if it.modified_at else None
        vals = dict(key=key, mention_id='live:' + key[:12], url=it.url, canonical_url=canon, content_hash=ch, title_key=tk,
                    dup_of=dup, source=it.source, projects=it.project, title=it.title, text=it.text, published_at=pub,
                    source_name=it.source_name, language=it.language, country=it.country, media_type=it.media_type,
                    author_hash=it.author_hash, engagements=it.engagements, source_terms=it.source_terms,
                    retrieved_at=now, first_seen=now, query=it.query, title_hit=1 if it.title_hit else 0,
                    kind=it.kind or DEFAULT_KIND.get(it.source, 'article'), modified_at=mod, version_no=1,
                    first_run_id=self.run_id, last_changed_at=now, last_changed_run_id=self.run_id,
                    text_scope=it.text_scope, date_known=1 if it.date_known else 0, radar_match=it.radar_match)
        self.db.execute(f"INSERT INTO items ({','.join(self.COLS)}) VALUES ({','.join('?' * len(self.COLS))})",
                        [vals[c] for c in self.COLS])
        self.db.execute('INSERT INTO item_versions VALUES (?,?,?,?,?,?,?)', (key, 1, ch, it.title, it.text, now, self.run_id))
        st = 'dup' if dup else 'new'
        self.run[st].add(key)
        return st

    # ---- page snapshots (official page change monitor)
    def last_snapshot(self, page_id):
        return self.db.execute('SELECT fetched_at, content_hash, text FROM page_snapshots WHERE page_id=? ORDER BY rowid DESC LIMIT 1',
                               (page_id,)).fetchone()

    def add_snapshot(self, page_id, url, content_hash, text, fetched_at):
        self.db.execute('INSERT INTO page_snapshots VALUES (?,?,?,?,?)', (page_id, fetched_at, url, content_hash, text))

    def versions(self, key):
        """All stored versions of a record, oldest first: [(version_no, content_hash, title, text, seen_at, run_id)]."""
        return self.db.execute('SELECT version_no, content_hash, title, text, seen_at, run_id FROM item_versions WHERE key=? ORDER BY version_no',
                               (key,)).fetchall()

    def commit(self):
        self.db.commit()

    def backfill_radar(self, projects):
        """Tag rows stored before the radar gate existed (title + start of the text; page watch rows are the project's own official page)."""
        by = {p.id: p for p in projects}
        rows = self.db.execute('SELECT key, projects, title, text, kind FROM items WHERE radar_match IS NULL').fetchall()
        for key, pids, title, text, kind in rows:
            p = by.get(pids.split(',')[0])
            if p:
                self.db.execute('UPDATE items SET radar_match=? WHERE key=?',
                                ('strong' if kind == 'official_page_change' else p.relevance(title, (text or '')[:600]), key))
        self.db.commit()

    def export_raw(self, path, since=None, mode='discovered', dataset_edge=DATASET_EDGE, run_id=None):
        """Raw records in the shape pipeline/stages/s01_ingest.py accepts (REQUIRED: mention_id, published_at, url,
        media_type_name). `authors` holds a hashed id only (or []), never a name or handle. Duplicates (dup_of) are not exported.
        mode 'discovered' (default): records FIRST SEEN or CHANGED on or after `since`. "New" means discovered, not published, so an
                         old article found for the first time today is exported.
        mode 'run'       : only records first seen or changed in run `run_id` (a delta for one run).
        mode 'published' : the old behaviour, published_at or modified_at on or after `since` (can miss late discoveries).
        late_discovered = published before the dataset edge but first seen after it."""
        q = 'SELECT * FROM items WHERE dup_of IS NULL'
        args = []
        s = since.strftime('%Y-%m-%dT%H:%M:%S+0000') if since else None
        sd = since.isoformat(timespec='seconds') if since else None
        if mode == 'discovered' and since:
            q += ' AND (first_seen >= ? OR last_changed_at >= ?)'
            args += [sd, sd]
        elif mode == 'published' and since:
            q += ' AND (published_at >= ? OR modified_at >= ?)'
            args += [s, s]
        elif mode == 'run':
            q += ' AND (first_run_id = ? OR last_changed_run_id = ?)'
            args += [run_id, run_id]
        found_by = {}
        for k, src, n in self.db.execute('SELECT key, group_concat(DISTINCT source), count(*) FROM sightings GROUP BY key'):
            found_by[k] = (sorted(set((src or '').split(','))), n)
        cur = self.db.execute(q + ' ORDER BY published_at, key', args)
        cols = [c[0] for c in cur.description]
        recs = []
        edge_iso = dataset_edge
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            first_iso = d['first_seen'].replace('+00:00', '+0000')
            late = d['published_at'] < edge_iso <= first_iso
            recs.append({
                'mention_id': d['mention_id'], 'media_type_name': d['media_type'], 'published_at': d['published_at'],
                'source_name': d['source_name'], 'url': d['url'], 'country_code': d['country'],
                'language_code': d['language'], 'sentiment': -99, 'reach': None, 'engagements': d['engagements'] or 0,
                'authors': [d['author_hash']] if d['author_hash'] else [], 'title': mask_for_kind(d['kind'], d['title']),
                'content': mask_for_kind(d['kind'], d['text']),
                # extra fields: s01_ingest ignores them; they stay for audit and for the integration contract
                'discovered_at': d['first_seen'], 'retrieved_at': d['retrieved_at'], 'modified_at': d['modified_at'],
                'last_changed_at': d['last_changed_at'], 'version_no': d['version_no'], 'late_discovered': bool(late),
                'kind': d['kind'], 'replay': False, 'published': False,
                'source_terms': d['source_terms'], 'collector_source': d['source'],
                'project_hint': d['projects'], 'content_hash': d['content_hash'], 'title_hit': bool(d['title_hit']),
                # provenance for information value: which of our sources found it, and how often (copies vs independent finds)
                'found_by_sources': found_by.get(d['key'], ([d['source']], 1))[0], 'n_sightings': found_by.get(d['key'], ([], 1))[1],
                'radar_match': d['radar_match'], 'text_scope': d['text_scope'], 'date_known': bool(d['date_known']) if d['date_known'] is not None else True,
                # where the date came from: 'source' (the service gave it) or a recovery rule: 'url', 'text', 'page_meta'
                'date_source': (d.get('date_source') or 'source') if (d['date_known'] is None or d['date_known']) else None,
            })
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(recs, f, ensure_ascii=False, indent=1)
        return len(recs)
