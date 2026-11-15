"""Preflight: is everything the demo needs in place on this machine?   python -m citypulse.check"""
import hashlib, json, shutil, urllib.request
from . import config


def main():
    rows = []
    def add(name, ok, detail, needed="required"):
        rows.append((name, "OK" if ok else ("MISSING" if needed == "required" else "not available"), needed, detail))
    b = config.DATA
    ok = (b / "posts.parquet").exists() and (b / "claims.parquet").exists() and (b / "claims_emb.npy").exists()
    add("data bundle", ok, str(b) + ("" if ok else "  -> see README, section Data"))
    ps = (b / "pair_scores.parquet").exists() and (b / "matcher.json").exists()
    add("cached matcher scores + thresholds", ps, "pair_scores.parquet, matcher.json")
    w = config.MODEL_DIR / "model.safetensors"
    want = None
    cs = config.ROOT / "models" / "checksums.txt"
    if cs.exists():
        for line in cs.read_text(encoding="utf-8").split("\n"):
            if line.strip().endswith("model.safetensors"):
                want = line.split()[0]
    if w.exists():
        h = hashlib.sha256(w.read_bytes()).hexdigest()
        add("matcher model weights", want is None or h == want, f"{w} sha256 {h[:16]}…" + ("" if want is None or h == want else f"  DOES NOT MATCH models/checksums.txt ({want[:16]}…)"), "optional")
    else:
        add("matcher model weights", False, f"{w} absent: the app runs on cached scores; live matching of new text and batches is off (models/MODEL_CARD.md)", "optional")
    # the bundle's cached scores must come from the same model as the weights on this machine
    mf = b / "MANIFEST.json"
    if mf.exists():
        m = json.loads(mf.read_text(encoding="utf-8"))
        mj = json.loads((b / "matcher.json").read_text(encoding="utf-8")) if (b / "matcher.json").exists() else {}
        same = m.get("matcher_version") == mj.get("version") and (want is None or m.get("model_sha256") == want)
        add("bundle manifest", same, f"data {m.get('data_version')}, scores from {m.get('matcher_version')} (model sha256 {str(m.get('model_sha256'))[:16]}…)"
            + ("" if same else "  -> bundle and models/checksums.txt disagree: rebuild the bundle or get the matching model"))
    else:
        add("bundle manifest", False, "app_data/MANIFEST.json absent (older bundle): cannot prove which model the cached scores came from", "optional")
    if w.exists() and (b / "pair_scores.parquet").exists():
        try:
            import numpy as np, pandas as pd
            from .engine import matcher, store
            S = store.get()
            P = S.pair_scores.dropna(subset=["ft_same"]).sample(16, random_state=0)
            txt = S.claims.set_index("cid").claim
            live = matcher.probs(txt.reindex(P.qid).tolist(), txt.reindex(P.cand).tolist())[:, 0]
            d = float(np.max(np.abs(live - P.ft_same.to_numpy())))
            add("live model reproduces cached scores", d < 0.01, f"16 cached pairs re-scored on {matcher.status().get('device')}: max difference {d:.4f} (must be < 0.01)", "optional")
        except Exception as e:
            add("live model reproduces cached scores", False, f"could not run: {type(e).__name__}: {str(e)[:120]}", "optional")
    try:
        with urllib.request.urlopen(config.OLLAMA_URL + "/api/tags", timeout=4) as r:
            names = [m["name"] for m in json.load(r)["models"]]
        add("embedder (Ollama bge-m3)", any(n.startswith(config.EMBED_MODEL) for n in names), f"{config.OLLAMA_URL}: {', '.join(names)[:80]}", "optional")
    except Exception as e:
        add("embedder (Ollama bge-m3)", False, f"{config.OLLAMA_URL} unreachable: search falls back to keywords; batches cannot be matched", "optional")
    if config.LLM_BACKEND == "claude":
        add("LLM for new batches (Claude Code CLI)", shutil.which("claude") is not None, shutil.which("claude") or "claude not on PATH: set CITYPULSE_LLM_BACKEND=ollama or install and log in", "optional")
    elif config.LLM_BACKEND == "openrouter":
        import os
        add("LLM for new batches (OpenRouter)", bool(os.environ.get("OPENROUTER_API_KEY")), f"{config.LLM_MODEL}, key from live/.env, cap {os.environ.get('CITYPULSE_LLM_MAX_USD', '1.0')} USD", "optional")
    else:
        add("LLM for new batches (Ollama)", True, f"{config.LLM_MODEL} at {config.OLLAMA_URL} (not probed)", "optional")
    add("frontend dependencies", (config.ROOT / "web" / "node_modules").exists(), "web/node_modules (run: cd web && npm install)", "required")
    wd = max(len(r[0]) for r in rows)
    for n, s, need, d in rows:
        print(f"{n:<{wd}}  {s:<13} {need:<9} {d}")
    bad = [r for r in rows if r[1] == "MISSING"]
    print("\nready for the demo" if not bad else f"\n{len(bad)} required item(s) missing")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
