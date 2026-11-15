"""GDELT DOC 2.0 API: news articles worldwide, updated every 15 minutes, free, no key.
Fields: url, title, seendate, domain, language, sourcecountry. No article text. Asks for 1 request per 5 s."""
import datetime as dt
from ..core import Adapter, Item, UTC

LANG = {'de': 'german', 'fr': 'french', 'en': 'english'}
LCODE = {'German': 'de', 'French': 'fr', 'English': 'en'}


class Gdelt(Adapter):
    name = 'gdelt'
    source_terms = 'GDELT Project, free use with citation (gdeltproject.org/about.html). Headlines and links only.'
    URL = 'https://api.gdeltproject.org/api/v2/doc/doc'

    def fetch(self, project, since):
        out, seen = [], set()
        now = dt.datetime.now(UTC)
        for lang, queries in project.queries.items():
            for q in queries:
                full = f'{q} sourcelang:{LANG[lang]}' if lang in LANG else q
                data = self.http.json(self.URL, interval=self.interval, robots=False, params={
                    'query': full, 'mode': 'artlist', 'format': 'json', 'sort': 'datedesc',
                    'maxrecords': self.cfg.get('max_records', 250),
                    'startdatetime': since.strftime('%Y%m%d%H%M%S'), 'enddatetime': now.strftime('%Y%m%d%H%M%S')})
                for a in data.get('articles', []):
                    if a['url'] in seen:
                        continue
                    seen.add(a['url'])
                    title = a.get('title', '')
                    hit = project.matches(title)     # GDELT matched the body; we only see the title. Keep all, flag title hits.
                    pub = dt.datetime.strptime(a['seendate'], '%Y%m%dT%H%M%SZ').replace(tzinfo=UTC)
                    out.append(Item(self.name, project.id, a['url'], title, title, pub, a.get('domain', ''),
                                    LCODE.get(a.get('language')), None, 'News', None, 0, self.source_terms, full, hit))
        return out
