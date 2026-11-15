"""Mocked tests for the key-based adapters (Exa, Tavily, YouTube, Apify) and the radar report. No network, no real keys.
Run:  cd live && python -I -X utf8 -m pytest tests -v
"""
import datetime as dt
import os
import sys
from argparse import Namespace

import pytest
import yaml

LIVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LIVE)
import run_collect  # noqa: E402
from collector import core  # noqa: E402
from collector.adapters._search import classify  # noqa: E402
from collector.adapters.apify import Apify  # noqa: E402
from collector.adapters.exa import Exa  # noqa: E402
from collector.adapters.tavily import Tavily  # noqa: E402
from collector.adapters.youtube import YouTube  # noqa: E402
from collector.core import HttpError, Project, SkipSource  # noqa: E402

UTC = dt.timezone.utc
SINCE = dt.datetime(2026, 11, 1, tzinfo=UTC)
PROJ = {'name': 'Test project', 'city': 'Heilbronn', 'keywords': {'de': ['Seilbahn']}, 'specific': ['Seilbahn Heilbronn'],
        'place_words': ['Heilbronn'], 'negative_words': ['Ski'], 'queries': {'de': ['Seilbahn Heilbronn']}}
ARTICLE = 'https://www.stimme.de/seilbahn-heilbronn-gemeinderat'
HTML = '<html><body><article>' + ('Die Seilbahn Heilbronn beschaeftigt den Gemeinderat seit Wochen und die Buerger streiten. ' * 8) + '</article></body></html>'


@pytest.fixture(autouse=True)
def nokeys(monkeypatch):
    for k in ('EXA_API_KEY', 'TAVILY_API_KEY', 'YOUTUBE_API_KEY', 'APIFY_TOKEN'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(core, '_ENV', {'__loaded__': '1'})      # do not read a real live/.env during tests


class FakeHttp:
    """Stands in for core.Http. posts / jsons: a list of responses (dict) or exceptions, consumed in order, last one repeats."""

    def __init__(self, posts=None, jsons=None, pages=None, robots_ok=True):
        self.posts, self.jsons, self.pages, self.robots = list(posts or []), list(jsons or []), pages or {}, robots_ok
        self.post_calls, self.json_calls, self.get_calls = [], [], []

    @staticmethod
    def _next(lst):
        r = lst[0] if len(lst) == 1 else lst.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def post_json(self, url, payload, headers=None, interval=None, retries=None):
        self.post_calls.append((url, payload, headers))
        return self._next(self.posts)

    def json(self, url, **kw):
        self.json_calls.append((url, kw.get('params')))
        return self._next(self.jsons)

    def robots_ok(self, url):
        return self.robots

    def get(self, url, **kw):
        self.get_calls.append(url)
        if url not in self.pages:
            raise HttpError(404, 'HTTP 404')
        return self.pages[url], 'text/html'


def project(**extra):
    return Project('p1', {**PROJ, **extra})


def exa_response():
    return {'costDollars': {'total': 0.005}, 'results': [
        {'url': ARTICLE, 'title': 'Seilbahn Heilbronn: Streit im Gemeinderat', 'publishedDate': '2026-11-10T08:00:00.000Z', 'highlights': ['Streit um die Seilbahn in Heilbronn']},
        {'url': 'https://www.reddit.com/r/heilbronn/comments/abc/seilbahn', 'title': 'Seilbahn Heilbronn, was denkt ihr?', 'publishedDate': '2026-11-11T09:00:00.000Z',
         'highlights': ['Ich finde die Seilbahn in Heilbronn zu teuer']},
        {'url': 'https://www.gutefrage.net/frage/seilbahn-heilbronn', 'title': 'Seilbahn Heilbronn sinnvoll?', 'publishedDate': '2026-11-12T09:00:00.000Z', 'highlights': ['Heilbronn Seilbahn']},
        {'url': 'https://example.org/ski', 'title': 'Seilbahn Ski Ausflug ab Heilbronn', 'publishedDate': '2026-11-12T09:00:00.000Z', 'highlights': ['Ski Heilbronn']},
        {'url': 'https://example.org/other', 'title': 'Kochrezepte', 'publishedDate': '2026-11-12T09:00:00.000Z', 'highlights': ['Kuchen']},
        {'url': 'https://example.org/old', 'title': 'Seilbahn Heilbronn alt', 'publishedDate': '2026-05-01T09:00:00.000Z', 'highlights': ['Seilbahn Heilbronn']},
    ]}


def adapter(cls, http, **cfg):
    return cls({'enabled': True, 'min_interval_s': 0, 'site_scopes': [['reddit.com']], 'max_queries_per_project': 1, **cfg}, http)


# ---------------------------------------------------------------- classification
def test_classify_by_domain():
    assert classify('reddit.com') == 'social_link' and classify('www.instagram.com'.replace('www.', '')) == 'social_link'
    assert classify('youtube.com') == 'video' and classify('stimme.de') == 'news' and classify('heilbronn.de') == 'official'
    assert classify('skyscrapercity.com') == 'forum' and classify('meinblog.wordpress.com') == 'blog' and classify('example.org') == 'web'


# ---------------------------------------------------------------- missing key: clean skip
@pytest.mark.parametrize('cls', [Exa, Tavily, YouTube, Apify])
def test_missing_key_skips_with_clear_line(cls):
    http = FakeHttp()
    ad = adapter(cls, http)
    with pytest.raises(SkipSource) as e:
        ad.fetch(project(), SINCE)
    assert ad.key_env in str(e.value) and 'no key' in str(e.value)
    assert http.post_calls == [] and http.json_calls == []          # nothing was sent


def test_run_receipt_lists_skipped_sources(tmp_path, monkeypatch):
    cfgp = tmp_path / 'c.yaml'
    cfgp.write_text(yaml.safe_dump({'defaults': {'since': '2026-11-01', 'user_agent': 't', 'known_not_covered': []},
                                    'projects': {'p1': PROJ}, 'sources': {'exa': {'enabled': True}, 'youtube': {'enabled': True}}}), encoding='utf-8')
    monkeypatch.setattr(run_collect, 'ADAPTERS', [Exa, YouTube])
    a = Namespace(config=str(cfgp), since='2026-11-01', project=None, source=None, db=str(tmp_path / 'l.db'), out_dir=str(tmp_path / 'out'),
                  out=None, examples=0, export_mode='discovered', health=False, radar=True)
    rc = run_collect.run(a)
    assert {s['source'] for s in rc['sources_skipped']} == {'exa', 'youtube'}
    assert rc['sources'] == [] and any(g.startswith('SKIPPED: youtube: no key') for g in rc['coverage_gaps'])
    md = open(os.path.join(tmp_path, 'out', f"receipt_{rc['run_id']}.md"), encoding='utf-8').read()
    assert 'skipped' in md and 'YOUTUBE_API_KEY' in md
    radar = open(os.path.join(tmp_path, 'out', f"radar_{rc['run_id']}.md"), encoding='utf-8').read()
    assert 'SKIPPED. youtube: no key' in radar and 'What this scan cannot see' in radar


# ---------------------------------------------------------------- Exa
def test_exa_items_kinds_and_snippet_rules(monkeypatch):
    monkeypatch.setenv('EXA_API_KEY', 'test-key-not-real')
    http = FakeHttp(posts=[exa_response()], pages={ARTICLE: HTML.encode()})
    ad = adapter(Exa, http)
    items = ad.fetch(project(), SINCE)
    by = {i.url: i for i in items}
    assert set(by) == {ARTICLE, 'https://www.reddit.com/r/heilbronn/comments/abc/seilbahn', 'https://www.gutefrage.net/frage/seilbahn-heilbronn'}
    news, social, forum = by[ARTICLE], by['https://www.reddit.com/r/heilbronn/comments/abc/seilbahn'], by['https://www.gutefrage.net/frage/seilbahn-heilbronn']
    assert (news.kind, news.text_scope, news.source_name) == ('news', 'full', 'stimme.de') and len(news.text) > 200
    assert social.kind == 'social_link' and social.text_scope == 'snippet' and 'zu teuer' in social.text
    assert forum.kind == 'forum' and forum.text_scope == 'snippet'            # page not available (404) -> snippet only
    assert not any('reddit.com' in u for u in http.get_calls)                  # a social page is never opened
    assert ad.stats['off_topic_dropped'] >= 2 and ad.stats['before_since_dropped'] == 1 and ad.cost_usd > 0
    # key sent in a header, never in the URL or the log lines
    assert http.post_calls[0][2] == {'x-api-key': 'test-key-not-real'} and 'key' not in http.post_calls[0][0]
    # first call is the normal query with a date filter, second the site-scoped one
    assert 'includeDomains' not in http.post_calls[0][1] and http.post_calls[1][1]['includeDomains'] == ['reddit.com']
    assert http.post_calls[0][1]['startPublishedDate'].startswith('2026-11-01')


def test_robots_disallowed_page_stays_snippet_only(monkeypatch):
    monkeypatch.setenv('EXA_API_KEY', 'test-key-not-real')
    http = FakeHttp(posts=[exa_response()], pages={ARTICLE: HTML.encode()}, robots_ok=False)
    ad = adapter(Exa, http)
    items = ad.fetch(project(), SINCE)
    news = next(i for i in items if i.url == ARTICLE)
    assert news.text_scope == 'snippet' and 'Streit um die Seilbahn' in news.text
    assert http.get_calls == [] and ad.stats['robots_blocked'] >= 1 and ad.stats['full_text'] == 0


def test_exa_undated_hit_is_flagged(monkeypatch):
    monkeypatch.setenv('EXA_API_KEY', 'test-key-not-real')
    resp = {'results': [{'url': 'https://example.org/a', 'title': 'Seilbahn Heilbronn Forum', 'publishedDate': None, 'highlights': ['Seilbahn Heilbronn']}]}
    ad = adapter(Exa, FakeHttp(posts=[resp]), fulltext=False)
    it = ad.fetch(project(), SINCE)[0]
    assert it.date_known is False and ad.stats['undated'] >= 1


@pytest.mark.parametrize('cls,status,env', [(Exa, 402, 'EXA_API_KEY'), (Exa, 429, 'EXA_API_KEY'), (Tavily, 432, 'TAVILY_API_KEY'), (Tavily, 433, 'TAVILY_API_KEY')])
def test_quota_error_stops_source_and_is_reported(monkeypatch, cls, status, env):
    monkeypatch.setenv(env, 'test-key-not-real')
    ok = exa_response() if cls is Exa else {'results': [{'url': ARTICLE, 'title': 'Seilbahn Heilbronn', 'content': 'Seilbahn Heilbronn', 'published_date': '2026-11-10'}]}
    http = FakeHttp(posts=[ok, HttpError(status, f'HTTP {status}')])
    ad = adapter(cls, http, fulltext=False, topics=['general'])
    items = ad.fetch(project(), SINCE)                         # first query worked, second hit the limit: items so far are kept
    assert items and ad.quota_hit and any('stopped' in w for w in ad.warnings)
    with pytest.raises(SkipSource):                            # the next project is skipped without another request
        n = len(http.post_calls)
        ad.fetch(project(), SINCE)
    assert len(http.post_calls) == n


def test_quota_error_before_any_item_is_a_skip(monkeypatch):
    monkeypatch.setenv('EXA_API_KEY', 'test-key-not-real')
    ad = adapter(Exa, FakeHttp(posts=[HttpError(402, 'HTTP 402')]))
    with pytest.raises(SkipSource) as e:
        ad.fetch(project(), SINCE)
    assert 'credits' in str(e.value)


def test_other_http_error_is_a_normal_failure(monkeypatch):
    monkeypatch.setenv('EXA_API_KEY', 'test-key-not-real')
    ad = adapter(Exa, FakeHttp(posts=[HttpError(500, 'HTTP 500')]))
    with pytest.raises(HttpError):
        ad.fetch(project(), SINCE)


# ---------------------------------------------------------------- Tavily
def test_tavily_news_and_general_with_dates(monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'test-key-not-real')
    resp = {'results': [
        {'url': ARTICLE, 'title': 'Seilbahn Heilbronn kommt', 'content': 'Gemeinderat Seilbahn Heilbronn', 'published_date': '2026-11-09T07:00:00Z'},
        {'url': 'https://www.instagram.com/p/xyz/', 'title': 'Seilbahn Heilbronn', 'content': 'Seilbahn Heilbronn Foto', 'published_date': None}]}
    http = FakeHttp(posts=[resp])
    ad = adapter(Tavily, http, fulltext=False)
    items = ad.fetch(project(), SINCE)
    topics = [c[1]['topic'] for c in http.post_calls]
    assert topics[:2] == ['general', 'news'] and http.post_calls[0][2] == {'Authorization': 'Bearer test-key-not-real'}
    assert http.post_calls[0][1]['start_date'] == '2026-11-01'
    insta = next(i for i in items if 'instagram' in i.url)
    assert insta.kind == 'social_link' and insta.text_scope == 'snippet' and insta.date_known is False
    assert [i.kind for i in items if i.url == ARTICLE] == ['news']
    assert len([i for i in items if i.url == ARTICLE]) == 1                    # same URL from two topics is one item


# ---------------------------------------------------------------- Apify
def test_apify_discovery_only_parse_and_budget(monkeypatch):
    monkeypatch.setenv('APIFY_TOKEN', 'test-token-not-real')
    page = [{'organicResults': [
        {'url': 'https://www.facebook.com/groups/1/posts/2', 'title': 'Seilbahn Heilbronn Diskussion', 'description': 'Seilbahn in Heilbronn: ja oder nein?'},
        {'url': 'https://example.org/x', 'title': 'Unrelated', 'description': 'nothing'}]}]
    http = FakeHttp(posts=[page])
    ad = adapter(Apify, http, max_total_usd=0.004, usd_per_serp_page=0.0025, fulltext=False)
    items = ad.fetch(project(), SINCE)
    assert [i.kind for i in items] == ['social_link'] and items[0].text_scope == 'snippet'
    assert http.post_calls[0][2] == {'Authorization': 'Bearer test-token-not-real'} and 'token' not in http.post_calls[0][0]
    assert 'site:reddit.com' in http.post_calls[1][1]['queries'] and http.post_calls[1][1]['saveHtml'] is False
    # budget: 2 searches x 0.0025 = 0.005 > 0.004, so the next project makes no request
    n = len(http.post_calls)
    with pytest.raises(SkipSource) as e:
        ad.fetch(project(), SINCE)
    assert 'budget' in str(e.value) and len(http.post_calls) == n


# ---------------------------------------------------------------- YouTube
def yt_search():
    return {'items': [{'id': {'videoId': 'VID1'}, 'snippet': {'title': 'Seilbahn Heilbronn Debatte', 'description': 'Gemeinderat', 'publishedAt': '2026-11-05T10:00:00Z', 'channelId': 'UCx', 'channelTitle': 'Some Name'}},
                      {'id': {'videoId': 'VID2'}, 'snippet': {'title': 'Katzen', 'description': 'lustig', 'publishedAt': '2026-11-05T10:00:00Z'}}]}


def yt_threads():
    c1 = {'id': 'C1', 'snippet': {'textDisplay': 'Zu teuer, siehe @MaxMustermann', 'authorDisplayName': 'Max Mustermann', 'authorChannelId': {'value': 'UCmax'},
                                   'likeCount': 4, 'publishedAt': '2026-11-06T10:00:00Z'}}
    r1 = {'id': 'C1.R1', 'snippet': {'textDisplay': 'Stimme ich zu', 'authorDisplayName': 'Erika', 'authorChannelId': {'value': 'UCerika'},
                                      'likeCount': 0, 'publishedAt': '2026-11-07T10:00:00Z'}}
    old = {'id': 'C2', 'snippet': {'textDisplay': 'alter Kommentar', 'authorChannelId': {'value': 'UCold'}, 'publishedAt': '2026-01-01T10:00:00Z'}}
    return {'items': [{'snippet': {'topLevelComment': c1}, 'replies': {'comments': [r1]}}, {'snippet': {'topLevelComment': old}}]}


def test_youtube_videos_and_comments_hashed(monkeypatch):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'test-key-not-real')
    http = FakeHttp(jsons=[yt_search(), yt_threads()])
    ad = adapter(YouTube, http, include_older_videos=False)
    items = ad.fetch(project(), SINCE)
    kinds = sorted(i.kind for i in items)
    assert kinds == ['video', 'video_comment', 'video_comment']                # off-topic video skipped, old comment skipped
    video = next(i for i in items if i.kind == 'video')
    assert video.url == 'https://www.youtube.com/watch?v=VID1' and video.published_at.year == 2026
    cm = [i for i in items if i.kind == 'video_comment']
    assert all(i.author_hash and len(i.author_hash) == 16 for i in cm) and cm[0].author_hash != cm[1].author_hash
    blob = ' '.join(f'{i.title} {i.text} {i.url} {i.source_name}' for i in items)
    assert 'Max Mustermann' not in blob and 'MaxMustermann' not in blob and 'UCmax' not in blob and '@[USER]' in blob
    assert any(i.url.endswith('&lc=C1') and i.engagements == 4 for i in cm)
    # search call: dated, language set, key as parameter (the Data API requires it), comments call: threads with replies
    sp = http.json_calls[0][1]
    assert sp['publishedAfter'] == '2026-11-01T00:00:00Z' and sp['relevanceLanguage'] == 'de' and sp['type'] == 'video'
    assert http.json_calls[1][1]['part'] == 'snippet,replies' and http.json_calls[1][1]['videoId'] == 'VID1'


def test_youtube_quota_exceeded_is_skip_not_crash(monkeypatch):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'test-key-not-real')
    body = '{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    http = FakeHttp(jsons=[HttpError(403, 'HTTP 403', body)])
    ad = adapter(YouTube, http)
    with pytest.raises(SkipSource) as e:
        ad.fetch(project(), SINCE)
    assert 'quota' in str(e.value) and any('quotaExceeded' in w for w in ad.warnings)
    n = len(http.json_calls)
    with pytest.raises(SkipSource):
        ad.fetch(project(), SINCE)
    assert len(http.json_calls) == n                                            # no further request after the quota is gone


def test_youtube_keeps_video_when_quota_dies_during_comments(monkeypatch):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'test-key-not-real')
    http = FakeHttp(jsons=[yt_search(), HttpError(403, 'HTTP 403', 'quotaExceeded')])
    items = adapter(YouTube, http, include_older_videos=False).fetch(project(), SINCE)
    assert [i.kind for i in items] == ['video']


def test_youtube_comments_disabled_and_search_cap(monkeypatch):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'test-key-not-real')
    http = FakeHttp(jsons=[yt_search(), HttpError(403, 'HTTP 403', 'commentsDisabled')])
    ad = adapter(YouTube, http, include_older_videos=False)
    items = ad.fetch(project(), SINCE)
    assert [i.kind for i in items] == ['video'] and ad.stats['videos_comments_off'] == 1
    capped = adapter(YouTube, FakeHttp(jsons=[{'items': []}]), max_search_calls=1)
    capped.fetch(project(), SINCE)                                              # fresh + older = 2 searches, cap is 1
    assert capped.search_calls == 1 and any('max_search_calls' in w for w in capped.warnings)


# ---------------------------------------------------------------- radar report end to end
def test_radar_report_content(tmp_path, monkeypatch):
    monkeypatch.setenv('EXA_API_KEY', 'test-key-not-real')
    fake = FakeHttp(posts=[exa_response()], pages={ARTICLE: HTML.encode()})
    monkeypatch.setattr(run_collect, 'Http', lambda *a, **k: fake)
    cfgp = tmp_path / 'c.yaml'
    cfgp.write_text(yaml.safe_dump({'defaults': {'since': '2026-11-01', 'user_agent': 't', 'known_not_covered': []}, 'projects': {'p1': PROJ},
                                    'sources': {'exa': {'enabled': True, 'min_interval_s': 0, 'site_scopes': [['reddit.com']], 'max_queries_per_project': 1},
                                                'youtube': {'enabled': True}}}), encoding='utf-8')
    monkeypatch.setattr(run_collect, 'ADAPTERS', [Exa, YouTube])
    a = Namespace(config=str(cfgp), since='2026-11-01', project=None, source=None, db=str(tmp_path / 'l.db'), out_dir=str(tmp_path / 'out'),
                  out=None, examples=0, export_mode='discovered', health=False, radar=True)
    rc = run_collect.run(a)
    text = open(os.path.join(tmp_path, 'out', f"radar_{rc['run_id']}.md"), encoding='utf-8').read()
    assert rc['status'] == 'success'                                           # a skipped YouTube does not make the run partial
    assert 'Reddit link: 1' in text and 'URL in the export only' in text and 'reddit.com/r/heilbronn' not in text      # no social URL in the markdown
    assert 'Top 5 strong titles' in text and 'Seilbahn Heilbronn: Streit im Gemeinderat' in text
    assert 'SKIPPED. youtube: no key' in text and 'Instagram, Facebook, TikTok, X, LinkedIn' in text
    assert '**Strong: 3**' in text and 'Noise filtered: 0' in text and 'estimated cost' in text
    row = [r for r in __import__('sqlite3').connect(a.db).execute('select kind, text_scope, date_known from items')]
    assert ('social_link', 'snippet', 1) in row and ('news', 'full', 1) in row


# ---------------------------------------------------------------- radar gate, dates, masking, query tightening
def test_gate_strong_weak_none_and_negative_words():
    p = project(place_words=['Heilbronn', 'Neckarturm'])
    assert p.relevance('Seilbahn Heilbronn: Gemeinderat', '') == 'strong'                                 # project phrase
    assert p.relevance('Partys in Heilbronn', 'Ideen ... zu 80 km/h an der Seilbahn ins Tal ... Adresse Oberaudorf') == 'weak'   # words in different fragments
    assert p.relevance('Seilbahn im Allgaeu', 'Ausflug mit Kindern') == 'weak'                           # cable word only
    assert p.relevance('Stadt Heilbronn Termine', 'Wochenmarkt') == 'weak'                               # place word only
    assert p.relevance('Kochrezepte', 'Kuchen backen') == 'none'
    assert p.relevance('Skilift Gondel', 'Seilbahn Ski Neckarturm Wochenende') == 'none'                 # negative word, no project phrase
    assert p.relevance('Seilbahn Heilbronn Ski', '') == 'strong'                                         # a project phrase still wins over a negative word
    far = 'Seilbahn ' + 'x' * 200 + ' Neckarturm'
    assert p.relevance('Titel', far) == 'weak'                                                           # same fragment but too far apart
    assert p.relevance('Titel', 'Seilbahn zum Neckarturm geplant') == 'strong'


def test_adapter_tags_radar_match_and_keeps_all(monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'test-key-not-real')
    resp = {'results': [
        {'url': 'https://www.tiktok.com/@someone/video/1', 'title': 'Partys in Heilbronn - TikTok', 'content': 'Partys in Heilbronn ... an der Seilbahn ins Tal', 'published_date': None},
        {'url': 'https://www.instagram.com/p/abc/', 'title': 'Photo by Max Mustermann (@maxm)', 'content': 'Gemeinderat beschliesst Seilbahn Heilbronn', 'published_date': None},
        {'url': ARTICLE, 'title': 'Seilbahn Heilbronn kommt', 'content': 'Seilbahn Heilbronn', 'published_date': '2026-11-09T07:00:00Z'}]}
    ad = adapter(Tavily, FakeHttp(posts=[resp]), fulltext=False)
    by = {i.url: i for i in ad.fetch(project(), SINCE)}
    assert len(by) == 3                                                                                  # weak items are kept, not dropped
    assert by['https://www.tiktok.com/@someone/video/1'].radar_match == 'weak'
    insta = by['https://www.instagram.com/p/abc/']
    assert insta.radar_match == 'strong' and by[ARTICLE].radar_match == 'strong'
    assert 'maxm' not in insta.title and 'Mustermann' not in insta.title and insta.url.endswith('/p/abc/')   # title masked, URL kept for the export


def test_masking_handles_names_and_kinds():
    m = core.mask_for_kind
    assert m('social_link', 'Photo by BITVION GROUPS (@bitviongroups)') == 'Photo by [USER]'
    assert m('social_link', 'Bus Marne on X: "#Bus429 @foo"') == '[USER] on X: "#Bus429 [USER]"'
    assert m('forum', 'Antwort von Anna Schmidt an @peter.m') == 'Antwort von [USER] an [USER]'
    assert m('web', 'Vortrag von Karl-Heinz Rochlitz') == 'Vortrag von [USER]'
    assert m('social_link', 'Stadt Heilbronn Seilbahn') == 'Stadt Heilbronn Seilbahn'                    # place names stay
    assert m('news', 'Oberbuergermeister Harry Mergel sagt') == 'Oberbuergermeister Harry Mergel sagt'   # news and official text keep names
    assert m('news', 'Kontakt @redaktion') == 'Kontakt [USER]'                                           # handles are masked for every kind


def test_site_queries_are_quoted_and_need_the_cable_word(monkeypatch):
    monkeypatch.setenv('EXA_API_KEY', 'test-key-not-real')
    http = FakeHttp(posts=[{'results': []}])
    ad = adapter(Exa, http, max_queries_per_project=3)
    p = project(queries={'de': ['Heilbronn Ausflug', 'Seilbahn Heilbronn Gemeinderat']})                  # first query has no cable word
    ad.fetch(p, SINCE)
    qs = [c[1]['query'] for c in http.post_calls]
    assert qs == ['Seilbahn Heilbronn Gemeinderat', '"Seilbahn Heilbronn"']                              # city-only query dropped, site query quoted
    assert 'includeText' not in http.post_calls[0][1] and http.post_calls[1][1]['includeText'] == ['Seilbahn']
    assert http.post_calls[1][1]['includeDomains'] == ['reddit.com']


def test_undated_items_are_not_counted_as_new_since(tmp_path, monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'test-key-not-real')
    resp = {'results': [
        {'url': ARTICLE, 'title': 'Seilbahn Heilbronn kommt', 'content': 'Seilbahn Heilbronn Gemeinderat', 'published_date': '2026-11-09T07:00:00Z'},
        {'url': 'https://www.instagram.com/p/abc/', 'title': 'Seilbahn Heilbronn Foto', 'content': 'Seilbahn in Heilbronn gesehen', 'published_date': None},
        {'url': 'https://www.tiktok.com/@u/video/9', 'title': 'Partys in Heilbronn', 'content': 'Partys ... Seilbahn ... Heilbronn', 'published_date': None}]}
    fake = FakeHttp(posts=[resp])
    monkeypatch.setattr(run_collect, 'Http', lambda *a, **k: fake)
    cfgp = tmp_path / 'c.yaml'
    cfgp.write_text(yaml.safe_dump({'defaults': {'since': '2026-11-01', 'user_agent': 't', 'known_not_covered': []}, 'projects': {'p1': PROJ},
                                    'sources': {'tavily': {'enabled': True, 'min_interval_s': 0, 'site_scopes': [['instagram.com']], 'max_queries_per_project': 1,
                                                           'topics': ['general'], 'fulltext': False}}}), encoding='utf-8')
    monkeypatch.setattr(run_collect, 'ADAPTERS', [Tavily])
    a = Namespace(config=str(cfgp), since='2026-11-01', project=None, source=None, db=str(tmp_path / 'l.db'), out_dir=str(tmp_path / 'out'),
                  out=None, examples=0, export_mode='discovered', health=False, radar=True)
    rc = run_collect.run(a)
    text = open(os.path.join(tmp_path, 'out', f"radar_{rc['run_id']}.md"), encoding='utf-8').read()
    assert '**Strong: 2**' in text and '**1 dated since 2026-11-01**' in text and '**1 found today, date unknown**' in text
    assert 'Possible, check: 1' in text and '<details><summary>Possible, check: 1</summary>' in text and 'Noise filtered: 0' in text
    assert 'Found today, date unknown (1 strong' in text
    assert 'instagram.com/p/abc' not in text and 'tiktok.com/@u' not in text and 'Instagram link: Seilbahn Heilbronn Foto' in text
    rmd = open(os.path.join(tmp_path, 'out', f"receipt_{rc['run_id']}.md"), encoding='utf-8').read()          # receipt: counts, no URL
    assert '2/1/0' in rmd and 'date unknown' in rmd and 'instagram.com/p/abc' not in rmd
    import json
    raw = json.load(open(os.path.join(tmp_path, 'out', 'raw_live.json'), encoding='utf-8'))                  # export keeps the URL and the tag
    insta = next(r for r in raw if 'instagram' in r['url'])
    assert insta['radar_match'] == 'strong' and insta['date_known'] is False and insta['url'] == 'https://www.instagram.com/p/abc/'
    tt = next(r for r in raw if 'tiktok' in r['url'])
    assert tt['radar_match'] == 'weak' and tt['url'].startswith('https://www.tiktok.com/@u')
    assert rc['per_project']['p1']['new_radar_match'] == {'strong': 2, 'weak': 1, 'none': 0}


def test_parse_date_iso_and_rfc2822():
    from collector.adapters._search import parse_date
    assert parse_date('2026-11-09T07:00:00Z') == dt.datetime(2026, 11, 9, 7, tzinfo=UTC)
    assert parse_date('Sat, 07 Nov 2026 10:45:53 GMT') == dt.datetime(2026, 11, 7, 10, 45, 53, tzinfo=UTC)      # Tavily news format
    assert parse_date('') is None and parse_date('yesterday') is None


def test_gate_splits_sentences_but_not_after_a_date_number():
    p = project()
    assert p.relevance('5 Ausflugsziele', 'Rund um Heilbronn gesammelt! An der Seilbahn ins Tal gerauscht! Adresse') == 'weak'      # two sentences
    p2 = project(place_words=['Heilbronner'])
    assert p2.relevance('Rat', 'Der Heilbronner Gemeinderat hat am 27. Juli 2026 den Bau einer urbanen Seilbahn beschlossen.') == 'strong'   # "27. Juli" is not a sentence end
