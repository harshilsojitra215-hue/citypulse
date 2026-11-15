"""Step 23 (CityPulse): benchmark argument matchers and the novelty detector on the historical replay set.

Everything that is fitted (thresholds, logistic combiners, the conformal novelty cut-off) is fitted on CAL
(queries dated before 2026-07-01) and measured on TEST (queries from 2026-07-01 on). Nothing from TEST is seen earlier.

python -I src/23_match_eval.py  ->  out/citypulse/eval_results.json, eval_errors.csv, matcher.joblib
Reference labels: Opus (annotator A). Sonnet (annotator B) gives the agreement ceiling. If
out/citypulse/human_labels.csv exists (pid,label), the same tables are also computed against the human labels.
"""
import json, os, sys, time
import numpy as np, pandas as pd, joblib
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (precision_recall_fscore_support as prf, average_precision_score, roc_auc_score,
                             f1_score, cohen_kappa_score)

OUT = "out/citypulse"
rng = np.random.default_rng(11)
P = pd.read_parquet(f"{OUT}/pairs.parquet")
Q = pd.read_parquet(f"{OUT}/queries.parquet").set_index("qid")
C = pd.read_parquet(f"{OUT}/claims.parquet").set_index("cid")


def load(name):
    f = f"{OUT}/pairlabels_{name}.jsonl"
    if not os.path.exists(f):
        return None
    return pd.DataFrame([json.loads(l) for l in open(f)]).drop_duplicates("pid").set_index("pid").label


for name in ["opus", "sonnet", "qwen27", "haiku"]:  # qwen27 = local Qwen 3.8 27B on Hamburg
    s = load(name)
    if s is not None:
        P[name] = P.pid.map(s)
if os.path.exists(f"{OUT}/human_labels.csv"):
    P["human"] = P.pid.map(pd.read_csv(f"{OUT}/human_labels.csv").drop_duplicates("pid").set_index("pid").label)
REF = sys.argv[1] if len(sys.argv) > 1 else "opus"
# fitting always uses the Opus labels on CAL; REF only decides what TEST is scored against (opus | sonnet | human)
P = P[P.opus.notna() & ((P.split == "cal") | P[REF].notna())].reset_index(drop=True)
P["y"] = np.where(P.split == "cal", P.opus == "same", P[REF] == "same").astype(int)
P["ref4"] = np.where(P.split == "cal", P.opus, P[REF])

sys.path.insert(0, "pipeline")
from citypulse_feats import add_features, LABELS
P, feats, seeds = add_features(P, C, "pairs")

cal, test = P[P.split == "cal"], P[P.split == "test"]
print(f"reference={REF}  cal pairs {len(cal)} ({cal.y.mean():.1%} same)  test pairs {len(test)} ({test.y.mean():.1%} same)")
res = {"reference": REF, "n_cal_pairs": len(cal), "n_test_pairs": len(test), "test_same_rate": float(test.y.mean())}
if "sonnet" in P and REF != "sonnet":
    d = P[P.sonnet.notna() & P[REF].notna()]
    res["annotator_agreement"] = dict(n=len(d), kappa_4way=cohen_kappa_score(d[REF], d.sonnet),
                                      kappa_same=cohen_kappa_score(d[REF] == "same", d.sonnet == "same"),
                                      raw=float((d[REF] == d.sonnet).mean()))
    print("annotator agreement", {k: round(v, 3) for k, v in res["annotator_agreement"].items()})


def best_thr(score, y):
    cands = np.unique(np.round(score, 4))
    f = [f1_score(y, score >= t, zero_division=0) for t in cands]
    return float(cands[int(np.argmax(f))])


def boot_f1(yt, pred, groups, base=None, B=1000):
    """cluster bootstrap over queries: 95% CI of F1, and of the F1 gain over the baseline prediction"""
    ug = np.unique(groups)
    idx = {g: np.flatnonzero(groups == g) for g in ug}
    f, dlt = [], []
    for _ in range(B):
        ii = np.concatenate([idx[g] for g in rng.choice(ug, len(ug))])
        f.append(f1_score(yt[ii], pred[ii], zero_division=0))
        if base is not None:
            dlt.append(f[-1] - f1_score(yt[ii], base[ii], zero_division=0))
    out = dict(f1_lo=float(np.percentile(f, 2.5)), f1_hi=float(np.percentile(f, 97.5)))
    if base is not None:
        out.update(gain_lo=float(np.percentile(dlt, 2.5)), gain_hi=float(np.percentile(dlt, 97.5)), p_gain_le0=float(np.mean(np.array(dlt) <= 0)))
    return out


yt, groups = test.y.values, test.qid.values
table, models, score_test, score_cal, pred_test = [], {}, {}, {}, {}
for name, cols in feats.items():
    m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced")).fit(cal[cols], cal.y)
    sc, st = m.predict_proba(cal[cols])[:, 1], m.predict_proba(test[cols])[:, 1]
    thr = best_thr(sc, cal.y.values)
    pred = (st >= thr).astype(int)
    p, r, f, _ = prf(yt, pred, average="binary", zero_division=0)
    # 4-way: same features, multinomial
    m4 = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=3000, class_weight="balanced")).fit(cal[cols], cal.ref4)
    mf1 = f1_score(test.ref4, m4.predict(test[cols]), average="macro")
    row = dict(method=name, precision=p, recall=r, f1=f, ap=average_precision_score(yt, st), auroc=roc_auc_score(yt, st), macro_f1_4way=mf1, thr=thr)
    # model selection signal that never touches TEST: out-of-fold F1 on CAL, folds split by query
    oof = np.zeros(len(cal))
    for tr_i, te_i in GroupKFold(5).split(cal, cal.y, cal.qid):
        mm = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced")).fit(cal.iloc[tr_i][cols], cal.y.iloc[tr_i])
        oof[te_i] = mm.predict_proba(cal.iloc[te_i][cols])[:, 1]
    row["cal_cv_f1"] = f1_score(cal.y, oof >= best_thr(oof, cal.y.values))
    tag = name.split(" ")[1] if name.startswith("fine-tuned") and name.endswith("(ours)") and "+ meta" not in name else None
    if tag:  # the model's own 4-way decision, no fitting on CAL at all; plus the spread over training seeds
        own = np.array(LABELS)[test[[f"ft_{tag}_{l}" for l in LABELS]].values.argmax(1)]
        row["macro_f1_4way"] = f1_score(test.ref4, own, average="macro")
        row["per_class_f1"] = dict(zip(LABELS, f1_score(test.ref4, own, average=None, labels=LABELS, zero_division=0).round(3)))
        fs = []
        for sd in seeds[tag]:
            cs, ts_ = cal[f"ft_{tag}_s{sd}_same"].values, test[f"ft_{tag}_s{sd}_same"].values
            fs.append(f1_score(yt, ts_ >= best_thr(cs, cal.y.values)))
        row["seed_f1s"] = [round(float(x), 3) for x in fs]
    models[name], score_test[name], score_cal[name], pred_test[name] = (m, cols, thr), st, sc, pred
    table.append(row)
base_pred = pred_test["cosine (current baseline)"]
for row in table:
    row.update(boot_f1(yt, pred_test[row["method"]], groups, None if row["method"].startswith("cosine (") else base_pred))
# LLM judges: no threshold, the label is the decision
for j in ("sonnet", "qwen27", "haiku"):
    if j in P and j != REF and test[j].notna().all() and REF != j:
        pred = (test[j] == "same").astype(int).values
        p, r, f, _ = prf(yt, pred, average="binary", zero_division=0)
        row = dict(method=f"LLM judge: {j}", precision=p, recall=r, f1=f, ap=None, auroc=None,
                   macro_f1_4way=f1_score(test.ref4, test[j], average="macro"), thr=None)
        row.update(boot_f1(yt, pred, groups, base_pred))
        pred_test[row["method"]] = pred
        table.append(row)
T = pd.DataFrame(table)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
print("\n== PAIR MATCHING on TEST (is the candidate the SAME argument?) ==")
print(T[["method", "cal_cv_f1", "precision", "recall", "f1", "f1_lo", "f1_hi", "ap", "auroc", "macro_f1_4way", "gain_lo", "gain_hi"]].round(3).to_string(index=False))
for r_ in table:
    if r_.get("seed_f1s"): print("  seeds", r_["method"], r_["seed_f1s"], "| 4-way per class", r_["per_class_f1"])
res["pair_matching_test"] = T.to_dict("records")
res["label_counts_test"] = test.ref4.value_counts().to_dict()

# ---------- novelty: does a new claim have NO equivalent in history? ----------
def claim_level(df, score, project_only):
    d = df.assign(s=score)
    if project_only:
        d = d[d.same_project]
    g = d.groupby("qid")
    return pd.DataFrame(dict(novel=(g.y.max() == 0).astype(int), match=g.s.max()))


print("\n== NOVELTY on TEST claims (novel = annotator found no equivalent among the historical candidates) ==")
nov_rows = []
ALPHA = 0.10
for scope, po in (("anywhere (all projects)", False), ("within the same project", True)):
    for name in feats:
        cl, te = claim_level(cal, score_cal[name], po), claim_level(test, score_test[name], po)
        fam = np.sort(cl.match[cl.novel == 0].values)
        # split-conformal cut-off: at most ALPHA of familiar claims fall below it (finite-sample corrected)
        k = int(np.floor(ALPHA * (len(fam) + 1)))
        tau = float(fam[max(k - 1, 0)]) if k >= 1 else -np.inf
        flag = (te.match < tau).astype(int)
        p, r, f, _ = prf(te.novel, flag, average="binary", zero_division=0)
        nov_rows.append(dict(scope=scope, method=name, n=len(te), n_novel=int(te.novel.sum()), precision=p, recall=r, f1=f,
                             auroc=roc_auc_score(te.novel, -te.match), ap=average_precision_score(te.novel, -te.match),
                             familiar_wrongly_flagged=float(flag[te.novel == 0].mean()), target=ALPHA, tau=tau))
# the old pipeline as a novelty detector: UMAP + HDBSCAN fitted on the frozen history, a new claim that lands in no cluster = new
try:
    from umap import UMAP
    from hdbscan import HDBSCAN, approximate_predict
    Call = pd.read_parquet(f"{OUT}/claims.parquet"); Emb = np.load(f"{OUT}/claims_emb.npy")
    old = (Call.date < pd.Timestamp("2026-07-01")).values
    um = UMAP(n_neighbors=15, n_components=8, min_dist=0.0, metric="cosine", random_state=42).fit(Emb[old])
    hd = HDBSCAN(min_cluster_size=8, min_samples=3, prediction_data=True).fit(um.embedding_)
    te = claim_level(test, score_test["cosine (current baseline)"], False)
    pos = Call.reset_index().set_index("cid")["index"].loc[te.index].values
    lab, strength = approximate_predict(hd, um.transform(Emb[pos]))
    flag = (lab == -1).astype(int)
    p, r, f, _ = prf(te.novel, flag, average="binary", zero_division=0)
    nov_rows.insert(0, dict(scope="anywhere (all projects)", method="HDBSCAN clusters on frozen history (old pipeline): no cluster = new", n=len(te), n_novel=int(te.novel.sum()),
                            precision=p, recall=r, f1=f, auroc=roc_auc_score(te.novel, -strength), ap=average_precision_score(te.novel, -strength),
                            familiar_wrongly_flagged=float(flag[te.novel == 0].mean()), target=None, tau=None))
except Exception as e:
    print("hdbscan baseline skipped:", repr(e)[:200])
N = pd.DataFrame(nov_rows)
print(N.drop(columns=["tau", "target"]).round(3).to_string(index=False))
res["novelty_test"] = N.to_dict("records")
# how often is an equivalent found only outside the cosine top-5 (retrieval miss estimate)
top = P[P.cos_rank <= 5].groupby("qid").y.max()
deep = P[P.cos_rank > 5].groupby("qid").y.max()
both = pd.concat([top, deep], axis=1, keys=["top", "deep"]).dropna()
res["retrieval_depth_check"] = dict(n_queries=len(both), found_only_beyond_top5=int(((both.top == 0) & (both.deep == 1)).sum()))
print("retrieval depth check:", res["retrieval_depth_check"])

best = T[T.ap.notna()].sort_values("cal_cv_f1", ascending=False).iloc[0].method   # chosen on CAL only
res["selected_method"] = best
m, cols, thr = models[best]
tau = {r["scope"]: r["tau"] for r in nov_rows if r["method"] == best}
joblib.dump(dict(model=m, cols=cols, thr=thr, name=best, tau_any=tau["anywhere (all projects)"], tau_project=tau["within the same project"]), f"{OUT}/matcher.joblib")
E = test.assign(p_same=score_test[best], pred=pred_test[best], base=base_pred)
E[(E.pred != E.y) | (E.base != E.y)][["qid", "cand", "q_project", "c_project", "q_claim", "c_claim", REF, "cos", "p_same", "pred", "base"]].to_csv(f"{OUT}/eval_errors.csv", index=False)
json.dump(res, open(f"{OUT}/eval_results{'' if REF == 'opus' else '_' + REF}.json", "w"), indent=1, default=float)
print("\nselected on CAL (out-of-fold F1):", best, "| errors ->", f"{OUT}/eval_errors.csv")
