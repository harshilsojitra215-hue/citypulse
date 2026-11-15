"""The Update-now bridge, end to end, offline: a fake labeller instead of a model (no network, no cost).
Checks: the team's stages run in the scratch copy, pipeline/ is not written, labels are cached by content hash,
a second update does not label the same item again, an edited item is labelled again, and the report says
"test" and never prints a social URL.
Run: python -I -X utf8 -m pytest live/tests/test_update_now.py -q   (about 1 minute)
"""
import glob
import hashlib
import json
import os
import shutil
import sys

LIVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(LIVE)
sys.path.insert(0, LIVE)
import update_now  # noqa: E402


def rec(i, project, title, kind='web', url=None, match='strong', h=None):
    return {'mention_id': f'live:test{i:08x}', 'media_type_name': 'News', 'published_at': '2026-11-10T08:00:00+0000',
            'source_name': 'example.org', 'url': url or f'https://example.org/a{i}', 'country_code': 'DE', 'language_code': 'de',
            'sentiment': -99, 'reach': None, 'engagements': 0, 'authors': [], 'title': title, 'content': title + ' Mehr Text.',
            'discovered_at': '2026-11-14T10:00:00+00:00', 'retrieved_at': '2026-11-14T10:00:00+00:00', 'modified_at': None,
            'last_changed_at': '2026-11-14T10:00:00+00:00', 'version_no': 1, 'late_discovered': False, 'kind': kind,
            'replay': False, 'published': False, 'project_hint': project, 'content_hash': h or f'h{i}', 'radar_match': match,
            'text_scope': 'snippet' if kind == 'social_link' else 'full', 'date_known': True}


def fingerprint(d):
    h = hashlib.sha1()
    for p in sorted(glob.glob(os.path.join(d, '**', '*'), recursive=True)):
        if os.path.isfile(p):
            st = os.stat(p)
            h.update(f'{os.path.relpath(p, d)}|{st.st_size}|{int(st.st_mtime)}'.encode())
    return h.hexdigest()


def run(tmp, recs):
    out = os.path.join(tmp, 'out')
    os.makedirs(out, exist_ok=True)
    json.dump(recs, open(os.path.join(out, 'raw_live.json'), 'w', encoding='utf-8'))
    shutil.copy(sorted(glob.glob(os.path.join(LIVE, 'out', 'receipt_*.json')))[-1], out)
    return update_now.main(['--no-collect', '--provider', 'fake', '--out-dir', out, '--cache-dir', os.path.join(tmp, 'cache'),
                            '--scratch', os.path.join(tmp, 'scratch')])


def test_bridge_end_to_end(tmp_path):
    tmp = str(tmp_path)
    recs = [rec(1, 'paris_c1', 'Câble C1 : une station fermée'),
            rec(2, 'heilbronn_cablecar', 'Seilbahn Heilbronn: Gemeinderat berät', kind='social_link',
                url='https://www.instagram.com/p/SECRETHANDLE/'),
            rec(3, 'koeln_cablecar', 'Seilbahn Köln wieder in Betrieb'),       # comparator: not labelled by default
            rec(4, 'paris_c1', 'Câble C1 weak mention', match='weak')]           # weak: not taken
    before = fingerprint(os.path.join(REPO, 'pipeline'))
    r1 = run(tmp, recs)
    assert fingerprint(os.path.join(REPO, 'pipeline')) == before, 'pipeline/ was written'
    m = r1['meta']
    assert m['test_only'] is True
    assert m['counts']['strong'] == 3 and m['counts']['labelled_this_update'] == 2
    items = {i['id']: i for i in r1['items']}
    assert items['live:test00000001']['label_state'] == 'labelled' and items['live:test00000001']['n_runs'] == 3
    assert items['live:test00000003']['label_state'] == 'pending'
    md = open(glob.glob(os.path.join(tmp, 'out', 'update', 'update_*.md'))[0], encoding='utf-8').read()
    assert 'TEST RUN' in md and 'instagram.com' not in md and 'SECRETHANDLE' not in md
    assert items['live:test00000002']['title'] is None and 'Seilbahn Heilbronn' in items['live:test00000002']['snippet']
    assert not os.path.exists(os.path.join(tmp, 'out', 'update', 'latest.md')), 'a test run must not become latest'

    # second update, nothing changed: no new labels, the cached ones are still used
    r2 = run(tmp, recs)
    assert r2['meta']['counts']['labelled_this_update'] == 0 and r2['meta']['counts']['with_label'] == 2

    # item 1 edited at the source (new content hash): labelled again, old labels not mixed in
    recs[0] = rec(1, 'paris_c1', 'Câble C1 : la station rouvre', h='h1b')
    r3 = run(tmp, recs)
    assert r3['meta']['counts']['labelled_this_update'] == 1
    it = {i['id']: i for i in r3['items']}['live:test00000001']
    assert it['n_runs'] == 3, 'old-version labels leaked into the vote'


def test_report_is_written_even_when_pipeline_stages_fail(tmp_path):
    """If the pipeline code breaks (here: a record normalise() refuses), the collection report must still be written."""
    broken = rec(9, 'paris_c1', 'Câble C1 : panne')
    broken['url'] = None
    r = run(str(tmp_path), [rec(1, 'paris_c1', 'Câble C1 : une station fermée'), broken])
    assert r['meta']['counts']['strong'] == 2 and r['meta']['counts']['with_label'] == 0
    md = open(glob.glob(os.path.join(str(tmp_path), 'out', 'update', 'update_*.md'))[0], encoding='utf-8').read()
    assert "pipeline stages failed" in md and 'Per project' in md


def test_social_links_that_name_an_account_are_withheld():
    pu = update_now.public_url
    assert pu('social_link', 'https://linkedin.com/in/anna-weber-1876a3231') is None
    assert pu('social_link', 'https://www.facebook.com/steffen.schoch/posts/123') is None
    assert pu('social_link', 'https://www.tiktok.com/@rowena_x/video/7300000000000000000') is None
    assert pu('social_link', 'https://www.instagram.com/reel/DfSbEYxlcxt?igsh=abc') == 'https://www.instagram.com/reel/DfSbEYxlcxt/'
    assert pu('social_link', 'https://x.com/MarneSeine_IDFM/status/1989000000000000000') == 'https://x.com/i/web/status/1989000000000000000'
    assert pu('social_link', 'https://www.linkedin.com/posts/anna-weber_ipai-activity-7521488848573353985-yKwx') == \
        'https://www.linkedin.com/feed/update/urn:li:activity:7521488848573353985/'
    assert pu('video_comment', 'https://www.youtube.com/watch?v=kHqI0Evl79A&lc=xyz') == 'https://www.youtube.com/watch?v=kHqI0Evl79A'
    assert pu('news', 'https://www.stimme.de/a/b') == 'https://www.stimme.de/a/b'      # news links stay as they are
