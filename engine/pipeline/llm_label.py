"""LLM labeller (Claude via the Claude Code CLI on the subscription, or a local Ollama model).

Usage:
  python -I src/llm_label.py --items data/gold_items.parquet --out labels/gold_opus.jsonl --backend claude --model opus
  python -I src/llm_label.py --items data/gold_items.parquet --out labels/gold_qwen.jsonl --backend ollama --model qwen3:8b
Resumable: ids already in --out are skipped. Every output row records model + prompt hash.
"""
import argparse, json, os, re, shutil, subprocess, hashlib, time, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

LOCK_PRINT = True


def fmt_item(r, max_chars, show_id=None):
    s = r.snippet if len(r.snippet) <= max_chars else r.snippet[:max_chars] + " …"
    return f"### id={show_id or r.mention_id} | type={r.media_type} | date={str(r.date)} | source={r.domain} | lang={r.lang}\n{s}"


def parse_array(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
    m = re.search(r"\[.*\]", txt, flags=re.S)
    if not m:
        raise ValueError("no JSON array in output: " + txt[:200])
    return json.loads(m.group(0))


def call_claude(system, user, model, effort=None):
    # full path from shutil.which: also finds claude.exe / claude.cmd on Windows
    cmd = [shutil.which("claude") or "claude", "-p", user, "--model", model, "--output-format", "json", "--tools", "",
           "--strict-mcp-config", "--system-prompt", system, "--disable-slash-commands",
           "--setting-sources", "", "--no-session-persistence"]
    if effort:
        cmd += ["--effort", effort]
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # never bill an API key
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=env,
                       cwd=os.environ.get("LABEL_CWD", "/tmp"))
    d = json.loads(p.stdout)
    if d.get("is_error"):
        raise RuntimeError(d.get("result", "")[:300])
    return d["result"], d.get("usage", {})


def call_ollama(system, user, model):
    body = json.dumps({"model": model, "stream": False, "think": False,
                       "options": {"temperature": 0, "num_ctx": 16384, "seed": 7},
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        d = json.load(r)
    return d["message"]["content"], {"eval_count": d.get("eval_count"), "total_s": d.get("total_duration", 0) / 1e9}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend", default="claude", choices=["claude", "ollama"])
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--prompt", default="prompts/codebook_v1.md")
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max_chars", type=int, default=1100)
    ap.add_argument("--effort", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--short_ids", action="store_true", help="number items 1..n in the prompt (small local models mangle ids like 123,456)")
    a = ap.parse_args()

    system = open(a.prompt, encoding="utf-8").read()
    phash = hashlib.sha1(system.encode()).hexdigest()[:8]
    items = pd.read_parquet(a.items)
    done = set()
    if os.path.exists(a.out):
        for line in open(a.out, encoding="utf-8"):
            try:
                done.add(str(json.loads(line)["id"]))
            except Exception:
                pass
    todo = items[~items.mention_id.astype(str).isin(done)]
    if a.limit:
        todo = todo.head(a.limit)
    batches = [todo.iloc[i:i + a.batch] for i in range(0, len(todo), a.batch)]
    print(f"{len(done)} done, {len(todo)} to label in {len(batches)} batches ({a.backend}:{a.model}, prompt {phash})", flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

    def run(b):
        shown = [str(k + 1) for k in range(len(b))] if a.short_ids else [str(x) for x in b.mention_id]
        user = "Label these items:\n\n" + "\n\n".join(fmt_item(r, a.max_chars, sid) for r, sid in zip(b.itertuples(), shown))
        real = dict(zip(shown, [str(x) for x in b.mention_id]))
        want = shown
        for attempt in range(3):
            t = time.time()
            try:
                if a.backend == "claude":
                    txt, usage = call_claude(system, user, a.model, a.effort)
                else:
                    txt, usage = call_ollama(system, user, a.model)
                arr = parse_array(txt)
                got = {str(o.get("id")): o for o in arr if isinstance(o, dict)}
                missing = [i for i in want if i not in got]
                if len(missing) > len(want) // 4:
                    raise ValueError(f"{len(missing)} ids missing")
                rows = []
                for i in want:
                    if i in got:
                        o = dict(got[i]); o["id"] = real[i]
                        o["_model"] = f"{a.backend}:{a.model}"; o["_prompt"] = phash; o["_secs"] = round(time.time() - t, 1)
                        rows.append(o)
                return rows, usage, None
            except Exception as e:
                err = repr(e)[:300]
                time.sleep(3 * (attempt + 1))
        return [], {}, err

    n_ok = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex, open(a.out, "a", encoding="utf-8") as f:
        futs = [ex.submit(run, b) for b in batches]
        for k, fu in enumerate(as_completed(futs), 1):
            rows, usage, err = fu.result()
            for o in rows:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
            f.flush()
            n_ok += len(rows)
            print(f"[{k}/{len(batches)}] +{len(rows)} labelled {'ERR ' + err if err else ''}", flush=True)
    print("done, labelled", n_ok)


if __name__ == "__main__":
    main()
