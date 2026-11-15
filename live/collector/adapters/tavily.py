"""Tavily search API (tavily.com): POST https://api.tavily.com/search, Bearer key. topic 'news' adds published dates.
Free: 1000 credits per month, no card; basic search = 1 credit (docs.tavily.com, checked 14 Nov 2026).
Kept per hit: URL, title, content snippet, published date, domain. Social platforms: link, title, snippet only."""
from ._search import SearchAdapter, parse_date


class Tavily(SearchAdapter):
    name = 'tavily'
    key_env = 'TAVILY_API_KEY'
    source_terms = 'Tavily search API (tavily.com). URL, title, snippet, date. Copyright stays with the publisher; we link back.'
    URL = 'https://api.tavily.com/search'

    def search(self, query, since, lang, domains=None, must_have=None):
        out = []
        for topic in (['general'] if domains else self.cfg.get('topics', ['general', 'news'])):
            body = {'query': query, 'topic': topic, 'max_results': self.cfg.get('max_results', 10), 'search_depth': 'basic',
                    'start_date': since.strftime('%Y-%m-%d'), 'include_usage': True}
            if domains:
                body['include_domains'] = domains
            data = self.http.post_json(self.URL, body, headers={'Authorization': 'Bearer ' + self.key()}, interval=self.interval)
            credits = float((data.get('usage') or {}).get('credits') or 0)
            self.cost_usd += credits * 0.008
            self.stats['credits'] = self.stats.get('credits', 0) + credits
            for r in data.get('results', []):
                out.append({'url': r.get('url'), 'title': r.get('title'), 'snippet': r.get('content'),
                            'published': parse_date(r.get('published_date')), 'text': None})
        return out

    def quota_error(self, e):
        if e.status in (402, 429, 432, 433):
            return 'credits or plan limit used up (HTTP %d)' % e.status
        return None
