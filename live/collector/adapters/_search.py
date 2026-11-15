"""Shared pieces for the key-based search adapters (Exa, Tavily) and YouTube.

- key handling: the key comes from the environment variable named in projects.yaml (`key_env`) or live/.env. Missing key: SkipSource,
  the receipt says "skipped: no key". A key is never printed, logged or stored.
- classify(domain) -> kind: news, forum, blog, video, official, social_link, web (unknown). RESIDENT_KINDS are the ones where residents
  (not outlets or the city) talk.
- full_text(): fetch page text ONLY where robots.txt allows. Social platforms are never fetched. Otherwise the hit stays snippet-only.
"""
import datetime as dt
import email.utils
import re
import urllib.parse

from ..core import Adapter, HttpError, Item, SkipSource, UTC, canonical_url, get_env, mask_for_kind, strip_html

SOCIAL = ('reddit.com', 'instagram.com', 'facebook.com', 'fb.com', 'tiktok.com', 'x.com', 'twitter.com', 'linkedin.com', 'quora.com',
          'threads.net', 'pinterest.com', 'pinterest.de', 'bsky.app', 'snapchat.com', 'xing.com', 'telegram.org', 't.me', 'whatsapp.com')
VIDEO = ('youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com', 'arte.tv')
FORUM_PARTS = ('forum', 'foren', 'skyscrapercity', 'architekturforum', 'nebenan.de', 'gutefrage.net', 'openpetition.de', 'change.org',
               'abgeordnetenwatch', 'stackexchange', 'mitmachen', 'buergerbeteiligung', 'beteiligung', 'dialog', 'meinestadt.de',
               'buergerportal', 'petition', 'leserbrief', 'kommentar')
BLOG_PARTS = ('blog', 'wordpress.com', 'medium.com', 'substack.com', 'tumblr.com', 'ghost.io', 'blogspot', 'bloggen')
OFFICIAL_RX = re.compile(r'(^|\.)((heilbronn|bonn|koeln|berlin|hamburg|stuttgart|muenchen|wuppertal|koblenz|bochum|herne|ludwigshafen|creteil'
                         r'|paris|val-de-marne)\.(de|fr)|bund\.de|baden-wuerttemberg\.de|nrw\.de|bayern\.de|iledefrance-mobilites\.fr|ile-de-france\.fr'
                         r'|gouv\.fr|bmv\.de|bmdv\.bund\.de|europa\.eu|sitzung-online\.de|ratsinfo|allris|sessionnet|bi\.rathaus|ris\.)', re.I)
NEWS_DOMAINS = ('swr.de', 'ga.de', 'stimme.de', 'echo24.de', 'tagesschau.de', 'zdf.de', 'ard.de', 'br.de', 'wdr.de', 'ndr.de', 'spiegel.de', 'zeit.de',
                'faz.net', 'sueddeutsche.de', 'welt.de', 'bild.de', 'focus.de', 'stuttgarter-zeitung.de', 'stuttgarter-nachrichten.de', 'rnz.de',
                'heilbronn.de', 'rheinische-post.de', 'wz.de', 'rundschau-online.de', 'ksta.de', 'general-anzeiger-bonn.de', 'waz.de', 'taz.de',
                'tagesspiegel.de', 'berliner-zeitung.de', 'berliner-kurier.de', 'morgenpost.de', 'abendblatt.de', 'mopo.de', 'merkur.de', 'tz.de',
                'n-tv.de', 't-online.de', 'rtl.de', 'deutschlandfunk.de', 'mdr.de', 'hr.de', 'rbb24.de', 'swp.de', 'ipai-hn.de',
                'lemonde.fr', 'leparisien.fr', 'francetvinfo.fr', '20minutes.fr', 'lefigaro.fr', 'liberation.fr', 'actu.fr', 'bfmtv.com',
                'ouest-france.fr', 'europe1.fr', 'rfi.fr', 'lci.fr', 'franceinfo.fr', 'lamarne.fr', 'le-pays.fr', 'ladepeche.fr')
NEWS_PARTS = ('zeitung', 'nachrichten', 'presse', 'kurier', 'anzeiger', 'rundschau', 'tageblatt', 'journal', 'news', 'echo', 'tagespost',
              'express', 'courrier', 'quotidien', 'gazette')
RESIDENT_KINDS = ('forum', 'blog', 'video', 'video_comment', 'social_link', 'social_post')
KINDS = ('news', 'official', 'forum', 'blog', 'video', 'video_comment', 'social_link', 'social_post', 'council_paper', 'official_page_change',
         'official_news', 'article', 'web')
ROBOTS_BLOCKED = 'robots.txt disallows'
PLATFORM = {'reddit.com': 'Reddit', 'facebook.com': 'Facebook', 'instagram.com': 'Instagram', 'x.com': 'X', 'twitter.com': 'X',
            'tiktok.com': 'TikTok', 'youtube.com': 'YouTube', 'youtu.be': 'YouTube', 'linkedin.com': 'LinkedIn', 'quora.com': 'Quora',
            'threads.net': 'Threads', 'bsky.app': 'Bluesky'}
# one query per entry; the last entry groups German forums and participation sites
DEFAULT_SITE_SCOPES = [['reddit.com'], ['facebook.com'], ['instagram.com'], ['x.com', 'twitter.com'], ['tiktok.com'], ['youtube.com'],
                       ['skyscrapercity.com', 'nebenan.de', 'gutefrage.net', 'openpetition.de', 'change.org']]


def domain_of(url):
    h = urllib.parse.urlsplit(url or '').netloc.lower().split(':')[0]
    return h[4:] if h.startswith('www.') else h


def _in(domain, names):
    return any(domain == n or domain.endswith('.' + n) for n in names)


def classify(domain):
    d = (domain or '').lower()
    if _in(d, SOCIAL):
        return 'social_link'
    if _in(d, VIDEO):
        return 'video'
    if _in(d, NEWS_DOMAINS) and not OFFICIAL_RX.search(d):
        return 'news'
    if OFFICIAL_RX.search(d):
        return 'official'
    if any(p in d for p in FORUM_PARTS):
        return 'forum'
    if any(p in d for p in BLOG_PARTS):
        return 'blog'
    if any(p in d for p in NEWS_PARTS):
        return 'news'
    return 'web'


def parse_date(s):
    """ISO date or datetime (also 'YYYY-MM-DD', 'Z' suffix) or RFC 2822 date -> aware UTC datetime, or None."""
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
        return (t if t.tzinfo else t.replace(tzinfo=UTC)).astimezone(UTC)
    except Exception:
        pass
    try:                                    # Tavily news returns RFC 2822: 'Sat, 07 Nov 2026 10:45:53 GMT'
        t = email.utils.parsedate_to_datetime(str(s))
        return (t if t.tzinfo else t.replace(tzinfo=UTC)).astimezone(UTC)
    except Exception:
        return None


def full_text(http, url, max_chars=8000, max_bytes=600000):
    """-> (text, scope). Page text only if robots.txt allows this URL for our user agent; otherwise ('', 'snippet').
    Never called for social platforms (see SearchAdapter._to_item). HTML only; PDFs and errors fall back to snippet."""
    try:
        if not http.robots_ok(url):
            return '', 'snippet', ROBOTS_BLOCKED
        body, ctype = http.get(url, interval=1.5, robots=True, accept='text/html', max_bytes=max_bytes)
    except HttpError as e:
        return '', 'snippet', f'HTTP {e.status}' if e.status > 0 else str(e)[:60]
    except Exception as e:      # a page that fails must never stop the run
        return '', 'snippet', type(e).__name__
    if 'html' not in (ctype or '').lower():
        return '', 'snippet', 'not html'
    html = body.decode('utf-8', 'replace')
    html = re.sub(r'(?is)<(script|style|nav|header|footer|aside|form|noscript)\b.*?</\1>', ' ', html)
    m = re.search(r'(?is)<article\b.*?</article>', html) or re.search(r'(?is)<main\b.*?</main>', html)
    text = strip_html(m.group(0) if m else html)
    if len(text) < 200:
        return '', 'snippet', 'no readable text'
    return text[:max_chars], 'full', ''


class SearchAdapter(Adapter):
    """Base for key-based web search APIs. Subclass sets name, key_env default, source_terms and implements search().
    search(query, since, lang) -> list of dicts: url, title, snippet, published (aware datetime or None), (optional) text."""
    key_env = ''

    def __init__(self, cfg, http):
        super().__init__(cfg, http)
        self.key_env = cfg.get('key_env', self.key_env)
        self.stats = {'queries': 0, 'raw_hits': 0, 'off_topic_dropped': 0, 'before_since_dropped': 0, 'full_text': 0,
                      'snippet_only': 0, 'robots_blocked': 0, 'undated': 0, 'strong': 0, 'weak': 0, 'none': 0}
        self.warnings = []
        self.quota_hit = None
        self.cost_usd = 0.0
        self._fulltext_done = 0

    def key(self):
        k = get_env(self.key_env)
        if not k:
            raise SkipSource(f'{self.name}: no key ({self.key_env} not set), source skipped')
        return k

    def search(self, query, since, lang, domains=None, must_have=None):
        """domains: restrict the search to these hosts (site-scoped discovery), or None. must_have: a word every result must contain, where the API can enforce it."""
        raise NotImplementedError

    def quota_error(self, e):
        """Credits or plan limit used up? -> short reason, else None."""
        return None

    def fetch(self, project, since):
        self.key()
        if self.quota_hit:
            raise SkipSource(f'{self.name}: {self.quota_hit}')
        out, seen = [], set()
        maxq = self.cfg.get('max_queries_per_project', 3)
        # a query without a cable word (a city-only query) returns anything about the city: not asked
        jobs = [(lang, q, None) for lang, queries in project.queries.items() for q in queries if project.cable_word(q)][:maxq]
        jobs += self.site_jobs(project)
        for lang, q, domains in jobs:
            try:
                hits = self.search(q, since, lang, domains, project.cable_word(q) if domains else None)
            except HttpError as e:
                why = self.quota_error(e)
                if why:
                    self.quota_hit = why
                    self.warnings.append(f'{self.name}: {why} (HTTP {e.status}); stopped, items so far are kept')
                    if out:
                        return out
                    raise SkipSource(f'{self.name}: {why}')
                raise
            self.stats['queries'] += 1
            self.stats['raw_hits'] += len(hits)
            for h in hits:
                it = self._to_item(project, since, q, lang, h, seen)
                if it:
                    out.append(it)
        return out

    def site_jobs(self, project):
        """Discovery-only queries, one per platform: "Seilbahn Heilbronn" (quoted, cable word required) on reddit.com, facebook.com, ...
        The search service returns links, titles and snippets. We store those and nothing more."""
        scopes = self.cfg.get('site_scopes', DEFAULT_SITE_SCOPES)
        base = project.site_query()
        lang = next(iter(project.queries), 'de')
        return [(lang, base, list(d)) for d in scopes[:self.cfg.get('max_site_queries_per_project', 7)]] if base else []

    def _to_item(self, project, since, q, lang, h, seen):
        url = h.get('url') or ''
        if not url.startswith('http'):
            return None
        canon = canonical_url(url)
        if canon in seen:
            return None
        seen.add(canon)
        domain = domain_of(url)
        kind = classify(domain)
        title = (h.get('title') or '').strip()
        snippet = strip_html(h.get('snippet') or '')
        pub = h.get('published')
        text, scope = snippet, 'snippet'
        if kind == 'video':
            kind = 'social_link'      # a video platform found through a search service is discovery only (the YouTube adapter handles API comments)
        if kind == 'social_link':
            text = snippet or title   # discovery only: link, title, snippet as the search service returned them. The post page is never fetched.
        elif h.get('text'):
            text, scope = strip_html(h['text'])[:8000], 'full'
        if not project.matches(f'{title} {snippet}'):
            # the search engine may know more than the snippet; if robots allows, look at the page before dropping it
            if kind == 'social_link' or not self._can_fetch():
                self.stats['off_topic_dropped'] += 1
                return None
        if kind != 'social_link' and scope != 'full' and self._can_fetch():
            ft, sc, why = full_text(self.http, url, self.cfg.get('fulltext_max_chars', 8000))
            self._fulltext_done += 1
            if sc == 'full':
                text, scope = ft, 'full'
                self.stats['full_text'] += 1
            elif why == ROBOTS_BLOCKED:
                self.stats['robots_blocked'] += 1
        if not project.matches(f'{title} {text}'):
            self.stats['off_topic_dropped'] += 1
            return None
        radar_match = project.relevance(title, snippet)          # gate on what the search service showed (title + snippet), not on the full page
        self.stats[radar_match] = self.stats.get(radar_match, 0) + 1
        title, text = mask_for_kind(kind, title), mask_for_kind(kind, text)
        if scope == 'snippet':
            self.stats['snippet_only'] += 1
        date_known = pub is not None
        if pub is None:
            pub = dt.datetime.now(UTC)
            self.stats['undated'] += 1
        elif pub < since:
            self.stats['before_since_dropped'] += 1
            return None
        langs = {'de': 'de', 'fr': 'fr', 'en': 'en'}
        country = {'de': 'DE', 'fr': 'FR'}.get(lang)
        return Item(self.name, project.id, url, title or domain, text or title, pub, domain, langs.get(lang), country,
                    'Other', None, 0, self.source_terms, q, True, kind, None, None, scope, date_known, radar_match)

    def _can_fetch(self):
        return bool(self.cfg.get('fulltext', True)) and self._fulltext_done < self.cfg.get('max_fulltext_per_run', 60)
