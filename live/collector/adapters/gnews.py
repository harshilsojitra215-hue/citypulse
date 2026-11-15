"""Google News RSS search. Title, link, date, outlet. No article text.
Extends the idea of app/live.py and pipeline/stages/s12_live.py: queries come from projects.yaml, `after:` date instead of when:Nd.
NOTE: robots.txt of news.google.com disallows /rss for generic crawlers; the feed is offered to feed readers.
We do not apply robots.txt here, which is a team decision (see STADT_LIVE_SOURCES.md). GDELT is the safer primary news source."""
import email.utils
import xml.etree.ElementTree as ET
from ..core import Adapter, Item, UTC


class GNews(Adapter):
    name = 'gnews'
    source_terms = 'Google News RSS: personal, non-commercial feed use, attribute Google News and the publisher, link to the original.'

    def fetch(self, project, since):
        out = []
        for lang, queries in project.queries.items():
            gl, ceid = ('FR', 'FR:fr') if lang == 'fr' else ('DE', 'DE:de') if lang == 'de' else ('US', 'US:en')
            for q in queries:
                body, _ = self.http.get('https://news.google.com/rss/search', interval=self.interval, robots=False, params={
                    'q': f'{q} after:{since.date().isoformat()}', 'hl': lang, 'gl': gl, 'ceid': ceid})
                for it in ET.fromstring(body).iter('item'):
                    title = (it.findtext('title') or '').strip()
                    src = it.find('source')
                    outlet = (src.text or '').strip() if src is not None else ''
                    if outlet and title.endswith(' - ' + outlet):
                        title = title[:-len(outlet) - 3]
                    try:
                        pub = email.utils.parsedate_to_datetime(it.findtext('pubDate')).astimezone(UTC)
                    except Exception:
                        continue
                    if pub < since:
                        continue
                    hit = project.matches(title)   # Google matched the body; we only see the title. Keep all, flag title hits.
                    domain = (src.get('url') if src is not None else '') or outlet
                    domain = domain.replace('https://', '').replace('http://', '').strip('/')
                    out.append(Item(self.name, project.id, it.findtext('link'), title, title, pub, domain, lang,
                                    None, 'News', None, 0, self.source_terms, q, hit))
        return out
