"""score_run.py: one command for any contract-format label run. Fails clearly, tolerates alias values."""
import json
import os

import pytest

import score_run as SR

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = os.path.join(os.path.dirname(HERE), 'xstance', '_answer_key', 'xstance_key.jsonl')


def write(tmp_path, rows, name='run.jsonl'):
    p = tmp_path / name
    p.write_text('\n'.join(json.dumps(r) if not isinstance(r, str) else r for r in rows) + '\n', encoding='utf-8')
    return str(p)


def test_missing_id_column_gives_clear_error(tmp_path):
    p = write(tmp_path, [{'text': 'x', 'project': 'irrelevant'}])
    with pytest.raises(SR.RunError, match='id column missing'):
        SR.load_run(p)
    assert SR.main([p, '--no-write']) == 2


def test_no_label_column_and_bad_json_and_missing_file(tmp_path):
    with pytest.raises(SR.RunError, match='no label column'):
        SR.load_run(write(tmp_path, [{'post_id': '1', 'foo': 'bar'}]))
    with pytest.raises(SR.RunError, match='not valid JSON'):
        SR.load_run(write(tmp_path, ['{broken'], 'b.jsonl'))
    assert SR.main([str(tmp_path / 'nope.jsonl'), '--no-write']) == 2


def test_tolerates_header_pid_alias_values_and_missing_optional_columns(tmp_path):
    p = write(tmp_path, [{'_run': {'run_id': 'r'}},
                         {'pid': 'a', 'project': 'Heilbronn', 'stance': 'Neutral'},       # aliases, no voice/arguments
                         {'post_id': 'b', 'project': 'heilbronn_cablecar', 'stance': 'against', 'arguments': '["cost"]'},
                         {'post_id': 'c', 'abstain': True},                                # abstain: kept, no project
                         {'post_id': 'd', 'project': 'irrelevant', 'stance': 'weird_value'}])
    labels, info = SR.load_run(p)
    assert labels['a']['project'] == 'heilbronn_cablecar' and labels['a']['stance'] == 'neutral_informative'
    assert labels['b']['stance'] == 'oppose' and labels['b']['arguments'] == ['cost']
    assert labels['c']['stance'] is None and info['n_abstain'] == 1
    assert any('weird_value' in w for w in info['warnings'])


def test_project_only_run_scores_and_reports(tmp_path, capsys):
    p = write(tmp_path, [{'post_id': '15565093,44', 'project': 'irrelevant'}, {'post_id': 'z', 'project': 'paris_c1'}])
    assert SR.main([p, '--no-write', '--B', '50']) == 0
    out = capsys.readouterr().out
    assert 'Regression suite' in out and 'project-only run' in out and 'no X001' in out.replace('The run has ', 'no ')


@pytest.mark.skipif(not os.path.exists(KEY), reason='X-Stance key not built')
def test_xstance_side_accuracy_and_no_side(tmp_path):
    key = [json.loads(l) for l in open(KEY, encoding='utf-8') if l.strip()][:10]
    rows = []
    for i, k in enumerate(key):
        right = 'support' if k['label'] == 'FAVOR' else 'oppose'
        wrong = 'oppose' if right == 'support' else 'support'
        rows.append({'post_id': k['pid'], 'project': 'heilbronn_cablecar',
                     'stance': right if i < 6 else (wrong if i < 8 else 'unclear')})
    labels, _ = SR.load_run(write(tmp_path, rows))
    x = SR.score_xstance(labels, 50)
    assert x['n'] == 10 and x['swapped'] == 2 and x['no_side']['k'] == 2
    assert x['accuracy']['value'] == pytest.approx(0.6)
