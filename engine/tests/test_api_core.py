"""API tests on the real data bundle: endpoints answered from the store (health, meta, overview, trends, posts, families, cross-city).

Every expected number is recomputed here directly from the store (pandas or DuckDB), never copied from an earlier answer.
"""
import math
from urllib.parse import quote

import pandas as pd, pytest
from fastapi.testclient import TestClient
from scipy.stats import poisson

from citypulse import config

pytestmark = pytest.mark.skipif(not (config.DATA / "posts.parquet").exists(), reason=f"data bundle missing in {config.DATA}")

HN = "heilbronn_cablecar"
POST_KEYS = {"doc_id", "date", "channel", "media_type", "domain", "source_name", "url", "lang", "title", "excerpt", "project", "stance", "tone",
             "passing", "label_source", "voice", "dup_count", "n_claims", "run_id"}
CLAIM_KEYS = {"cid", "claim", "project", "project_name", "date", "channel", "domain", "url", "topic", "polarity", "doc_id", "voice", "family_id",
              "family_name"}
BANNED = {"author", "authors", "author_hash", "author_name", "author_handle", "username", "user_name", "handle"}


@pytest.fixture(scope="module")
def client():
    from citypulse.api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def S():
    from citypulse.engine import store
    return store.get()


def ok(client, url, **params):
    r = client.get(url, params=params)
    assert r.status_code == 200, f"{url} {params}: {r.status_code} {r.text[:300]}"
    return r.json()


def is_error(r, status, code=None):
    assert r.status_code == status, r.text[:300]
    body = r.json()
    assert set(body) == {"error"} and isinstance(body["error"].get("code"), str) and isinstance(body["error"].get("message"), str), body
    assert body["error"]["message"]
    if code:
        assert body["error"]["code"] == code, body
    return body["error"]


def is_share(s):
    assert {"value", "lo", "hi", "n"} <= set(s), s
    if s["n"]:
        assert 0 <= s["lo"] <= s["value"] <= s["hi"] <= 1
    else:
        assert s["value"] is None and s["lo"] is None and s["hi"] is None


def wilson_ref(k, n, z=1.959963984540054):
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


# ---------------------------------------------------------------- health, meta

def test_every_contract_endpoint_is_registered(client):
    have = {(e["method"], e["path"].split("{")[0]) for e in ok(client, "/api")["endpoints"]}
    want = [("GET", "/api/health"), ("GET", "/api/meta"), ("GET", "/api/overview"), ("GET", "/api/trends"), ("GET", "/api/posts"),
            ("GET", "/api/posts/"), ("GET", "/api/arguments/families"), ("GET", "/api/arguments/families/"), ("GET", "/api/claims/"),
            ("GET", "/api/search"), ("POST", "/api/match"), ("GET", "/api/emerging"), ("GET", "/api/emerging/"), ("GET", "/api/replay"),
            ("GET", "/api/replay/cutoffs"), ("POST", "/api/replay/live-check"), ("GET", "/api/crosscity"), ("GET", "/api/crosscity/similar"),
            ("POST", "/api/crosscity/similar"), ("POST", "/api/batches"), ("GET", "/api/batches"), ("GET", "/api/batches/"),
            ("GET", "/api/batches/template"), ("GET", "/api/export/briefing")]
    assert not [w for w in want if w not in have], [w for w in want if w not in have]


def test_health_shape(client, S):
    h = ok(client, "/api/health")
    assert h["status"] == "ok" and h["data_version"] == S.data_version
    assert h["n_posts"] == len(S.posts) and h["n_claims"] == len(S.claims)
    assert isinstance(h["matcher"]["available"], bool) and h["matcher"]["mode"] in ("local-model", "cached-only") and "version" in h["matcher"]
    assert isinstance(h["embedder"]["available"], bool) and h["embedder"]["backend"]
    assert isinstance(h["llm"]["available"], bool) and h["llm"]["backend"]
    assert str(config.ROOT) not in str(h), "no local file paths in answers"


def test_meta_shape_and_projects_from_data(client, S):
    m = ok(client, "/api/meta")
    assert {"projects", "topics", "channels", "stances", "limitations", "metrics", "model"} <= set(m)
    by_id = {p["id"]: p for p in m["projects"]}
    assert set(by_id) == set(S.posts.project.unique())
    for pid, p in by_id.items():
        d = S.posts[S.posts.project == pid]
        assert {"id", "name", "has_arguments", "n_posts", "n_claims", "first_date", "last_date"} <= set(p)
        assert p["n_posts"] == len(d) and p["n_claims"] == int((S.claims.project == pid).sum())
        assert p["first_date"] == d.date.min() and p["last_date"] == d.date.max()
        assert p["has_arguments"] == bool((S.claims.project == pid).any())
    assert by_id["ipai"]["has_arguments"] is False and by_id["ipai"]["n_claims"] == 0
    assert set(m["topics"]) == set(S.claims.topic.unique())
    assert m["stances"] == ["support", "oppose", "neutral", "mixed"] and set(m["channels"]) == set(S.posts.channel.unique())
    assert {"name", "version", "trained_until", "checksum"} <= set(m["model"])


def test_meta_metrics_are_provisional(client):
    m = ok(client, "/api/meta")["metrics"]
    assert m["provisional"] is True
    assert "agreement with AI reference labels, not human-validated" in m["note"]
    eval_files = sorted(p.name for p in config.DATA.glob("eval_*.json"))
    assert m["files"] == eval_files
    if eval_files:
        import json
        d = json.load(open(config.DATA / eval_files[0]))
        ref = m["references"][d["reference"]]
        sel = next(r for r in d["pair_matching_test"] if r["method"] == d["selected_method"])
        assert ref["pair_matching"]["selected"]["f1"] == pytest.approx(sel["f1"])
        assert ref["n_test_pairs"] == d["n_test_pairs"]


def test_meta_limitations_come_from_data(client, S):
    L = ok(client, "/api/meta")["limitations"]
    assert all(isinstance(x, str) and x for x in L) and len(L) >= 6
    text = " ".join(L)
    h = S.posts[(S.posts.project == HN) & S.posts.is_first_copy & ~S.posts.passing]
    n_side = int(h.stance.isin(["support", "oppose", "mixed"]).sum())
    assert f"Only {n_side} Heilbronn posts take a side" in text
    assert "not a representative poll" in text
    assert "Contradiction" in text and "disabled" in text
    assert "matcher model is" in text
    for pid, name in S.meta["projects"].items():
        assert f"{name}: {int((S.posts.project == pid).sum())} posts" in text
    assert "No arguments were extracted for this project" in next(x for x in L if x.startswith("IPAI"))


# ---------------------------------------------------------------- overview

def test_overview_shape(client):
    o = ok(client, "/api/overview")
    for k in ["n_posts", "n_unique_posts", "n_voices", "n_with_stance", "stance_counts", "opposition_share", "channel_counts", "top_sources",
              "topic_shares", "top_arguments", "monthly", "notes"]:
        assert k in o, k
    is_share(o["opposition_share"])
    assert {"support", "oppose", "neutral", "mixed"} <= set(o["stance_counts"])
    assert all({"domain", "n"} <= set(s) for s in o["top_sources"])
    assert all({"topic", "n", "pro", "contra", "neutral"} <= set(t) for t in o["topic_shares"])
    assert all({"family_id", "name", "n", "pro", "contra", "by_project"} <= set(a) for a in o["top_arguments"])
    assert all({"month", "n", "support", "oppose", "neutral", "mixed"} <= set(r) for r in o["monthly"])
    assert all(isinstance(n, str) for n in o["notes"])
    notes = " ".join(o["notes"])
    assert "oppose / (support + oppose + mixed)" in notes and "Wilson" in notes and "passing" in notes and "unique" in notes


def test_opposition_share_heilbronn_equals_hand_computation(client, S):
    o = ok(client, "/api/overview", project=HN)
    p = S.posts
    h = p[(p.project == HN) & (p.is_first_copy == True) & (p.passing == False)]          # noqa: E712
    support, oppose, mixed = int((h.stance == "support").sum()), int((h.stance == "oppose").sum()), int((h.stance == "mixed").sum())
    n = support + oppose + mixed
    assert n > 0
    lo, hi = wilson_ref(oppose, n)
    s = o["opposition_share"]
    assert s["n"] == n == o["n_with_stance"]
    assert s["value"] == pytest.approx(oppose / n, abs=1e-4)
    assert s["lo"] == pytest.approx(lo, abs=1e-4) and s["hi"] == pytest.approx(hi, abs=1e-4)
    assert o["stance_counts"]["support"] == support and o["stance_counts"]["oppose"] == oppose and o["stance_counts"]["mixed"] == mixed
    assert o["n_posts"] == int((p.project == HN).sum()) and o["n_unique_posts"] == int(((p.project == HN) & p.is_first_copy).sum())
    try:                                             # second, independent implementation when statsmodels is installed
        from statsmodels.stats.proportion import proportion_confint
        lo2, hi2 = proportion_confint(oppose, n, method="wilson")
        assert s["lo"] == pytest.approx(lo2, abs=1e-4) and s["hi"] == pytest.approx(hi2, abs=1e-4)
    except ImportError:
        pass


def test_overview_numbers_equal_direct_sql(client, S):
    o = ok(client, "/api/overview", project="paris_c1", channel="news")
    q = S.sql("select count(*) n, count(*) filter (where is_first_copy) u, count(distinct voice) v from posts where project = ? and channel = ?", ["paris_c1", "news"])[0]
    assert (o["n_posts"], o["n_unique_posts"], o["n_voices"]) == (q["n"], q["u"], q["v"])
    st = {r["stance"]: r["n"] for r in S.sql("select stance, count(*) n from posts where project = ? and channel = ? and is_first_copy and not passing group by 1", ["paris_c1", "news"])}
    assert {k: v for k, v in o["stance_counts"].items() if v} == st
    assert o["channel_counts"] == {"news": q["n"]}
    top = S.sql("select domain, count(*) n from posts where project = ? and channel = ? group by 1 order by n desc limit 1", ["paris_c1", "news"])[0]
    assert o["top_sources"][0]["n"] == top["n"]
    tp = {r["topic"]: r for r in S.sql("""select topic, count(*) n, count(*) filter (where polarity = 'contra') contra from claims
                                         where doc_id in (select doc_id from posts where project = ? and channel = ?) group by 1""", ["paris_c1", "news"])}
    assert {t["topic"]: (t["n"], t["contra"]) for t in o["topic_shares"]} == {k: (v["n"], v["contra"]) for k, v in tp.items()}
    assert sum(r["n"] for r in o["monthly"]) == q["n"]


def test_overview_zero_posts_gives_null_share(client):
    o = ok(client, "/api/overview", project=HN, **{"from": "2020-01-01", "to": "2020-01-31"})
    assert o["n_posts"] == 0 and o["opposition_share"] == {"value": None, "lo": None, "hi": None, "n": 0, "k": 0}
    assert o["monthly"] == [] and o["topic_shares"] == [] and o["top_arguments"] == []


def test_ipai_says_it_has_no_arguments(client, S):
    o = ok(client, "/api/overview", project="ipai")
    assert o["has_arguments"] is False and o["n_posts"] == int((S.posts.project == "ipai").sum()) and o["topic_shares"] == []
    assert "No arguments have been extracted" in o["notes"][0]
    f = ok(client, "/api/arguments/families", project="ipai")
    assert f["items"] == [] and f["has_arguments"] is False and "No arguments have been extracted" in f["notes"][0]
    p = ok(client, "/api/posts", project="ipai", limit=1)
    assert p["has_arguments"] is False
    d = ok(client, "/api/posts/" + quote(p["items"][0]["doc_id"], safe=""))
    assert d["has_arguments"] is False and d["claims"] == [] and d["notes"]
    cc = {x["id"]: x for x in ok(client, "/api/crosscity")["projects"]}
    assert cc["ipai"]["has_arguments"] is False and cc[HN]["has_arguments"] is True


# ---------------------------------------------------------------- posts

@pytest.mark.parametrize("params", [
    {"project": HN, "from": "2026-07-01", "to": "2026-07-31"},
    {"project": "paris_c1", "from": "2025-12-13"},
    {"channel": "social", "stance": "oppose"},
    {"topic": "cost_financing", "project": "bonn_cablecar"},
    {"run_id": "base", "to": "2024-12-31"},
])
def test_posts_filter_count_equals_pandas(client, S, params):
    r = ok(client, "/api/posts", limit=500, **params)
    p = S.posts
    m = pd.Series(True, index=p.index)
    if "project" in params: m &= p.project == params["project"]
    if "from" in params: m &= p.date >= params["from"]
    if "to" in params: m &= p.date <= params["to"]
    if "channel" in params: m &= p.channel == params["channel"]
    if "stance" in params: m &= p.stance == params["stance"]
    if "run_id" in params: m &= p.run_id == params["run_id"]
    if "topic" in params: m &= p.doc_id.isin(set(S.claims[S.claims.topic == params["topic"]].doc_id))
    assert r["total"] == int(m.sum()) > 0
    if r["total"] <= 500:
        assert {i["doc_id"] for i in r["items"]} == set(p.doc_id[m])
    for i in r["items"]:
        assert POST_KEYS <= set(i), POST_KEYS - set(i)
        for k in ("project", "channel", "stance"):
            if k in params:
                assert i[k] == params[k]


def test_posts_paging_and_search(client, S):
    a = ok(client, "/api/posts", project=HN, limit=10, offset=0)
    b = ok(client, "/api/posts", project=HN, limit=10, offset=10)
    assert len(a["items"]) == 10 and len(b["items"]) == 10 and not {i["doc_id"] for i in a["items"]} & {i["doc_id"] for i in b["items"]}
    assert [i["date"] for i in a["items"]] == sorted([i["date"] for i in a["items"]], reverse=True)
    q = ok(client, "/api/posts", q="Seilbahn", project=HN, limit=500)
    d = S.posts[S.posts.project == HN]
    expect = d[d.title.str.contains("seilbahn", case=False, regex=False) | d.excerpt.str.contains("seilbahn", case=False, regex=False)]
    assert q["total"] == len(expect) > 0
    assert len(d[d.is_first_copy]) == ok(client, "/api/posts", project=HN, unique="true")["total"]
    assert len(a["items"][0]["excerpt"]) <= 400 + 30


def test_post_detail_shape(client, S):
    doc_id = S.claims[S.claims.project == HN].doc_id.iloc[0]
    d = ok(client, "/api/posts/" + quote(doc_id, safe=""))
    assert POST_KEYS <= set(d) and d["doc_id"] == doc_id
    assert {"claims", "classifications", "duplicates"} <= set(d)
    assert d["classifications"]["codebook"] == "codebook_v1"
    assert {"project", "stance", "tone", "passing", "label_source"} <= set(d["classifications"])
    assert len(d["claims"]) == int((S.claims.doc_id == doc_id).sum()) == d["n_claims"] > 0
    for c in d["claims"]:
        assert CLAIM_KEYS <= set(c) and c["doc_id"] == doc_id and c["url"]
    row = S.posts_by_id.loc[doc_id]
    assert d["duplicates"] == int((S.posts.dup_key == row.dup_key).sum()) - 1
    assert ok(client, "/api/posts/" + doc_id)["doc_id"] == doc_id            # the raw comma form works too


def test_every_listed_doc_id_resolves(client, S):
    ids = set()
    for off in range(0, 400, 200):
        ids |= {i["doc_id"] for i in ok(client, "/api/posts", project=HN, limit=200, offset=off)["items"]}
    assert len(ids) == int((S.posts.project == HN).sum())
    ids |= {i["doc_id"] for i in ok(client, "/api/posts", limit=150, offset=1000)["items"]}
    for t in ("week", "month"):
        ids |= {p["headline_doc_id"] for p in ok(client, "/api/trends", granularity=t)["peaks"] if p["headline_doc_id"]}
    for doc_id in ids:
        d = ok(client, "/api/posts/" + quote(doc_id, safe=""))
        assert d["doc_id"] == doc_id and d["url"]


def test_no_author_fields_anywhere(client):
    for url in ["/api/posts?limit=50", "/api/overview", "/api/meta", "/api/arguments/families", "/api/crosscity", "/api/trends"]:
        keys = set(walk_keys(ok(client, url)))
        assert not keys & BANNED, (url, keys & BANNED)
    for i in ok(client, "/api/posts", limit=500)["items"]:
        assert len(i["voice"]) == 6


# ---------------------------------------------------------------- trends

@pytest.mark.parametrize("gran", ["week", "month"])
def test_trends_shape_and_series(client, S, gran):
    t = ok(client, "/api/trends", granularity=gran, project=HN)
    assert {"series", "peaks", "events"} <= set(t)
    d = S.posts[S.posts.project == HN]
    assert sum(r["n"] for r in t["series"]) == len(d)
    counted = d[d.is_first_copy & ~d.passing]
    for s in ("support", "oppose", "neutral", "mixed"):
        assert sum(r[s] for r in t["series"]) == int((counted.stance == s).sum())
    periods = [r["period"] for r in t["series"]]
    assert periods == sorted(periods) and len(set(periods)) == len(periods)
    if gran == "week":
        assert all(pd.Timestamp(p).weekday() == 0 for p in periods), "weeks are named by their Monday"
        assert all((pd.Timestamp(b) - pd.Timestamp(a)).days == 7 for a, b in zip(periods, periods[1:])), "no missing weeks"
        day = pd.to_datetime(d.date)
        direct = (day - pd.to_timedelta(day.dt.day_of_week, unit="D")).dt.strftime("%Y-%m-%d").value_counts()
    else:
        direct = d.date.str.slice(0, 7).value_counts()
    assert {r["period"]: r["n"] for r in t["series"] if r["n"]} == direct.to_dict()
    ev = S.events[S.events.project == HN]
    assert len(t["events"]) == len(ev)
    for e in t["events"]:
        assert {"date", "title", "event_type", "verified", "source_url", "project"} <= set(e) and e["project"] == HN


@pytest.mark.parametrize("gran", ["week", "month"])
def test_trends_peaks_follow_the_poisson_test(client, gran):
    t = ok(client, "/api/trends", granularity=gran, project=HN)
    m = t["peak_method"]
    n_by_period = {r["period"]: r["n"] for r in t["series"]}
    periods = [r["period"] for r in t["series"]]
    assert t["peaks"], "the Heilbronn debate has known attention peaks"
    for p in t["peaks"]:
        assert {"period", "n", "expected", "p_value", "headline", "event"} <= set(p)
        assert p["n"] == n_by_period[p["period"]] >= m["min_count"]
        assert p["p_value"] < m["alpha"]
        i = periods.index(p["period"])
        if i >= m["window"]:                                # recompute the baseline from the series itself
            lam = sum(n_by_period[x] for x in periods[i - m["window"]:i]) / m["window"] + 0.1
            assert p["expected"] == pytest.approx(lam, abs=0.006)
            assert p["p_value"] == pytest.approx(float(poisson.sf(p["n"] - 1, lam)), rel=1e-6)
        assert p["event"] is None or {"date", "title", "verified"} <= set(p["event"])
        assert p["headline"]


def test_trends_date_filter_limits_series_and_peaks(client, S):
    t = ok(client, "/api/trends", granularity="week", project="paris_c1", **{"from": "2025-12-01", "to": "2025-12-31"})
    d = S.posts[(S.posts.project == "paris_c1") & (S.posts.date >= "2025-12-01") & (S.posts.date <= "2025-12-31")]
    assert sum(r["n"] for r in t["series"]) == len(d)
    assert all("2025-11-24" <= p["period"] <= "2025-12-31" for p in t["peaks"])
    assert all("2025-12-01" <= e["date"] <= "2025-12-31" for e in t["events"])


# ---------------------------------------------------------------- argument families

def test_families_unfiltered_equal_the_families_table(client, S):
    f = ok(client, "/api/arguments/families")
    items = {i["family_id"]: i for i in f["items"]}
    assert set(items) == set(S.families.family_id) and f["total"] == len(S.families)
    for r in S.families.itertuples():
        i = items[r.family_id]
        assert {"family_id", "name", "n", "main_topic", "pro", "contra", "by_project", "first_seen", "last_seen"} <= set(i)
        assert i["n"] == r.n and i["name"] == r.name and i["first_seen"] == r.first_seen and i["last_seen"] == r.last_seen
        assert i["pro"] / i["n"] == pytest.approx(r.pro) and i["contra"] / i["n"] == pytest.approx(r.contra)
        assert sum(i["by_project"].values()) == r.n
    ns = [i["n"] for i in f["items"]]
    assert ns == sorted(ns, reverse=True)


def test_families_filters(client, S):
    f = ok(client, "/api/arguments/families", project=HN)
    c = S.claims[(S.claims.project == HN) & ~S.claims.family_id.str.startswith("solo:")]
    assert {i["family_id"]: i["n"] for i in f["items"]} == c.groupby("family_id").size().to_dict()
    full = S.claims.groupby(["family_id", "project"]).size()
    for i in f["items"][:10]:
        assert i["by_project"] == full[i["family_id"]].to_dict(), "by_project shows every project, also under a project filter"
    t = ok(client, "/api/arguments/families", topic="cost_financing", project="bonn_cablecar")
    c = S.claims[(S.claims.project == "bonn_cablecar") & (S.claims.topic == "cost_financing") & ~S.claims.family_id.str.startswith("solo:")]
    assert sum(i["n"] for i in t["items"]) == len(c)
    q = ok(client, "/api/arguments/families", q="hospital")
    assert 0 < q["total"] < len(S.families)


def test_family_detail_and_claim_evidence(client, S):
    fid = S.families.sort_values("n", ascending=False).family_id.iloc[0]
    d = ok(client, "/api/arguments/families/" + fid)
    c = S.claims[S.claims.family_id == fid]
    assert d["family_id"] == fid and d["n"] == len(c) == len(d["claims"])
    assert d["pro"] == int((c.polarity == "pro").sum()) and d["contra"] == int((c.polarity == "contra").sum())
    assert d["by_project"] == c.project.value_counts().to_dict()
    for cl in d["claims"]:
        assert CLAIM_KEYS <= set(cl) and cl["doc_id"] and cl["url"] and cl["family_id"] == fid
    for doc_id in sorted({cl["doc_id"] for cl in d["claims"]})[:60]:
        assert ok(client, "/api/posts/" + quote(doc_id, safe=""))["doc_id"] == doc_id
    solo = S.claims[S.claims.family_id.str.startswith("solo:")].family_id.iloc[0]
    s = ok(client, "/api/arguments/families/" + solo)
    assert s["n"] == 1 and s["is_family"] is False and len(s["claims"]) == 1
    only = ok(client, "/api/arguments/families/" + fid, project=HN)
    assert len(only["claims"]) == int((c.project == HN).sum()) and only["n"] == len(c)


# ---------------------------------------------------------------- cross-city statistics

def test_crosscity_statistics(client, S):
    cc = ok(client, "/api/crosscity")
    assert {"projects", "shared_arguments", "notes"} <= set(cc)
    assert {p["id"] for p in cc["projects"]} == set(S.posts.project.unique())
    for p in cc["projects"]:
        assert {"id", "name", "n_posts", "n_with_stance", "opposition_share", "topic_shares"} <= set(p)
        is_share(p["opposition_share"])
        o = ok(client, "/api/overview", project=p["id"])
        assert (p["n_posts"], p["n_with_stance"], p["opposition_share"]) == (o["n_posts"], o["n_with_stance"], o["opposition_share"])
        assert p["topic_shares"] == o["topic_shares"]
    per = S.claims[~S.claims.family_id.str.startswith("solo:")].groupby("family_id").project.nunique()
    assert {a["family_id"] for a in cc["shared_arguments"]} == set(per[per >= 2].index)
    for a in cc["shared_arguments"]:
        assert {"family_id", "name", "by_project", "pro", "contra"} <= set(a) and len(a["by_project"]) >= 2
    t = ok(client, "/api/crosscity", topic="cost_financing")
    hn = next(p for p in t["projects"] if p["id"] == HN)
    assert [x["topic"] for x in hn["topic_shares"]] == ["cost_financing"]
    assert hn["topic_shares"][0]["n"] == int(((S.claims.project == HN) & (S.claims.topic == "cost_financing")).sum())


# ---------------------------------------------------------------- errors, CORS

def test_error_shape_404(client):
    is_error(client.get("/api/does-not-exist"), 404, "not_found")
    is_error(client.get("/api/posts/no-such-post"), 404, "unknown_post")
    is_error(client.get("/api/arguments/families/fam999999"), 404, "unknown_family")


@pytest.mark.parametrize("url,code", [
    ("/api/overview?from=2026-7-1", "invalid_parameter"),
    ("/api/overview?from=2026-02-31", "invalid_parameter"),
    ("/api/overview?from=2026-08-01&to=2026-07-01", "invalid_parameter"),
    ("/api/overview?channel=tv", "invalid_parameter"),
    ("/api/posts?stance=angry", "invalid_parameter"),
    ("/api/posts?project=atlantis", "invalid_parameter"),
    ("/api/overview?topic=weather", "invalid_parameter"),
    ("/api/posts?run_id=r-nope", "invalid_parameter"),
    ("/api/trends?granularity=day", "invalid_parameter"),
    ("/api/posts?limit=0", "invalid_request"),
    ("/api/posts?limit=abc", "invalid_request"),
    ("/api/posts?offset=-1", "invalid_request"),
])
def test_bad_parameters_use_the_error_shape(client, url, code):
    is_error(client.get(url), 422, code)


def test_method_not_allowed_and_internal_error_shape(client, monkeypatch):
    is_error(client.post("/api/overview"), 405, "method_not_allowed")
    from citypulse.api import routes_data
    monkeypatch.setattr(routes_data.meta_mod, "health", lambda st: 1 / 0)
    e = is_error(TestClient(client.app, raise_server_exceptions=False).get("/api/health"), 500, "internal_error")
    assert "ZeroDivisionError" in e["message"]


def test_cors_only_for_the_web_app(client):
    for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        r = client.get("/api/health", headers={"Origin": origin})
        assert r.headers.get("access-control-allow-origin") == origin
        assert client.get("/api/nope", headers={"Origin": origin}).headers.get("access-control-allow-origin") == origin
    assert "access-control-allow-origin" not in client.get("/api/health", headers={"Origin": "http://evil.example"}).headers
    pre = client.options("/api/match", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
                                                "Access-Control-Request-Headers": "content-type"})
    assert pre.status_code == 200 and pre.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_requests_and_errors_are_logged(client, caplog):
    import logging
    logging.getLogger("citypulse").propagate = True
    try:
        with caplog.at_level(logging.INFO, logger="citypulse.api"):
            client.get("/api/health")
            client.get("/api/posts/no-such-post")
    finally:
        logging.getLogger("citypulse").propagate = False
    text = caplog.text
    assert "GET /api/health -> 200" in text and "GET /api/posts/no-such-post -> 404" in text and "unknown_post" in text


def test_store_is_reloaded_when_the_bundle_changes_on_disk(monkeypatch, S):
    """A rebuilt app_data/ must not leave the server on old numbers: reload once the files have stopped changing."""
    from citypulse.api import common
    calls, sig = [], {"v": ("a",)}
    monkeypatch.setattr(common, "_bundle_signature", lambda: sig["v"])
    monkeypatch.setattr(common.store, "reload", lambda: calls.append(1) or S)
    monkeypatch.setattr(common, "BUNDLE_CHECK_SECS", -1)
    monkeypatch.setattr(common, "_bundle", {"loaded": None, "seen": None, "checked": 0.0})
    common.S(); common.S()
    assert calls == [], "unchanged bundle: no reload"
    sig["v"] = ("b",)
    common.S()
    assert calls == [], "first sight of a change: the copy may still be running"
    common.S()
    assert calls == [1], "same new state seen twice: reload"
    common.S()
    assert calls == [1], "no second reload for the same bundle"
    monkeypatch.setattr(common.store, "reload", lambda: 1 / 0)
    sig["v"] = ("c",)
    common.S()
    assert common.S() is S, "a bundle that cannot be loaded keeps the previous data"
