"""Bluesky public search (AT Protocol AppView, api.bsky.app). No login needed for searchPosts at this host (tested 14 Nov 2026).
Kept per post: text, date, platform, URL, hashed author id, engagement count.
Not kept: handle, display name, avatar, profile text. Why: we only need the debate, not who said it (brief: collect only what is needed).
The URL contains the author's DID (a pseudonymous account id). It is kept as the link to the original; the dashboard should show it as a link icon only."""
import datetime as dt
from ..core import Adapter, Item, UTC, author_hash, mask_handles


class Bluesky(Adapter):
    name = 'bluesky'
    source_terms = 'Bluesky public AT Protocol API (bsky.app terms and rate limits). Text, date, URL, hashed author id only.'
    URL = 'https://api.bsky.app/xrpc/app.bsky.feed.searchPosts'

    def fetch(self, project, since):
        out, seen = [], set()
        for lang, queries in project.queries.items():
            for q in queries:
                cursor = None
                for _ in range(self.cfg.get('max_pages', 3)):
                    params = {'q': q, 'limit': 100, 'sort': 'latest', 'since': since.strftime('%Y-%m-%dT%H:%M:%SZ')}
                    if cursor:
                        params['cursor'] = cursor
                    data = self.http.json(self.URL, interval=self.interval, robots=False, params=params)
                    for p in data.get('posts', []):
                        if p['uri'] in seen:
                            continue
                        seen.add(p['uri'])
                        rec = p.get('record', {})
                        text = mask_handles(rec.get('text', '')).strip()
                        if not project.matches(text):
                            continue
                        try:
                            pub = dt.datetime.fromisoformat(rec['createdAt'].replace('Z', '+00:00')).astimezone(UTC)
                        except Exception:
                            continue
                        if pub < since:
                            continue
                        did = p['author']['did']
                        url = 'https://bsky.app/profile/%s/post/%s' % (did, p['uri'].rsplit('/', 1)[-1])
                        eng = sum(p.get(k, 0) or 0 for k in ('likeCount', 'repostCount', 'replyCount', 'quoteCount'))
                        langs = rec.get('langs') or [lang]
                        out.append(Item(self.name, project.id, url, text[:120], text, pub, 'bsky.app', langs[0][:2], None,
                                        'Microblog', author_hash('bluesky', did), eng, self.source_terms, q))
                    cursor = data.get('cursor')
                    if not cursor:
                        break
        return out
