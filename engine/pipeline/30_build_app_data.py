"""Step 30: build the compact data bundle the CityPulse application reads (app_data/).

Run from the lab directory (the one holding data/ and out/):
    cd "$CITYPULSE_LAB" && python -I <repo>/pipeline/30_build_app_data.py <repo>/app_data

The bundle holds only what the app needs: relevant posts with a 400-character excerpt (no author handles, only a
salted hash), claims with embeddings, events, cached matcher scores, thresholds, review queues. It is derived from the
challenge dataset, so it stays out of git (see README "Data").
"""
import sys, os, json, hashlib, shutil
import numpy as np, pandas as pd

DST = sys.argv[1] if len(sys.argv) > 1 else "app_data"
OUT = "out/citypulse"
os.makedirs(f"{DST}/review", exist_ok=True)
PROJECTS = {"heilbronn_cablecar": "Heilbronn", "bonn_cablecar": "Bonn", "paris_c1": "Paris Câble C1",
            "other_urban_cablecar": "Other cities", "ipai": "IPAI campus"}
h6 = lambda s: hashlib.sha1(str(s).encode()).hexdigest()[:6]

# ---------- posts ----------
L = pd.read_parquet("data/labelled.parquet")
L = L[L.project.isin(PROJECTS)].copy()
L["doc_id"] = L.mention_id.astype(str)
L["voice"] = L.author_hash.fillna("dom:" + L.domain.fillna("unknown")).map(h6)
L["excerpt"] = L.text_clean.fillna("").str.slice(0, 400)
L["date"] = pd.to_datetime(L.date).dt.strftime("%Y-%m-%d")
L["week"] = pd.to_datetime(L.week).dt.strftime("%Y-%m-%d")
L["n_claims_labelled"] = L.arguments.map(lambda a: len(a) if a is not None else 0)
L["run_id"] = "base"
posts = L[["doc_id", "published_at", "date", "month", "week", "channel", "media_type", "domain", "source_name", "url", "lang", "title",
           "excerpt", "project", "passing", "stance", "tone", "label_source", "voice", "dup_key", "dup_count", "is_first_copy",
           "tool_sentiment", "run_id"]].copy()
posts["project_name"] = posts.project.map(PROJECTS)

# ---------- claims ----------
C = pd.read_parquet(f"{OUT}/claims.parquet")
E = np.load(f"{OUT}/claims_emb.npy")
ts = L.drop_duplicates("doc_id").set_index("doc_id").published_at
C["doc_id"] = C.id.astype(str)
C["ts"] = C.doc_id.map(ts)
C["voice"] = C.source_key.map(h6)
C["date"] = pd.to_datetime(C.date).dt.strftime("%Y-%m-%d")
K = pd.read_csv("out/argument_clusters.csv").set_index("cluster")
C["family_id"] = [f"fam{c}" if c >= 0 else f"solo:{cid}" for c, cid in zip(C.cluster_all, C.cid)]
C["family_name"] = [K.name.get(c, None) if c >= 0 else cl for c, cl in zip(C.cluster_all, C.claim)]
C["project_name"] = C.project.map(PROJECTS)
C["run_id"] = "base"
# argument families as they were known on 2026-06-30 (refitted on older claims only, step 32): used by the replay
ff = f"{OUT}/app/family_frozen.parquet"
if os.path.exists(ff):
    C = C.merge(pd.read_parquet(ff), on="cid", how="left")
else:
    C["family_frozen"], C["family_frozen_name"] = C.family_id, C.family_name
claims = C[["cid", "doc_id", "claim", "project", "project_name", "date", "ts", "channel", "domain", "url", "topic", "polarity", "stance",
            "voice", "norm", "family_id", "family_name", "family_frozen", "family_frozen_name", "cluster_all", "run_id"]]
posts["n_claims"] = posts.doc_id.map(claims.groupby("doc_id").size()).fillna(0).astype(int)
fam = (claims[claims.cluster_all >= 0].groupby("family_id")
       .agg(name=("family_name", "first"), n=("cid", "size"), main_topic=("topic", lambda s: s.mode().iloc[0]),
            pro=("polarity", lambda s: float((s == "pro").mean())), contra=("polarity", lambda s: float((s == "contra").mean())),
            first_seen=("date", "min"), last_seen=("date", "max")).reset_index())
posts.to_parquet(f"{DST}/posts.parquet", index=False)
claims.to_parquet(f"{DST}/claims.parquet", index=False)
np.save(f"{DST}/claims_emb.npy", E.astype(np.float32))
fam.to_parquet(f"{DST}/families.parquet", index=False)
ev = pd.read_csv("data/events_timeline.csv")
ev.to_parquet(f"{DST}/events.parquet", index=False)

# ---------- cached matcher scores + thresholds (written by step 31 when the model has been run) ----------
for f in ["pair_scores.parquet", "matcher.json", "matcher_combiner.json"]:
    if os.path.exists(f"{OUT}/app/{f}"):
        shutil.copy(f"{OUT}/app/{f}", f"{DST}/{f}")
# once the v2 benchmark exists the app shows only that one (v1 numbers stay in docs/REPORT_exploration.md as history)
EVAL = ["eval_v2.json", "eval_v2_sonnet.json"] if os.path.exists(f"{OUT}/eval_v2.json") else ["eval_results.json", "eval_results_sonnet.json"]
for f in {"eval_v2.json", "eval_v2_sonnet.json", "eval_results.json", "eval_results_sonnet.json"} - set(EVAL):
    if os.path.exists(f"{DST}/{f}"):
        os.remove(f"{DST}/{f}")          # never ship two benchmarks side by side
for f in EVAL + ["leakage_audit.json"]:
    if os.path.exists(f"{OUT}/{f}"):
        shutil.copy(f"{OUT}/{f}", f"{DST}/{f}")

# ---------- review queues ----------
P = pd.read_parquet(f"{OUT}/pairs.parquet").set_index("pid")
rs = pd.read_csv(f"{OUT}/review_sample.csv")
pq = rs.join(P[["q_claim", "q_project", "c_claim", "c_project"]], on="pid")[["pid", "q_claim", "q_project", "c_claim", "c_project", "why"]]
pq.to_parquet(f"{DST}/review/pair_queue.parquet", index=False)
hn = posts[(posts.project == "heilbronn_cablecar") & posts.is_first_copy].sort_values("date")
hn[["doc_id", "date", "channel", "domain", "url", "title", "excerpt"]].assign(
    model_project=hn.project, model_stance=hn.stance, model_tone=hn.tone, label_source=hn.label_source
).to_parquet(f"{DST}/review/stance_queue.parquet", index=False)
G = {}
for m in ["opus", "haiku", "sonnet", "qwen38-27b"]:
    p = f"labels/gold_{m}.jsonl"
    if os.path.exists(p):
        d = pd.DataFrame([json.loads(l) for l in open(p, encoding="utf-8")]).drop_duplicates("id", keep="last").set_index("id")
        G[m.replace("qwen38-27b", "qwen27")] = d[["project", "stance"]]
D = pd.concat(G, axis=1)
D.columns = [f"{m}_{c}" for m, c in D.columns]
D.index = D.index.astype(str)
is_hn = D[[c for c in D if c.endswith("_project")]].eq("heilbronn_cablecar").any(axis=1)
st = D[[c for c in D if c.endswith("_stance")]]
pr = D[[c for c in D if c.endswith("_project")]]
dis = D[is_hn & ((st.nunique(axis=1, dropna=True) > 1) | (pr.nunique(axis=1, dropna=True) > 1))].reset_index(names="doc_id")
base = pd.read_parquet("data/gold_items.parquet", columns=["mention_id", "snippet", "url", "date", "domain"])
base["doc_id"] = base.mention_id.astype(str)
dis = dis.merge(base.drop_duplicates("doc_id")[["doc_id", "snippet", "url", "date", "domain"]], on="doc_id", how="left")
dis["excerpt"] = dis.snippet.fillna("").str.slice(0, 600); dis["date"] = dis.date.astype(str)
dis.drop(columns="snippet").to_parquet(f"{DST}/review/disputes_queue.parquet", index=False)
ev.reset_index(names="event_id").to_parquet(f"{DST}/review/events_queue.parquet", index=False)

meta = dict(data_version=pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%MZ"), projects=PROJECTS,
            n_posts=len(posts), n_claims=len(claims), date_min=posts.date.min(), date_max=posts.date.max(),
            arguments_available_for=["heilbronn_cablecar", "bonn_cablecar", "paris_c1", "other_urban_cablecar"],
            classifier="claude-haiku (codebook_v1); reference sample by claude-opus", embedder="bge-m3 (1024-d, via Ollama)")
json.dump(meta, open(f"{DST}/meta.json", "w"), indent=1)

# ---------- manifest: which model and evaluation this bundle belongs to ----------
import hashlib
def _sha(f):
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 22), b""):
            h.update(ch)
    return h.hexdigest()
_cs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "checksums.txt")
_model_sha = next((l.split()[0] for l in open(_cs) if l.strip().endswith("model.safetensors")), None) if os.path.exists(_cs) else None
_mj = json.load(open(f"{DST}/matcher.json")) if os.path.exists(f"{DST}/matcher.json") else {}
manifest = dict(data_version=meta["data_version"], matcher_version=_mj.get("version"), model_sha256=_model_sha,
                thresholds=_mj.get("thresholds"), evaluation="eval_v2.json" if os.path.exists(f"{DST}/eval_v2.json") else None,
                files={f: _sha(f"{DST}/{f}") for f in sorted(os.listdir(DST)) if os.path.isfile(f"{DST}/{f}") and f != "MANIFEST.json"})
json.dump(manifest, open(f"{DST}/MANIFEST.json", "w"), indent=1)
print("manifest", manifest["matcher_version"], (manifest["model_sha256"] or "no model checksum")[:16])
print("posts", len(posts), posts.project.value_counts().to_dict())
print("claims", len(claims), "families", len(fam), "events", len(ev))
print("review queues: pairs", len(pq), "stance", len(hn), "disputes", len(dis), "events", len(ev))
print("bundle size MB", round(sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(DST) for f in fs) / 1e6, 1))
