"""Router tests: queue listing, blind queues, append-only corrections, validation, export."""
import json

from test_review_support import (DOCS, PIDS, SENTINEL_SOURCE, SENTINEL_WHY, client, env, keys_in, post)  # noqa: F401

HIDDEN_KEYS = {"why", "model_project", "model_stance", "model_tone", "label_source"}


def test_queues_listed_in_review_order(client):
    r = client.get("/api/review/queues", params={"labeller": "Alice"})
    assert r.status_code == 200
    body = r.json()
    assert [q["queue"] for q in body["queues"]] == ["pairs", "stance", "events", "disputes"]
    by = {q["queue"]: q for q in body["queues"]}
    assert [by[k]["n_items"] for k in ("pairs", "stance", "events", "disputes")] == [8, 6, 4, 3]
    assert by["pairs"]["blind"] and by["stance"]["blind"] and not by["events"]["blind"] and not by["disputes"]["blind"]
    assert by["pairs"]["label_schema"]["relation"]["values"] == ["same", "related", "opposing", "unrelated"]
    assert by["pairs"]["my_progress"] == {"labeller": "alice", "done": 0, "total": 8, "last_ts": None}
    assert all(q["guidelines"] for q in body["queues"])
    assert "not human-validated" in body["provisional_note"]


def test_blind_queue_hides_model_labels_until_annotated(client):
    for queue, sentinel in (("pairs", SENTINEL_WHY), ("stance", SENTINEL_SOURCE)):
        for url in (f"/api/review/queues/{queue}/items", f"/api/review/queues/{queue}/items?labeller=alice",
                    f"/api/review/queues/{queue}/next?labeller=alice"):
            r = client.get(url)
            assert r.status_code == 200
            assert sentinel not in r.text, url
            assert not HIDDEN_KEYS & set(keys_in(r.json())), url
    one = client.get(f"/api/review/queues/stance/items/{DOCS[0]}", params={"labeller": "alice"}).json()
    assert one["revealed"] is None and one["my_annotation"] is None
    assert set(one["data"]) == {"doc_id", "date", "channel", "domain", "url", "title", "excerpt"}


def test_blind_queue_reveals_only_to_the_labeller_who_annotated_that_item(client):
    r = post(client, "stance", DOCS[0], {"about": "yes", "stance": "neutral"})
    assert r.status_code == 200
    assert r.json()["item"]["revealed"] == {"model_project": "heilbronn_cablecar", "model_stance": "neutral",
                                            "model_tone": "neutral", "label_source": SENTINEL_SOURCE}
    items = client.get("/api/review/queues/stance/items", params={"labeller": "alice"}).json()["items"]
    assert items[0]["revealed"]["label_source"] == SENTINEL_SOURCE
    assert all(i["revealed"] is None for i in items[1:])           # her other items stay blind
    for params in ({"labeller": "bob"}, {}):                       # another labeller, and nobody
        r = client.get("/api/review/queues/stance/items", params=params)
        assert SENTINEL_SOURCE not in r.text and not HIDDEN_KEYS & set(keys_in(r.json()))
    post(client, "pairs", PIDS[1], {"relation": "same"})
    assert client.get(f"/api/review/queues/pairs/items/{PIDS[1]}?labeller=alice").json()["revealed"] == {"why": SENTINEL_WHY}
    assert client.get(f"/api/review/queues/pairs/items/{PIDS[1]}?labeller=bob").json()["revealed"] is None


def test_retracting_makes_the_item_blind_again(client):
    post(client, "pairs", PIDS[1], {"relation": "same"})
    r = post(client, "pairs", PIDS[1], None)
    assert r.status_code == 200 and r.json()["item"]["revealed"] is None and r.json()["item"]["my_annotation"] is None
    assert r.json()["progress"]["done"] == 0
    assert post(client, "pairs", PIDS[2], None).status_code == 400   # nothing to retract


def test_next_and_progress(client):
    n = client.get("/api/review/queues/pairs/next", params={"labeller": "alice"}).json()
    assert n["item"]["item_id"] == PIDS[0] and n["progress"]["done"] == 0
    r = post(client, "pairs", PIDS[0], {"relation": "related"}).json()
    assert r["next_item_id"] == PIDS[1] and r["progress"]["done"] == 1 and r["progress"]["total"] == 8
    assert client.get("/api/review/queues/pairs/next?labeller=alice").json()["item"]["item_id"] == PIDS[1]
    assert client.get("/api/review/queues/pairs/next?labeller=bob").json()["item"]["item_id"] == PIDS[0]
    for p in PIDS[1:]:
        last = post(client, "pairs", p, {"relation": "unrelated"}).json()
    assert last["next_item_id"] is None
    assert client.get("/api/review/queues/pairs/next?labeller=alice").json()["item"] is None
    todo = client.get("/api/review/queues/pairs/items?labeller=alice&status=todo").json()
    assert todo["n_matching"] == 0 and todo["n_done"] == 8
    assert client.get("/api/review/queues/pairs/items?labeller=bob&status=todo&limit=3").json()["n_matching"] == 8
    assert client.get("/api/review/queues/pairs/next").status_code == 400     # labeller required


def test_correction_is_appended_and_history_is_kept(client, env):
    post(client, "pairs", PIDS[0], {"relation": "same"}, note="first try")
    f = env / "review" / "annotations" / "pairs.jsonl"
    first_bytes = f.read_bytes()
    r = post(client, "pairs", PIDS[0], {"relation": "related"}, note="changed my mind")
    assert r.json()["annotation"]["rev"] == 2
    assert f.read_bytes().startswith(first_bytes)                   # the old line is untouched
    lines = [json.loads(l) for l in f.read_text().splitlines()]
    assert [l["label"]["relation"] for l in lines] == ["same", "related"] and [l["rev"] for l in lines] == [1, 2]
    assert set(lines[0]) == {"ts", "queue", "item_id", "labeller", "label", "note", "rev"}
    cur = client.get("/api/review/annotations", params={"queue": "pairs", "labeller": "alice"}).json()
    assert cur["n"] == 1 and cur["annotations"][0]["label"] == {"relation": "related"}
    hist = client.get("/api/review/annotations", params={"queue": "pairs", "history": "true"}).json()
    assert hist["n"] == 2
    item = client.get(f"/api/review/queues/pairs/items/{PIDS[0]}?labeller=alice").json()
    assert [h["note"] for h in item["history"]] == ["first try", "changed my mind"]
    assert item["my_annotation"]["label"] == {"relation": "related"}
    assert client.get("/api/review/queues/pairs/items?labeller=alice").json()["n_done"] == 1   # still one item


def test_annotation_file_holds_no_post_text_and_no_model_labels(client, env):
    post(client, "stance", DOCS[0], {"about": "yes", "stance": "oppose"}, note="ok")
    post(client, "disputes", DOCS[0], {"about": "passing", "stance": "neutral"})
    for name in ("stance", "disputes"):
        text = (env / "review" / "annotations" / f"{name}.jsonl").read_text()
        assert "POSTTEXT" not in text and SENTINEL_SOURCE not in text and "example.org" not in text


def test_label_validation(client):
    bad = [("pairs", PIDS[0], {"relation": "equal"}), ("pairs", PIDS[0], {}), ("pairs", PIDS[0], "same"),
           ("pairs", PIDS[0], {"relation": "same", "extra": 1}),
           ("stance", DOCS[0], {"about": "yes"}),                      # stance needed when it is about the project
           ("stance", DOCS[0], {"about": "maybe", "stance": "neutral"}),
           ("stance", DOCS[0], {"about": "yes", "stance": "unclear"}),
           ("events", "0", {"verdict": "confirmed", "correct_date": "2025-01-01"}),
           ("events", "0", {"verdict": "wrong_date", "correct_date": "last week"}),
           ("disputes", DOCS[0], {"about": "no", "project": "mars"})]
    for queue, item, label in bad:
        r = post(client, queue, item, label)
        assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_label", (queue, label, r.text)
    good = [("stance", DOCS[0], {"about": "no"}), ("stance", DOCS[1], {"about": "no", "stance": None}),
            ("stance", DOCS[2], {"about": "passing", "stance": "mixed"}),
            ("events", "0", {"verdict": "wrong_date", "correct_date": "2025-03-27"}),
            ("events", "2", {"verdict": "wrong_date", "correct_date": "2025-06"}),
            ("events", "1", {"verdict": "source_dead"}),
            ("disputes", DOCS[2], {"about": "no", "project": "ipai"})]
    for queue, item, label in good:
        assert post(client, queue, item, label).status_code == 200, (queue, label)
    assert post(client, "events", 3, {"verdict": "confirmed"}).status_code == 200   # numeric id accepted


def test_request_errors_use_the_contract_shape(client):
    cases = [(post(client, "nope", "x", {"relation": "same"}), 404, "unknown_queue"),
             (post(client, "pairs", "nope", {"relation": "same"}), 404, "unknown_item"),
             (post(client, "pairs", PIDS[0], {"relation": "same"}, labeller="has space"), 400, "invalid_labeller"),
             (post(client, "pairs", PIDS[0], {"relation": "same"}, labeller=""), 400, "invalid_labeller"),
             (client.post("/api/review/annotations", json={"queue": "pairs", "item_id": PIDS[0], "labeller": "a"}), 400, "invalid_request"),
             (client.get("/api/review/queues/nope/items"), 404, "unknown_queue"),
             (client.get("/api/review/queues/pairs/items/nope"), 404, "unknown_item"),
             (client.get("/api/review/queues/pairs/items?status=todo"), 400, "invalid_labeller"),
             (client.get("/api/review/export"), 404, "unknown_queue"),
             (client.get("/api/review/export?queue=pairs&format=xml"), 400, "invalid_request")]
    for r, status, code in cases:
        assert r.status_code == status and r.json()["error"]["code"] == code and r.json()["error"]["message"], r.text
    assert client.get("/api/review/annotations").json() == {"n": 0, "history": False, "annotations": []}


def test_missing_queue_file(client, env):
    (env / "queues" / "events_queue.parquet").unlink()
    by = {q["queue"]: q for q in client.get("/api/review/queues").json()["queues"]}
    assert by["events"]["available"] is False and by["events"]["n_items"] == 0 and by["pairs"]["available"] is True
    r = client.get("/api/review/queues/events/items")
    assert r.status_code == 503 and r.json()["error"]["code"] == "queue_unavailable"


def test_disputes_show_model_labels(client):
    items = client.get("/api/review/queues/disputes/items").json()["items"]
    assert items[0]["data"]["models"] == [{"model": "opus", "project": "heilbronn_cablecar", "stance": "neutral"},
                                          {"model": "haiku", "project": "heilbronn_cablecar", "stance": "support"},
                                          {"model": "qwen27", "project": "heilbronn_cablecar", "stance": "neutral"}]
    assert items[1]["data"]["models"][2] == {"model": "qwen27", "project": None, "stance": None}
    assert items[0]["revealed"] is None
    ev = client.get("/api/review/queues/events/items/2").json()
    assert ev["data"]["event_id"] == 2 and ev["data"]["date_precision"] == "month" and ev["item_id"] == "2"


def test_export_json_and_csv(client):
    post(client, "stance", DOCS[1], {"about": "yes", "stance": "support"}, labeller="bob", note="clear, friendly")
    post(client, "stance", DOCS[0], {"about": "no"})
    post(client, "stance", DOCS[0], {"about": "yes", "stance": "oppose"})
    j = client.get("/api/review/export", params={"queue": "stance"}).json()
    assert j["columns"] == ["item_id", "labeller", "about", "stance", "note", "ts", "rev"] and j["n"] == 2
    assert j["rows"][0]["labeller"] == "alice" and j["rows"][0]["stance"] == "oppose" and j["rows"][0]["rev"] == 2
    r = client.get("/api/review/export", params={"queue": "stance", "format": "csv", "labeller": "bob"})
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().split("\n")
    assert lines[0] == "item_id,labeller,about,stance,note,ts,rev" and len(lines) == 2
    assert lines[1].startswith('"100,1",bob,yes,support,"clear, friendly",')
    assert "POSTTEXT" not in r.text and SENTINEL_SOURCE not in r.text
