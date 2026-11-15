"""Exa search API (exa.ai): web search with publish-date filter. POST https://api.exa.ai/search, key in header x-api-key.
Free: 10 USD credits per month, no card (exa.ai/pricing, checked 14 Nov 2026). About 4 USD per 1000 searches plus 1 USD per 1000 pages of highlights.
Kept per hit: URL, title, highlight snippet, published date, domain. Full text only where robots.txt allows (see _search.full_text).
Social platforms: link, title and snippet only, never fetched. Terms: exa.ai/terms; read the storage clause before keeping results for the city."""
from ._search import SearchAdapter, parse_date


class Exa(SearchAdapter):
    name = 'exa'
    key_env = 'EXA_API_KEY'
    source_terms = 'Exa search API (exa.ai). URL, title, snippet, date. Copyright stays with the publisher; we link back.'
    URL = 'https://api.exa.ai/search'

    def search(self, query, since, lang, domains=None, must_have=None):
        body = {'query': query, 'type': 'auto', 'numResults': self.cfg.get('num_results', 10),
                'startPublishedDate': since.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                'contents': {'highlights': {'maxCharacters': 600}}}
        if domains:
            body['includeDomains'] = domains
        if must_have:
            body['includeText'] = [must_have]       # Exa keeps only pages that contain this text (one phrase, up to 5 words)
        data = self.http.post_json(self.URL, body, headers={'x-api-key': self.key()}, interval=self.interval)
        self.cost_usd += float(((data.get('costDollars') or {}).get('total')) or 0)
        out = []
        for r in data.get('results', []):
            hl = r.get('highlights') or []
            out.append({'url': r.get('url'), 'title': r.get('title'), 'snippet': ' ... '.join(hl) if isinstance(hl, list) else str(hl),
                        'published': parse_date(r.get('publishedDate')), 'text': None})
        return out

    def quota_error(self, e):
        if e.status in (402, 429):
            return 'credits used up or rate limit (HTTP %d)' % e.status
        return None
