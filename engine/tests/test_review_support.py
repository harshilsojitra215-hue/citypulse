"""Shared fixtures for the review tests: synthetic queues and a temporary annotation store.

Every test runs against temporary folders. Nothing is ever written to the real review/annotations/ or to the lab.
The labels used here are synthetic test data, not human judgements.
"""
import json

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SENTINEL_WHY = "models disagree"
SENTINEL_SOURCE = "sentinelmodel"
PIDS = [f"p{i:02d}" for i in range(8)]
DOCS = [f"100,{i}" for i in range(6)]
OPUS_PAIR = ["same", "same", "related", "related", "unrelated", "unrelated", "opposing", "related"]
MODEL_STANCE = ["neutral", "neutral", "support", "oppose", "unclear", "neutral"]


def make_queues(folder):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"pid": PIDS, "q_claim": [f"query claim {i}" for i in range(8)], "q_project": "heilbronn_cablecar",
                  "c_claim": [f"candidate claim {i}" for i in range(8)], "c_project": "bonn_cablecar",
                  "why": [SENTINEL_WHY if i % 2 else "random" for i in range(8)]}).to_parquet(folder / "pair_queue.parquet")
    pd.DataFrame({"doc_id": DOCS, "date": "2026-07-01", "channel": "news", "domain": "example.org",
                  "url": [f"https://example.org/{i}" for i in range(6)], "title": [f"title {i}" for i in range(6)],
                  "excerpt": [f"POSTTEXT excerpt {i}" for i in range(6)], "model_project": "heilbronn_cablecar",
                  "model_stance": MODEL_STANCE, "model_tone": "neutral",
                  "label_source": SENTINEL_SOURCE}).to_parquet(folder / "stance_queue.parquet")
    pd.DataFrame({"doc_id": DOCS[:3], "opus_project": ["heilbronn_cablecar", "heilbronn_cablecar", "ipai"],
                  "opus_stance": ["neutral", "support", "neutral"],
                  "haiku_project": ["heilbronn_cablecar", "other_urban_cablecar", "heilbronn_cablecar"],
                  "haiku_stance": ["support", "support", "oppose"],
                  "qwen27_project": ["heilbronn_cablecar", None, "ipai"], "qwen27_stance": ["neutral", None, "na"],
                  "url": "https://example.org/x", "date": "2026-07-01", "domain": "example.org",
                  "excerpt": "POSTTEXT disputed"}).to_parquet(folder / "disputes_queue.parquet")
    pd.DataFrame({"event_id": [0, 1, 2, 3], "date": ["2025-03-28", "2025-04-01", "2025-05", "2025-06-10"],
                  "date_precision": ["day", "day", "month", "day"], "project": "heilbronn_cablecar",
                  "event_type": "media", "title_en": [f"event {i}" for i in range(4)], "detail": "detail",
                  "source_url": "https://example.org/e", "source_name": "Example",
                  "verified": ["no", "yes", "no", "no"]}).to_parquet(folder / "events_queue.parquet")


def make_lab(folder):
    """A minimal fake lab: model pair labels, a tiny train.csv and the pair table (for query ids)."""
    out = folder / "out" / "citypulse"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "pairlabels_opus.jsonl", "w") as f:
        for p, l in zip(PIDS, OPUS_PAIR):
            f.write(json.dumps({"pid": p, "label": l}) + "\n")
    pd.DataFrame({"pid": PIDS, "qid": [f"c{i // 2:04d}" for i in range(8)]}).to_parquet(out / "pairs.parquet")
    pd.DataFrame({"pid": ["t1", "t2", "p00"], "qid": ["c9001", "c9001", "c0000"],
                  "q_claim": ["train q", "train q", "query claim 0"], "c_claim": ["train c1", "train c2", "candidate claim 0"],
                  "label": ["same", "unrelated", "same"]}).to_csv(out / "train.csv", index=False)
    return folder


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Temporary queues, store and lab. Returns the tmp folder."""
    monkeypatch.setenv("CITYPULSE_REVIEW_QUEUES", str(tmp_path / "queues"))
    monkeypatch.setenv("CITYPULSE_REVIEW_DIR", str(tmp_path / "review"))
    monkeypatch.setenv("CITYPULSE_LAB", str(tmp_path / "lab"))
    make_queues(tmp_path / "queues")
    make_lab(tmp_path / "lab")
    from citypulse.review import config, queues
    queues._cache.clear()
    assert tmp_path in config.annotations_dir().parents  # the real store is never the target
    yield tmp_path
    queues._cache.clear()


@pytest.fixture
def client(env):
    from citypulse.review import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def post(client, queue, item_id, label, labeller="alice", note=""):
    return client.post("/api/review/annotations",
                       json={"queue": queue, "item_id": item_id, "label": label, "labeller": labeller, "note": note})


def keys_in(obj):
    """every dict key anywhere inside a JSON value"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from keys_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from keys_in(v)
