"""Small checks for the helpers of experiments/fable_eval (no lab data, no network)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments" / "fable_eval"))
import fe_common as fe  # noqa: E402


def test_kappa_known_values():
    assert fe.kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert abs(fe.kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"])) < 1e-9
    assert fe.kappa(["a", "a"], ["a", "a"]) is None        # undefined: one label on both sides
    assert fe.kappa([], []) is None


def test_prf_plain_and_weighted():
    y, p = [True, True, False, False], [True, False, True, False]
    r = fe.prf(y, p)
    assert (r["precision"], r["recall"], r["f1"]) == (0.5, 0.5, 0.5)
    w = fe.prf(y, p, [1, 3, 1, 1])                          # the missed pair stands for three
    assert w["precision"] == 0.5 and w["recall"] == 0.25
    assert fe.prf([False], [False])["f1"] is None           # nothing to score: no fake number


def test_human_labels_newest_line_retraction_and_ties(tmp_path):
    d = tmp_path / "annotations"
    d.mkdir()
    rows = [("h", "p1", "same"), ("h", "p1", "related"),    # corrected: the newest line counts
            ("h", "p2", "same"), ("h", "p2", None),         # retracted
            ("h", "p3", "same"), ("j", "p3", "related"),    # two labellers disagree: left out
            ("h", "p4", "unrelated"), ("j", "p4", "unrelated")]
    with open(d / "pairs.jsonl", "w") as f:
        for who, pid, lab in rows:
            f.write(json.dumps({"labeller": who, "item_id": pid, "label": {"relation": lab} if lab else None}) + "\n")
        f.write("not json\n")
    labels, ties, who = fe.human_labels(tmp_path)
    assert labels == {"p1": "related", "p4": "unrelated"} and ties == ["p3"] and who == ["h", "j"]
    only_h, _, _ = fe.human_labels(tmp_path, "h")
    assert only_h == {"p1": "related", "p3": "same", "p4": "unrelated"}
    assert fe.human_labels(tmp_path / "missing") == ({}, [], [])
