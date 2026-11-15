"""Stage 12 (optional): new public news items after the dataset end (27 Oct 2026).

Source: Google News RSS search (public feed, no key, no login). It gives title, link, date and
outlet, no article text. Items become posts with origin='live' and new_since_dataset=true and go
through the same stages (candidates, labels, export) as the dataset.
Not run by run_all unless --live is given. Ask the city first whether live items may be shown (open question 5).
A saved snapshot (data/live_snapshot.json) is the offline fallback for the stage demo.
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import CFG, DATA, DATASET_END, log, read_table, write_table  # noqa: E402
from stages.s01_ingest import normalise  # noqa: E402

SNAP = os.path.join(DATA, 'live_snapshot.json')
UA = 'Mozilla/5.0 (research prototype; city-debate-monitor)'


def fetch(query, days):
    lang = 'fr' if re.search(r'[âéè]|câble', query, re.I) else 'de'
    gl = 'FR' if lang == 'fr' else 'DE'
    q = urllib.parse.quote(f'{query} when:{days}d')
    url = f'https://news.google.com/rss/search?q={q}&hl={lang}&gl={gl}&ceid={gl}:{lang}'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    items = []
    for it in root.iter('item'):
        title = it.findtext('title') or ''
        src = it.find('source')
        items.append({'mention_id': 'live:' + hashlib.sha1((it.findtext('link') or '').encode()).hexdigest()[:12],
                      'published_at': parsedate_to_datetime(it.findtext('pubDate')).isoformat(),
                      'url': it.findtext('link'), 'media_type_name': 'News',
                      'source_name': (src.get('url') if src is not None else '') or '',
                      'language_code': lang, 'title': title, 'content': title, 'sentiment': -99, 'engagements': 0,
                      'query': query})
    return items


def run(offline=False):
    if offline:
        if not os.path.exists(SNAP):
            log('live', 'no snapshot yet; run once with network')
            return None
        items = json.load(open(SNAP, encoding='utf-8'))['items']
    else:
        items = []
        for q in CFG['live']['queries']:
            try:
                got = fetch(q, CFG['live']['days'])
                items += got
                log('live', f'{q!r}: {len(got)} items')
            except Exception as e:
                log('live', f'{q!r}: failed ({e})')
            time.sleep(1)
        json.dump({'fetched_at': pd.Timestamp.now(tz='UTC').isoformat(), 'items': items}, open(SNAP, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
    if not items:
        return None
    seen, uniq = set(), []
    for it in items:
        if it['url'] not in seen:
            seen.add(it['url'])
            uniq.append(it)
    live = normalise(uniq, origin='live')
    new = live[live.published_at > pd.Timestamp(DATASET_END)]
    posts = read_table('posts')
    posts = posts[posts.origin != 'live']
    merged = pd.concat([posts, new], ignore_index=True).drop_duplicates('post_id')
    write_table('posts', merged)
    log('live', f'{len(uniq)} unique items, {len(new)} published after {DATASET_END[:10]} added as origin=live')
    return new


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--offline', action='store_true', help='use the saved snapshot instead of the network')
    run(ap.parse_args().offline)
