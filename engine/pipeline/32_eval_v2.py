"""Step 32 (CityPulse v2): benchmark, calibration, second-stage check, leakage audit, and the app's matcher artefacts.

Run from the lab directory after step 31 and after the Hamburg training (27) has written out/citypulse/v2/*_ft_mdeberta2_s*.csv.
Everything fitted here (combiner, thresholds, cut-offs, the second-stage band) is fitted on CAL (queries Jan-Jun 2026).
TEST (queries Jul-Oct 2026) is only scored. TRAIN queries end 2025-12-31.

Writes out/citypulse/eval_v2.json, leakage_audit.json, v2/eval_errors.csv and out/citypulse/app/{matcher.json,pair_scores.parquet,family_frozen.parquet}.
"""
import json, os, glob, sys
import numpy as np, pandas as pd
from scipy.stats import binom
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import precision_recall_fscore_support as prf, average_precision_score, roc_auc_score, f1_score, cohen_kappa_score

OUT = "out/citypulse"; V2 = f"{OUT}/v2"; APP = f"{OUT}/app"; os.makedirs(APP, exist_ok=True)
REF = sys.argv[1] if len(sys.argv) > 1 else "opus"       # opus | sonnet | human : what TEST is scored against
rng = np.random.default_rng(11)
TAG = os.environ.get("CITYPULSE_FT_TAG", "mdeberta2")   # mdeberta2 = Hamburg CUDA run (3 seeds), mdeberta2mps = local Apple MPS reproduction (1 seed)
C = pd.read_parquet(f"{OUT}/claims.parquet").set_index("cid")
A = pd.read_parquet(f"{V2}/pairs_labelled.parquet").rename(columns={"label": "opus"})


def labels(files):
    d = {}
    for f in files:
        if os.path.exists(f"{OUT}/{f}.jsonl"):
            for l in open(f"{OUT}/{f}.jsonl"):
                o = json.loads(l); d[o["pid"]] = o["label"]
    return d


A["sonnet"] = A.pid.map(labels(["pairlabels_sonnet", "pairlabels_v2_sonnet"]))
A["qwen27"] = A.pid.map(labels(["pairlabels_qwen27", "pairlabels_v2_qwen27"]))
A["haiku"] = A.pid.map(labels(["pairlabels_v2_haiku"]))
if os.path.exists(f"{OUT}/human_labels.csv"):
    A["human"] = A.pid.map(pd.read_csv(f"{OUT}/human_labels.csv").drop_duplicates("pid", keep="last").set_index("pid").label)
seeds = sorted(int(f.split("_s")[-1][:-4]) for f in glob.glob(f"{V2}/eval_ft_{TAG}_s*.csv"))
assert seeds, "no fine-tuned scores found: run step 27 on the GPU box first"
for s in seeds:
    d = pd.read_csv(f"{V2}/eval_ft_{TAG}_s{s}.csv").set_index("pid")
    for l in ["same", "related", "opposing"]:
        A[f"s{s}_{l}"] = A.pid.map(d[f"ft_{TAG}_{l}"])
for l in ["same", "related", "opposing"]:
    A[f"ens_{l}"] = A[[f"s{s}_{l}" for s in seeds]].mean(axis=1)


def meta(P):
    qp, cp = P.qid.map(C.polarity).values, P.cand.map(C.polarity).values
    return pd.DataFrame(dict(cos=P.cos.values, same_pol=(qp == cp).astype(float),
                             flip_pol=(np.isin(qp, ["pro", "contra"]) & np.isin(cp, ["pro", "contra"]) & (qp != cp)).astype(float),
                             same_topic=(P.qid.map(C.topic).values == P.cand.map(C.topic).values).astype(float),
                             same_proj=P.same_project.values.astype(float)), index=P.index)


M = meta(A)
for c in M:
    A[c] = M[c]
META = list(M.columns)
E = A[(A.split != "train") & A.s0_same.notna()].copy()
E["y"] = np.where(E.split == "cal", E.opus == "same", E[REF] == "same").astype(int)
E = E[(E.split == "cal") | E[REF].notna()]
E10 = E[E.side_rank <= 10]                                   # the product looks at 10 candidates per side
cal, test = E10[E10.split == "cal"], E10[E10.split == "test"]
if REF == "human":   # every human-labelled pair counts: whether two claims are the same argument does not depend on the candidate's rank
    test = E[E.split == "test"]
res = dict(reference=REF, seeds=seeds, n_cal_pairs=len(cal), n_test_pairs=len(test), n_cal_queries=cal.qid.nunique(), n_test_queries=test.qid.nunique(),
           test_same_rate=float(test.y.mean()), train_queries_until="2025-12-31", cal_queries="2026-01-01..2026-06-30", test_queries="2026-07-01..")
d = test[test.sonnet.notna()]
res["annotator_agreement_test"] = dict(n=len(d), kappa_same=cohen_kappa_score(d.opus == "same", d.sonnet == "same"), kappa_4way=cohen_kappa_score(d.opus, d.sonnet))
print(f"reference={REF} | CAL {len(cal)} pairs / {cal.qid.nunique()} queries | TEST {len(test)} pairs / {test.qid.nunique()} queries ({test.y.mean():.1%} same)")
print("annotator agreement on TEST (Opus vs Sonnet):", {k: round(v, 3) for k, v in res["annotator_agreement_test"].items()})


def fit(cols):
    sc = StandardScaler().fit(cal[cols]); lr = LogisticRegression(C=1.0, max_iter=3000, class_weight="balanced").fit(sc.transform(cal[cols]), cal.y)
    f = lambda X: lr.predict_proba(sc.transform(X[cols]))[:, 1]
    cfg = dict(cols=cols, mean=sc.mean_.tolist(), scale=sc.scale_.tolist(), coef=lr.coef_[0].tolist(), intercept=float(lr.intercept_[0]))
    return f, cfg


def best_thr(score, y):
    cands = np.unique(np.round(score, 3))
    return float(cands[int(np.argmax([f1_score(y, score >= t, zero_division=0) for t in cands]))])


def boot(yt, pred, groups, base=None, B=1000):
    ug = np.unique(groups); idx = {g: np.flatnonzero(groups == g) for g in ug}; f, dl = [], []
    for _ in range(B):
        ii = np.concatenate([idx[g] for g in rng.choice(ug, len(ug))])
        f.append(f1_score(yt[ii], pred[ii], zero_division=0))
        if base is not None:
            dl.append(f[-1] - f1_score(yt[ii], base[ii], zero_division=0))
    o = dict(f1_lo=float(np.percentile(f, 2.5)), f1_hi=float(np.percentile(f, 97.5)))
    if base is not None:
        o.update(gain_lo=float(np.percentile(dl, 2.5)), gain_hi=float(np.percentile(dl, 97.5)))
    return o


FEATS = {"cosine (baseline)": ["cos"], "cosine + topic/polarity": META,
         "fine-tuned matcher, text only (one model)": ["s0_same", "s0_related", "s0_opposing"],
         "fine-tuned matcher + topic/polarity (one model) = PRODUCT": META + ["s0_same", "s0_related", "s0_opposing"],
         f"fine-tuned + topic/polarity, average of {len(seeds)} training runs": META + ["ens_same", "ens_related", "ens_opposing"]}
PROD, TEXT = "fine-tuned matcher + topic/polarity (one model) = PRODUCT", "fine-tuned matcher, text only (one model)"
yt, groups = test.y.values, test.qid.values
rows, score, thr, cfgs, pred = [], {}, {}, {}, {}
for name, cols in FEATS.items():
    f, cfgs[name] = fit(cols)
    score[name] = dict(cal=f(cal), test=f(test)); thr[name] = best_thr(score[name]["cal"], cal.y.values)
    pred[name] = (score[name]["test"] >= thr[name]).astype(int)
    p, r, f1, _ = prf(yt, pred[name], average="binary", zero_division=0)
    rows.append(dict(method=name, precision=p, recall=r, f1=f1, ap=average_precision_score(yt, score[name]["test"]), auroc=roc_auc_score(yt, score[name]["test"]), thr=thr[name]))
base = pred["cosine (baseline)"]
# single training runs, text only (spread over seeds)
res["seed_f1_text_only"] = []
for s in seeds:
    cols = [f"s{s}_same", f"s{s}_related", f"s{s}_opposing"]; f, _ = fit(cols)
    res["seed_f1_text_only"].append(round(float(f1_score(yt, f(test) >= best_thr(f(cal), cal.y.values))), 3))
# LLM judges and the two-stage check: the fast model decides clear cases, an LLM re-reads only the uncertain band
for j in ["sonnet", "qwen27", "haiku"]:
    if j in test and j != REF and test[j].notna().all():
        pj = (test[j] == "same").astype(int).values
        p, r, f1, _ = prf(yt, pj, average="binary", zero_division=0)
        rows.append(dict(method=f"LLM as judge on every pair: {j}", precision=p, recall=r, f1=f1, ap=None, auroc=None, thr=None)); pred[rows[-1]["method"]] = pj
bands = {}
for j in ["haiku", "qwen27"]:
    cj = cal[cal[j].notna()] if j in cal else cal.head(0)
    if len(cj) < 300 or not test[j].notna().all():
        continue
    sc_c = pd.Series(score[PROD]["cal"], index=cal.index)[cj.index].values
    best = (0, None)
    for lo in [0.02, 0.05, 0.1, 0.2, 0.3]:
        for hi in [thr[PROD], 0.9, 0.95, 0.98]:
            if hi <= lo: continue
            in_band = (sc_c >= lo) & (sc_c < hi)
            if in_band.mean() > 0.25: continue                 # at most a quarter of the pairs may go to the LLM
            pc = np.where(in_band, cj[j] == "same", sc_c >= hi).astype(int)
            f = f1_score(cj.y, pc)
            if f > best[0]: best = (f, (lo, hi))
    if best[1] is None:                                     # no band keeps the LLM share <= 25% and helps on CAL
        bands[j] = dict(skipped="every candidate band sends more than 25% of CAL pairs to the LLM", n_cal=len(cj)); continue
    lo, hi = best[1]; st = score[PROD]["test"]; in_band = (st >= lo) & (st < hi)
    pc = np.where(in_band, test[j] == "same", st >= hi).astype(int)
    p, r, f1, _ = prf(yt, pc, average="binary", zero_division=0)
    name = f"two-stage: PRODUCT, then {j} re-reads the uncertain band"
    rows.append(dict(method=name, precision=p, recall=r, f1=f1, ap=None, auroc=None, thr=None, band=[lo, hi], share_sent_to_llm=float(in_band.mean()), cal_f1=best[0]))
    pred[name] = pc; bands[j] = dict(lo=lo, hi=hi, share_sent_to_llm_test=float(in_band.mean()))
for r_ in rows:
    r_.update(boot(yt, pred[r_["method"]], groups, None if r_["method"].startswith("cosine (") else base))
T = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 70)
print("\n== SAME ARGUMENT? TEST pairs, 10 candidates per side ==")
print(T[["method", "precision", "recall", "f1", "f1_lo", "f1_hi", "ap", "gain_lo", "gain_hi"]].round(3).to_string(index=False))
print("single training runs, text only, F1:", res["seed_f1_text_only"])
res["pair_matching_test"] = T.to_dict("records")
res["selected_method"], res["baseline_method"], res["version"] = PROD, "cosine (baseline)", "citypulse-matcher-v2"
# comparable with v1: only the 5 nearest per side
t5 = test[test.side_rank <= 5]
res["product_f1_depth5"] = float(f1_score(t5.y, pd.Series(pred[PROD], index=test.index)[t5.index]))
res["baseline_f1_depth5"] = float(f1_score(t5.y, pd.Series(base, index=test.index)[t5.index]))
print(f"depth 5 only (comparable with v1): product F1 {res['product_f1_depth5']:.3f}, baseline {res['baseline_f1_depth5']:.3f}")

if REF == "human":   # human labels cover a reviewed sample of TEST pairs only: the pair table is valid, the claim-level tables are not
    json.dump(res, open(f"{OUT}/eval_v2_human.json", "w"), indent=1, default=float)
    print("\nwrote", f"{OUT}/eval_v2_human.json", "(pair table only)")
    raise SystemExit(0)

# ---------- related tier: "at least related" (same or related) ----------
relc, relt = cal.opus.isin(["same", "related"]).astype(int), test[REF].isin(["same", "related"]).astype(int)
pr_c, pr_t = (cal.s0_same + cal.s0_related).values, (test.s0_same + test.s0_related).values
cand = np.unique(np.round(pr_c, 2)); ok = [t for t in cand if prf(relc, pr_c >= t, average="binary", zero_division=0)[0] >= 0.90]
thr_rel = float(min(ok)) if ok else 0.9
p, r, f1, _ = prf(relt, pr_t >= thr_rel, average="binary", zero_division=0)
res["related_tier"] = dict(threshold=thr_rel, rule="lowest cut-off with precision >= 0.90 on CAL", test_precision=p, test_recall=r, test_f1=f1, n=len(test), base_rate=float(relt.mean()))
print(f"\n== RELATED TIER (same or related vs unrelated): cut-off {thr_rel:.2f} -> TEST precision {p:.3f}, recall {r:.3f} (base rate {relt.mean():.2f})")

# ---------- novelty: does a new claim have no equivalent among its older candidates? ----------
def claim_level(df, s, k, project_only):
    d = df.assign(s=s)
    d = d[d.side_rank <= k]
    truth = df[df.side_rank <= 10]                               # ground truth always uses all 10 labelled candidates per side
    if project_only:
        d, truth = d[d.same_project], truth[truth.same_project]
    return pd.DataFrame(dict(novel=(truth.groupby("qid").y.max() == 0).astype(int), match=d.groupby("qid").s.max())).fillna({"match": 0.0})


print("\n== NEW CLAIM? TEST claims; truth = no equivalent among the 10+10 older candidates (reference labels) ==")
nov, cuts = [], {}
for scope, po in (("within the same project", True), ("anywhere", False)):
    for name in ["cosine (baseline)", PROD]:
        for k in (5, 10):
            cl, te = claim_level(cal, score[name]["cal"], k, po), claim_level(test, score[name]["test"], k, po)
            fam, novs = np.sort(cl.match[cl.novel == 0].values), np.sort(cl.match[cl.novel == 1].values)
            kq = int(np.floor(0.10 * (len(fam) + 1))); tau = float(fam[max(kq - 1, 0)])
            flag = (te.match < tau).astype(int)
            p, r, f1, _ = prf(te.novel, flag, average="binary", zero_division=0)
            nfam = int((te.novel == 0).sum()); nfa = int(flag[te.novel == 0].sum())
            nov.append(dict(scope=scope, method=name, depth=k, n=len(te), n_novel=int(te.novel.sum()), precision=p, recall=r, f1=f1,
                            auroc=roc_auc_score(te.novel, -te.match), familiar_flagged=nfa, n_familiar=nfam, familiar_flag_rate=nfa / max(nfam, 1),
                            p_at_least_this_many_if_true_rate_10pct=float(binom.sf(nfa - 1, nfam, 0.10)), tau=tau))
            if name == PROD and k == 10:
                # three states: "new" only below the 5% quantile of familiar claims; "familiar" only above the 90% quantile of novel claims
                t_new = float(fam[max(int(np.floor(0.05 * (len(fam) + 1))) - 1, 0)])
                t_fam = float(novs[min(int(np.ceil(0.90 * (len(novs) + 1))) - 1, len(novs) - 1)])
                if t_fam <= t_new:
                    t_fam = t_new = tau
                st = np.where(te.match >= t_fam, "familiar", np.where(te.match < t_new, "new", "ambiguous"))
                tab = pd.crosstab(pd.Series(st, name="state"), te.novel.map({1: "truly_new", 0: "truly_familiar"}).values).to_dict()
                cuts[scope] = dict(single_cut_10pct=tau, new=t_new, familiar=t_fam, test_states_by_truth=tab,
                                   new_precision=float(((st == "new") & (te.novel == 1)).sum() / max((st == "new").sum(), 1)),
                                   familiar_precision=float(((st == "familiar") & (te.novel == 0)).sum() / max((st == "familiar").sum(), 1)),
                                   share_ambiguous=float((st == "ambiguous").mean()))
N = pd.DataFrame(nov)
print(N[["scope", "method", "depth", "n", "n_novel", "precision", "recall", "f1", "auroc", "familiar_flagged", "n_familiar", "familiar_flag_rate", "p_at_least_this_many_if_true_rate_10pct"]].round(3).to_string(index=False))
for sc_, c_ in cuts.items():
    print(f"three states ({sc_}): new < {c_['new']:.3f} <= ambiguous < {c_['familiar']:.3f} <= familiar | 'new' is right {c_['new_precision']:.0%}, 'familiar' is right {c_['familiar_precision']:.0%}, ambiguous share {c_['share_ambiguous']:.0%} | {c_['test_states_by_truth']}")
res["novelty_test"] = N.to_dict("records"); res["novelty_three_states"] = cuts

# ---------- leakage audit ----------
norm = lambda s: " ".join("".join(ch for ch in s.lower() if ch.isalnum() or ch == " ").split())
tr = A[A.split == "train"]
train_file = pd.read_csv(f"{V2}/train.csv")
tk = lambda P: set(" || ".join(sorted((norm(a), norm(b)))) for a, b in zip(P.q_claim, P.c_claim))
tr_texts = set(map(norm, train_file.q_claim)) | set(map(norm, train_file.c_claim))
test_q_seen = test.q_claim.map(norm).isin(tr_texts)
ident = test.q_claim.map(norm) == test.c_claim.map(norm)
strict = test[~test_q_seen & ~ident]
aud = dict(
    candidates_older_than_query_all_pairs=bool((A.c_date < A.q_date).all()),
    query_sets_disjoint=bool(not (set(tr.qid) & set(E.qid)) and not (set(cal.qid) & set(test.qid))),
    train_newest_query=str(tr.q_date.max().date()), cal_oldest_query=str(cal.q_date.min().date()), cal_newest_query=str(cal.q_date.max().date()), test_oldest_query=str(test.q_date.min().date()),
    time_order_train_cal_test=bool(tr.q_date.max() < cal.q_date.min() and cal.q_date.max() < test.q_date.min()),
    train_pairs_removed_same_text_pair_as_eval=int(len(tr) - len(train_file)),
    text_pair_overlap_train_file_vs_eval=int(len(tk(train_file) & tk(E))),
    test_pairs_identical_text=int(ident.sum()), test_pairs_whose_query_text_occurs_in_training=int(test_q_seen.sum()),
    test_queries_whose_text_occurs_in_training=int(test[test_q_seen].qid.nunique()),
    product_f1_all_test=float(f1_score(yt, pred[PROD])),
    product_f1_strict_subset=float(f1_score(strict.y, pd.Series(pred[PROD], index=test.index)[strict.index])) if len(strict) else None,
    baseline_f1_strict_subset=float(f1_score(strict.y, pd.Series(base, index=test.index)[strict.index])) if len(strict) else None,
    strict_subset_pairs=int(len(strict)),
    fitted_on_cal_only=["combiner weights", "pair threshold", "related threshold", "novelty cut-offs", "second-stage band"],
    epoch_selection="DEV = 12% of TRAIN queries", test_used_for="scoring only",
    known_soft_spots=["The replay period (Jul-Oct 2026, Heilbronn) was looked at by hand while the grouping and voice rules were designed in v1; those rules have no fitted parameters but were not chosen blind.",
                      "bge-m3 and the base mDeBERTa were pre-trained by others on data of unknown date; claim extraction by Haiku reads one post at a time.",
                      "Reference labels are from Opus, the same model family that produced the training labels."])
assert aud["candidates_older_than_query_all_pairs"] and aud["query_sets_disjoint"] and aud["time_order_train_cal_test"] and aud["text_pair_overlap_train_file_vs_eval"] == 0
print("\n== LEAKAGE AUDIT ==")
for k_, v_ in aud.items():
    if not isinstance(v_, list): print(f"  {k_}: {v_ if not isinstance(v_, float) else round(v_, 3)}")

# ---------- artefacts for the application ----------
I = pd.read_parquet(f"{V2}/index_pairs.parquet")
si = pd.read_csv(f"{V2}/index_ft_{TAG}_s0.csv").set_index("pid")
for l in ["same", "related", "opposing"]:
    I[f"s0_{l}"] = I.pid.map(si[f"ft_{TAG}_{l}"])
MI = meta(I)
for c in MI:
    I[c] = MI[c]
fprod, cfg_meta = fit(FEATS[PROD]); ftext, cfg_text = fit(FEATS[TEXT])
I["p_same"], I["p_rel"], I["ft_same"] = fprod(I), (I.s0_same + I.s0_related).values, I.s0_same
I["score_source"], I["model_version"] = "cached", "citypulse-matcher-v2"
I[["pid", "qid", "cand", "same_project", "side_rank", "cos", "p_same", "p_rel", "ft_same", "score_source", "model_version"]].to_parquet(f"{APP}/pair_scores.parquet", index=False)
tcl, tte = claim_level(cal, score[TEXT]["cal"], 10, True), claim_level(test, score[TEXT]["test"], 10, True)
fam_t, nov_t = np.sort(tcl.match[tcl.novel == 0].values), np.sort(tcl.match[tcl.novel == 1].values)
text_new = float(fam_t[max(int(np.floor(0.05 * (len(fam_t) + 1))) - 1, 0)]); text_fam = float(nov_t[min(int(np.ceil(0.90 * (len(nov_t) + 1))) - 1, len(nov_t) - 1)])
if text_fam <= text_new: text_fam = text_new
cp = cuts["within the same project"]
prow = T[T.method == PROD].iloc[0]; brow = T[T.method == "cosine (baseline)"].iloc[0]
nprod = N[(N.method == PROD) & (N.depth == 10) & (N.scope == "within the same project")].iloc[0]
matcher_cfg = dict(
    version="citypulse-matcher-v2", base_model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli (MIT)", labels=["same", "related", "opposing", "unrelated"],
    trained_on="Opus-labelled claim pairs, queries published before 2026-01-01", calibrated_on="queries 2026-01-01..2026-06-30", tested_on="queries from 2026-07-01",
    combiner_meta=cfg_meta, combiner_text=cfg_text,
    thresholds=dict(pair_same=thr[PROD], text_pair_same=thr[TEXT], related=thr_rel, familiar=cp["familiar"], new=cp["new"], text_familiar=text_fam, text_new=text_new),
    second_stage_band=bands, contradiction_detection="disabled",
    metrics=dict(provisional=True, note="agreement with AI reference labels (Opus), not human-validated", reference=REF,
                 pair_f1=float(prow.f1), pair_precision=float(prow.precision), pair_recall=float(prow.recall), pair_f1_interval=[float(prow.f1_lo), float(prow.f1_hi)],
                 baseline_pair_f1=float(brow.f1), n_test_pairs=len(test), n_test_claims=int(nprod.n),
                 novelty_f1=float(nprod.f1), novelty_precision=float(nprod.precision), novelty_recall=float(nprod.recall),
                 familiar_claims_wrongly_flagged=f"{int(nprod.familiar_flagged)} of {int(nprod.n_familiar)}"))
json.dump(matcher_cfg, open(f"{APP}/matcher.json", "w"), indent=1)
res["thresholds"] = matcher_cfg["thresholds"]; res["second_stage_band"] = bands
# the hospital concern as a fixed regression example (was under-grouped in v1)
h = I[I.q_claim.str.contains("hospital|clinic|medical care", case=False) & I.same_project & I.qid.map(C.project).eq("heilbronn_cablecar") & (I.qid.map(C.date) >= pd.Timestamp("2026-07-01"))]
h = h.sort_values("p_same", ascending=False).drop_duplicates("qid")
res["hospital_example"] = [dict(q=r.q_claim, best_older=r.c_claim, p_same=round(float(r.p_same), 3), p_rel=round(float(r.p_rel), 3)) for r in h.itertuples()]
print("\n== hospital example (best older Heilbronn match per claim) ==")
for x in res["hospital_example"]: print("  ", x)
# frozen argument families for the replay: the argument map refitted on claims before 2026-07-01 only
try:
    from umap import UMAP
    from hdbscan import HDBSCAN
    Cr = pd.read_parquet(f"{OUT}/claims.parquet"); Em = np.load(f"{OUT}/claims_emb.npy")
    old = (Cr.date < pd.Timestamp("2026-07-01")).values
    lab = HDBSCAN(min_cluster_size=8, min_samples=3).fit_predict(UMAP(n_neighbors=15, n_components=8, min_dist=0.0, metric="cosine", random_state=42).fit_transform(Em[old]))
    Cr["family_frozen"] = Cr.cid
    Cr.loc[old, "family_frozen"] = [f"ff{l}" if l >= 0 else c for l, c in zip(lab, Cr.cid[old])]
    names = {}
    for f_, g in Cr[old & Cr.family_frozen.str.startswith("ff")].groupby("family_frozen"):
        ix = g.index.values; names[f_] = g.claim.iloc[int(np.argmax(Em[ix] @ Em[ix].mean(0)))]
    Cr["family_frozen_name"] = [names.get(f_, cl) for f_, cl in zip(Cr.family_frozen, Cr.claim)]
    Cr[["cid", "family_frozen", "family_frozen_name"]].to_parquet(f"{APP}/family_frozen.parquet", index=False)
except Exception as e:
    print("frozen families skipped:", repr(e)[:200])
Eo = test.assign(p_same=score[PROD]["test"], pred=pred[PROD], base=base)
Eo[(Eo.pred != Eo.y) | (Eo.base != Eo.y)][["qid", "cand", "q_project", "c_project", "q_claim", "c_claim", REF, "cos", "p_same", "pred", "base"]].to_csv(f"{V2}/eval_errors.csv", index=False)
json.dump(res, open(f"{OUT}/eval_v2{'' if REF == 'opus' else '_' + REF}.json", "w"), indent=1, default=float)
if REF == "opus":
    json.dump(aud, open(f"{OUT}/leakage_audit.json", "w"), indent=1, default=float)
print("\nwrote", f"{OUT}/eval_v2.json", f"{APP}/matcher.json", f"{APP}/pair_scores.parquet", len(I))
