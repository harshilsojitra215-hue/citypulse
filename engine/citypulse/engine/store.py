"""Loads the data bundle (app_data/) plus every finished batch run (runs/<run_id>/) into memory and DuckDB.

S = store.get()
  S.posts, S.claims, S.events, S.families, S.pair_scores   pandas DataFrames
  S.emb                                                     numpy [n_claims, 1024], row i belongs to S.claims.iloc[i]
  S.meta, S.matcher_cfg                                     dicts
  S.con                                                     DuckDB connection with tables of the same names
store.reload() after a batch run has finished.
"""
import json, threading
import duckdb, numpy as np, pandas as pd
from .. import config

_lock = threading.Lock()
_S = None


class Store:
    def __init__(self):
        D = config.DATA
        if not (D / "posts.parquet").exists():
            raise FileNotFoundError(f"data bundle not found in {D}. See README, section Data.")
        self.posts = pd.read_parquet(D / "posts.parquet")
        self.claims = pd.read_parquet(D / "claims.parquet")
        self.emb = np.load(D / "claims_emb.npy")
        self.events = pd.read_parquet(D / "events.parquet")
        self.families = pd.read_parquet(D / "families.parquet")
        self.meta = json.load(open(D / "meta.json", encoding="utf-8"))
        ps = D / "pair_scores.parquet"
        self.pair_scores = pd.read_parquet(ps) if ps.exists() else pd.DataFrame(
            columns=["qid", "cand", "same_project", "side_rank", "cos", "p_same", "p_related", "score_source"])
        mc = D / "matcher.json"
        self.matcher_cfg = json.load(open(mc, encoding="utf-8")) if mc.exists() else {}
        self.run_ids = ["base"]
        if config.RUNS.exists():
            for rd in sorted(p for p in config.RUNS.iterdir() if (p / "DONE").exists()):
                try:
                    cl = pd.read_parquet(rd / "claims.parquet") if (rd / "claims.parquet").exists() else None
                    if cl is not None and len(cl):
                        em = np.load(rd / "claims_emb.npy")
                        assert len(em) == len(cl)
                        self.claims = pd.concat([self.claims, cl], ignore_index=True)
                        self.emb = np.vstack([self.emb, em])
                    if (rd / "posts.parquet").exists():
                        self.posts = pd.concat([self.posts, pd.read_parquet(rd / "posts.parquet")], ignore_index=True)
                    if (rd / "pair_scores.parquet").exists():
                        self.pair_scores = pd.concat([self.pair_scores, pd.read_parquet(rd / "pair_scores.parquet")], ignore_index=True)
                    self.run_ids.append(rd.name)
                except Exception as e:   # a broken run folder must never take the whole app down
                    print(f"[store] skipped run {rd.name}: {e!r}")
        self.claims["ts"] = pd.to_datetime(self.claims.ts, utc=True)
        self.posts["published_at"] = pd.to_datetime(self.posts.published_at, utc=True)
        self.events["date"] = self.events.date.astype(str)
        self.cidx = {c: i for i, c in enumerate(self.claims.cid)}        # cid -> row in claims / emb
        self.claims_by_cid = self.claims.set_index("cid", drop=False)
        self.posts_by_id = self.posts.drop_duplicates("doc_id").set_index("doc_id", drop=False)
        self.con = duckdb.connect(":memory:")
        for name in ["posts", "claims", "events", "families", "pair_scores"]:
            self.con.register(f"_{name}", getattr(self, name))      # real tables, so every thread's cursor sees them
            self.con.execute(f"create or replace table {name} as select * from _{name}")
            self.con.unregister(f"_{name}")
        self.data_version = f"{self.meta.get('data_version')}+{len(self.run_ids) - 1}runs"

    def sql(self, query, params=None):
        """Thread-safe query helper: returns a list of dicts."""
        cur = self.con.cursor()
        df = cur.execute(query, params or []).df()
        return json.loads(df.to_json(orient="records", date_format="iso"))


def get() -> Store:
    global _S
    with _lock:
        if _S is None:
            _S = Store()
        return _S


def reload() -> Store:
    global _S
    with _lock:
        _S = Store()
    try:
        from . import replay
        replay.clear_cache()
    except Exception:
        pass
    return _S
