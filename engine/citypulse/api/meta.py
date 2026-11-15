"""/api/health and /api/meta: what is loaded, which projects exist, benchmark numbers (provisional) and limitations.

Every sentence in `limitations` is built from the loaded data or from the state of the engine.
"""
import glob, hashlib, json, os, shutil, time, urllib.request
from datetime import date, timedelta

from .. import config
from .common import PROVISIONAL_NOTE, SIDE, STANCES, CHANNELS, clean, has_arguments, log, project_name
from .stats import stance_block

_probe_cache = {}


def _ollama_up(model_wanted: bool = False) -> bool:
    """Is the local Ollama server answering (and, if asked, does it have the embedding model)? Local request, cached 30 s."""
    hit = _probe_cache.get(("ollama", model_wanted))
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    ok = False
    try:
        with urllib.request.urlopen(config.OLLAMA_URL.rstrip("/") + "/api/tags", timeout=0.5) as r:
            names = [m.get("name", "") for m in json.load(r).get("models", [])]
            ok = any(n.split(":")[0] == config.EMBED_MODEL.split(":")[0] for n in names) if model_wanted else True
    except Exception:
        ok = False
    _probe_cache[("ollama", model_wanted)] = (time.time(), ok)
    return ok


def matcher_status() -> dict:
    """matcher.status() from the engine, or a clear 'not loaded' answer. Never raises."""
    try:
        from ..engine import matcher
        s = clean(matcher.status()) or {}
        s.setdefault("available", False)
        return s
    except Exception as e:
        return {"available": False, "mode": "cached-only", "version": None, "message": f"matcher engine not loaded: {type(e).__name__}: {e}"}


def health(st) -> dict:
    m = matcher_status()
    emb = m.pop("embedder", None) if isinstance(m.get("embedder"), dict) else None
    if emb is None:
        emb = {"available": _ollama_up(True), "backend": f"ollama:{config.EMBED_MODEL}"}
    llm = m.pop("llm", None) if isinstance(m.get("llm"), dict) else None
    if llm is None:
        backend = config.LLM_BACKEND
        if backend == "openrouter":
            import os
            avail = bool(os.environ.get("OPENROUTER_API_KEY"))
        else:
            avail = shutil.which("claude") is not None if backend == "claude" else _ollama_up()
        llm = {"backend": f"{backend}:{config.LLM_MODEL}", "available": bool(avail)}
    m.setdefault("mode", "local-model" if m.get("available") else "cached-only")
    m.setdefault("version", st.matcher_cfg.get("version"))
    return {"status": "ok", "data_version": st.data_version, "n_posts": int(len(st.posts)), "n_claims": int(len(st.claims)),
            "matcher": m, "embedder": emb, "llm": llm, "runs": list(st.run_ids), "cached_pair_scores": int(len(st.pair_scores))}


def projects(st) -> list:
    out = []
    ids = [p for p in dict.fromkeys(list(st.meta.get("projects", {})) + sorted(st.posts.project.unique()))]
    for pid in ids:
        p = st.posts[st.posts.project == pid]
        out.append({"id": pid, "name": project_name(st, pid), "has_arguments": has_arguments(st, pid), "n_posts": int(len(p)),
                    "n_unique_posts": int(p.is_first_copy.sum()), "n_claims": int((st.claims.project == pid).sum()),
                    "first_date": p.date.min() if len(p) else None, "last_date": p.date.max() if len(p) else None})
    return out


def _pick(rows, method, **where):
    for r in rows or []:
        if r.get("method") == method and all(r.get(k) == v for k, v in where.items()):
            return r
    return None


def metrics(st) -> dict:
    """Benchmark numbers from the eval_*.json files of the data bundle and from matcher.json. Always provisional."""
    out = {"provisional": True, "note": PROVISIONAL_NOTE,
           "explanation": "Test pairs and novelty cases were labelled by an AI reference model, not by people. "
                          "Human labels are being collected in the review tool; until then these numbers are provisional.",
           "references": {}, "files": []}
    for path in sorted(glob.glob(str(config.DATA / "eval_*.json"))):
        try:
            d = clean(json.load(open(path, encoding="utf-8")))
        except Exception as e:
            log.warning("could not read %s: %r", path, e)
            continue
        name = os.path.basename(path)
        out["files"].append(name)
        if not isinstance(d, dict) or "pair_matching_test" not in d:
            out.setdefault("other", {})[name] = d
            continue
        sel = d.get("selected_method")
        base = d.get("baseline_method") or "cosine (current baseline)"   # v1 files name it "current baseline"
        ref = {"reference": d.get("reference"), "file": name, "n_test_pairs": d.get("n_test_pairs"), "n_cal_pairs": d.get("n_cal_pairs"),
               "test_same_rate": d.get("test_same_rate"), "label_counts_test": d.get("label_counts_test"), "selected_method": sel,
               "pair_matching": {"selected": _pick(d.get("pair_matching_test"), sel), "baseline": _pick(d.get("pair_matching_test"), base),
                                 "all_methods": d.get("pair_matching_test")},
               "novelty": {"selected": [r for r in d.get("novelty_test", []) if r.get("method") == sel],
                           "baseline": [r for r in d.get("novelty_test", []) if r.get("method") == base],
                           "all_methods": d.get("novelty_test")},
               "retrieval_depth_check": d.get("retrieval_depth_check")}
        if d.get("annotator_agreement"):
            out["annotator_agreement"] = {**d["annotator_agreement"], "between": "two AI reference models (not people)"}
        out["references"][str(d.get("reference") or name)] = ref
    cfg = st.matcher_cfg or {}
    out["matcher_config"] = clean({k: v for k, v in cfg.items() if not isinstance(v, (list, dict)) or len(json.dumps(v, default=str)) < 2000})
    out["available"] = bool(out["references"] or cfg)
    return out


_checksum_cache = {}


def _weights_checksum():
    """sha256 of the matcher weights, if they are on this machine (computed once per file version)."""
    f = config.MODEL_DIR / "model.safetensors"
    if not f.exists():
        return None
    key = (str(f), f.stat().st_mtime_ns, f.stat().st_size)
    if key not in _checksum_cache:
        h = hashlib.sha256()
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 22), b""):
                h.update(chunk)
        _checksum_cache.clear()
        _checksum_cache[key] = h.hexdigest()
    return _checksum_cache[key]


def model(st) -> dict:
    """Which matcher the scores come from: matcher.json of the data bundle, the eval files, and the engine's own status."""
    cfg = st.matcher_cfg or {}
    ms = matcher_status()
    first = lambda *keys: next((src[k] for src in (cfg, ms) for k in keys if src.get(k) not in (None, "")), None)
    selected = None
    for path in sorted(glob.glob(str(config.DATA / "eval_*.json"))):
        try:
            selected = selected or json.load(open(path, encoding="utf-8")).get("selected_method")
        except Exception:
            pass
    trained_until = first("trained_until", "train_until", "training_end")
    source = "matcher.json"
    if trained_until is None:      # the replay limit in config.py is defined as the first day the matcher has not seen
        trained_until = (date.fromisoformat(config.EARLIEST_REPLAY_CUTOFF) - timedelta(days=1)).isoformat()
        source = "config.EARLIEST_REPLAY_CUTOFF minus one day"
    return {"name": first("name", "model", "model_name") or selected, "version": first("version", "model_version"),
            "trained_until": trained_until, "trained_until_source": source,
            "checksum": first("checksum", "sha256", "weights_sha256") or _weights_checksum(),
            "thresholds": clean(cfg.get("thresholds")), "replay_earliest_cutoff": config.EARLIEST_REPLAY_CUTOFF,
            "loaded": bool(ms.get("available")), "mode": ms.get("mode"), "provisional": True, "note": PROVISIONAL_NOTE,
            "config_present": bool(cfg)}


def limitations(st) -> list:
    L = ["This is observable online debate, not a representative poll. Every share is shown with its sample size (n) and a 95% interval.",
         f"The data covers {st.posts.date.min()} to {st.posts.date.max()}: {len(st.posts)} collected posts, "
         f"{int(st.posts.is_first_copy.sum())} unique texts, {len(st.claims)} extracted claims (data version {st.data_version})."]
    for p in projects(st):
        b = stance_block(st.posts[st.posts.project == p["id"]])
        o = b["opposition_share"]
        share = (f"opposition share {o['value']:.0%} (95% interval {o['lo']:.0%} to {o['hi']:.0%})" if o["n"] else "no opposition share can be given")
        L.append(f"{p['name']}: {p['n_posts']} posts, {p['n_unique_posts']} unique; {b['n_with_stance']} unique posts take a side "
                 f"(support, oppose or mixed), {share}." + ("" if p["has_arguments"] else " No arguments were extracted for this project."))
    for p in projects(st):
        if p["id"].startswith("heilbronn"):
            b = stance_block(st.posts[st.posts.project == p["id"]])
            width = (b["opposition_share"]["hi"] - b["opposition_share"]["lo"]) if b["n_with_stance"] else None
            L.append(f"Only {b['n_with_stance']} Heilbronn posts take a side"
                     + (f"; the interval of the opposition share is {width:.0%} wide. " if width is not None else ". ")
                     + "Treat Heilbronn shares as indications, not as measurements.")
    ls = st.posts.label_source.value_counts().to_dict()
    L.append(f"Project, stance and tone are AI labels ({st.meta.get('classifier', 'AI classifier')}; label sources: "
             + ", ".join(f"{k} {v}" for k, v in ls.items()) + "). They have not been validated by people.")
    L.append("All accuracy numbers are provisional: " + PROVISIONAL_NOTE + ".")
    ms = matcher_status()
    if ms.get("available"):
        L.append(f"The argument matcher model is loaded (mode {ms.get('mode')}, version {ms.get('version')}); new text is scored live.")
    else:
        L.append("The argument matcher model is not loaded on this server"
                 + (f"; {len(st.pair_scores)} cached pair scores are used where they exist" if len(st.pair_scores) else "; no cached pair scores are in the data bundle")
                 + ". Matching of new text falls back to a weaker baseline or is unavailable.")
    L.append(f"Historical replay is only offered from {config.EARLIEST_REPLAY_CUTOFF} on, because the matcher was trained on data before this date.")
    L.append("Contradiction ('opposing') detection is disabled in this release: it is not reliable enough. Equivalent and related arguments are kept apart.")
    ev = st.events
    if len(ev):
        nv = int((ev.verified.astype(str).str.lower() != "yes").sum())
        L.append(f"{nv} of {len(ev)} timeline events have not been verified against their source by a person.")
    L.append("Cross-city cases are historical examples from other projects, not forecasts for Heilbronn.")
    return L


def meta(st) -> dict:
    topics = [t for t in st.claims.topic.value_counts().index]
    return {"projects": projects(st), "topics": topics, "channels": [c for c in CHANNELS if (st.posts.channel == c).any()],
            "stances": list(STANCES), "side_stances": list(SIDE),
            "stance_labels_in_data": {str(k): int(v) for k, v in st.posts.stance.value_counts().items()},
            "limitations": limitations(st), "metrics": metrics(st), "model": model(st),
            "data_version": st.data_version, "date_min": st.posts.date.min(), "date_max": st.posts.date.max(),
            "runs": list(st.run_ids), "codebook": "codebook_v1", "classifier": st.meta.get("classifier"), "embedder": st.meta.get("embedder")}
