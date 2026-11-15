"""Evaluation tests. All labels here are synthetic and live in temporary folders."""
import json
import os

import pandas as pd
import pytest

from test_review_support import DOCS, OPUS_PAIR, PIDS, client, env, post  # noqa: F401

METRIC_KEYS = {"human_vs_model", "model_vs_human", "verdict_counts", "human_sided_with", "label_counts", "kappa",
               "accuracy", "agreement", "about_counts"}


def _keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


def test_kappa_and_agreement():
    from citypulse.review.evaluate import agreement, kappa
    a = ["y"] * 20 + ["y"] * 5 + ["n"] * 10 + ["n"] * 15
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert agreement(a, b) == 0.7 and kappa(a, b) == 0.4          # textbook example: po 0.7, pe 0.5
    assert kappa(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    assert kappa([], []) is None and agreement([], []) is None    # undefined, never a made-up number
    assert kappa(["a", "a"], ["a", "a"]) is None                  # one single label on both sides
    sk = pytest.importorskip("sklearn.metrics")
    x, y = list("aabbccabca"), list("abbbccaaca")
    assert kappa(x, y) == pytest.approx(sk.cohen_kappa_score(x, y), abs=1e-4)


def test_evaluate_with_zero_labels_reports_no_human_labels(env, capsys):
    from citypulse.review import evaluate
    assert evaluate.main(["--no-benchmark"]) == 0
    out = capsys.readouterr().out
    assert "no human labels yet" in out
    res = json.loads((env / "review" / "results" / "latest.json").read_text())
    assert res["message"] == "no human labels yet" and res["n_annotations"] == 0 and res["labellers"] == []
    for name, n in (("pairs", 8), ("stance", 6), ("events", 4), ("disputes", 3)):
        assert res[name]["status"] == "no human labels yet" and res[name]["n_labelled"] == 0 and res[name]["n_items"] == n
    assert not METRIC_KEYS & set(_keys(res))                       # no metric of any kind without labels
    assert not (env / "lab" / "out" / "citypulse" / "human_labels.csv").exists()
    assert evaluate.main([]) == 0                                  # with the benchmark switched on it still runs cleanly
    assert "no human labels yet" in capsys.readouterr().out


def test_evaluate_runs_without_queue_files_and_without_lab(env, capsys):
    from citypulse.review import evaluate, queues
    for f in (env / "queues").iterdir():
        f.unlink()
    queues._cache.clear()
    assert evaluate.main(["--no-benchmark"]) == 0
    assert "no human labels yet" in capsys.readouterr().out


def test_pairs_against_synthetic_labels(client, env):
    from citypulse.review import evaluate
    human = list(OPUS_PAIR)
    human[0], human[4] = "related", "related"                      # 6 of 8 agree with the model
    for p, l in zip(PIDS, human):
        post(client, "pairs", p, {"relation": l})
    post(client, "pairs", PIDS[7], {"relation": "same"})           # a slip ...
    post(client, "pairs", PIDS[7], {"relation": human[7]})         # ... corrected: only the last one counts
    res = evaluate.evaluate(run_benchmark=True)                    # 8 pairs: too few, benchmark must be skipped
    s = res["pairs"]
    assert s["status"] == "ok" and s["n_labelled"] == 8 and s["complete"] is True
    assert s["label_counts"] == {"same": 1, "related": 5, "opposing": 1, "unrelated": 1}
    opus = s["human_vs_model"][0]
    assert opus["model"] == "opus" and opus["n"] == 8 and opus["agreement"] == 0.75
    sk = pytest.importorskip("sklearn.metrics")
    assert opus["kappa_4way"] == pytest.approx(sk.cohen_kappa_score(human, OPUS_PAIR), abs=1e-4)
    assert opus["kappa_same"] == pytest.approx(sk.cohen_kappa_score([h == "same" for h in human], [o == "same" for o in OPUS_PAIR]), abs=1e-4)
    assert 0 < opus["kappa_4way"] < 1
    assert {r["why"]: r["n"] for r in s["by_why"]} == {"models disagree": 4, "random": 4}
    assert s["benchmark"]["status"] == "skipped" and "at least" in s["benchmark"]["message"]
    # the CSV the benchmark script reads: pid,label first, one row per pair, in the temporary lab only
    csv = pd.read_csv(env / "lab" / "out" / "citypulse" / "human_labels.csv")
    assert list(csv.columns[:2]) == ["pid", "label"] and len(csv) == 8
    assert csv.drop_duplicates("pid").set_index("pid").label.to_dict() == dict(zip(PIDS, human))
    assert res["message"].startswith("human review in progress") and res["labellers"] == ["alice"]


def test_stance_events_disputes_against_synthetic_labels(client, env):
    from citypulse.review import evaluate
    # model stance: neutral, neutral, support, oppose, unclear, neutral
    post(client, "stance", DOCS[0], {"about": "yes", "stance": "neutral"})     # agrees
    post(client, "stance", DOCS[1], {"about": "yes", "stance": "oppose"})      # model said neutral
    post(client, "stance", DOCS[2], {"about": "passing", "stance": "support"})  # agrees
    post(client, "stance", DOCS[3], {"about": "no"})                           # not about: removed
    post(client, "stance", DOCS[4], {"about": "yes", "stance": "mixed"})       # model 'unclear' counts as mixed
    post(client, "events", "0", {"verdict": "confirmed"})
    post(client, "events", "1", {"verdict": "wrong_date", "correct_date": "2025-04-02"}, note="article says 2 April")
    post(client, "events", "2", {"verdict": "source_dead"})
    post(client, "disputes", DOCS[0], {"about": "yes", "stance": "neutral"})   # opus + qwen27 right, haiku wrong
    post(client, "disputes", DOCS[1], {"about": "yes", "stance": "support"})   # opus + haiku right, qwen27 no label
    res = client.post("/api/review/evaluate").json()
    st = res["stance"]
    assert st["n_labelled"] == 5 and st["about_counts"] == {"yes": 3, "passing": 1, "no": 1}
    allrow = st["model_vs_human"][0]
    assert allrow["n"] == 4 and allrow["accuracy"] == 0.75 and -1 <= allrow["kappa"] <= 1
    c = st["stance_counts"]
    assert c["model"] == {"neutral": 3, "support": 1, "oppose": 1, "unclear": 1}
    assert c["corrected"] == {"neutral": 2, "oppose": 1, "support": 1, "mixed": 1}   # DOCS[5] keeps the model label
    assert (c["n_reviewed"], c["n_unreviewed"], c["n_changed"], c["n_not_about"], c["n_passing"]) == (5, 1, 1, 1, 1)
    assert c["opposition_share_of_sided"] == {"value": 0.5, "n": 2}
    assert st["relevance"]["human_confirms_about"] == 4
    ev = res["events"]
    assert ev["verdict_counts"] == {"confirmed": 1, "wrong_date": 1, "wrong_content": 0, "source_dead": 1}
    assert [t["item_id"] for t in ev["to_fix"]] == ["1", "2"] and ev["to_fix"][0]["correct_date"] == "2025-04-02"
    assert ev["by_previous_verified_flag"] == {"no": {"confirmed": 1, "source_dead": 1}, "yes": {"wrong_date": 1}}
    d = res["disputes"]
    assert d["n_labelled"] == 2 and d["stance_counts"]["neutral"] == 1 and d["stance_counts"]["support"] == 1
    sided = {r["model"]: r for r in d["human_sided_with"]}
    assert sided["opus"]["stance_agreement"] == 1.0 and sided["opus"]["n_stance"] == 2
    assert sided["haiku"]["stance_agreement"] == 0.5 and sided["haiku"]["about_agreement"] == 0.5
    assert sided["qwen27"]["n_stance"] == 1 and sided["qwen27"]["n_about"] == 1
    assert res["pairs"]["status"] == "no human labels yet"
    assert client.get("/api/review/results").json()["stance"]["n_labelled"] == 5
    assert "accuracy 75.0%" in evaluate.render(res)


def test_two_labellers_agreement_and_conflicts(client, env):
    from citypulse.review import evaluate
    for p, a, b in zip(PIDS[:4], ["same", "related", "related", "unrelated"], ["same", "related", "same", "unrelated"]):
        post(client, "pairs", p, {"relation": a}, labeller="alice")
        post(client, "pairs", p, {"relation": b}, labeller="bob")
    post(client, "pairs", PIDS[4], {"relation": "opposing"}, labeller="alice")
    s = evaluate.evaluate(run_benchmark=False)["pairs"]
    il = s["inter_labeller"][0]
    assert (il["a"], il["b"], il["n"]) == ("alice", "bob", 4)
    assert il["relation"]["agreement"] == 0.75 and il["relation"]["kappa"] == pytest.approx(0.6364, abs=1e-3)
    assert s["n_conflicts"] == 1 and s["conflicts"] == [PIDS[2]]   # the tie is left out, not guessed
    assert s["n_labelled"] == 4 and s["labellers"] == ["alice", "bob"]
    only_bob = evaluate.evaluate(run_benchmark=False, labeller="bob", write=False)["pairs"]
    assert only_bob["n_labelled"] == 4 and "n_conflicts" not in only_bob


def test_results_endpoint_before_any_evaluation(client):
    assert client.get("/api/review/results").json()["available"] is False
    r = client.post("/api/review/evaluate").json()
    assert r["message"] == "no human labels yet"
    assert client.get("/api/review/results").json()["message"] == "no human labels yet"


def test_benchmark_is_reported_as_failed_not_faked(client, env):
    """With labels but a lab that lacks the benchmark inputs, the script fails: the result must say so."""
    from citypulse.review import evaluate
    for p, l in zip(PIDS, OPUS_PAIR):
        post(client, "pairs", p, {"relation": l})
    b = evaluate.evaluate(run_benchmark=True, min_pairs=1)["pairs"]["benchmark"]
    assert b["status"] in ("failed", "skipped") and "methods" not in b and "precision" not in json.dumps(b)


@pytest.mark.skipif(not os.environ.get("CITYPULSE_TEST_BENCHMARK"), reason="slow (about 30 s) and needs the real lab; set CITYPULSE_TEST_BENCHMARK=1")
def test_benchmark_runs_on_the_real_lab_without_changing_it(tmp_path, monkeypatch):
    """Opt-in plumbing check: SYNTHETIC labels (model labels with random flips) in a temp store, real lab read-only."""
    import random
    from citypulse.review import config, evaluate, queues, store
    real_lab, real_queues = config.lab_out(), config.queue_dir()
    if not (real_lab / "pairs.parquet").exists() or not (real_queues / "pair_queue.parquet").exists():
        pytest.skip("real lab or pair queue not on this machine")
    before = {f.name: (f.stat().st_mtime_ns, f.stat().st_size) for f in real_lab.iterdir()}
    shadow = tmp_path / "lab" / "out" / "citypulse"
    shadow.mkdir(parents=True)
    for f in real_lab.iterdir():
        if (f.is_file() and not f.name.startswith(evaluate.BENCHMARK_OUTPUTS)) or (f.is_dir() and f.name == "v2"):
            try:
                os.symlink(f.resolve(), shadow / f.name, target_is_directory=f.is_dir())
            except OSError:                                   # Windows without Developer Mode
                import shutil
                (shutil.copytree if f.is_dir() else shutil.copy2)(f, shadow / f.name)
    monkeypatch.setenv("CITYPULSE_REVIEW_QUEUES", str(real_queues))
    monkeypatch.setenv("CITYPULSE_REVIEW_DIR", str(tmp_path / "review"))
    monkeypatch.setenv("CITYPULSE_LAB", str(tmp_path / "lab"))
    queues._cache.clear()
    opus = evaluate.load_model_pair_labels()["opus"]
    rnd = random.Random(3)
    for p in queues.load("pairs").ids:
        store.append("pairs", p, "synthetic", {"relation": opus[p] if rnd.random() > 0.25 else rnd.choice(queues.RELATIONS)})
    b = evaluate.evaluate(run_benchmark=True)["pairs"]["benchmark"]
    queues._cache.clear()
    assert b["status"] == "ok", b
    assert b["n_test_pairs"] == 120 and b["selected"] and len(b["methods"]) >= 3
    for m in b["methods"]:
        assert 0 <= m["precision"] <= 1 and 0 <= m["recall"] <= 1 and 0 <= m["f1"] <= 1
    assert {f.name: (f.stat().st_mtime_ns, f.stat().st_size) for f in real_lab.iterdir()} == before   # lab untouched
