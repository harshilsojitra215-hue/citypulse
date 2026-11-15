"""Stage 1: ingest, validate and normalise the export into the `posts` table.

Checks (the stage stops if one fails):
- every record has mention_id, published_at, url, media_type_name
- mention_id is unique
- row count in == row count out
Privacy: every author string of a record is replaced by [USER] in its title and text, plus
"verfasst ... von <x>", "geschrieben von <x>" and @handles. Then the `authors` field is dropped
(only `has_author` is kept). Names inside news body text (journalists, quoted officials) are not masked;
the export shows short snippets only.
"""
import html
import json
import os
import re
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import DATASET_END, log, path, write_table  # noqa: E402

REQUIRED = ['mention_id', 'published_at', 'url', 'media_type_name']
PAYWALL = re.compile(r'vollen zugang freischalten|jetzt (?:weiterlesen|abonnieren)|stimme\+|artikel ist exklusiv|réservé aux abonnés', re.I)


def platform(url):
    u = str(url).lower()
    for key, name in [('youtube.', 'youtube'), ('youtu.be', 'youtube'), ('instagram.', 'instagram'),
                      ('facebook.', 'facebook'), ('reddit.', 'reddit'), ('linkedin.', 'linkedin'),
                      ('tiktok.', 'tiktok'), ('t.me/', 'telegram'), ('bsky.', 'bluesky'),
                      ('mastodon', 'mastodon'), ('troet.', 'mastodon'), ('x.com/', 'x'), ('twitter.', 'x')]:
        if key in u:
            return name
    return 'web'


def norm_source(s):
    return re.sub(r'^(www\d?|m|amp)\.', '', str(s).lower().strip())


def clean_text(s):
    if not isinstance(s, str):
        return ''
    s = html.unescape(s)
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


BYLINE = re.compile(r'(?i)((?:verfasst am [\d.]+|geschrieben|antwort|kommentar zu .{0,140}?|posted by|par)\s+von\s+|@)([\w.\-]{2,40})')


def mask(text, authors):
    if not text:
        return text
    for a in authors or []:
        a = str(a).strip()
        if len(a) >= 3 and a.lower() not in ('redaktion', 'kontaktieren sie', 'dpa', 'swr', 'wdr'):
            text = re.sub(re.escape(a), '[USER]', text, flags=re.I)
    return BYLINE.sub(lambda m: m.group(1) + '[USER]', text)


def normalise(records, origin='dataset'):
    df = pd.DataFrame(records)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise SystemExit(f'ingest: missing columns {missing}')
    bad = df[REQUIRED].isna().any(axis=1).sum()
    if bad:
        raise SystemExit(f'ingest: {bad} records miss a required field')
    out = pd.DataFrame()
    out['post_id'] = df['mention_id'].astype(str)
    ts = pd.to_datetime(df['published_at'], utc=True)
    out['published_at'] = ts
    out['day'] = ts.dt.tz_localize(None).dt.normalize()
    out['week'] = (ts.dt.tz_localize(None).dt.normalize()
                   - pd.to_timedelta(ts.dt.weekday, unit='D'))
    out['media_type'] = df['media_type_name'].astype(str)
    out['platform'] = df['url'].map(platform)
    out['source'] = df.get('source_name', pd.Series([''] * len(df))).map(norm_source)
    out['url'] = df['url'].astype(str)
    out['language'] = df.get('language_code', pd.Series([None] * len(df))).fillna('unknown').astype(str)
    out['country_code'] = df.get('country_code', pd.Series([None] * len(df)))
    auth = df.get('authors', pd.Series([None] * len(df)))
    auth_l = auth.map(lambda a: a if isinstance(a, list) else ([a] if isinstance(a, str) and a else []))
    out['title'] = [mask(clean_text(t), a) for t, a in zip(df.get('title', pd.Series([''] * len(df))), auth_l)]
    out['text'] = [mask(clean_text(t), a) for t, a in zip(df.get('content', pd.Series([''] * len(df))), auth_l)]
    out['text_len'] = out['text'].str.len()
    out['is_paywall_stub'] = out['text'].str.contains(PAYWALL) & (out['text_len'] < 1500)
    out['is_truncated'] = out['text'].str.rstrip().str.endswith(('...', '…'))
    sent = pd.to_numeric(df.get('sentiment', pd.Series([None] * len(df))), errors='coerce')
    out['vendor_sentiment'] = sent.where(sent.isin([-1, 0, 1])).astype('Int64')
    out['engagements'] = pd.to_numeric(df.get('engagements', 0), errors='coerce').fillna(0).astype('int64')
    out['reach'] = pd.to_numeric(df.get('reach', None), errors='coerce')
    out['has_author'] = auth.map(lambda a: bool(a) and str(a).strip() not in ('', '[]', 'None', 'nan'))
    out['origin'] = origin
    out['new_since_dataset'] = ts > pd.Timestamp(DATASET_END)
    out['ingested_at'] = pd.Timestamp.now(tz='UTC')
    if out['post_id'].duplicated().any():
        raise SystemExit(f"ingest: {out['post_id'].duplicated().sum()} duplicate mention_id")
    if len(out) != len(df):
        raise SystemExit('ingest: row count changed')
    return out


def run(limit=None):
    t = time.time()
    src = path('raw_json')
    log('ingest', f'reading {os.path.basename(src)} ({os.path.getsize(src) / 1e6:.0f} MB)')
    with open(src, encoding='utf-8') as f:
        records = json.load(f)
    if limit:
        records = records[:limit]
    posts = normalise(records)
    del records
    write_table('posts', posts)
    log('ingest', f"posts={len(posts):,} first={posts.published_at.min()} last={posts.published_at.max()} "
                  f"paywall_stubs={int(posts.is_paywall_stub.sum()):,} no_vendor_sentiment={int(posts.vendor_sentiment.isna().sum()):,} "
                  f"({time.time() - t:.0f}s)")
    return posts


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None, help='only the first N records (smoke test)')
    run(ap.parse_args().limit)
