"""Controlled fixture tests for the collector. Each test checks the DB state AND the run receipt.
Run:  cd live && python -X utf8 -m pytest tests -v
No network: sources are fake adapter classes returning fixed items (or failing on purpose).
"""
import datetime as dt
import json
import os
import sqlite3
import sys
from argparse import Namespace

import pytest
import yaml

LIVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LIVE)
import run_collect  # noqa: E402
from collector.core import Adapter, Item, Store  # noqa: E402

UTC = dt.timezone.utc
CFG = {
    'defaults': {'since': '2026-10-27', 'user_agent': 'test', 'known_not_covered': ['TEST gap'], 'dataset_edge': '2026-10-27T12:29:00+0000'},
    'projects': {'p1': {'name': 'Test project', 'city': 'Heilbronn', 'keywords': {'de': ['Seilbahn']}, 'specific': ['Seilbahn Heilbronn'],
                        'place_words': ['Heilbronn'], 'queries': {'de': ['Seilbahn']}}},
    'sources': {'fake_a': {'enabled': True}, 'fake_b': {'enabled': True}, 'fake_fail': {'enabled': True}, 'fake_empty': {'enabled': True}},
}


def make_adapter(name, items=None, fail=None):
    """A fake source. items: list of dicts (url, title, text, published) returned for every project; fail: exception to raise."""
    class A(Adapter):
        pass
    A.name = name

    def fetch(self, project, since):
        if fail:
            raise fail
        return [Item(name, project.id, i['url'], i['title'], i.get('text', i['title']), i['published'], i.get('outlet', 'example.org'),
                     'de', 'DE', 'News', None, 0, '', 'q', True) for i in (items or [])]
    A.fetch = fetch
    return A


def article(url='https://www.example.org/seilbahn-heilbronn?utm_source=x', title='Seilbahn Heilbronn: Gemeinderat entscheidet',
            text=None, published=dt.datetime(2026, 11, 10, 8, 0, tzinfo=UTC)):
    return {'url': url, 'title': title, 'text': text or title, 'published': published}


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfgp = tmp_path / 'cfg.yaml'
    cfgp.write_text(yaml.safe_dump(CFG), encoding='utf-8')

    class Env:
        db = str(tmp_path / 'live.db')
        out = str(tmp_path / 'out')

        def run(self, adapters, mode='discovered', since='2026-10-27'):
            monkeypatch.setattr(run_collect, 'ADAPTERS', adapters)
            a = Namespace(config=str(cfgp), since=since, project=None, source=None, db=self.db, out_dir=self.out, out=None,
                          examples=0, export_mode=mode, health=False)
            return run_collect.run(a)

        def rows(self, sql, *args):
            c = sqlite3.connect(self.db)
            try:
                return c.execute(sql, args).fetchall()
            finally:
                c.close()

        def export(self):
            return json.load(open(os.path.join(self.out, 'raw_live.json'), encoding='utf-8'))
    return Env()


# (a) a genuinely new article
def test_a_new_article(env):
    rc = env.run([make_adapter('fake_a', [article()])])
    assert rc['status'] == 'success' and rc['published'] is False
    assert rc['totals']['truly_new'] == 1 and rc['totals']['changed_versions'] == 0 and rc['totals']['late_discovered_new'] == 0
    assert rc['new_items'][0]['title'].startswith('Seilbahn Heilbronn')
    assert env.rows('select count(*) from items')[0][0] == 1
    assert env.rows('select version_no from item_versions') == [(1,)]
    assert env.rows('select count(*) from sightings')[0][0] == 1
    ex = env.export()
    assert len(ex) == 1 and ex[0]['version_no'] == 1 and ex[0]['late_discovered'] is False and ex[0]['published'] is False
    assert ex[0]['authors'] == [] and ex[0]['mention_id'].startswith('live:')
    assert os.path.exists(os.path.join(env.out, 'receipt_%s.md' % rc['run_id']))


# (b) the same article from two sources: one record, two sightings
def test_b_same_article_two_sources(env):
    a = make_adapter('fake_a', [article('https://www.example.org/seilbahn-heilbronn?utm_source=x')])
    b = make_adapter('fake_b', [article('https://example.org/seilbahn-heilbronn/')])        # same canonical URL
    rc = env.run([a, b])
    assert rc['totals']['truly_new'] == 1 and rc['totals']['unique_items_seen'] == 1
    assert rc['totals']['items_returned_by_adapters'] == 2
    assert env.rows('select count(*) from items')[0][0] == 1
    assert sorted(r[0] for r in env.rows('select source from sightings')) == ['fake_a', 'fake_b']
    assert len(env.export()) == 1


# (c) an old article discovered late: exported and flagged
def test_c_late_discovery(env):
    old = article('https://www.example.org/alt', 'Seilbahn Heilbronn: Vorprojekt', published=dt.datetime(2026, 9, 1, 8, 0, tzinfo=UTC))
    rc = env.run([make_adapter('fake_a', [old])])
    assert rc['totals']['truly_new'] == 1 and rc['totals']['late_discovered_new'] == 1
    assert rc['new_items'][0]['late_discovered'] is True
    ex = env.export()
    assert len(ex) == 1 and ex[0]['late_discovered'] is True and ex[0]['published_at'].startswith('2026-09-01')
    # the old publish-date mode would have dropped it: this is the bug that was fixed
    env.run([make_adapter('fake_a', [old])], mode='published')
    assert env.export() == []


# (d) an existing article is edited: new version, old one kept, receipt says changed
def test_d_edit_creates_version(env):
    url = 'https://www.example.org/seilbahn-heilbronn'
    env.run([make_adapter('fake_a', [article(url, 'Seilbahn Heilbronn: 157 Millionen', 'Kosten 157 Millionen Euro')])])
    key = env.rows('select key from items')[0][0]
    rc = env.run([make_adapter('fake_a', [article(url, 'Seilbahn Heilbronn: 160 Millionen', 'Kosten 160 Millionen Euro')])])
    assert rc['totals']['truly_new'] == 0 and rc['totals']['changed_versions'] == 1
    assert 'changed' in rc['message'].lower()
    assert env.rows('select count(*) from items')[0][0] == 1
    vs = Store(env.db).versions(key)
    assert [v[0] for v in vs] == [1, 2]
    assert 'Kosten 157' in vs[0][3] and 'Kosten 160' in vs[1][3] and vs[0][1] != vs[1][1]
    assert env.rows('select version_no, text from items')[0] == (2, 'Kosten 160 Millionen Euro')
    ex = env.export()
    assert len(ex) == 1 and ex[0]['version_no'] == 2 and ex[0]['mention_id'] == 'live:' + key[:12]
    rc3 = env.run([make_adapter('fake_a', [article(url, 'Seilbahn Heilbronn: 160 Millionen', 'Kosten 160 Millionen Euro')])])
    assert rc3['totals']['changed_versions'] == 0 and env.rows('select count(*) from item_versions')[0][0] == 2


# (e) a source that fails and a source that returns nothing
def test_e_failing_and_empty_sources(env):
    env.run([make_adapter('fake_a', [article()])])
    before = env.export()
    rc = env.run([make_adapter('fake_fail', fail=OSError('boom: connection reset')), make_adapter('fake_empty', [])])
    st = {s['source']: s['status'] for s in rc['sources']}
    assert st == {'fake_fail': 'failed', 'fake_empty': 'success'}
    assert rc['status'] == 'partial' and rc['status'] != 'success'
    fail = next(s for s in rc['sources'] if s['source'] == 'fake_fail')
    assert 'boom' in fail['projects_failed'][0]['reason']
    assert any('boom' in g for g in rc['coverage_gaps'])
    assert rc['totals']['truly_new'] == 0 and rc['published'] is False
    assert env.rows('select count(*) from items')[0][0] == 1                 # nothing deleted or overwritten
    assert env.export() == before                                            # the export file still holds the old record
    rc2 = env.run([make_adapter('fake_empty', [])])
    assert rc2['status'] == 'success' and 'not evidence' in rc2['message']
    rc3 = env.run([make_adapter('fake_fail', fail=OSError('down'))])
    assert rc3['status'] == 'failed'
    assert 'FAILED' in rc3['message'] and 'incomplete' in rc3['message']


# idempotent rerun
def test_idempotent_rerun(env):
    def ads():
        return [make_adapter('fake_a', [article()]), make_adapter('fake_b', [article('https://example.org/zwei', 'Seilbahn Heilbronn: zweiter Artikel')])]
    rc1 = env.run(ads())
    q = 'select key, content_hash, version_no, first_seen from items order by key'
    snap1 = env.rows(q), env.rows('select count(*) from item_versions')
    ex1 = sorted((r['mention_id'], r['content_hash'], r['discovered_at']) for r in env.export())
    rc2 = env.run(ads())
    snap2 = env.rows(q), env.rows('select count(*) from item_versions')
    ex2 = sorted((r['mention_id'], r['content_hash'], r['discovered_at']) for r in env.export())
    assert rc1['totals']['truly_new'] == 2 and rc2['totals']['truly_new'] == 0 and rc2['totals']['changed_versions'] == 0
    assert rc2['totals']['already_known'] == 2
    assert snap1 == snap2 and ex1 == ex2
    assert 'not evidence' in rc2['message']


def test_youtube_text_purged_after_30_days(tmp_path):
    """YouTube API terms: stored API data older than 30 days (not refreshed) loses title and text; other sources are kept."""
    st = Store(str(tmp_path / 'p.db'))
    st.reset_run('r1')
    pub = dt.datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
    for src, url in (('youtube', 'https://www.youtube.com/watch?v=abc&lc=1'), ('tavily', 'https://example.org/a')):
        st.upsert(Item(src, 'heilbronn_cablecar', url, 'Seilbahn Heilbronn Kommentar', 'Ich finde die Seilbahn gut', pub,
                       'example.org', 'de', 'DE', 'News', None, 0, '', 'q', True))
    st.commit()
    later = dt.datetime.now(UTC) + dt.timedelta(days=31)
    assert st.purge_api_text('youtube', 30, now=dt.datetime.now(UTC)) == 0          # fresh: kept
    assert st.purge_api_text('youtube', 30, now=later) == 1
    rows = dict(st.db.execute('SELECT source, text FROM items').fetchall())
    assert rows['youtube'] == Store.PURGED and rows['tavily'] == 'Ich finde die Seilbahn gut'
    assert all(t == Store.PURGED for (t,) in st.db.execute("SELECT v.text FROM item_versions v JOIN items i ON i.key = v.key WHERE i.source = 'youtube'"))
    assert st.purge_api_text('youtube', 30, now=later) == 0                         # idempotent


def test_snippet_from_another_query_is_not_a_new_version(tmp_path):
    """Search services return a different snippet for the same link per query. That is not an edit: no new version, first snippet
    kept, sighting recorded, strongest radar match kept. A full-text page that really changes still gets version 2."""
    st = Store(str(tmp_path / 's.db'))
    st.reset_run('r1')
    pub = dt.datetime(2026, 11, 1, 8, 0, tzinfo=UTC)

    def item(url, text, scope, match, project='heilbronn_cablecar'):
        it = Item('tavily', project, url, 'Seilbahn Post', text, pub, 'instagram.com', 'de', 'DE', 'Other', None, 0, '', 'q', True)
        it.text_scope, it.radar_match = scope, match
        return it
    url = 'https://www.instagram.com/p/abc/'
    assert st.upsert(item(url, 'Heilbronner Gemeinderat beschliesst urbane Seilbahn', 'snippet', 'weak')) == 'new'
    assert st.upsert(item(url, 'Kölner Seilbahn fährt ab 10 Uhr', 'snippet', 'strong', 'koeln_cablecar')) == 'seen'
    row = st.db.execute('SELECT text, version_no, radar_match, projects FROM items').fetchone()
    assert row[0].startswith('Heilbronner') and row[1] == 1 and row[2] == 'strong' and 'koeln_cablecar' in row[3]
    assert st.db.execute('SELECT count(*) FROM item_versions').fetchone()[0] == 1
    page = 'https://example.org/seilbahn-heilbronn'
    st.upsert(item(page, 'Version eins des Artikels zur Seilbahn Heilbronn', 'full', 'strong'))
    assert st.upsert(item(page, 'Version zwei: der Gemeinderat hat entschieden', 'full', 'strong')) == 'updated'


def test_export_says_which_sources_found_an_item(tmp_path):
    st = Store(str(tmp_path / 'e.db'))
    st.reset_run('r1')
    pub = dt.datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    for n, src in enumerate(('exa', 'tavily', 'tavily')):
        it = Item(src, 'heilbronn_cablecar', 'https://example.org/seilbahn', 'Seilbahn Heilbronn', 'Seilbahn Heilbronn Text', pub,
                  'example.org', 'de', 'DE', 'News', None, 0, '', 'q-' + src, True)
        st.upsert(it)
        st.reset_run(f'r{n + 2}')      # one sighting per source, project and run
    st.commit()
    out = tmp_path / 'raw.json'
    st.export_raw(str(out), dt.datetime(2026, 10, 27, tzinfo=UTC))
    r = json.load(open(out, encoding='utf-8'))[0]
    assert r['found_by_sources'] == ['exa', 'tavily'] and r['n_sightings'] == 3


def test_source_where_every_feed_failed_is_failed_not_partial():
    import run_collect as rc
    dead = [{'source': 'rss', 'project': 'heilbronn_cablecar', 'items': 0, 'feed_status': {'a': ('error', 'dns'), 'b': ('error', 'timeout')}},
            {'source': 'rss', 'project': '*', 'feed_status': {'c': ('gated', 'HTML challenge')}}]
    assert rc.source_status(dead) == 'failed'
    half = [{'source': 'rss', 'project': 'heilbronn_cablecar', 'items': 3, 'feed_status': {'a': ('ok', ''), 'b': ('error', 'timeout')}}]
    assert rc.source_status(half) == 'partial'
    ok = [{'source': 'rss', 'project': 'heilbronn_cablecar', 'items': 3, 'feed_status': {'a': ('ok', '')}}]
    assert rc.source_status(ok) == 'success'
