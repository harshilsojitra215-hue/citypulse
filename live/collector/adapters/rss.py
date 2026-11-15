"""Outlet and official RSS feeds listed in projects.yaml. One download per feed per run, then filtered per project.
robots.txt is honoured. Feeds that are paywalled, forbid bots or do not exist are not listed (see STADT_LIVE_SOURCES.md)."""
import datetime as dt
import email.utils
import xml.etree.ElementTree as ET
from ..core import Adapter, HttpError, Item, UTC, strip_html

NS = {'atom': 'http://www.w3.org/2005/Atom', 'content': 'http://purl.org/rss/1.0/modules/content/'}


def _date(s):
    if not s:
        return None
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(UTC)
    except Exception:
        try:
            return dt.datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone(UTC)
        except Exception:
            return None


class Rss(Adapter):
    name = 'rss'
    source_terms = 'Public RSS feed of the outlet or city. Headline, summary, link, date. Copyright stays with the publisher; we link back.'

    def __init__(self, cfg, http):
        super().__init__(cfg, http)
        self._cache = {}
        self.feed_status = {}

    def _feed(self, f):
        if f['id'] in self._cache:
            return self._cache[f['id']]
        try:
            body, _ = self.http.get(f['url'], interval=self.interval, robots=True)
            root = ET.fromstring(body)
            entries = []
            for it in list(root.iter('item')) + list(root.iter('{%s}entry' % NS['atom'])):
                link = it.findtext('link') or ''
                if not link:
                    le = it.find('atom:link', NS)
                    link = le.get('href') if le is not None else ''
                desc = (it.findtext('description') or it.findtext('content:encoded', namespaces=NS)
                        or it.findtext('atom:summary', namespaces=NS) or '')
                pub = _date(it.findtext('pubDate') or it.findtext('atom:updated', namespaces=NS)
                            or it.findtext('atom:published', namespaces=NS))
                entries.append((strip_html(it.findtext('title') or ''), strip_html(desc), link.strip(), pub))
            self.feed_status[f['id']] = ('ok', len(entries))
        except (HttpError, ET.ParseError) as e:
            self.feed_status[f['id']] = ('error', str(e)[:100])
            entries = None
        self._cache[f['id']] = entries
        return entries

    def fetch(self, project, since):
        out, errs = [], []
        for f in self.cfg.get('feeds', []):
            entries = self._feed(f)
            if entries is None:
                errs.append(f['id'])
                continue
            for title, desc, link, pub in entries:
                if not link or pub is None or pub < since:
                    continue
                if project.matches(title + ' ' + desc):
                    text = f'{title}. {desc}' if desc else title
                    out.append(Item(self.name, project.id, link, title, text, pub, f['outlet'], f.get('language'),
                                    f.get('country'), 'Other' if f.get('kind') == 'official' else 'News', None, 0,
                                    self.source_terms, f['id'], kind='official_news' if f.get('kind') == 'official' else 'article'))
        feeds = self.cfg.get('feeds', [])
        if errs and len(errs) == len(feeds):      # some feeds failing is 'partial' (see feed_status), all failing is a failure
            raise HttpError(-1, 'all feeds failed: ' + ', '.join(f'{e} ({self.feed_status[e][1]})' for e in errs))
        return out
