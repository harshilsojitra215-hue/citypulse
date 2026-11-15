"""Batch runs: one folder per upload in config.RUNS/<run_id>/.

  run.json            the Run (docs/API_CONTRACT.md), rewritten after every step so a client can poll it
  posts.parquet       new relevant posts, the store's columns, run_id set
  claims.parquet      their extracted arguments, the store's columns, run_id set
  claims_emb.npy      float32, row i belongs to claims row i
  pair_scores.parquet matcher scores of every new claim against older claims (from engine.ingest)
  novelty.parquet     cid, novelty_state, novelty_score, best_match_cid (from engine.ingest)
  DONE                empty marker: store.reload() only reads folders that have it

The uploaded file itself is never copied here. Only its SHA-256 and name are kept.
"""
import hashlib, json, math, os, re, secrets, threading, time, traceback
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np, pandas as pd
from .. import config
from ..engine import store
from . import formats, steps

STEP_NAMES = ["validate", "clean", "dedupe", "relevance", "classify", "extract", "match", "novelty", "store"]
RUN_ID = re.compile(r"^r\d{8}-\d{4}-[0-9a-f]{4}$")
STALE_SECS = 1800            # a run.json still "running" after this long, in a process that does not own it, was interrupted
_registry = threading.Lock() # guards _active and run-folder creation
_processing = threading.Lock()   # one batch at a time: two runs must not both add the same new post
_active = {}                 # run_id -> sha256 of runs queued or running in this process


class DuplicateUpload(Exception):
    """The same file (same SHA-256) was already processed, or is being processed right now."""
    def __init__(self, run_id):
        super().__init__(f"this file was already processed as run {run_id}")
        self.run_id = run_id


# ---------------------------------------------------------------- engine calls (kept in one place so tests can replace them)
def _match_new_claims(claims_df):
    from ..engine import ingest
    return ingest.match_new_claims(claims_df)


def _concerns(run_id):
    from ..engine import replay
    return replay.concerns(run_id=run_id)


def _engine_info() -> dict:
    """What the matcher and the embedder are, for Run.models."""
    out = dict(embedder=f"ollama:{config.EMBED_MODEL}", matcher="unknown")
    try:
        from ..engine import matcher
        st = matcher.status()
        out["matcher"] = f"{st.get('version') or config.MODEL_DIR.name} ({st.get('mode')})" if st.get("available") else \
            f"not available: {st.get('reason')}"
        out["matcher_available"] = bool(st.get("available"))
    except Exception as e:
        out["matcher"] = f"not available: {e!r}"[:300]
        out["matcher_available"] = False
    return out


# ---------------------------------------------------------------- run.json
def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, np.ndarray)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return None if pd.isna(o) else o.isoformat()
    if o is None or o is pd.NaT or o is pd.NA:
        return None
    if isinstance(o, (str, int, bool)):
        return o
    return str(o)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Run:
    def __init__(self, filename, sha):
        config.RUNS.mkdir(parents=True, exist_ok=True)
        while True:
            run_id = "r" + datetime.now().strftime("%Y%m%d-%H%M") + "-" + secrets.token_hex(2)   # local time; created_at is UTC
            try:
                (config.RUNS / run_id).mkdir()
                break
            except FileExistsError:
                continue
        self.dir = config.RUNS / run_id
        self.d = dict(
            run_id=run_id, filename=os.path.basename(filename or "upload"), sha256=sha, created_at=_now(), finished_at=None,
            status="queued", message="",
            steps=[dict(name=n, status="pending", n_in=0, n_out=0, secs=0.0, message="") for n in STEP_NAMES],
            counts=dict(records=0, valid=0, rejected=0, duplicates_in_file=0, already_known=0, candidates=0, relevant=0,
                        not_relevant=0, unclassified=0, claims=0, familiar=0, ambiguous=0, new=0, unscored=0),
            errors=[], findings=dict(concerns=[], note="not computed yet"),
            models=dict(classifier=f"{config.LLM_BACKEND}:{config.LLM_MODEL} ({steps.PROMPT.stem})", matcher="not used yet",
                        embedder=f"ollama:{config.EMBED_MODEL}", llm_backend=config.LLM_BACKEND, llm_model=config.LLM_MODEL,
                        prompt=steps.PROMPT.stem, prompt_hash=steps.prompt()[1]))
        self.save()

    @property
    def run_id(self):
        return self.d["run_id"]

    def save(self):
        tmp = self.dir / "run.json.tmp"
        tmp.write_text(json.dumps(_jsonable(self.d), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
        os.replace(tmp, self.dir / "run.json")

    def error(self, record, step, message):
        self.d["errors"].append(dict(record=str(record), step=step, message=str(message)))

    def skip(self, name, message):
        s = next(x for x in self.d["steps"] if x["name"] == name)
        s.update(status="skipped", message=message)
        self.save()

    @contextmanager
    def step(self, name, n_in=0):
        s = next(x for x in self.d["steps"] if x["name"] == name)
        s.update(status="running", n_in=int(n_in))
        self.save()
        t = time.time()
        try:
            yield s
        except Exception as e:
            s.update(status="failed", message=s["message"] or str(e)[:500])
            raise
        else:
            s["status"] = "done"
        finally:
            s["secs"] = round(time.time() - t, 2)
            self.save()


def _read(run_dir: Path):
    try:
        d = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if d.get("status") in ("queued", "running") and d.get("run_id") not in _active \
            and time.time() - (run_dir / "run.json").stat().st_mtime > STALE_SECS:
        d["status"] = "failed"
        d["message"] = "interrupted: the server stopped while this run was being processed. Upload the file again."
    return d


def list_runs() -> list:
    """All runs, newest first."""
    if not config.RUNS.exists():
        return []
    runs = [d for d in (_read(p) for p in config.RUNS.iterdir() if p.is_dir() and RUN_ID.match(p.name)) if d]
    return sorted(runs, key=lambda d: (d.get("created_at") or "", d.get("run_id") or ""), reverse=True)


def get_run(run_id: str):
    if not isinstance(run_id, str) or not RUN_ID.match(run_id):
        return None
    return _read(config.RUNS / run_id)


def step_table(run: dict) -> str:
    rows = [f"{'step':<10} {'status':<8} {'n_in':>5} {'n_out':>5} {'secs':>7}  message"]
    rows += [f"{s['name']:<10} {s['status']:<8} {s['n_in']:>5} {s['n_out']:>5} {s['secs']:>7.2f}  {s['message']}" for s in run["steps"]]
    return "\n".join(rows)


# ---------------------------------------------------------------- the workflow
def _dedupe(R, valid, df, S):
    """Skip what the store already has, collapse repeated ids, keep the pipeline's grouping of in-file copies."""
    known = df.dup_key.isin(set(S.posts.dup_key)) | df.doc_id.isin(set(S.posts.doc_id))
    repeat = ~known & df.doc_id.where(~known).duplicated(keep="first")
    first_key = df[~known & ~repeat].set_index("doc_id").dup_key
    for r in df[repeat].itertuples():
        if first_key.get(r.doc_id) != r.dup_key:
            R.error(r.doc_id, "dedupe", f"the id is used twice in this file with different text: the later record (row {r.row}) was skipped")
    drop = known | repeat
    if drop.any():
        keep = set(df.row[~drop])
        # regroup the remaining records with the pipeline itself, so dup_count and is_first_copy describe what is stored
        df = steps.run_base([r for r in valid if r["_row"] in keep]) if keep else df[~drop]
    return df, int(known.sum()), int(repeat.sum())


def _adopt_families(claims: pd.DataFrame, S) -> int:
    """A claim the matcher calls familiar joins the argument family of its best older match. Everything else stays
    its own single-claim family, as unclustered claims do in the bundle."""
    known = S.claims_by_cid
    own, n = {}, 0
    for i in claims.index:
        b = claims.at[i, "best_match_cid"]
        if claims.at[i, "novelty_state"] == "familiar" and isinstance(b, str):
            fam = own.get(b) or ((known.family_id[b], known.family_name[b], int(known.cluster_all[b])) if b in known.index else None)
            if fam:
                claims.at[i, "family_id"], claims.at[i, "family_name"], claims.at[i, "cluster_all"] = fam
                n += 1
        own[claims.at[i, "cid"]] = (claims.at[i, "family_id"], claims.at[i, "family_name"], int(claims.at[i, "cluster_all"]))
    return n


def _process(R: _Run, data: bytes):
    S = store.get()
    c, run_id = R.d["counts"], R.run_id
    dim = S.emb.shape[1]
    posts, claims = S.posts.iloc[:0], S.claims.iloc[:0]
    emb = np.zeros((0, dim), dtype=np.float32)
    pairs = S.pair_scores.iloc[:0]
    nov = pd.DataFrame(columns=["cid", "novelty_state", "novelty_score", "best_match_cid"])

    with R.step("validate") as s:
        records = formats.read_records(data, R.d["filename"])
        valid, errs = formats.validate(records)
        R.d["errors"] += errs
        c.update(records=len(records), valid=len(valid), rejected=len(errs))
        s.update(n_in=len(records), n_out=len(valid), message=f"{len(valid)} of {len(records)} records usable" +
                 (f"; {len(errs)} rejected (see errors)" if errs else ""))
        if not valid:
            raise formats.UnusableFile("no usable record in the file. First problem: " + errs[0]["message"])

    with R.step("clean", len(valid)) as s:
        df = steps.run_base(valid)
        s.update(n_out=len(df), message=f"HTML and whitespace removed (pipeline/01_build_base.py); {int(df.author_hash.notna().sum())} "
                 "author names replaced by salted hashes and dropped")

    with R.step("dedupe", len(df)) as s:
        df, n_known, n_repeat = _dedupe(R, valid, df, S)
        n_copies = int((~df.is_first_copy).sum()) if len(df) else 0
        c.update(already_known=n_known, duplicates_in_file=n_repeat + n_copies)
        s.update(n_out=int(df.is_first_copy.sum()) if len(df) else 0,
                 message=f"{n_known} already known and skipped; {n_copies} copies of the same text grouped with their first copy; "
                         f"{n_repeat} repeated ids collapsed")

    lab = None
    if not len(df):
        for n in ["relevance", "classify", "extract", "match", "novelty"]:
            R.skip(n, "no new post left after dedupe")
    else:
        with R.step("relevance", len(df)) as s:
            cand = steps.run_rules(df)
            todo = cand[(cand.bucket != "background") & cand.is_first_copy]
            c["candidates"] = len(todo)
            buckets = cand[cand.is_first_copy].bucket.value_counts().to_dict()
            s.update(n_out=len(todo), message=f"keyword rules (pipeline/02_candidates.py): {buckets}; background is not sent to the model; "
                     + steps.boilerplate_note(cand))

        if not len(todo):
            R.skip("classify", "no record passed the keyword rules")
            lab = steps.assemble(cand, {})
        else:
            with R.step("classify", len(todo)) as s:
                labels, errs = steps.label(cand)
                R.d["errors"] += errs
                lab = steps.assemble(cand, labels)
                by = lab[lab.is_first_copy & (lab.project != "not_reviewed")].project.value_counts().to_dict()
                s.update(n_out=len(labels), message=f"{R.d['models']['classifier']}, prompt {R.d['models']['prompt_hash']}: {by}" +
                         (f"; {len(errs)} not classified (see errors)" if errs else ""))

        with R.step("extract", int((lab.project.isin(steps.ARGUMENT_PROJECTS) & lab.is_first_copy).sum())) as s:
            claims = steps.claims_frame(lab, run_id)
            posts = steps.posts_frame(lab, claims, run_id)
            rel = lab.project.isin(config.PROJECT_NAMES)
            unclassified = (lab.project == "not_reviewed") & (lab.bucket != "background")
            c.update(relevant=int(rel.sum()), unclassified=int(unclassified.sum()), not_relevant=int((~rel & ~unclassified).sum()),
                     claims=len(claims))
            s.update(n_out=len(claims), message=f"{len(claims)} arguments from {claims.doc_id.nunique()} posts (the codebook call returns "
                     "them with the label; one row per argument as in pipeline/10_argument_map.py)")

        if not len(claims):
            R.skip("match", "no argument to match")
            R.skip("novelty", "no argument to match")
        else:
            claims["novelty_state"], claims["novelty_score"], claims["best_match_cid"] = "unscored", None, None
            with R.step("match", len(claims)) as s:
                R.d["models"].update(_engine_info())
                try:
                    out, P, E = _match_new_claims(claims[[x for x in claims.columns if not x.startswith(("novelty_", "best_match"))]])
                    E = np.asarray(E, dtype=np.float32)
                    if list(out.cid) != list(claims.cid) or E.shape != (len(claims), dim):
                        raise RuntimeError(f"ingest returned {len(out)} claims and embeddings {E.shape}, expected {len(claims)} and {(len(claims), dim)}")
                    for col in ["novelty_state", "novelty_score", "best_match_cid"]:
                        claims[col] = out[col].values
                    emb, pairs = E, P
                    s.update(n_out=len(pairs), message=f"embedded with {R.d['models']['embedder']}; {len(pairs)} pairs with older claims "
                             f"(matcher: {R.d['models']['matcher']})")
                except Exception as e:
                    emb = np.zeros((len(claims), dim), dtype=np.float32)
                    R.error("all claims", "match", f"matching failed, claims are stored as unscored and without embeddings: {str(e) or repr(e)}"[:500])
                    s.update(n_out=0, message="matching not available: claims stored as unscored (see errors)")
            with R.step("novelty", len(claims)) as s:
                claims["novelty_state"] = claims.novelty_state.fillna("unscored")
                st = claims.novelty_state.value_counts().to_dict()
                c.update({k: int(st.get(k, 0)) for k in ["familiar", "ambiguous", "new", "unscored"]})
                joined = _adopt_families(claims, S)
                if c["unscored"] and not any(e["step"] == "match" for e in R.d["errors"]):
                    R.error(f"{c['unscored']} claims", "novelty", "stored as unscored: the matcher model is not on this machine "
                            f"({R.d['models']['matcher']}). Put the weights in {config.MODEL_DIR}, delete this run folder and upload again.")
                s.update(n_out=c["new"] + c["ambiguous"], message=f"familiar {c['familiar']}, ambiguous {c['ambiguous']}, new {c['new']}, "
                         f"unscored {c['unscored']}; {joined} familiar claims joined a known argument family")
            nov = claims[["cid", "novelty_state", "novelty_score", "best_match_cid"]].copy()

    with R.step("store", len(posts)) as s:
        P_out, C_out = steps.like_store(posts, S.posts), steps.like_store(claims, S.claims)
        P_out.to_parquet(R.dir / "posts.parquet", index=False)
        C_out.to_parquet(R.dir / "claims.parquet", index=False)
        np.save(R.dir / "claims_emb.npy", emb)
        pairs.to_parquet(R.dir / "pair_scores.parquet", index=False)
        nov["novelty_score"] = pd.to_numeric(nov.novelty_score, errors="coerce")
        nov.astype({"cid": str, "novelty_state": str, "best_match_cid": object}).to_parquet(R.dir / "novelty.parquet", index=False)
        (R.dir / "DONE").touch()
        S2 = store.reload()
        if run_id not in S2.run_ids:
            (R.dir / "DONE").unlink(missing_ok=True)
            raise RuntimeError("the store could not load this run (see the server log line '[store] skipped run')")
        try:
            R.d["findings"] = dict(concerns=_concerns(run_id) if len(C_out) else [], note="")
        except Exception as e:
            R.d["findings"] = dict(concerns=[], note=f"concerns could not be computed: {e!r}"[:300])
        s.update(n_out=len(P_out), message=f"{len(P_out)} posts and {len(C_out)} claims stored under run_id {run_id}; the application shows them now")


def _execute(R: _Run, data: bytes, path, delete_upload: bool):
    with _processing:
        R.d["status"] = "running"
        R.save()
        try:
            _process(R, data)
            R.d["status"] = "done_with_errors" if R.d["errors"] else "done"
            R.d["message"] = f"{len(R.d['errors'])} problems recorded, see errors" if R.d["errors"] else ""
        except (formats.UnusableFile, steps.LLMUnavailable) as e:
            R.d.update(status="failed", message=str(e))
        except Exception as e:
            R.d.update(status="failed", message=f"unexpected error: {e!r}"[:500])
            R.error("run", "internal", traceback.format_exc()[-1500:])
        finally:
            for s in R.d["steps"]:
                if s["status"] in ("pending", "running"):
                    s["status"] = "skipped"
                if R.d["status"] == "failed" and s["status"] == "failed":
                    s["message"] = R.d["message"]
            R.d["finished_at"] = _now()
            R.save()
            with _registry:
                _active.pop(R.run_id, None)
            if delete_upload:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass
    return R.d


def _create(path, filename):
    data = Path(path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    with _registry:
        dup = next((rid for rid, h in _active.items() if h == sha), None) or \
              next((d["run_id"] for d in list_runs() if d.get("sha256") == sha and d.get("status") in ("done", "done_with_errors")), None)
        if dup:
            raise DuplicateUpload(dup)
        R = _Run(filename or os.path.basename(str(path)), sha)
        _active[R.run_id] = sha
    return R, data


def submit(path, filename=None) -> dict:
    """Create the run, process it in a background thread, return the Run at once (status "queued").
    The uploaded file at `path` is deleted when processing has finished (also when it is a duplicate)."""
    try:
        R, data = _create(path, filename)
    except DuplicateUpload:
        Path(path).unlink(missing_ok=True)
        raise
    queued = json.loads(json.dumps(_jsonable(R.d)))
    threading.Thread(target=_execute, args=(R, data, path, True), name=f"batch-{R.run_id}", daemon=True).start()
    return queued


def process_sync(path, filename=None, delete_upload=False) -> dict:
    """Same workflow, in the calling thread; returns the finished Run. For tests and `python -m citypulse.batch <file>`.
    The file is kept unless delete_upload is set (the command line is usually pointed at a file the user wants to keep)."""
    R, data = _create(path, filename)
    return json.loads(json.dumps(_jsonable(_execute(R, data, path, delete_upload))))
