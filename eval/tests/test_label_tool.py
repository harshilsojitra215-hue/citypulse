"""Label tool: saves after every label, validates values, resumes after restart."""
import csv
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'label_tool'))
import server  # noqa: E402


def _tasks(tmp_path):
    p = tmp_path / 'tasks.csv'
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['pid', 'ref', 'tier', 'date', 'media_type', 'text'])
        w.writerow(['P001', 'R1', '1', '2025-04-04', 'News', 'Heilbronn sagt Ja zur Seilbahn-Idee'])
        w.writerow(['P002', 'R2', '1', '2025-01-01', 'Forums', 'Skilift am Kampenwand, "Umlaut" test äöü'])
    return str(p)


def _start(state):
    srv = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(state))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}'


def _post(url, body):
    req = urllib.request.Request(url + '/api/label', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_save_validate_resume(tmp_path):
    out = str(tmp_path / 'labels_t.csv')
    st = server.build_state([_tasks(tmp_path)], 't', out)
    srv, url = _start(st)
    try:
        page = urllib.request.urlopen(url + '/').read().decode()
        assert 'Save and next' in page
        state = json.loads(urllib.request.urlopen(url + '/api/state').read())
        assert [t['pid'] for t in state['tasks']] == ['P001', 'P002'] and 'vendor_sentiment' not in state['tasks'][0]
        assert 'Codebook v1 (frozen)' in urllib.request.urlopen(url + '/codebook').read().decode()
        code, j = _post(url, {'pid': 'P001', 'project': 'heilbronn_cablecar', 'stance': 'neutral_informative',
                              'voice': 'news_institutional', 'arguments': ['cost']})
        assert code == 200 and j['done'] == 1
        rows = list(csv.DictReader(open(out, encoding='utf-8-sig')))      # on disk right after one label
        assert rows[0]['pid'] == 'P001' and rows[0]['arguments'] == 'cost' and rows[0]['labeller'] == 't'
        assert list(rows[0])[:8] == ['pid', 'labeller', 'project', 'stance', 'voice', 'arguments', 'note', 'saved_at']
        assert rows[0]['ref'] == 'R1'
        code, j = _post(url, {'pid': 'P002', 'project': 'irrelevant', 'stance': 'support', 'voice': 'citizen',
                              'arguments': ['cost']})
        assert code == 200 and j['row']['stance'] == 'unclear' and j['row']['arguments'] == ''   # codebook rule enforced
        code, j = _post(url, {'pid': 'P001', 'project': 'heilbronn', 'stance': 'support', 'voice': 'citizen'})
        assert code == 400 and 'project must be one of' in j['error']
        code, j = _post(url, {'pid': 'P999', 'project': 'irrelevant', 'stance': 'unclear', 'voice': 'citizen'})
        assert code == 400
        # relabel overwrites, no duplicate row
        _post(url, {'pid': 'P001', 'project': 'heilbronn_cablecar', 'stance': 'support', 'voice': 'citizen', 'note': 'a\nb'})
        rows = list(csv.DictReader(open(out, encoding='utf-8-sig')))
        assert len(rows) == 2 and rows[0]['stance'] == 'support' and rows[0]['note'] == 'a b'
    finally:
        srv.shutdown()
    st2 = server.build_state([_tasks(tmp_path)], 't', out)     # restart: resumes from disk
    assert set(st2['labels']) == {'P001', 'P002'}


def test_eval_reads_tool_output(tmp_path):
    from evallib.io import load_labels
    out = str(tmp_path / 'labels_t.csv')
    st = server.build_state([_tasks(tmp_path)], 't', out)
    srv, url = _start(st)
    try:
        _post(url, {'pid': 'P001', 'project': 'heilbronn_cablecar', 'stance': 'mixed', 'voice': 'citizen',
                    'arguments': ['cost', 'traffic_mobility']})
    finally:
        srv.shutdown()
    d = load_labels(out)
    assert d['P001']['stance'] == 'mixed' and d['P001']['arguments'] == ['cost', 'traffic_mobility']


def test_human_labels_map_to_pilot_ids(tmp_path, monkeypatch):
    """Tool writes the contract post_id (mention_id); eval maps it back to the pilot pid for comparisons."""
    from evallib import io
    key = io.mention_to_pilot()
    mid, pid = next(iter(key.items()))
    gold = tmp_path / 'gold'
    gold.mkdir()
    with open(gold / 'labels_a.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(server.COLS)
        w.writerow([mid, 'a', 'irrelevant', 'unclear', 'unclear', '', '', '2026-11-14T20:00:00', pid])
    monkeypatch.setattr(io, 'GOLD', str(gold))
    hum, adj = io.load_human()
    assert pid in hum['a'] and hum['a'][pid]['post_id'] == mid and adj is None


def test_contract_label_run_file(tmp_path):
    """Pipeline run files: header line, post_id key, JSON-string arguments, abstain."""
    import json as _j
    from evallib.io import load_labels
    lines = [{'_run': {'run_id': 'x'}},
             {'post_id': '1,2', 'project': 'heilbronn_cablecar', 'stance': 'oppose', 'voice': 'citizen',
              'arguments': '["cost"]', 'abstain': False},
             {'post_id': '3,4', 'project': 'paris_c1', 'stance': 'support', 'voice': 'citizen',
              'arguments': [], 'abstain': True}]
    p = tmp_path / 'run.jsonl'
    p.write_text('\n'.join(_j.dumps(x) for x in lines) + '\n', encoding='utf-8')
    d = load_labels(str(p))
    assert set(d) == {'1,2', '3,4'} and d['1,2']['arguments'] == ['cost'] and d['3,4']['stance'] is None
