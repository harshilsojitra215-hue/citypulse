"""Apify, DISCOVERY ONLY: a Google search-results actor (default apify/google-search-scraper) run with the same site-scoped queries
(site:reddit.com ...). Stored: link, title, snippet, platform. Never an actor that logs in to, crawls or downloads posts from a social
platform, and never the post page itself. Off by default (enabled: false) until APIFY_TOKEN exists.
Platform terms, one sentence: a search-results scraper reads Google result pages, which Google's terms restrict (the Google v. SerpApi
case is still open), so switching this adapter on is the owner's call; Exa and Tavily do the same discovery through licensed APIs.
Budget: max_results_per_query and max_total_usd (the run stops asking once the estimate is used up). Sync run endpoint, token in the
Authorization header, never in the URL."""
from ..core import SkipSource
from ._search import SearchAdapter, parse_date


class Apify(SearchAdapter):
    name = 'apify'
    key_env = 'APIFY_TOKEN'
    source_terms = 'Apify search-results actor (discovery only): link, title, snippet. No post content, no logins.'
    API = 'https://api.apify.com/v2/acts/%s/run-sync-get-dataset-items'

    def __init__(self, cfg, http):
        super().__init__(cfg, http)
        self.actor = cfg.get('actor', 'apify~google-search-scraper').replace('/', '~')
        self.cost_per_page_usd = cfg.get('usd_per_serp_page', 0.0025)     # list price starts at 1.8 USD per 1000 pages; this is pessimistic
        self.max_total = cfg.get('max_total_usd', 4.0)

    def search(self, query, since, lang, domains=None, must_have=None):
        if self.cost_usd >= self.max_total:
            self.quota_hit = f'run budget of {self.max_total} USD used up'
            raise SkipSource('apify: ' + self.quota_hit)
        q = query if not domains else query + ' (' + ' OR '.join('site:' + d for d in domains) + ')'
        body = {'queries': q, 'maxPagesPerQuery': 1, 'resultsPerPage': min(self.cfg.get('max_results_per_query', 10), 20),
                'languageCode': lang if lang in ('de', 'fr', 'en') else 'de', 'countryCode': 'fr' if lang == 'fr' else 'de',
                'afterDate': since.strftime('%Y-%m-%d'), 'saveHtml': False, 'saveHtmlToKeyValueStore': False}
        rows = self.http.post_json(self.API % self.actor, body, headers={'Authorization': 'Bearer ' + self.key()},
                                   interval=self.interval, retries=0)
        self.cost_usd += self.cost_per_page_usd
        out = []
        for page in rows if isinstance(rows, list) else []:
            for r in page.get('organicResults', []) or []:
                out.append({'url': r.get('url'), 'title': r.get('title'), 'snippet': r.get('description'),
                            'published': parse_date(r.get('date')), 'text': None})
        return out[:self.cfg.get('max_results_per_query', 10)]

    def quota_error(self, e):
        if e.status in (402, 403, 429):
            return 'Apify credits or limit used up (HTTP %d)' % e.status
        return None
