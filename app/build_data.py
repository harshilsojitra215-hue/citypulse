"""Build the data snapshots the CityPulse website reads.

Run (from the repo root):
    python -I -X utf8 app/build_data.py                 # historical part stays "awaiting the final run"
    python -I -X utf8 app/build_data.py --history pilot # preview with the v1 export (14 Nov), marked provisional
    python -I -X utf8 app/build_data.py --history final # after the final run: show its numbers as the result

Inputs (read only, never written):
    live/out/update/latest.json        the last "Update now" receipt (Harshil's live part)
    pipeline/data/export/data.json     the pipeline export (contract: pipeline/CONTRACT.md)
    pipeline/reference/faq_heilbronn.json   the city's official figures (FAQ page)

Outputs (app/data/, plain JS so the page also works from file:// with no server):
    live.js     window.CP_LIVE      receipt meta + the items found since 27 Oct (no snippets, no authors)
    history.js  window.CP_HISTORY   the pipeline export, trimmed to the keys the page reads
    facts.js    window.CP_FACTS     official figures from the city's FAQ
    config.js   window.CP_CONFIG    which state the historical part shows (awaiting / pilot / final)

Rules: no author names or handles leave this script (the inputs carry none; titles were masked upstream).
Standard library only.
"""
import os, re, sys, json, argparse, datetime as dt

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
OUT = os.path.join(APP, 'data')

LIVE = os.path.join(ROOT, 'live', 'out', 'update', 'latest.json')
HIST = os.path.join(ROOT, 'pipeline', 'data', 'export', 'data.json')
FAQ = os.path.join(ROOT, 'pipeline', 'reference', 'faq_heilbronn.json')

LIVE_ITEM_KEYS = ['id', 'radar_project', 'counted_project', 'llm_project', 'date', 'date_known', 'date_class',
                  'date_source', 'discovered_at', 'kind', 'source', 'collector_source', 'url', 'title',
                  'label_state', 'stance', 'voice', 'confidence', 'agreement_stance', 'n_runs', 'label_source',
                  'new_this_update', 'url_withheld']
POST_KEYS = ['id', 'date', 'project', 'source', 'platform', 'media_type', 'language', 'url', 'title', 'stance',
             'voice', 'arguments', 'confidence', 'label_source', 'cluster_size', 'new_since_dataset']
HIST_KEYS = ['meta', 'funnel', 'funnel_live', 'projects', 'weekly', 'stance', 'arguments', 'events', 'peaks',
             'placebo', 'faq', 'faq_figure_differs', 'reliability']


# Links that name an account are withheld, as in the collector's export; @handles in titles are masked.
HANDLE_URL = re.compile(r'/@[^/?#]+|(?:^|//)(?:www\.)?(?:x|twitter)\.com/(?!i/|search)[^/?#]+|tiktok\.com/@|'
                        r'facebook\.com/(?!\d+/|groups/\d+|watch|share|events)[A-Za-z][^/?#]*|instagram\.com/(?!p/|reel/|tv/)[^/?#]+/?$|'
                        r'linkedin\.com/in/|threads\.net/@|bsky\.app/profile/')
HANDLE_TXT = re.compile(r'@[A-Za-z0-9_][A-Za-z0-9_.]{1,40}')


# Titles of social posts, photos and comments can name private people, so they are not shown
# (the collector's report does the same). News, video and web titles stay.
NO_TITLE_KINDS = {'Social Network', 'Pictures', 'Microblog', 'YouTube Comments', 'Comments', 'Forums',
                  'social_link', 'social_post', 'video_comment', 'forum'}


def privacy(rec):
    url = rec.get('url') or ''
    if rec.get('url_withheld') or (url and HANDLE_URL.search(url)):
        rec['url'] = None
        rec['link_withheld'] = True
    kind = rec.get('media_type') or rec.get('kind')
    if kind in NO_TITLE_KINDS:
        rec['title'] = None
        rec['title_withheld'] = True
    elif rec.get('title'):
        rec['title'] = HANDLE_TXT.sub('@[USER]', rec['title'])
    return rec


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_js(name, var, obj):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(f'window.{var} = ')
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    return p, os.path.getsize(p)


def build_live():
    d = load(LIVE)
    if d is None:
        return None
    meta = d.get('meta', {})
    items = [privacy({k: it.get(k) for k in LIVE_ITEM_KEYS}) for it in d.get('items', [])]
    return {'meta': meta, 'items': items, 'source_file': 'live/out/update/latest.json'}


def build_history():
    d = load(HIST)
    if d is None:
        return None
    out = {k: d.get(k) for k in HIST_KEYS}
    out['posts'] = [privacy({k: p.get(k) for k in POST_KEYS}) for p in d.get('posts', [])]
    out['review_queue_n'] = len(d.get('review_queue', []) or [])
    out['source_file'] = 'pipeline/data/export/data.json'
    return out


def build_facts():
    d = load(FAQ)
    if d is None:
        return None
    figs = {f['figure_id']: {k: f.get(k) for k in ('label', 'value', 'unit', 'note', 'valid_from')}
            for f in d.get('official_figures', [])}
    return {'figures': figs, 'source_url': (d.get('meta') or {}).get('source_url') or (d.get('meta') or {}).get('url'),
            'source_file': 'pipeline/reference/faq_heilbronn.json'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--history', choices=['awaiting', 'pilot', 'final'], default=None,
                    help='state of the historical part; default keeps the current config (first run: awaiting)')
    a = ap.parse_args()

    cfg_path = os.path.join(OUT, 'config.js')
    mode = a.history
    if mode is None:
        mode = 'awaiting'
        if os.path.exists(cfg_path):
            txt = open(cfg_path, encoding='utf-8').read()
            for m in ('pilot', 'final', 'awaiting'):
                if f'"history_mode":"{m}"' in txt:
                    mode = m
                    break

    live, hist, facts = build_live(), build_history(), build_facts()
    report = []
    report.append(write_js('live.js', 'CP_LIVE', live))
    report.append(write_js('history.js', 'CP_HISTORY', hist))
    report.append(write_js('facts.js', 'CP_FACTS', facts))
    cfg = {'history_mode': mode, 'built_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}
    report.append(write_js('config.js', 'CP_CONFIG', cfg))
    wl = sum(1 for x in (live or {}).get('items', []) if x.get('link_withheld')) + sum(1 for x in (hist or {}).get('posts', []) if x.get('link_withheld'))
    print(f'links withheld because they name an account: {wl}')
    for p, n in report:
        print(f'{os.path.relpath(p, ROOT)}  {n:,} bytes')
    print(f'history_mode = {mode}'
          + ('' if hist else '  (no pipeline export found: the historical part shows its awaiting state)'))
    if live is None:
        print('no live receipt found: section 02 and 03 show "no update has run yet"')


if __name__ == '__main__':
    sys.exit(main())
