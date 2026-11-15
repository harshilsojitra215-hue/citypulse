"""Radar report: one short page after a --radar run. Written to out/radar_<run_id>.md next to the normal receipt.
Per project: strong / possible / noise counts (radar gate, see Project.relevance), dated vs date-unknown, links per platform (no URLs printed), top 5 strong titles.
Then sources that ran, were skipped or failed, and a plain statement of what this scan cannot see."""
import collections
import re

from collector.adapters._search import PLATFORM, RESIDENT_KINDS, domain_of  # noqa: F401
from collector.core import mask_for_kind

STOP = set('''aber alle als also auch auf aus bei bin bis das dass dem den der des die doch dort ein eine einem einen einer eines euch for
fuer für gegen hat hier ich ihr ist jetzt kann kein man mehr mit nach nicht noch nur oder ohne sich sie sind und uns von vor war was wenn wer
wie wir wird zu zum zur über the and are that this with from have not you your les des une est pour dans qui que sur par pas plus mais
comme cette ont aux the was were will can about just more https http www com html news seilbahn heilbronn heilbronner bonn bonner'''.split())

KIND_LABEL = {'news': 'news', 'official': 'city / official', 'forum': 'forum / petition', 'blog': 'blog', 'video': 'video',
              'video_comment': 'video comment', 'social_link': 'social link', 'social_post': 'social post (Bluesky, Mastodon)',
              'article': 'article (RSS)', 'official_news': 'official news', 'council_paper': 'council paper', 'web': 'other web',
              'official_page_change': 'official page change'}

COVERAGE = [
    'Instagram, Facebook, TikTok, X, LinkedIn: no access to posts or comments. Where a search service returned a public link, we list the link, '
    'title and snippet only. We did not open or download those pages. Private groups, stories and anything behind a login are invisible.',
    'Reddit: only links a search service returned. No post text, no comments (the official API needs approval, not set up).',
    'Paywalled outlets (for example Heilbronner Stimme): headline and snippet only, no article text.',
    'Pages whose robots.txt disallows our user agent: snippet only, marked text_scope=snippet.',
    'Local radio, TV, podcasts, citizen-participation platform comments, council meetings that are not published as text: not covered.',
    'Search services show a sample, not everything. Zero hits for a source is not proof that nobody spoke.',
]


def keywords(texts, project, n=8):
    skip = STOP | {w.lower() for w in re.findall(r'\w+', ' '.join(project.place_words + project.keywords + project.specific))}
    c = collections.Counter()
    for t in texts:
        for w in set(re.findall(r'[^\W\d_]{5,}', (t or '').lower())):
            if w not in skip:
                c[w] += 1
    return [w for w, k in c.most_common(n) if k >= 2] or [w for w, _ in c.most_common(n)]


def platform_of(domain, source_name):
    d = domain or source_name or ''
    for k, v in PLATFORM.items():
        if d == k or d.endswith('.' + k):
            return v
    return d


def _title(i):
    """Title for the report: handles and person names masked. A social link is shown as '<platform> link', its URL stays in the export only."""
    t = re.sub(r'\s+', ' ', mask_for_kind(i['kind'], i['title'])).strip()[:110]
    return f"{platform_of(domain_of(i['url']), i['source_name'])} link: {t}" if i['kind'] == 'social_link' else f"[{KIND_LABEL.get(i['kind'], i['kind'])}, {i['source_name']}] {t}"


def write_radar(path, rc, rows, store, adapters, projects, since):
    keys = list(store.run['new'])
    items = []
    if keys:
        cols = ['key', 'projects', 'kind', 'title', 'text', 'source', 'source_name', 'published_at', 'url', 'date_known', 'text_scope', 'radar_match']
        q = f"SELECT {', '.join(cols)} FROM items WHERE key IN ({','.join('?' * len(keys))})"
        items = [dict(zip(cols, r)) for r in store.db.execute(q, keys)]
    for i in items:
        i['radar_match'] = i['radar_match'] or 'none'
    by_proj = collections.defaultdict(list)
    for it in items:
        by_proj[it['projects'].split(',')[0]].append(it)
    since_d = since.date().isoformat()
    split = lambda its, m: [i for i in its if i['radar_match'] == m]            # noqa: E731
    dated = lambda its: [i for i in its if i['date_known'] != 0]                # noqa: E731
    strong, weak, none = split(items, 'strong'), split(items, 'weak'), split(items, 'none')
    L = [f"# Radar report {rc['run_id']}", '',
         f"Scan for items since {since_d} across {len(projects)} projects. Run status: **{rc['status']}**. Nothing is published by the collector.", '',
         f"- **Strong: {len(strong)}** (a cable word and a place word together, or a project phrase): "
         f"**{len(dated(strong))} dated since {since_d}**; **{len(strong) - len(dated(strong))} found today, date unknown** (search results without a publish date).",
         f"- Possible, check: {len(weak)} (only one of the two words, or far apart). Collapsed per project below.",
         f"- Noise filtered: {len(none)} (neither word, or a negative word).",
         f"- All {len(items)} new items stay stored and in the export with their `radar_match`; the pipeline decides final relevance.",
         f"- Social links among the strong ones: {sum(1 for i in strong if i['kind'] == 'social_link')} (links only, not opened).", '']
    plat = collections.Counter(platform_of(domain_of(i['url']), i['source_name']) for i in strong if i['kind'] == 'social_link')
    if plat:
        L += ['Strong links found on: ' + ', '.join(f'{p} {n}' for p, n in plat.most_common()) + '.', '']
    for p in projects:
        its = by_proj.get(p.id, [])
        st, wk, nz = split(its, 'strong'), split(its, 'weak'), split(its, 'none')
        L += [f'## {p.name} (`{p.id}`)', '']
        if not its:
            L += ['No new items in this scan. This is not evidence that nobody discussed it.', '']
            continue
        L += [f"Strong {len(st)} ({len(dated(st))} dated since {since_d}, {len(st) - len(dated(st))} found today, date unknown). "
              f"Possible, check: {len(wk)}. Noise filtered: {len(nz)}.", '']
        if st:
            kinds = collections.Counter(i['kind'] for i in st)
            L += ['| Strong, by kind | New |', '|---|---|'] + [f"| {KIND_LABEL.get(k, k)} | {n} |" for k, n in kinds.most_common()] + ['']
            links = collections.Counter(platform_of(domain_of(i['url']), i['source_name']) for i in st if i['kind'] == 'social_link')
            for pl, n in links.most_common():
                L.append(f"- {pl} link: {n} (URL in the export only)")
            kw = keywords([f"{mask_for_kind(i['kind'], i['title'])} {mask_for_kind(i['kind'], i['text']) if i['text_scope'] != 'full' else ''}" for i in st], p)
            if kw:
                L.append('- Topic words in the strong items: ' + ', '.join(kw))
            L += ['', 'Top 5 strong titles (dated):']
            for i in sorted(dated(st), key=lambda i: i['published_at'], reverse=True)[:5]:
                L.append(f"- {i['published_at'][:10]} {_title(i)}")
            if not dated(st):
                L.append('- none with a publish date')
            und = [i for i in st if i['date_known'] == 0]
            if und:
                L += ['', f'Found today, date unknown ({len(und)} strong, publish date not given by the source):']
                L += [f"- {_title(i)}" for i in und[:5]]
        else:
            L.append('No strong item in this scan.')
        if wk:
            L += ['', f'<details><summary>Possible, check: {len(wk)}</summary>', ''] + [f"- {_title(i)}" for i in wk[:5]]
            L += [f'- ... and {len(wk) - 5} more' if len(wk) > 5 else '', '', '</details>']
        L.append('')
    L += ['## Sources', '']
    for s in rc['sources']:
        L.append(f"- {s['source']}: {s['status']}, {s['items_returned']} returned, {s['new']} new" +
                 ('; failed for ' + ', '.join(f"{f['project']} ({f['reason'][:70]})" for f in s['projects_failed']) if s['projects_failed'] else ''))
    for s in rc.get('sources_skipped', []):
        L.append(f"- {s['source']}: SKIPPED. {s['reason']}")
    for ad in adapters:
        st = getattr(ad, 'stats', None)
        if st and 'raw_hits' in st:
            L.append(f"  - {ad.name} detail: {st['queries']} queries, {st['raw_hits']} raw hits, {st['off_topic_dropped']} dropped as off topic, "
                     f"{st['full_text']} read in full (robots.txt allowed), {st['robots_blocked']} blocked by robots.txt, {st['snippet_only']} snippet only, "
                     f"{st['undated']} without date; radar match strong {st.get('strong', 0)} / weak {st.get('weak', 0)} / none {st.get('none', 0)}; "
                     f"estimated cost {getattr(ad, 'cost_usd', 0):.2f} USD" + (f", {st['credits']:g} credits used" if 'credits' in st else ''))
        elif st and ad.name == 'youtube':
            L.append(f"  - youtube detail: {st['queries']} searches, {st['videos']} videos, {st['comments']} comments, {st['videos_comments_off']} with comments off")
    for w in [g for g in rc['coverage_gaps'] if not g.startswith('NOT COVERED BY DESIGN')]:
        L.append(f'- Problem: {w}')
    L += ['', '## What this scan cannot see', ''] + [f'- {c}' for c in COVERAGE] + ['']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    return path
