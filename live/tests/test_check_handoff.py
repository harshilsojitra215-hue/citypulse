"""The handoff checker must pass a good file and catch each kind of broken one (otherwise "HANDOFF OK" means nothing)."""
import copy
import json
import os
import sys

LIVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LIVE, 'tools'))
import check_handoff as ch  # noqa: E402

GOOD = {'mention_id': 'live:0123456789ab', 'published_at': '2026-11-10T08:00:00+0000', 'url': 'https://example.org/a',
        'media_type_name': 'News', 'source_name': 'example.org', 'language_code': 'de', 'country_code': 'DE', 'sentiment': -99,
        'reach': None, 'engagements': 0, 'authors': ['0123456789abcdef'], 'title': 'Seilbahn Heilbronn', 'content': 'Text',
        'discovered_at': '2026-11-14T10:00:00+00:00', 'retrieved_at': '2026-11-14T10:00:00+00:00', 'modified_at': None,
        'last_changed_at': '2026-11-14T10:00:00+00:00', 'version_no': 1, 'late_discovered': False, 'kind': 'news', 'replay': False,
        'published': False, 'source_terms': 'x', 'collector_source': 'exa', 'project_hint': 'heilbronn_cablecar', 'content_hash': 'ab',
        'title_hit': True, 'radar_match': 'strong', 'text_scope': 'full', 'date_known': True, 'found_by_sources': ['exa'], 'n_sightings': 1}
RECEIPT = {'run_id': 'r', 'status': 'partial', 'published': False, 'started_at': 'x', 'finished_at': 'x', 'since': 'x', 'sources': [],
           'totals': {}, 'coverage_gaps': [], 'export': {}}


def run(tmp_path, recs, receipt=RECEIPT):
    raw, rc = tmp_path / 'raw_live.json', tmp_path / 'receipt_x.json'
    raw.write_text(json.dumps(recs), encoding='utf-8')
    rc.write_text(json.dumps(receipt), encoding='utf-8')
    return ch.main(['--raw', str(raw), '--receipt', str(rc)])


def bad(**change):
    r = copy.deepcopy(GOOD)
    for k, v in change.items():
        if v is KeyError:
            del r[k]
        else:
            r[k] = v
    return [r]


def test_good_file_passes(tmp_path):
    assert run(tmp_path, [GOOD]) == 0


def test_each_broken_file_fails(tmp_path):
    for case in (bad(authors=['Max Mustermann']), bad(mention_id='12345'), bad(published=True), bad(kind='tweet'),
                 bad(radar_match='maybe'), bad(url=KeyError), bad(published_at='14.11.2026'), [GOOD, GOOD]):
        assert run(tmp_path, case) == 1, case
    assert run(tmp_path, [GOOD], dict(RECEIPT, published=True)) == 1
    assert run(tmp_path, [GOOD], dict(RECEIPT, status='green')) == 1
