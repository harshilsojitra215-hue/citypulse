"""The processing steps of a batch run. Every rule comes from the research pipeline in pipeline/: the numbered
scripts are loaded by file path and their own functions are called, so a batch is cleaned, filtered and labelled
exactly like the historical data.

  pipeline/01_build_base.py   main(): clean, title+content text, author hash, dates, dup_key, dup_count, channel
  pipeline/02_candidates.py   main(): strip_boilerplate, keyword rules R, bucket, kwic snippet
  pipeline/llm_label.py       fmt_item, parse_array, call_claude, call_ollama (its batching and retry loop sits
                              inside its command-line main(), so label() repeats that loop around the same calls)
  pipeline/prompts/codebook_v1.md   the system prompt, unchanged

pipeline/09_assemble.py, 10_argument_map.py, 20_pairs_build.py and 30_build_app_data.py are scripts without
functions (importing them would run them on the lab data). assemble(), claims_frame() and posts_frame() follow
them line by line and say which lines.
"""
import contextlib, functools, hashlib, importlib.util, io, json, os, shutil, tempfile, threading, time, urllib.request, warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
from .. import config

PIPE = config.ROOT / "pipeline"
PROMPT = PIPE / "prompts" / "codebook_v1.md"
LLM_BATCH, LLM_WORKERS, MAX_CHARS, RETRIES, RETRY_SLEEP = 20, 4, 1100, 3, 3.0   # same defaults as llm_label.py
# the label vocabulary of codebook_v1.md
CODEBOOK_PROJECTS = {"heilbronn_cablecar", "paris_c1", "bonn_cablecar", "other_urban_cablecar", "ipai",
                     "heilbronn_other", "leisure_cablecar", "unrelated"}
ARGUMENT_PROJECTS = ["heilbronn_cablecar", "paris_c1", "bonn_cablecar", "other_urban_cablecar"]   # CC in 10_argument_map.py
LABEL_COLS = ["project", "passing", "city", "stance", "tone", "arguments", "label_source"]      # keep[1:] in 09_assemble.py


class LLMUnavailable(Exception):
    """The labelling model cannot be reached at all. The message says what to configure."""


@functools.lru_cache(maxsize=None)
def pipeline_module(filename: str):
    """Load pipeline/<filename> as a module (the numbered names cannot be imported the normal way)."""
    path = PIPE / filename
    spec = importlib.util.spec_from_file_location("citypulse_pipeline_" + path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@contextlib.contextmanager
def _quiet():
    """The pipeline scripts print their own progress tables and pandas warns about a time-zone detail of the week
    column; neither belongs in the server log. Batch runs are processed one at a time, so swapping stdout is safe."""
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore", UserWarning)
        yield


def h6(s) -> str:
    return hashlib.sha1(str(s).encode()).hexdigest()[:6]     # same as h6 in 30_build_app_data.py


# ---------------------------------------------------------------- clean (01_build_base.py)
def run_base(records: list) -> pd.DataFrame:
    """Run 01_build_base.main() on the validated records. Author names exist only in a temporary file that is
    removed before this function returns; the result carries the salted hash (config.AUTHOR_SALT) and nothing else."""
    m = pipeline_module("01_build_base.py")
    m.SALT = config.AUTHOR_SALT
    ids = {r["mention_id"]: r["_id"] for r in records}
    tmp = Path(tempfile.mkdtemp(prefix="citypulse_batch_"))
    try:
        raw = [{k: v for k, v in r.items() if not k.startswith("_")} for r in records]
        (tmp / "raw.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with _quiet():
            m.main(str(tmp / "raw.json"), str(tmp / "base.parquet"))
        df = pd.read_parquet(tmp / "base.parquet")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    df["row"] = df.mention_id.astype(int)
    df["given_id"] = df.mention_id.map(ids)
    # stable id: the uploader's id, else a hash of url + normalised text (the pipeline's own normalisation)
    df["doc_id"] = [g if isinstance(g, str) and g else "u:" + hashlib.sha1(((u or "") + m.norm_for_dup(t)).encode()).hexdigest()[:16]
                    for g, u, t in zip(df.given_id, df.url, df.text)]
    df["mention_id"] = df.doc_id          # the pipeline calls the id mention_id (fmt_item, 09, 10)
    return df


# ---------------------------------------------------------------- relevance rules (02_candidates.py)
def run_rules(df: pd.DataFrame) -> pd.DataFrame:
    """Run 02_candidates.main(): boilerplate removal over the batch, the keyword rules R, the bucket and the snippet."""
    m = pipeline_module("02_candidates.py")
    tmp = Path(tempfile.mkdtemp(prefix="citypulse_batch_"))
    try:
        df.to_parquet(tmp / "base.parquet", index=False)
        with _quiet():
            m.main(str(tmp / "base.parquet"), str(tmp / "cand.parquet"))
        return pd.read_parquet(tmp / "cand.parquet")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def boilerplate_note(cand: pd.DataFrame) -> str:
    n = int(cand.is_first_copy.sum())
    if n < 15:   # min_docs in strip_boilerplate
        return (f"boilerplate filter inactive: it removes sentences repeated in 15 or more posts and this batch has {n} "
                "unique posts (known posts cannot be added: the store keeps only excerpts that are already filtered)")
    removed = int(cand.text.str.len().sum() - cand.text_clean.str.len().sum())
    return f"boilerplate filter applied over the {n} unique posts of this batch ({max(removed, 0):,} characters removed)"


# ---------------------------------------------------------------- classify + extract (llm_label.py, codebook_v1.md)
def prompt():
    system = PROMPT.read_text(encoding="utf-8")
    return system, hashlib.sha1(system.encode()).hexdigest()[:8]


def llm_info() -> dict:
    return dict(backend=config.LLM_BACKEND, model=config.LLM_MODEL, prompt=PROMPT.stem, prompt_hash=prompt()[1])


def check_llm():
    """Cheap reachability check before any text is sent. Raises LLMUnavailable with the exact fix."""
    b, model = config.LLM_BACKEND, config.LLM_MODEL
    if b == "claude":
        if shutil.which("claude") is None:
            raise LLMUnavailable("the Claude Code CLI ('claude') is not on PATH. Install it and log in once (run 'claude', then /login), "
                                 "or use a local model: set CITYPULSE_LLM_BACKEND=ollama and CITYPULSE_LLM_MODEL=<model pulled in Ollama>.")
    elif b == "ollama":
        try:
            with urllib.request.urlopen(config.OLLAMA_URL + "/api/tags", timeout=5) as r:
                names = [x.get("name", "") for x in json.load(r).get("models", [])]
        except Exception as e:
            raise LLMUnavailable(f"Ollama is not reachable at {config.OLLAMA_URL} ({e!r}). Start it ('ollama serve') or set OLLAMA_URL, "
                                 "or set CITYPULSE_LLM_BACKEND=claude to use the Claude Code CLI.")
        if model not in names and model + ":latest" not in names:
            raise LLMUnavailable(f"the model '{model}' is not available in Ollama at {config.OLLAMA_URL}. Run 'ollama pull {model}' "
                                 "or set CITYPULSE_LLM_MODEL to one of: " + ", ".join(names[:8]))
    elif b == "openrouter":
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise LLMUnavailable("CITYPULSE_LLM_BACKEND=openrouter but OPENROUTER_API_KEY is not set (the launcher loads it from live/.env).")
        if _OR_SPENT[0] >= _or_cap():
            raise LLMUnavailable(f"the OpenRouter cost cap of {_or_cap():.2f} USD for this process is reached.")
    else:
        raise LLMUnavailable(f"unknown CITYPULSE_LLM_BACKEND '{b}'. Use 'claude' (Claude Code CLI), 'openrouter' or 'ollama' (local model).")


# OpenRouter backend (Harshil, 15 Nov 2026): the Claude Code CLI on the demo laptop is not logged in on its own, so new
# batches use the same Haiku model through OpenRouter. The key is the key owner's, used with his OK, capped per process.
_OR_SPENT = [0.0]
_OR_LOCK = threading.Lock()


def _or_cap() -> float:
    try:
        return float(os.environ.get("CITYPULSE_LLM_MAX_USD", "1.0"))
    except ValueError:
        return 1.0


def call_openrouter(system: str, user: str, model: str) -> str:
    with _OR_LOCK:
        if _OR_SPENT[0] >= _or_cap():
            raise LLMUnavailable(f"OpenRouter cost cap {_or_cap():.2f} USD reached ({_OR_SPENT[0]:.3f} USD spent)")
    body = json.dumps({"model": model, "max_tokens": 8000, "usage": {"include": True},
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
        "X-Title": "studio"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    u = d.get("usage") or {}
    cost = u.get("cost")
    if not cost:   # no cost reported: estimate with Haiku list prices (1 USD in, 5 USD out per million tokens)
        cost = (u.get("prompt_tokens") or 0) * 1e-6 + (u.get("completion_tokens") or 0) * 5e-6
    with _OR_LOCK:
        _OR_SPENT[0] += float(cost)
    return d["choices"][0]["message"]["content"]


def or_spent() -> float:
    return round(_OR_SPENT[0], 4)


def call_llm(system: str, user: str) -> str:
    """One call through the pipeline's own callers (never an API key: call_claude removes ANTHROPIC_API_KEY)."""
    m = pipeline_module("llm_label.py")
    if config.LLM_BACKEND == "openrouter":
        return call_openrouter(system, user, config.LLM_MODEL)
    if config.LLM_BACKEND == "claude":
        os.environ.setdefault("LABEL_CWD", tempfile.gettempdir())
        return m.call_claude(system, user, config.LLM_MODEL)[0]
    os.environ["OLLAMA_URL"] = str(config.OLLAMA_URL)     # call_ollama reads the address from the environment
    return m.call_ollama(system, user, config.LLM_MODEL)[0]


def _clean_label(o: dict) -> dict:
    args = []
    for a in o.get("arguments") or []:
        if isinstance(a, dict) and isinstance(a.get("claim"), str) and a["claim"].strip():
            args.append(dict(topic=str(a.get("topic") or "other"), polarity=str(a.get("polarity") or "neutral"), claim=a["claim"].strip()))
    return dict(project=o["project"], passing=bool(o.get("passing") or False), city=o.get("city") if isinstance(o.get("city"), str) else None,
                stance=str(o.get("stance") or "na"), tone=str(o.get("tone") or "neutral"), arguments=args)


def label(cand: pd.DataFrame):
    """Label every unique candidate text (bucket != background) with the codebook prompt.
    -> (labels {doc_id: label dict}, errors [{record, step, message}]). A batch that fails three times is reported
    and skipped; the other batches still count. Raises LLMUnavailable when no batch at all could be labelled."""
    m = pipeline_module("llm_label.py")
    todo = cand[(cand.bucket != "background") & cand.is_first_copy]
    if not len(todo):
        return {}, []
    check_llm()
    system, _ = prompt()
    batches = [todo.iloc[i:i + LLM_BATCH] for i in range(0, len(todo), LLM_BATCH)]

    def run(b):   # the loop of llm_label.main(), with --short_ids (uploader ids can be any string)
        shown = [str(k + 1) for k in range(len(b))]
        real = dict(zip(shown, b.doc_id))
        user = "Label these items:\n\n" + "\n\n".join(m.fmt_item(r, MAX_CHARS, sid) for r, sid in zip(b.itertuples(), shown))
        err = None
        for attempt in range(RETRIES):
            try:
                arr = m.parse_array(call_llm(system, user))
                got = {str(o.get("id")): o for o in arr if isinstance(o, dict)}
                missing = [i for i in shown if i not in got]
                if len(missing) > len(shown) // 4:
                    raise ValueError(f"{len(missing)} ids missing")
                return {real[i]: got[i] for i in shown if i in got}, [real[i] for i in missing], None
            except Exception as e:
                err = repr(e)[:300]
                if attempt + 1 < RETRIES:
                    time.sleep(RETRY_SLEEP * (attempt + 1))
        return {}, list(b.doc_id), err

    labels, errors, n_failed, last = {}, [], 0, None
    with ThreadPoolExecutor(max_workers=LLM_WORKERS) as ex:
        for got, missing, err in ex.map(run, batches):
            if err:
                n_failed += 1
                last = err
            for d, o in got.items():
                if o.get("project") in CODEBOOK_PROJECTS:
                    labels[d] = _clean_label(o)
                else:
                    errors.append(dict(record=d, step="classify", message=f"the model returned an unknown project {o.get('project')!r}: record not classified"))
            for d in missing:
                errors.append(dict(record=d, step="classify", message=("LLM call failed 3 times: " + err) if err else "the model returned no label for this record"))
    if n_failed == len(batches):
        raise LLMUnavailable(f"no record could be classified with {config.LLM_BACKEND}:{config.LLM_MODEL} (last error: {last}). "
                             "For the default backend, check that 'claude' runs in a terminal and is logged in (/login). For a local model set "
                             "CITYPULSE_LLM_BACKEND=ollama, CITYPULSE_LLM_MODEL=<model> and OLLAMA_URL.")
    return labels, errors


def assemble(cand: pd.DataFrame, labels: dict) -> pd.DataFrame:
    """09_assemble.py: join the labels on the labelled copy, copy them to its duplicates (same dup_key), mark the
    rest not_reviewed."""
    key_of = cand.drop_duplicates("doc_id").set_index("doc_id").dup_key
    L = pd.DataFrame([dict(dup_key=key_of[d], **{c: v.get(c) for c in LABEL_COLS[:-1]}) for d, v in labels.items()],
                     columns=["dup_key"] + LABEL_COLS[:-1])
    L["label_source"] = config.LLM_MODEL
    lab = cand.merge(L.drop_duplicates("dup_key"), on="dup_key", how="left")
    lab["project"] = lab.project.fillna("not_reviewed")
    lab["passing"] = lab.passing.fillna(False).astype(bool)
    return lab


# ---------------------------------------------------------------- output tables in the store's shape
def claims_frame(lab: pd.DataFrame, run_id: str) -> pd.DataFrame:
    """10_argument_map.py (one row per extracted argument of a unique cable-car post) plus the columns that
    20_pairs_build.py and 30_build_app_data.py add (source_key -> voice, norm, family, project_name)."""
    d = lab[lab.project.isin(ARGUMENT_PROJECTS) & lab.is_first_copy]
    rows, seen = [], set()
    for r in d.itertuples():
        args = r.arguments if isinstance(r.arguments, (list, np.ndarray)) else []
        for a in args:
            if isinstance(a, dict) and a.get("claim"):
                cid = "n:" + hashlib.sha1((r.doc_id + a["claim"]).encode()).hexdigest()[:12]
                if cid in seen:
                    continue
                seen.add(cid)
                source_key = r.author_hash if isinstance(r.author_hash, str) and r.author_hash else "dom:" + (r.domain or "unknown")
                rows.append(dict(cid=cid, doc_id=r.doc_id, claim=a["claim"], project=r.project, project_name=config.PROJECT_NAMES.get(r.project),
                                 date=pd.Timestamp(r.published_at).strftime("%Y-%m-%d"), ts=r.published_at, channel=r.channel,
                                 domain=r.domain, url=r.url, topic=a.get("topic"), polarity=a.get("polarity"), stance=r.stance,
                                 voice=h6(source_key), family_id="solo:" + cid, family_name=a["claim"], cluster_all=-1, run_id=run_id))
    C = pd.DataFrame(rows, columns=["cid", "doc_id", "claim", "project", "project_name", "date", "ts", "channel", "domain", "url", "topic",
                                    "polarity", "stance", "voice", "family_id", "family_name", "cluster_all", "run_id"])
    C["norm"] = C.claim.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.split().str.join(" ")   # 20_pairs_build.py
    C["ts"] = pd.to_datetime(C.ts, utc=True)
    return C.sort_values(["ts", "doc_id"], kind="stable").reset_index(drop=True)


def posts_frame(lab: pd.DataFrame, claims: pd.DataFrame, run_id: str) -> pd.DataFrame:
    """30_build_app_data.py, section posts: only posts of the product's projects, 400-character excerpt, voice."""
    L = lab[lab.project.isin(config.PROJECT_NAMES)].copy()
    L["voice"] = L.author_hash.astype(object).where(L.author_hash.notna(), "dom:" + L.domain.fillna("unknown")).map(h6)
    L["excerpt"] = L.text_clean.fillna("").str.slice(0, 400)
    L["date"] = pd.to_datetime(L.published_at, utc=True).dt.strftime("%Y-%m-%d")
    L["week"] = pd.to_datetime(L.week).dt.strftime("%Y-%m-%d")
    L["tool_sentiment"] = pd.to_numeric(L.tool_sentiment, errors="coerce").fillna(-99).astype(int)   # -99 = not provided, as in the bundle
    L["run_id"] = run_id
    L["project_name"] = L.project.map(config.PROJECT_NAMES)
    L["n_claims"] = L.doc_id.map(claims.groupby("doc_id").size()).fillna(0).astype(int)
    return L.sort_values("published_at", kind="stable").reset_index(drop=True)


def like_store(df: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Exactly the store's columns, in its order and with its dtypes (a column the batch cannot fill stays empty)."""
    # frozen replay families (v2 bundle): a new claim's frozen family is its own family
    fallback = {"family_frozen": "family_id", "family_frozen_name": "family_name"}
    pick = lambda c: df[c] if c in df.columns else (df[fallback[c]] if c in fallback and fallback[c] in df.columns else None)
    out = pd.DataFrame({c: pick(c) for c in ref.columns}, index=df.index, columns=ref.columns)
    for c in ref.columns:
        try:
            if isinstance(ref[c].dtype, pd.DatetimeTZDtype):
                out[c] = pd.to_datetime(out[c], utc=True).astype(ref[c].dtype)
            else:
                out[c] = out[c].astype(ref[c].dtype)
        except (TypeError, ValueError):
            pass
    return out.reset_index(drop=True)
