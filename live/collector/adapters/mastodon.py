"""Mastodon public hashtag timelines on a few large instances (no login, no token).
Status full-text search needs a token on these servers, so it is not used. Hashtags only.
Kept per post: text, date, URL, hashed author id, engagement count. No handle, display name or avatar. @mentions in the text are masked.
The status URL contains the author's handle (that is how Mastodon URLs look). It is kept as the link to the original only."""
import datetime as dt
from ..core import Adapter, HttpError, Item, UTC, author_hash, mask_handles, strip_html


class Mastodon(Adapter):
    name = 'mastodon'
    source_terms = 'Mastodon public API on mastodon.social / troet.cafe (instance rules apply). Text, date, URL, hashed author id only.'

    def __init__(self, cfg, http):
        super().__init__(cfg, http)
        self._cache = {}
        self.warnings = []     # partial failures (one tag or instance), shown in the run log

    def _tag(self, inst, tag, since):
        k = (inst, tag)
        if k in self._cache:
            return self._cache[k]
        posts, max_id = [], None
        for _ in range(self.cfg.get('max_pages', 3)):
            params = {'limit': 40}
            if max_id:
                params['max_id'] = max_id
            data = self.http.json(f'https://{inst}/api/v1/timelines/tag/{tag}', interval=self.interval, robots=False, params=params)
            if not data:
                break
            posts += data
            max_id = data[-1]['id']
            if dt.datetime.fromisoformat(data[-1]['created_at'].replace('Z', '+00:00')) < since:
                break
        self._cache[k] = posts
        return posts

    def fetch(self, project, since):
        out, seen, errs = [], set(), []
        for inst in self.cfg.get('instances', []):
            for tag in project.hashtags:
                try:
                    posts = self._tag(inst, tag, since)
                except HttpError as e:
                    errs.append(f'{inst}#{tag}: {e}')
                    if str(e) not in self.warnings:
                        self.warnings.append(str(e))
                    continue
                for p in posts:
                    if p.get('uri') in seen or p.get('reblog'):
                        continue
                    seen.add(p.get('uri'))
                    pub = dt.datetime.fromisoformat(p['created_at'].replace('Z', '+00:00')).astimezone(UTC)
                    text = mask_handles(strip_html(p.get('content', '')))
                    if pub < since or not project.matches(text):
                        continue
                    acct = p['account']
                    ident = acct.get('url') or acct.get('acct')
                    eng = (p.get('favourites_count') or 0) + (p.get('reblogs_count') or 0) + (p.get('replies_count') or 0)
                    out.append(Item(self.name, project.id, p['url'], text[:120], text, pub, inst,
                                    (p.get('language') or '')[:2] or None, None, 'Microblog',
                                    author_hash('mastodon', ident), eng, self.source_terms, f'{inst}#{tag}'))
        if errs and not out:
            raise HttpError(-1, '; '.join(errs)[:200])
        return out
