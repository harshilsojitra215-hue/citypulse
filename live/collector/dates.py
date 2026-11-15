"""Date recovery for records the search services returned without a date (mostly Tavily general search).

Why: "what we found since 27 Oct" is only honest when we know when an item was published. A record without a date is shown as
"date unknown", never counted as new evidence after the cutoff.

Order, cheapest and safest first. The first rule that gives a plausible date wins, and the rule is stored in `date_source`:
  1. url      : a date in the link itself (/2026/11/05/, 2026-11-05, 20261105).
  2. text     : a date at the very start of the title or snippet ("[2026-10-06 ·", "05.11.2026 -", "5 Nov 2026 -").
  3. page_meta: the page's own published-date tag (article:published_time, datePublished, <time datetime>), read only for news,
                official and web pages whose robots.txt allows us, never for social platforms or video sites. Only the head
                of the page is read (first 200 KB).
Plausible = between 1 Jan 2024 and tomorrow. Anything else stays unknown. No guessing from "3 days ago" or from the discovery time.
"""
from __future__ import annotations

import datetime as dt
import re

from .core import UTC

SKIP_KINDS = ('social_link', 'social_post', 'video', 'video_comment')
MONTHS = {m: i for i, m in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}
MONTHS.update({'mär': 3, 'mai': 5, 'okt': 10, 'dez': 12, 'janv': 1, 'févr': 2, 'fevr': 2, 'mars': 3, 'avr': 4, 'juin': 6, 'juil': 7,
               'août': 8, 'aout': 8, 'sept': 9, 'déc': 12})

_URL = [re.compile(r'/(20\d\d)/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])(?:/|$|[-_.])'),
        re.compile(r'(?<!\d)(20\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?!\d)'),
        re.compile(r'(?<!\d)(20\d\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)')]
_LEAD_ISO = re.compile(r'^\W{0,4}(20\d\d)-(\d\d)-(\d\d)\b')
_LEAD_DE = re.compile(r'^\W{0,4}(\d{1,2})\.(\d{1,2})\.(20\d\d)\b')
_LEAD_TXT = re.compile(r'^\W{0,4}(\d{1,2})\.?\s+([A-Za-zäéû]{3,5})\.?[a-zäéû]*\s+(20\d\d)\b')
_META = [re.compile(r'''<meta[^>]+(?:property|name|itemprop)=["'](?:article:published_time|og:published_time|datePublished|'''
                    r'''pubdate|publishdate|date|dc\.date|dcterms\.created|parsely-pub-date|sailthru\.date)["'][^>]*content=["']([^"']+)''', re.I),
         re.compile(r'''<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name|itemprop)=["'](?:article:published_time|datePublished)["']''', re.I),
         re.compile(r'"datePublished"\s*:\s*"([^"]+)"'),
         re.compile(r'<time[^>]+datetime=["\']([^"\']+)', re.I)]


def _mk(y, m, d):
    try:
        t = dt.datetime(int(y), int(m), int(d), 12, 0, tzinfo=UTC)   # day only: noon UTC, so no time zone moves the day
    except ValueError:
        return None
    return t if dt.datetime(2024, 1, 1, tzinfo=UTC) <= t <= dt.datetime.now(UTC) + dt.timedelta(days=1) else None


def from_url(url):
    for rx in _URL:
        m = rx.search(url or '')
        if m and (t := _mk(*m.groups())):
            return t
    return None


def from_text(*texts):
    for s in texts:
        s = (s or '').strip()
        if m := _LEAD_ISO.match(s):
            if t := _mk(*m.groups()):
                return t
        if m := _LEAD_DE.match(s):
            if t := _mk(m.group(3), m.group(2), m.group(1)):
                return t
        if m := _LEAD_TXT.match(s):
            mon = MONTHS.get(m.group(2).lower()[:4]) or MONTHS.get(m.group(2).lower()[:3])
            if mon and (t := _mk(m.group(3), mon, m.group(1))):
                return t
    return None


def parse_any(s):
    s = (s or '').strip()
    try:
        t = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
        t = (t if t.tzinfo else t.replace(tzinfo=UTC)).astimezone(UTC)
        return t if dt.datetime(2024, 1, 1, tzinfo=UTC) <= t <= dt.datetime.now(UTC) + dt.timedelta(days=1) else None
    except ValueError:
        m = re.match(r'(20\d\d)-(\d\d)-(\d\d)', s)
        return _mk(*m.groups()) if m else None


def from_page(http, url, max_bytes=200_000):
    """Published date from the page head, only where robots.txt allows us. Returns (datetime or None, note)."""
    try:
        if not http.robots_ok(url):
            return None, 'robots.txt disallows'
        body, ctype = http.get(url, interval=1.5, robots=True, accept='text/html', max_bytes=max_bytes, retries=0)
    except Exception as e:      # one page must never stop the run
        return None, type(e).__name__
    if 'html' not in (ctype or '').lower():
        return None, 'not html'
    html = body.decode('utf-8', 'replace')
    for rx in _META:
        for m in rx.finditer(html):
            if t := parse_any(m.group(1)):
                return t, ''
    return None, 'no date tag'


_ACTIVITY = re.compile(r'^[\s\-*•]{0,4}\[(20\d\d)-(\d\d)-(\d\d) · [^\]]{0,120}\]')   # also "- [2026-10-06 · ...]" list items


def fix_activity_dates(store, log=print):
    """Social profile pages (e.g. linkedin.com/in/...) carry the date of the activity at the start of their text:
    "[2026-10-06 · [USER] shared this] ...". The search service dates such a page by when it crawled it, which can be weeks
    later (15 Nov: three LinkedIn pages dated 28 Oct / 4 Nov whose activity was 19 Aug, 6 Oct and 12 Oct were counted as new).
    The activity date in the stored text wins, for known and unknown dates alike. Idempotent; never touches other records."""
    db = store.db
    rows = db.execute("SELECT key, published_at, title, text FROM items WHERE dup_of IS NULL").fetchall()
    n = 0
    for key, pub, title, text in rows:
        m = _ACTIVITY.match((text or '').strip()) or _ACTIVITY.match((title or '').strip())
        t = _mk(*m.groups()) if m else None
        if t and (pub or '')[:10] != t.strftime('%Y-%m-%d'):
            db.execute('UPDATE items SET published_at=?, date_known=1, date_source=? WHERE key=?',
                       (t.strftime('%Y-%m-%dT%H:%M:%S+0000'), 'activity date in the text', key))
            n += 1
    db.commit()
    log(f"activity dates: {n} records re-dated from the date in their own text")
    return n


def recover_dates(store, http=None, keys=None, fetch_pages=True, max_pages=400, log=print):
    """Fill published_at for date_known=0 records (all of them, or only `keys`). Never changes a known date and never creates a new
    version (dates are metadata, not content). Returns counts per rule."""
    db = store.db
    q = 'SELECT key, url, kind, title, text FROM items WHERE date_known = 0 AND dup_of IS NULL'
    rows = db.execute(q).fetchall()
    if keys is not None:
        keys = set(keys)
        rows = [r for r in rows if r[0] in keys]
    counts = {'checked': len(rows), 'url': 0, 'text': 0, 'page_meta': 0, 'still_unknown': 0, 'pages_read': 0, 'pages_refused': 0}
    pages = 0
    for key, url, kind, title, text in rows:
        t, rule = from_url(url), 'url'
        if not t:
            t, rule = from_text(title, text), 'text'
        if not t and fetch_pages and http is not None and kind not in SKIP_KINDS and pages < max_pages:
            pages += 1
            t, note = from_page(http, url)
            rule = 'page_meta'
            counts['pages_read'] += int(note == '' or note == 'no date tag')
            counts['pages_refused'] += int(note == 'robots.txt disallows')
        if t:
            db.execute('UPDATE items SET published_at=?, date_known=1, date_source=? WHERE key=?',
                       (t.strftime('%Y-%m-%dT%H:%M:%S+0000'), rule, key))
            counts[rule] += 1
        else:
            counts['still_unknown'] += 1
    db.commit()
    log(f"date recovery: {counts['checked']} undated checked; found {counts['url']} from the link, {counts['text']} from the text, "
        f"{counts['page_meta']} from the page's date tag; {counts['still_unknown']} stay 'date unknown' "
        f"({counts['pages_read']} pages read, {counts['pages_refused']} refused by robots.txt)")
    return counts
