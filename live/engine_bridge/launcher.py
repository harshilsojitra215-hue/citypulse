"""Start, warm, check and stop everything CityPulse needs on this laptop, in the background.

    python -I -X utf8 live/engine_bridge/launcher.py start    # START_CITYPULSE.cmd
    python -I -X utf8 live/engine_bridge/launcher.py status
    python -I -X utf8 live/engine_bridge/launcher.py stop     # STOP_CITYPULSE.cmd

What runs (each hidden, logs in _run/logs/, process ids in _run/pids.json):
  1. Ollama with bge-m3 (port 11434), kept in memory (OLLAMA_KEEP_ALIVE=-1): embeds new claims on the GPU
  2. the argument engine API (port 8000): the team's FastAPI, with the fine-tuned matcher loaded once
  3. the engine's analyst console (port 3000): Next.js in production mode
  4. the CityPulse website (port 8790): app/serve.py, also runs "Update now"
"Warm" means every screen the demo opens has been asked once, so the engine's replay and concern answers sit in its
cache (first call 10 s, then under 0.5 s). Memory: maths libraries use 4 threads, not 16, so the engine stays near
1.5 GB; the model on the GPU leaves system memory free. Nothing here sends data anywhere except the engine's
labelling calls for new items (OpenRouter, capped), which only happen on "Update now".
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import envload  # noqa: E402

ROOT = HERE.parents[1]
ENGINE = ROOT / "engine"
VENV_PY = ENGINE / ".venv" / "Scripts" / "python.exe"
RUN = ROOT / "_run"
LOGS = RUN / "logs"
PIDS = RUN / "pids.json"
NO_WINDOW = 0x08000000
OLLAMA = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
SYS_PY = sys.executable

SERVICES = {
    "ollama": {"port": 11434, "probe": "http://127.0.0.1:11434/api/tags"},
    "engine_api": {"port": 8000, "probe": "http://127.0.0.1:8000/api/health"},
    "engine_web": {"port": 3000, "probe": "http://127.0.0.1:3000/"},
    "website": {"port": 8790, "probe": "http://127.0.0.1:8790/"},
}
WARM = [  # every engine answer the website and the demo use
    "http://127.0.0.1:8000/api/health", "http://127.0.0.1:8000/api/meta",
    "http://127.0.0.1:8000/api/overview?project=heilbronn_cablecar", "http://127.0.0.1:8000/api/overview",
    "http://127.0.0.1:8000/api/replay?project=heilbronn_cablecar&cutoff=2026-07-01",
    "http://127.0.0.1:8000/api/replay?cutoff=2026-07-01",
    "http://127.0.0.1:8000/api/emerging?project=heilbronn_cablecar&cutoff=2026-07-01",
    "http://127.0.0.1:8000/api/emerging?cutoff=2026-07-01", "http://127.0.0.1:8000/api/emerging?project=heilbronn_cablecar",
    "http://127.0.0.1:8000/api/emerging",
    "http://127.0.0.1:8000/api/arguments/families?project=heilbronn_cablecar", "http://127.0.0.1:8000/api/crosscity",
    "http://127.0.0.1:8000/api/trends?project=heilbronn_cablecar", "http://127.0.0.1:8000/api/replay/cutoffs",
    "http://127.0.0.1:3000/", "http://127.0.0.1:3000/replay", "http://127.0.0.1:3000/emerging", "http://127.0.0.1:3000/explorer",
    "http://127.0.0.1:3000/cross-city", "http://127.0.0.1:3000/review", "http://127.0.0.1:3000/new-data",
    "http://127.0.0.1:8790/", "http://127.0.0.1:8790/data/engine.js",
]


def up(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 500
    except Exception:
        return False


def wait_up(url, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        if up(url, timeout=5):
            return True
        time.sleep(1)
    return False


def env_for_engine():
    e = dict(os.environ)
    envload.load(["OPENROUTER_API_KEY"])
    e.update(os.environ)
    e.update({"PYTHONUTF8": "1", "CITYPULSE_DEVICE": "cpu", "CITYPULSE_LLM_BACKEND": "openrouter",
              "CITYPULSE_LLM_MODEL": "anthropic/claude-haiku-5.5", "CITYPULSE_LLM_MAX_USD": "1.0",
              "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4", "OPENBLAS_NUM_THREADS": "4", "TOKENIZERS_PARALLELISM": "false",
              "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    e.pop("ANTHROPIC_API_KEY", None)
    return e


def spawn(name, cmd, cwd, env=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / f"{name}.log", "a", encoding="utf-8")
    log.write(f"\n==== start {time.strftime('%Y-%m-%d %H:%M:%S')} ====\n")
    log.flush()
    p = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         creationflags=NO_WINDOW)
    pids = json.loads(PIDS.read_text()) if PIDS.exists() else {}
    pids[name] = p.pid
    PIDS.write_text(json.dumps(pids))
    return p


def start():
    t0 = time.time()
    RUN.mkdir(exist_ok=True)
    report = {}
    # 1. Ollama (embedder)
    if up(SERVICES["ollama"]["probe"]):
        report["ollama"] = "already running"
    elif OLLAMA.exists():
        app = OLLAMA.with_name("ollama app.exe")   # the tray app starts the server; plain ollama.exe can hand over to it
        spawn("ollama", [str(app if app.exists() else OLLAMA)] + ([] if app.exists() else ["serve"]), ROOT,
              dict(os.environ, OLLAMA_KEEP_ALIVE="-1"))
        report["ollama"] = "started" if wait_up(SERVICES["ollama"]["probe"], 30) else "FAILED (see _run/logs/ollama.log)"
    else:
        report["ollama"] = "not installed: new collector items cannot be matched (history still works)"
    if up(SERVICES["ollama"]["probe"]):
        try:   # load bge-m3 and keep it in memory
            body = json.dumps({"model": "bge-m3", "input": ["Seilbahn Heilbronn"], "keep_alive": -1}).encode()
            urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/embed", data=body,
                                                          headers={"Content-Type": "application/json"}), timeout=120).read()
            report["bge-m3"] = "loaded"
        except Exception as e:
            report["bge-m3"] = f"FAILED {e!r}"
    # 2. engine API
    if up(SERVICES["engine_api"]["probe"]):
        report["engine_api"] = "already running"
    else:
        spawn("engine_api", [str(VENV_PY), "-m", "uvicorn", "citypulse.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
              ENGINE, env_for_engine())
    # 3. engine console
    if up(SERVICES["engine_web"]["probe"]):
        report["engine_web"] = "already running"
    else:
        spawn("engine_web", ["cmd", "/c", "npm", "run", "start", "--", "-H", "127.0.0.1", "-p", "3000"], ENGINE / "web")
    # 4. website
    if up(SERVICES["website"]["probe"]):
        report["website"] = "already running"
    else:
        spawn("website", [SYS_PY, "-I", "-X", "utf8", str(ROOT / "app" / "serve.py")], ROOT, dict(os.environ, PYTHONUTF8="1"))
    for name in ("engine_api", "engine_web", "website"):
        if name not in report:
            report[name] = "started" if wait_up(SERVICES[name]["probe"], 120) else f"FAILED (see _run/logs/{name}.log)"
    # warm every screen
    warm_ok, slow = 0, []
    for u in WARM:
        t = time.time()
        if up(u, timeout=180):
            warm_ok += 1
        if time.time() - t > 2:
            slow.append(f"{u.split('127.0.0.1')[1]} {time.time() - t:.0f}s")
    report["warm"] = f"{warm_ok}/{len(WARM)} answers cached" + (f" (first-time slow: {', '.join(slow)})" if slow else "")
    # fresh engine snapshot for the website
    r = subprocess.run([SYS_PY, "-I", "-X", "utf8", str(HERE / "snapshot.py")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    report["website snapshot"] = (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:]])[-1]
    print_status(report, time.time() - t0)
    return 0 if all("FAILED" not in v for v in report.values()) else 1


def print_status(report=None, secs=None):
    try:
        with urllib.request.urlopen(SERVICES["engine_api"]["probe"], timeout=10) as r:
            h = json.load(r)
        eng = (f"matcher {h['matcher'].get('mode')} ({h['matcher'].get('device')}), embedder {'on' if h['embedder'].get('available') else 'OFF'}, "
               f"labeller {h['llm'].get('backend')} {'on' if h['llm'].get('available') else 'OFF'}, {h['n_claims']} claims, runs {h['runs']}")
    except Exception:
        eng = "engine API not answering"
    print("\nCityPulse on this laptop" + (f" (ready in {secs:.0f}s)" if secs else ""))
    for name, s in SERVICES.items():
        print(f"  {'OK  ' if up(s['probe']) else 'DOWN'} {name:<11} http://127.0.0.1:{s['port']}/")
    print(f"  engine: {eng}")
    for k, v in (report or {}).items():
        print(f"  {k}: {v}")
    print("\n  Website:          http://127.0.0.1:8790/\n  Analyst console:  http://127.0.0.1:3000/emerging\n")


def stop():
    pids = json.loads(PIDS.read_text()) if PIDS.exists() else {}
    for name, pid in pids.items():
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        print(f"stopped {name} (pid {pid})")
    PIDS.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    sys.exit({"start": start, "stop": stop, "status": lambda: print_status() or 0}[cmd]())
