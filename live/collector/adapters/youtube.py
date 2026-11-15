"""YouTube Data API v3 (official, free key from Google Cloud, no card). Search videos by query and date, then read comment threads.
Quota (developers.google.com/youtube/v3/determine_quota_cost, checked 14 Nov 2026): 10,000 units per day; search.list is capped at
100 calls per day; commentThreads.list costs 1 unit. We cap search calls per run (max_search_calls) and comment pages per video.
Kept: video title, description snippet, date, URL; per comment: text (handles masked), date, video URL with comment id, like count,
HASHED author id. Never the author name, handle, avatar or channel URL.
Retention: YouTube's developer policy limits how long non-authorized API data may be stored (30 days, then delete or refresh). See RADAR_SETUP.md.
Replies: the up to 5 replies that commentThreads returns inline are kept; longer reply chains are not paged."""
import datetime as dt

from ..core import Adapter, HttpError, Item, SkipSource, UTC, author_hash, get_env, mask_handles
from ._search import parse_date


class YouTube(Adapter):
    name = 'youtube'
    key_env = 'YOUTUBE_API_KEY'
    source_terms = 'YouTube Data API v3 (YouTube API Services terms). Text, date, URL, hashed author id only.'
    SEARCH = 'https://www.googleapis.com/youtube/v3/search'
    THREADS = 'https://www.googleapis.com/youtube/v3/commentThreads'

    def __init__(self, cfg, http):
        super().__init__(cfg, http)
        self.key_env = cfg.get('key_env', self.key_env)
        self.search_calls = 0
        self.warnings = []
        self.quota_hit = None
        self.stats = {'queries': 0, 'videos': 0, 'comments': 0, 'videos_comments_off': 0}
        self._videos_done = set()

    def key(self):
        k = get_env(self.key_env)
        if not k:
            raise SkipSource(f'youtube: no key ({self.key_env} not set), source skipped')
        return k

    def _api(self, url, params):
        try:
            return self.http.json(url, interval=self.interval, robots=False, params={**params, 'key': self.key()}, retries=0)
        except HttpError as e:
            if e.status == 403 and 'quotaExceeded' in (e.body or ''):
                self.quota_hit = 'daily quota used up'
                self.warnings.append('youtube: daily quota used up (quotaExceeded); stopped, items so far are kept')
                raise SkipSource('youtube: daily quota used up')
            raise

    def fetch(self, project, since):
        self.key()
        if self.quota_hit:
            raise SkipSource('youtube: ' + self.quota_hit)
        out = []
        maxq = self.cfg.get('max_queries_per_project', 2)
        queries = [(lang, q) for lang, qs in project.queries.items() for q in qs][:maxq]
        try:
            for lang, q in queries:
                for fresh in (True, False):
                    if not fresh and not self.cfg.get('include_older_videos', True):
                        continue
                    if self.search_calls >= self.cfg.get('max_search_calls', 60):
                        self.warnings.append('youtube: max_search_calls reached, remaining queries not run')
                        return out
                    params = {'part': 'snippet', 'q': q, 'type': 'video', 'maxResults': self.cfg.get('max_videos', 8),
                              'order': 'date' if fresh else 'relevance'}
                    if fresh:
                        params['publishedAfter'] = since.strftime('%Y-%m-%dT%H:%M:%SZ')
                    if lang in ('de', 'fr', 'en'):
                        params['relevanceLanguage'] = lang
                    self.search_calls += 1
                    self.stats['queries'] += 1
                    data = self._api(self.SEARCH, params)
                    for v in data.get('items', []):
                        vid = (v.get('id') or {}).get('videoId')
                        sn = v.get('snippet') or {}
                        if not vid or vid in self._videos_done:
                            continue
                        title, desc = sn.get('title', ''), sn.get('description', '')
                        if not project.matches(f'{title} {desc}'):
                            continue
                        self._videos_done.add(vid)
                        url = f'https://www.youtube.com/watch?v={vid}'
                        pub = parse_date(sn.get('publishedAt')) or dt.datetime.now(UTC)
                        if pub >= since:
                            out.append(Item(self.name, project.id, url, title, (title + '. ' + desc).strip(), pub, 'youtube.com', lang, None,
                                            'Video', author_hash('youtube', sn.get('channelId', '')), 0, self.source_terms, q,
                                            True, 'video', None, None, 'snippet', True))
                            self.stats['videos'] += 1
                        out += self._comments(project, since, vid, url, lang, q)
        except SkipSource:
            if not out:
                raise
        return out

    def _comments(self, project, since, vid, vurl, lang, q):
        out, token = [], None
        for _ in range(self.cfg.get('max_comment_pages', 2)):
            params = {'part': 'snippet,replies', 'videoId': vid, 'maxResults': 100, 'order': 'time', 'textFormat': 'plainText'}
            if token:
                params['pageToken'] = token
            try:
                data = self._api(self.THREADS, params)
            except HttpError as e:
                if e.status == 403 and 'commentsDisabled' in (e.body or ''):
                    self.stats['videos_comments_off'] += 1
                    return out
                if e.status == 404:
                    return out
                raise
            for th in data.get('items', []):
                top = (th.get('snippet') or {}).get('topLevelComment') or {}
                comments = [top] + list((th.get('replies') or {}).get('comments') or [])
                for c in comments:
                    sn = c.get('snippet') or {}
                    pub = parse_date(sn.get('publishedAt'))
                    text = mask_handles(sn.get('textDisplay') or sn.get('textOriginal') or '').strip()
                    if not text or not pub or pub < since:
                        continue
                    ident = ((sn.get('authorChannelId') or {}).get('value')) or ''
                    out.append(Item(self.name, project.id, f"{vurl}&lc={c.get('id', '')}", text[:120], text, pub, 'youtube.com', lang, None,
                                    'Forum', author_hash('youtube', ident) if ident else None, int(sn.get('likeCount') or 0),
                                    self.source_terms, q, project.matches(text), 'video_comment', None, None, 'full', True))
                    self.stats['comments'] += 1
            token = data.get('nextPageToken')
            if not token:
                break
        return out
