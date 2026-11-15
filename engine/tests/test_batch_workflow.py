"""Batch workflow tests.

Everything except the test marked `live` runs without a model and without the real data bundle: the store is pointed
at a tiny bundle built in a temporary folder, the LLM is replaced by a keyword stub and engine.ingest by a stub with
the same signature. The runs folder is always temporary (never the repository's runs/).

Live run (real Claude Haiku through the CLI, real embedder and ingest, real bundle, temporary runs folder):
    .venv/bin/python -m pytest tests/test_batch_workflow.py -m live -s
"""
import csv, hashlib, io, json, re, shutil, time
from pathlib import Path
import numpy as np, pandas as pd, pytest
from citypulse import batch, config
from citypulse.batch import formats, runs, steps
from citypulse.engine import store

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "samples" / "demo_batch_synthetic.json"
POST_COLS = ["doc_id", "published_at", "date", "month", "week", "channel", "media_type", "domain", "source_name", "url", "lang", "title",
             "excerpt", "project", "passing", "stance", "tone", "label_source", "voice", "dup_key", "dup_count", "is_first_copy",
             "tool_sentiment", "run_id", "project_name", "n_claims"]
CLAIM_COLS = ["cid", "doc_id", "claim", "project", "project_name", "date", "ts", "channel", "domain", "url", "topic", "polarity", "stance",
              "voice", "norm", "family_id", "family_name", "family_frozen", "family_frozen_name", "cluster_all", "run_id"]
PAIR_COLS = ["pid", "qid", "cand", "same_project", "side_rank", "cos", "p_same", "p_rel", "ft_same", "score_source", "model_version"]
DIM = 8
KNOWN_TEXT = "Die Seilbahn in Heilbronn wurde im Gemeinderat vorgestellt. Dieser Text ist dem System schon bekannt."
HN = "heilbronn_cablecar"


def _unit(seed, dim=DIM):
    v = np.random.default_rng(int(hashlib.md5(str(seed).encode()).hexdigest()[:8], 16)).normal(size=dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _build_bundle(d: Path):
    """A minimal data bundle with the real bundle's columns."""
    d.mkdir(parents=True)
    base = steps.pipeline_module("01_build_base.py")
    def post(doc_id, text, when, project, **kw):
        ts = pd.Timestamp(when, tz="UTC")
        return dict(doc_id=doc_id, published_at=ts, date=ts.strftime("%Y-%m-%d"), month=ts.strftime("%Y-%m"), week=ts.strftime("%Y-%m-%d"),
                    channel="news", media_type="News", domain="base.example", source_name="Base", url=f"https://base.example/{doc_id}",
                    lang="de", title="", excerpt=text[:400], project=project, passing=False, stance="neutral", tone="neutral",
                    label_source="haiku", voice=steps.h6("dom:base.example"), dup_key=hashlib.md5(base.norm_for_dup(text).encode()).hexdigest(),
                    dup_count=1, is_first_copy=True, tool_sentiment=0, run_id="base", project_name=config.PROJECT_NAMES[project], n_claims=1) | kw
    posts = pd.DataFrame([post("base-1", KNOWN_TEXT, "2026-05-01T10:00:00", HN),
                          post("known-id-1", "Ein älterer Beitrag zur Seilbahn Heilbronn und zur Stadtbahn.", "2026-06-01T10:00:00", HN),
                          post("base-3", "Le Câble C1 relie Créteil à Villeneuve-Saint-Georges.", "2026-06-10T10:00:00", "paris_c1")])[POST_COLS]
    def claim(cid, doc_id, text, when, project, topic, pol, fam, cl):
        ts = pd.Timestamp(when, tz="UTC")
        return dict(cid=cid, doc_id=doc_id, claim=text, project=project, project_name=config.PROJECT_NAMES[project], date=ts.strftime("%Y-%m-%d"),
                    ts=ts, channel="news", domain="base.example", url=f"https://base.example/{doc_id}", topic=topic, polarity=pol,
                    stance="neutral", voice=steps.h6("dom:base.example"), norm=re.sub(r"[^a-z0-9 ]", "", text.lower()),
                    family_id=fam, family_name=text, family_frozen=fam, family_frozen_name=text, cluster_all=cl, run_id="base")
    claims = pd.DataFrame([claim("c0001", "base-1", "Cable car costs are too high", "2026-05-01T10:00:00", HN, "cost_financing", "contra", "fam1", 1),
                           claim("c0002", "known-id-1", "A Stadtbahn would be the better choice", "2026-06-01T10:00:00", HN, "alternatives", "contra", "solo:c0002", -1),
                           claim("c0003", "base-3", "Cable C1 connects suburbs to the metro", "2026-06-10T10:00:00", "paris_c1", "transport_benefit", "pro", "solo:c0003", -1)])[CLAIM_COLS]
    posts.to_parquet(d / "posts.parquet", index=False)
    claims.to_parquet(d / "claims.parquet", index=False)
    np.save(d / "claims_emb.npy", np.vstack([_unit(c) for c in claims.cid]))
    pd.DataFrame([dict(date="2026-11-01", date_precision="day", project=HN, event_type="media", title_en="Fixture event", detail="",
                       source_url="https://base.example/e", source_name="Base", verified="no")]).to_parquet(d / "events.parquet", index=False)
    pd.DataFrame([dict(family_id="fam1", name="Cable car costs are too high", n=1, main_topic="cost_financing", pro=0.0, contra=1.0,
                       first_seen="2026-05-01", last_seen="2026-05-01")]).to_parquet(d / "families.parquet", index=False)
    pd.DataFrame([dict(pid="p1", qid="c0002", cand="c0001", same_project=True, side_rank=1, cos=0.4, p_same=0.05, p_rel=0.3, ft_same=0.04,
                       score_source="cached", model_version="fixture")])[PAIR_COLS].to_parquet(d / "pair_scores.parquet", index=False)
    json.dump(dict(data_version="fixture", projects=config.PROJECT_NAMES, arguments_available_for=steps.ARGUMENT_PROJECTS), open(d / "meta.json", "w"))
    json.dump(dict(version="fixture-matcher", thresholds=dict(pair_same=0.8, familiar=0.74, new=0.2, related=0.8)), open(d / "matcher.json", "w"))


# ---------------------------------------------------------------- stubs
def fake_llm(system, user):
    """Keyword stub for the codebook call: returns the JSON array the prompt asks for."""
    assert "Return ONLY a JSON array" in system, "the codebook prompt must be passed unchanged"
    out = []
    for item in re.split(r"^### id=", user, flags=re.M)[1:]:
        sid, body = item.split(" |", 1)[0], item.lower()
        if "failme" in body:
            raise RuntimeError("simulated LLM outage")
        arg = lambda topic, pol, claim: [dict(topic=topic, polarity=pol, claim=claim)]
        if "skigebiet" in body:
            o = dict(project="leisure_cablecar", stance="na", tone="neutral", arguments=[])
        elif "wind" in body:
            o = dict(project=HN, stance="oppose", tone="negative", arguments=arg("safety_operations", "contra", "Wind shutdowns leave evening shift workers stranded"))
        elif "teuer" in body:
            o = dict(project=HN, stance="oppose", tone="negative", arguments=arg("cost_financing", "contra", "Cable car is far too expensive"))
        elif "stadtbahn" in body:
            o = dict(project=HN, stance="oppose", tone="neutral", arguments=arg("alternatives", "contra", "Extend the Stadtbahn instead of the cable car"))
        elif "ipai" in body:
            o = dict(project=HN, stance="neutral", tone="positive", arguments=arg("urban_development", "pro", "Cable car links the IPAI campus quickly"))
        elif "seilbahn" in body:
            o = dict(project=HN, stance="support", tone="positive", arguments=arg("tourism_image", "pro", "Cable car would be a landmark"))
        else:
            o = dict(project="unrelated", stance="na", tone="neutral", arguments=[])
        out.append(dict(id=sid, passing=False, city=None, **o))
    return "Here you go:\n" + json.dumps(out)


def fake_match_new_claims(claims_df):
    """Stand-in for citypulse.engine.ingest.match_new_claims with the same signature and output columns:
    'wind' claims are new (later ones match the first one of the batch), every other claim matches base claim c0001."""
    S = store.get()
    N = claims_df.copy().reset_index(drop=True)
    N["ts"] = pd.to_datetime(N.ts, utc=True)
    rows, states, scores, bests, wind = [], [], [], [], []
    for r in N.itertuples():
        if "wind" in r.claim.lower():
            older = [w for w in wind if w.ts < r.ts and w.doc_id != r.doc_id]
            cand, p = (older[0].cid, 0.95) if older else ("c0001", 0.03)
            wind.append(r)
        else:
            cand, p = "c0001", 0.9
        rows.append(dict(pid=hashlib.md5((r.cid + cand).encode()).hexdigest()[:10], qid=r.cid, cand=cand, same_project=True, side_rank=1,
                         cos=0.5, p_same=p, p_rel=p, ft_same=p, score_source="live", model_version="fake"))
        states.append("familiar" if p >= 0.74 else "new"); scores.append(round(1 - p, 4)); bests.append(cand)
    N["novelty_state"], N["novelty_score"], N["best_match_cid"] = states, scores, bests
    emb = np.vstack([_unit(c, S.emb.shape[1]) for c in N.cid]) if len(N) else np.zeros((0, S.emb.shape[1]), dtype=np.float32)
    return N, pd.DataFrame(rows, columns=PAIR_COLS), emb


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Temporary bundle + temporary runs folder + stubs. Restores the process-wide store afterwards."""
    _build_bundle(tmp_path / "data")
    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    monkeypatch.setattr(config, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(steps, "call_llm", fake_llm)
    monkeypatch.setattr(steps, "check_llm", lambda: None)
    monkeypatch.setattr(steps, "RETRY_SLEEP", 0)
    monkeypatch.setattr(runs, "_match_new_claims", fake_match_new_claims)
    monkeypatch.setattr(runs, "_engine_info", lambda: dict(embedder="fake", matcher="fake", matcher_available=True))
    old = store._S
    store.reload()
    yield tmp_path
    store._S = old
    try:
        from citypulse.engine import replay
        replay.clear_cache()
    except Exception:
        pass


def write(tmp, name, records):
    p = tmp / name
    if name.endswith(".csv"):
        cols = list(dict.fromkeys(k for r in records for k in r))
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, delimiter=";" if "semicolon" in name else ",")
        w.writeheader()
        for r in records:
            w.writerow({k: (json.dumps(v) if isinstance(v, list) else v) for k, v in r.items()})
        p.write_text(buf.getvalue(), encoding="utf-8")
    else:
        p.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return p


def out(run):
    d = config.RUNS / run["run_id"]
    return pd.read_parquet(d / "posts.parquet"), pd.read_parquet(d / "claims.parquet")


def step(run, name):
    return next(s for s in run["steps"] if s["name"] == name)


P1 = dict(id="p1", title="Seilbahn Heilbronn", text="Die Seilbahn in Heilbronn ist <b>viel zu teuer</b>.&nbsp;Das sagen viele Bürger.",
          url="https://www.zeitung.example/a/1", published_at="2026-11-03T18:40:00Z", source_name="Zeitung", media_type="News", language="de", author="Anna Autorin")
P2 = dict(id="p2", text="Statt der Seilbahn sollte Heilbronn die Stadtbahn ausbauen.", url="https://forum.example/t/2", published_at="2026-11-04",
          source_name="Forum", media_type="Forums", language="de", author="nutzer_42")


def as_challenge(r):
    return dict(mention_id=r["id"], title=r.get("title"), content=r["text"], url=r["url"], published_at=r["published_at"],
                media_type_name=r["media_type"], source_name=r["source_name"], language_code=r["language"], authors=[r["author"]],
                country_code="DE", reach=10)


# ---------------------------------------------------------------- tests
def test_template_lists_fields_and_example():
    t = batch.template()
    names = {f["name"]: f for f in t["fields"]}
    assert names["text"]["required"] and names["published_at"]["required"] and not names["author"]["required"]
    assert "content" in names["text"]["aliases"] and "mention_id" in names["id"]["aliases"]
    valid, errors = formats.validate(t["example"])
    assert len(valid) == len(t["example"]) and not errors
    assert t["example_csv"].splitlines()[0].startswith("text,published_at")
    assert formats.validate(formats.read_records(t["example_csv"].encode(), "t.csv"))[1] == []


def test_validation_rejects_single_records_with_messages(env):
    recs = [P1, dict(id="no-text", published_at="2026-11-03"), dict(id="no-date", text="Seilbahn Heilbronn ohne Datum"),
            dict(id="bad-date", text="Seilbahn Heilbronn", published_at="gestern Abend"), "not an object",
            dict(text="   ", published_at="2026-11-03"), dict(P2, unknown_field={"x": 1}, another=5)]
    run = batch.process_sync(write(env, "mixed.json", recs))
    assert run["status"] == "done_with_errors"
    assert run["counts"]["records"] == 7 and run["counts"]["valid"] == 2 and run["counts"]["rejected"] == 5
    msg = {e["record"]: e["message"] for e in run["errors"]}
    assert "missing text" in msg["no-text"] and "missing published_at" in msg["no-date"]
    assert "not an ISO date" in msg["bad-date"] and "gestern" in msg["bad-date"]
    assert "not an object" in msg["row 5"] and "missing text" in msg["row 6"]
    assert all(e["step"] == "validate" for e in run["errors"])
    posts, _ = out(run)
    assert sorted(posts.doc_id) == ["p1", "p2"], "the valid records are still processed; unknown fields are ignored"
    assert step(run, "validate")["n_in"] == 7 and step(run, "validate")["n_out"] == 2


@pytest.mark.parametrize("name,conv", [("simple.json", lambda r: r), ("challenge.json", as_challenge), ("simple.csv", lambda r: r),
                                       ("challenge.csv", as_challenge), ("simple_semicolon.csv", lambda r: r)])
def test_both_layouts_as_json_and_csv(env, name, conv):
    run = batch.process_sync(write(env, name, [conv(P1), conv(P2)]))
    assert run["status"] == "done", run["errors"]
    posts, claims = out(run)
    posts = posts.set_index("doc_id")
    assert sorted(posts.index) == ["p1", "p2"]
    a = posts.loc["p1"]
    assert (a.channel, a.media_type, a.domain, a.lang, a.source_name) == ("news", "News", "zeitung.example", "de", "Zeitung")
    assert a.excerpt == "Seilbahn Heilbronn Die Seilbahn in Heilbronn ist viel zu teuer . Das sagen viele Bürger." or \
        a.excerpt == "Seilbahn Heilbronn\nDie Seilbahn in Heilbronn ist viel zu teuer . Das sagen viele Bürger."
    assert a.date == "2026-11-03" and a.month == "2026-11" and str(a.published_at) == "2026-11-03 18:40:00+00:00"
    assert posts.loc["p2"].channel == "social" and posts.loc["p2"].date == "2026-11-04"
    # authors: salted hash exactly as pipeline/01_build_base.py, shown only as a 6-character voice
    h = hashlib.sha256((config.AUTHOR_SALT + "Anna Autorin").encode()).hexdigest()[:12]
    assert a.voice == hashlib.sha1(h.encode()).hexdigest()[:6]
    assert (a.project, a.stance, a.label_source, a.run_id, a.n_claims) == (HN, "oppose", config.LLM_MODEL, run["run_id"], 1)
    assert sorted(claims.claim) == ["Cable car is far too expensive", "Extend the Stadtbahn instead of the cable car"]


def test_in_file_duplicates_are_grouped_like_the_pipeline(env):
    run = batch.process_sync(SAMPLE)
    posts, claims = out(run)
    p = posts.set_index("doc_id")
    assert p.loc["demo-01", "dup_key"] == p.loc["demo-09", "dup_key"]
    assert p.loc["demo-01", "dup_count"] == 2 and p.loc["demo-09", "dup_count"] == 2
    assert bool(p.loc["demo-01", "is_first_copy"]) and not bool(p.loc["demo-09", "is_first_copy"])
    assert p.loc["demo-09", "project"] == HN and p.loc["demo-09", "stance"] == "oppose", "the copy inherits the label of the first copy"
    assert "demo-09" not in set(claims.doc_id) and "demo-01" in set(claims.doc_id), "arguments are counted once, on the first copy"
    assert run["counts"]["duplicates_in_file"] == 1
    assert posts[posts.is_first_copy].dup_key.is_unique


def test_demo_file_counts_and_steps(env):
    run = batch.process_sync(SAMPLE)
    c = run["counts"]
    assert run["status"] == "done_with_errors" and len(run["errors"]) == 1 and run["errors"][0]["record"] == "demo-10"
    assert (c["records"], c["valid"], c["rejected"], c["already_known"]) == (10, 9, 1, 0)
    assert c["candidates"] == 7, "demo-08 (alpine hut) is background, demo-09 is a copy: neither is sent to the model"
    assert c["relevant"] == 7 and c["not_relevant"] == 2 and c["unclassified"] == 0
    assert (c["claims"], c["new"], c["familiar"], c["ambiguous"], c["unscored"]) == (6, 1, 5, 0, 0)
    assert [s["name"] for s in run["steps"]] == batch.STEP_NAMES
    assert all(s["status"] == "done" for s in run["steps"])
    assert "boilerplate filter inactive" in step(run, "relevance")["message"]
    assert run["models"]["llm_backend"] == config.LLM_BACKEND and run["models"]["llm_model"] == config.LLM_MODEL
    # line endings normalised: a Windows checkout has CRLF on disk, the prompt itself is read as text (LF)
    assert run["models"]["prompt_hash"] == hashlib.sha1((REPO / "pipeline/prompts/codebook_v1.md").read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:8]
    posts, claims = out(run)
    assert set(posts.doc_id) == {f"demo-0{i}" for i in (1, 2, 3, 4, 5, 6, 9)}
    wind = claims[claims.claim.str.contains("Wind")]
    assert len(wind) == 3 and wind.voice.nunique() == 3 and wind.family_id.nunique() == 1, "the three wind claims form one new family"
    assert wind.family_id.iloc[0].startswith("solo:n:")
    cost = claims[claims.doc_id == "demo-01"].iloc[0]
    assert (cost.family_id, cost.cluster_all) == ("fam1", 1), "a familiar claim joins the family of its best match"


def test_already_known_posts_are_skipped(env):
    recs = [dict(id="fresh-copy-of-known-text", text=KNOWN_TEXT, published_at="2026-11-05"),
            dict(id="known-id-1", text="Ganz neuer Text zur Seilbahn Heilbronn, aber die Kennung gibt es schon.", published_at="2026-11-05"),
            P1]
    run = batch.process_sync(write(env, "known.json", recs))
    assert run["counts"]["already_known"] == 2 and run["counts"]["valid"] == 3
    posts, _ = out(run)
    assert list(posts.doc_id) == ["p1"]
    assert "2 already known" in step(run, "dedupe")["message"]
    # a later file that repeats p1 finds it in the store
    run2 = batch.process_sync(write(env, "later.json", [P1, P2]))
    assert run2["counts"]["already_known"] == 1 and list(out(run2)[0].doc_id) == ["p2"]
    assert store.get().posts.doc_id.is_unique


def test_repeated_id_in_file_is_collapsed(env):
    recs = [P1, dict(P1), dict(P1, text="Die Seilbahn Heilbronn: anderer Text unter derselben Kennung.")]
    run = batch.process_sync(write(env, "repeat.json", recs))
    posts, _ = out(run)
    assert list(posts.doc_id) == ["p1"] and posts.dup_count.iloc[0] == 1
    assert run["counts"]["duplicates_in_file"] == 2
    assert [e["step"] for e in run["errors"]] == ["dedupe"] and "different text" in run["errors"][0]["message"]


def test_ids_are_stable_across_runs(env, tmp_path, monkeypatch):
    recs = [{k: v for k, v in r.items() if k != "id"} for r in (P1, P2)]
    a = batch.process_sync(write(env, "a.json", recs))
    pa, ca = out(a)
    monkeypatch.setattr(config, "RUNS", tmp_path / "runs_second")      # a fresh system that has not seen the file
    store.reload()
    b = batch.process_sync(write(env, "b.json", list(reversed(recs))))
    pb, cb = out(b)
    assert a["run_id"] != b["run_id"]
    assert sorted(pa.doc_id) == sorted(pb.doc_id) and sorted(ca.cid) == sorted(cb.cid)
    assert all(d.startswith("u:") and len(d) == 18 for d in pa.doc_id)
    assert all(c.startswith("n:") and len(c) == 14 for c in ca.cid)
    base = steps.pipeline_module("01_build_base.py")
    row = pa[pa.domain == "forum.example"].iloc[0]
    assert row.doc_id == "u:" + hashlib.sha1((P2["url"] + base.norm_for_dup(P2["text"])).encode()).hexdigest()[:16]
    cl = ca[ca.doc_id == row.doc_id].iloc[0]
    assert cl.cid == "n:" + hashlib.sha1((row.doc_id + cl.claim).encode()).hexdigest()[:12]


def test_duplicate_upload_raises_with_run_id(env):
    first = batch.process_sync(write(env, "one.json", [P1]))
    with pytest.raises(batch.DuplicateUpload) as e:
        batch.process_sync(write(env, "same_bytes_other_name.json", [P1]))
    assert e.value.run_id == first["run_id"]
    up = write(env, "upload_copy.json", [P1])
    with pytest.raises(batch.DuplicateUpload) as e:
        batch.submit(str(up), "upload_copy.json")
    assert e.value.run_id == first["run_id"] and not up.exists()
    assert len(batch.list_runs()) == 1


def test_failed_run_does_not_block_a_second_upload(env, monkeypatch):
    monkeypatch.setattr(steps, "call_llm", lambda s, u: (_ for _ in ()).throw(RuntimeError("connection refused")))
    f = write(env, "one.json", [P1])
    first = batch.process_sync(f)
    assert first["status"] == "failed"
    monkeypatch.setattr(steps, "call_llm", fake_llm)
    assert batch.process_sync(f)["status"] == "done"


def test_llm_failure_on_one_batch_gives_done_with_errors(env, monkeypatch):
    monkeypatch.setattr(steps, "LLM_BATCH", 2)
    recs = [P1, P2,
            dict(id="x1", text="Die Seilbahn Heilbronn FAILME zum IPAI.", published_at="2026-11-05"),
            dict(id="x2", text="Die Seilbahn in Heilbronn bringt den IPAI Campus näher.", published_at="2026-11-06"),
            dict(id="p5", text="Bei Wind steht die Seilbahn Heilbronn still.", published_at="2026-11-07")]
    run = batch.process_sync(write(env, "partial.json", recs))
    assert run["status"] == "done_with_errors"
    bad = [e for e in run["errors"] if e["step"] == "classify"]
    assert sorted(e["record"] for e in bad) == ["x1", "x2"] and all("simulated LLM outage" in e["message"] for e in bad)
    assert run["counts"]["unclassified"] == 2 and run["counts"]["relevant"] == 3
    posts, claims = out(run)
    assert sorted(posts.doc_id) == ["p1", "p2", "p5"] and len(claims) == 3
    assert step(run, "classify")["status"] == "done" and step(run, "classify")["n_out"] == 3


def test_llm_unreachable_fails_with_what_to_configure(env, monkeypatch):
    monkeypatch.setattr(steps, "call_llm", lambda s, u: (_ for _ in ()).throw(RuntimeError("connection refused")))
    run = batch.process_sync(write(env, "one.json", [P1, P2]))
    assert run["status"] == "failed"
    assert "CITYPULSE_LLM_BACKEND" in run["message"] and "connection refused" in run["message"]
    assert step(run, "classify")["status"] == "failed" and step(run, "store")["status"] == "skipped"
    assert not (config.RUNS / run["run_id"] / "DONE").exists()
    assert run["run_id"] not in store.get().run_ids


def test_missing_cli_or_backend_is_reported_before_any_text_is_sent(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "claude")
    monkeypatch.setattr(steps.shutil, "which", lambda name: None)
    with pytest.raises(steps.LLMUnavailable, match="not on PATH"):
        steps.check_llm()
    monkeypatch.setattr(config, "LLM_BACKEND", "ollama")
    monkeypatch.setattr(config, "OLLAMA_URL", "http://127.0.0.1:9")
    with pytest.raises(steps.LLMUnavailable, match="OLLAMA_URL"):
        steps.check_llm()
    monkeypatch.setattr(config, "LLM_BACKEND", "gpt")
    with pytest.raises(steps.LLMUnavailable, match="CITYPULSE_LLM_BACKEND"):
        steps.check_llm()


def test_output_has_the_stores_columns_and_reload_sees_it(env):
    S0 = store.get()
    n_posts, n_claims, cols_p, cols_c = len(S0.posts), len(S0.claims), list(S0.posts.columns), list(S0.claims.columns)
    run = batch.process_sync(SAMPLE)
    d = config.RUNS / run["run_id"]
    posts, claims = out(run)
    assert list(posts.columns) == cols_p == POST_COLS and list(claims.columns) == cols_c == CLAIM_COLS
    assert (posts.run_id == run["run_id"]).all() and (claims.run_id == run["run_id"]).all()
    for col in POST_COLS:
        assert posts[col].dtype == S0.posts[col].dtype, col
    for col in CLAIM_COLS:
        assert claims[col].dtype == S0.claims[col].dtype, col
    emb = np.load(d / "claims_emb.npy")
    assert emb.dtype == np.float32 and emb.shape == (len(claims), DIM)
    pairs, nov = pd.read_parquet(d / "pair_scores.parquet"), pd.read_parquet(d / "novelty.parquet")
    assert set(pairs.qid) == set(claims.cid) and list(nov.cid) == list(claims.cid)
    assert set(nov.novelty_state) == {"new", "familiar"}
    assert (d / "DONE").exists() and json.loads((d / "run.json").read_text())["status"] == run["status"]
    S1 = store.get()                                      # the workflow already called store.reload()
    assert S1 is not S0 and run["run_id"] in S1.run_ids
    assert len(S1.posts) == n_posts + len(posts) and len(S1.claims) == n_claims + len(claims) == len(S1.emb)
    assert set(posts.doc_id) <= set(S1.posts.doc_id) and set(claims.cid) <= set(S1.cidx)
    assert S1.sql("select count(*) n from claims where run_id = ?", [run["run_id"]])[0]["n"] == len(claims)
    assert set(claims.doc_id) <= set(posts.doc_id) and posts.excerpt.str.len().max() <= 400


def test_no_author_names_and_no_raw_upload_are_kept(env):
    up = env / "upload.json"
    shutil.copy(SAMPLE, up)
    run = batch.process_sync(up, "demo.json", delete_upload=True)
    assert not up.exists(), "the raw upload is deleted after processing"
    d = config.RUNS / run["run_id"]
    assert run["filename"] == "demo.json" and run["sha256"] == hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    names = [r["author"].encode() for r in json.loads(SAMPLE.read_text())]
    for f in d.iterdir():
        blob = f.read_bytes()
        assert not any(n in blob for n in names), f"author name found in {f.name}"
    posts, claims = out(run)
    assert not {"author", "authors", "author_hash"} & (set(posts.columns) | set(claims.columns))
    assert sorted(f.name for f in d.iterdir()) == ["DONE", "claims.parquet", "claims_emb.npy", "novelty.parquet", "pair_scores.parquet", "posts.parquet", "run.json"]


def test_ingest_failure_stores_claims_as_unscored(env, monkeypatch):
    def boom(df):
        raise RuntimeError("embedder unavailable (bge-m3 at http://127.0.0.1:11434)")
    monkeypatch.setattr(runs, "_match_new_claims", boom)
    run = batch.process_sync(SAMPLE)
    assert run["status"] == "done_with_errors"
    e = [x for x in run["errors"] if x["step"] == "match"]
    assert len(e) == 1 and "embedder unavailable" in e[0]["message"]
    assert run["counts"]["unscored"] == run["counts"]["claims"] == 6 and run["counts"]["new"] == 0
    d = config.RUNS / run["run_id"]
    assert set(pd.read_parquet(d / "novelty.parquet").novelty_state) == {"unscored"}
    assert np.load(d / "claims_emb.npy").shape == (6, DIM)
    assert run["run_id"] in store.get().run_ids and len(out(run)[1]) == 6


def test_matcher_missing_is_reported_even_if_ingest_does_not_raise(env, monkeypatch):
    def unscored(df):
        N, P, E = fake_match_new_claims(df)
        N["novelty_state"], N["novelty_score"], N["best_match_cid"] = "unscored", None, None
        return N, P.assign(p_same=np.nan), E
    monkeypatch.setattr(runs, "_match_new_claims", unscored)
    run = batch.process_sync(SAMPLE)
    assert run["status"] == "done_with_errors" and run["counts"]["unscored"] == 6
    assert any(e["step"] == "novelty" and "unscored" in e["message"] for e in run["errors"])


def test_unusable_file_fails_cleanly(env):
    for name, data in [("garbage.json", b"{not json"), ("empty.json", b"[]"), ("binary.csv", b"\xff\xfe\x00\x01"),
                       ("only_bad.json", json.dumps([dict(text="x")]).encode())]:
        p = env / name
        p.write_bytes(data)
        run = batch.process_sync(p)
        assert run["status"] == "failed" and run["message"], name
        assert step(run, "validate")["status"] == "failed" and step(run, "clean")["status"] == "skipped"
        assert not (config.RUNS / run["run_id"] / "DONE").exists()


def test_file_with_nothing_relevant_is_done_and_store_still_loads(env):
    recs = [dict(text="Die Almhütte hat geöffnet.", published_at="2026-11-07"),
            dict(title="Neue Seilbahn im Skigebiet", text="Die Talstation ist mit dem Nahverkehr erreichbar.", published_at="2026-11-05")]
    n = len(store.get().posts)
    run = batch.process_sync(write(env, "noise.json", recs))
    assert run["status"] == "done" and run["counts"]["relevant"] == 0 and run["counts"]["not_relevant"] == 2 and run["counts"]["candidates"] == 1
    posts, claims = out(run)
    assert len(posts) == 0 and len(claims) == 0 and list(posts.columns) == POST_COLS
    assert step(run, "match")["status"] == "skipped"
    S = store.get()
    assert run["run_id"] in S.run_ids and len(S.posts) == n and str(S.posts.published_at.dtype).startswith("datetime64")


def test_submit_runs_in_background_and_can_be_polled(env):
    up = env / "upload.json"
    shutil.copy(SAMPLE, up)
    queued = batch.submit(str(up), "demo.json")
    assert queued["status"] == "queued" and re.fullmatch(r"r\d{8}-\d{4}-[0-9a-f]{4}", queued["run_id"])
    assert [s["status"] for s in queued["steps"]] == ["pending"] * 9
    seen = set()
    for _ in range(600):
        run = batch.get_run(queued["run_id"])
        seen.add(run["status"])
        if run["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert run["status"] == "done_with_errors" and run["finished_at"] and seen <= {"queued", "running", "done_with_errors"}
    assert not up.exists()
    second = batch.process_sync(write(env, "second.json", [P1]))
    listed = batch.list_runs()
    assert {r["run_id"] for r in listed} == {queued["run_id"], second["run_id"]}
    assert [r["created_at"] for r in listed] == sorted((r["created_at"] for r in listed), reverse=True), "newest first"
    assert batch.get_run("r00000000-0000-0000") is None and batch.get_run("../../etc/passwd") is None


def test_findings_come_from_the_replay_engine(env):
    replay = pytest.importorskip("citypulse.engine.replay")
    run = batch.process_sync(SAMPLE)
    assert run["findings"]["note"] == "", run["findings"]["note"]
    new = [c for c in run["findings"]["concerns"] if c["state"] == "new_emerging"]
    assert len(new) == 1 and new[0]["n_claims"] == 3 and new[0]["n_voices"] == 3 and "Wind" in new[0]["label"]
    assert json.dumps(run)                                 # the Run is plain JSON


def test_findings_note_when_the_engine_cannot_compute_them(env, monkeypatch):
    monkeypatch.setattr(runs, "_concerns", lambda run_id: (_ for _ in ()).throw(ImportError("no replay")))
    run = batch.process_sync(SAMPLE)
    assert run["findings"]["concerns"] == [] and "no replay" in run["findings"]["note"]
    assert run["status"] == "done_with_errors" and len(run["errors"]) == 1, "a missing findings list does not fail the run"


def test_command_line(env, capsys):
    from citypulse.batch.__main__ import main
    assert main([str(SAMPLE)]) == 1                        # done_with_errors: demo-10 has no date
    text = capsys.readouterr().out
    assert "status: done_with_errors" in text and "validate" in text and "demo-10" in text
    assert SAMPLE.exists(), "the command line leaves the file where it is"
    assert main([str(SAMPLE)]) == 2 and "already processed" in capsys.readouterr().out


@pytest.mark.skipif(not (REPO / "app_data" / "posts.parquet").exists(), reason="real data bundle not on this machine")
def test_fixture_columns_match_the_real_bundle():
    assert list(pd.read_parquet(REPO / "app_data" / "posts.parquet").columns) == POST_COLS
    assert list(pd.read_parquet(REPO / "app_data" / "claims.parquet").columns) == CLAIM_COLS


# ---------------------------------------------------------------- live
@pytest.mark.live
def test_live_demo_batch(tmp_path, monkeypatch):
    """Real run: Claude Haiku through the CLI (or whatever CITYPULSE_LLM_* says), real bundle, real engine.ingest if it
    imports, temporary runs folder. Prints the step table."""
    if not (config.DATA / "posts.parquet").exists():
        pytest.skip("real data bundle missing")
    monkeypatch.setattr(config, "RUNS", tmp_path / "runs")
    try:
        from citypulse.engine import ingest  # noqa: F401
        used = "real citypulse.engine.ingest"
    except Exception as e:
        monkeypatch.setattr(runs, "_match_new_claims", fake_match_new_claims)
        used = f"FAKE ingest ({e!r})"
    old = store._S
    store.reload()
    try:
        run = batch.process_sync(SAMPLE)
        print(f"\ningest: {used}\nrun {run['run_id']} status {run['status']} {run['message']}\n" + batch.step_table(run))
        print("counts:", json.dumps(run["counts"]))
        print("models:", json.dumps(run["models"], ensure_ascii=False))
        for e in run["errors"]:
            print("problem:", e)
        posts, claims = out(run)
        print(claims[["doc_id", "topic", "polarity", "claim"]].to_string())
        print(pd.read_parquet(config.RUNS / run["run_id"] / "novelty.parquet").to_string())
        for c in run["findings"]["concerns"]:
            print("concern:", c["state"], "|", c["label"], "|", c["n_claims"], "claims,", c["n_voices"], "voices")
        print("findings note:", run["findings"].get("note"))
        assert run["status"] in ("done", "done_with_errors")
        assert run["counts"]["valid"] == 9 and run["counts"]["rejected"] == 1 and run["counts"]["duplicates_in_file"] == 1
        assert {"demo-01", "demo-02", "demo-03", "demo-04", "demo-05", "demo-06", "demo-09"} <= set(posts.doc_id)
        assert "demo-08" not in set(posts.doc_id) and "demo-07" not in set(posts.doc_id)
        assert (posts.project == HN).all() and len(claims) >= 6
        assert list(posts.columns) == list(store.get().posts.columns) and list(claims.columns) == list(store.get().claims.columns)
        assert run["run_id"] in store.get().run_ids
    finally:
        store._S = old
        try:
            from citypulse.engine import replay
            replay.clear_cache()
        except Exception:
            pass
