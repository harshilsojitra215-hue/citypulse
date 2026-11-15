"""Embeddings via local Ollama (bge-m3, multilingual, 1024-d). Cached per text hash in data/emb_cache/."""
import json, hashlib, os, urllib.request, numpy as np

CACHE = "data/emb_cache"


def _post(texts, model):
    body = json.dumps({"model": model, "input": texts, "truncate": True}).encode()
    req = urllib.request.Request(os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/embed", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["embeddings"]


def embed(texts, model="bge-m3", batch=32, max_chars=2000):
    os.makedirs(CACHE, exist_ok=True)
    keys = [hashlib.md5((model + t[:max_chars]).encode()).hexdigest() for t in texts]
    out = [None] * len(texts)
    todo = []
    for i, k in enumerate(keys):
        p = f"{CACHE}/{k}.npy"
        if os.path.exists(p):
            out[i] = np.load(p)
        else:
            todo.append(i)
    for s in range(0, len(todo), batch):
        idx = todo[s:s + batch]
        vecs = _post([texts[i][:max_chars] for i in idx], model)
        for i, v in zip(idx, vecs):
            v = np.asarray(v, dtype=np.float32)
            v /= (np.linalg.norm(v) + 1e-9)
            np.save(f"{CACHE}/{keys[i]}.npy", v)
            out[i] = v
    return np.vstack(out)
