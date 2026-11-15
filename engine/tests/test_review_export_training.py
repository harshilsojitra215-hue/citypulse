"""export_training: the file must be readable by pipeline/27_finetune_matcher.py --train. Synthetic labels only."""
import json

import pandas as pd

from test_review_support import PIDS, client, env, post  # noqa: F401

LABELS = ["same", "related", "opposing", "unrelated"]


def test_nothing_written_without_human_labels(env, capsys):
    from citypulse.review import export_training
    assert export_training.main([]) == 0
    assert "no human labels yet" in capsys.readouterr().out
    assert not (env / "review" / "results" / "train_with_human.csv").exists()


def test_training_file_format_and_merge(client, env, capsys):
    from citypulse.review import export_training
    post(client, "pairs", PIDS[0], {"relation": "related"})       # p00 is also in train.csv as "same": human wins
    post(client, "pairs", PIDS[1], {"relation": "same"})          # agrees with the model
    post(client, "pairs", PIDS[5], {"relation": "opposing"})
    out = env / "custom" / "train_h.csv"
    assert export_training.main(["--out", str(out)]) == 0
    T = pd.read_csv(out)
    assert list(T.columns) == ["pid", "qid", "q_claim", "c_claim", "label", "label_source", "model_label"]
    assert T.pid.is_unique and len(T) == 5                         # t1, t2 from the model file + 3 human pairs
    # the same reads the trainer does
    T2 = T[T.label.isin(LABELS)].reset_index(drop=True)
    assert len(T2) == len(T) and T2.qid.notna().all() and T2.q_claim.notna().all() and T2.c_claim.notna().all()
    by = T.set_index("pid")
    assert by.loc["t1", "label_source"] == "opus" and by.loc["t1", "label"] == "same"
    assert by.loc["p00", "label"] == "related" and by.loc["p00", "label_source"] == "human" and by.loc["p00", "model_label"] == "same"
    assert by.loc["p05", "label"] == "opposing" and by.loc["p05", "model_label"] == "unrelated"
    assert by.loc["p00", "qid"] == "c0000" and by.loc["p01", "qid"] == "c0000" and by.loc["p05", "qid"] == "c0002"
    assert by.loc["p05", "q_claim"] == "query claim 5" and by.loc["p05", "c_claim"] == "candidate claim 5"
    meta = json.loads(out.with_suffix(".meta.json").read_text())
    assert meta["n_human"] == 3 and meta["n_model"] == 2 and meta["n_human_changed_vs_model"] == 2
    assert meta["n_human_replacing_a_train_label"] == 1 and meta["test_queries_now_in_training"] == ["c0000", "c0002"]
    printed = capsys.readouterr().out
    assert "27_finetune_matcher.py --train" in printed and "TEST" in printed
    # the model's own training file is not modified
    src = pd.read_csv(env / "lab" / "out" / "citypulse" / "train.csv")
    assert src.set_index("pid").loc["p00", "label"] == "same" and list(src.columns) == ["pid", "qid", "q_claim", "c_claim", "label"]


def test_works_without_lab_files(client, env):
    from citypulse.review import export_training
    for f in (env / "lab" / "out" / "citypulse").iterdir():
        f.unlink()
    post(client, "pairs", PIDS[2], {"relation": "unrelated"})
    post(client, "pairs", PIDS[3], {"relation": "same"}, labeller="bob")
    df, meta = export_training.build()
    assert len(df) == 2 and set(df.label_source) == {"human"} and df.qid.str.startswith("h").all()
    assert meta["model_train_file"] is None and "warning" in meta
    df_bob, _ = export_training.build("bob")
    assert df_bob.pid.tolist() == [PIDS[3]]
