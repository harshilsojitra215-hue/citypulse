"""Score the AI labels against the stored human labels.

    python -m citypulse.review.evaluate                 # everything, including the pair benchmark (takes a few minutes)
    python -m citypulse.review.evaluate --no-benchmark  # fast part only
    python -m citypulse.review.evaluate --labeller harshil

Prints a summary and writes review/results/latest.json. With no human labels it says so and reports no metric.
Nothing here changes a model label or a pipeline output: the pair benchmark (pipeline/32_eval_v2.py human)
runs in a temporary copy of the lab folder, so its side outputs do not overwrite the lab's own files.
"""
import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from itertools import combinations
from pathlib import Path

from . import config, queues, store

NO_LABELS = "no human labels yet"
PAIR_MODELS = ["opus", "sonnet", "qwen27", "haiku"]
MIN_PAIRS_FOR_BENCHMARK = 30
BENCHMARK_OUTPUTS = ("eval_results", "eval_errors.csv", "matcher.joblib", "human_labels.csv", "eval_v2", "leakage_audit")   # never linked: the script writes them
BENCHMARK_NOTES = [
    "The 120 pairs are not a random sample: half were picked because the AI annotators disagreed. "
    "Scores on them are lower than on a random sample and are not comparable with the Opus-reference table.",
    "Only the pair-matching table is used from the benchmark. Its novelty tables are not valid against human "
    "labels, because only some candidates of each query were labelled.",
]
# pipeline/23_match_eval.py (as handed over) stops in "human" mode: it computes the human-vs-Sonnet agreement over
# all pairs, but human labels exist for reviewed TEST pairs only. The pipeline file is not ours to edit, so when the
# unmodified script fails on this, the benchmark is run once more from a temporary copy with this one line changed.
KNOWN_BUG = "d = P[P.sonnet.notna()]"
KNOWN_BUG_FIX = "d = P[P.sonnet.notna() & P[REF].notna()]"
KNOWN_BUG_NOTE = ("pipeline/23_match_eval.py stopped with an error in 'human' mode. The numbers come from a temporary copy "
                  "with one line changed (human-vs-Sonnet agreement limited to pairs that have a human label). "
                  "The file in pipeline/ is unchanged; the same one-line fix should be made there.")


# ---------------------------------------------------------------- small statistics (no fake numbers: None when undefined)
def agreement(a, b):
    n = len(a)
    return round(sum(x == y for x, y in zip(a, b)) / n, 4) if n else None


def kappa(a, b):
    """Cohen's kappa of two label lists. None when it is undefined (no items, or both sides use one single label)."""
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if pe >= 1.0:
        return None
    return round((po - pe) / (1 - pe), 4)


def _clean(o):
    """NaN / inf -> None, numpy scalars -> plain values, so the JSON is strict."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        try:
            o = o.item()
        except (ValueError, AttributeError):
            return str(o)
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def _key(queue, label):
    """The part of a label two labellers must agree on."""
    return tuple(label.get(k) for k in queues.LABEL_KEYS[queue] if k != "correct_date")


def consensus(queue, cur, item_ids, labeller=None):
    """One human label per item. One labeller: their label. Several: the majority; a tie is a conflict and the
    item is left out (reported, never guessed). Returns (labels, conflicts, who)."""
    per_item = {}
    for (l, i), r in cur.items():
        if i in item_ids and (labeller is None or l == labeller):
            per_item.setdefault(i, []).append(r)
    labels, conflicts, who = {}, [], {}
    for i, recs in per_item.items():
        votes = Counter(_key(queue, r["label"]) for r in recs)
        top = votes.most_common(2)
        if len(top) > 1 and top[0][1] == top[1][1]:
            conflicts.append(i)
            continue
        win = next(r for r in recs if _key(queue, r["label"]) == top[0][0])
        labels[i] = win["label"]
        who[i] = "+".join(sorted(r["labeller"] for r in recs if _key(queue, r["label"]) == top[0][0]))
    return labels, sorted(conflicts), who


def inter_labeller(queue, cur, item_ids):
    """Pairwise agreement between labellers on the items both have done."""
    by = {}
    for (l, i), r in cur.items():
        if i in item_ids:
            by.setdefault(l, {})[i] = r["label"]
    out = []
    for a, b in combinations(sorted(by), 2):
        both = sorted(set(by[a]) & set(by[b]))
        if not both:
            continue
        row = {"a": a, "b": b, "n": len(both)}
        for k in queues.LABEL_KEYS[queue]:
            if k in ("correct_date", "project"):
                continue
            ii = [i for i in both if by[a][i].get(k) is not None and by[b][i].get(k) is not None]
            xa, xb = [by[a][i][k] for i in ii], [by[b][i][k] for i in ii]
            row[k] = {"n": len(ii), "agreement": agreement(xa, xb), "kappa": kappa(xa, xb)}
        out.append(row)
    return out


def _base(queue, labeller):
    """Shared start of every section. Returns (section, Queue|None, current annotations)."""
    sec = {"status": NO_LABELS, "n_items": 0, "n_labelled": 0}
    cur = store.current(queue)
    try:
        q = queues.load(queue)
    except queues.QueueUnavailable as e:
        sec["queue_file"] = f"missing ({e})"
        if cur:
            sec["status"] = "queue file missing: cannot evaluate"
            sec["n_stored_labels"] = len(cur)
        return sec, None, cur
    sec["n_items"] = len(q)
    return sec, q, cur


def _finish(sec, queue, q, cur, labels, conflicts, labeller):
    ids = set(q.ids)
    sec["n_labelled"] = len(labels)
    sec["complete"] = len(labels) == len(q)
    sec["labellers"] = sorted({l for (l, i) in cur if i in ids and (labeller is None or l == labeller)})
    if conflicts:
        sec["n_conflicts"] = len(conflicts)
        sec["conflicts"] = conflicts[:50]
        sec["conflict_note"] = "labellers disagree with no majority on these items; they are left out until resolved"
    il = inter_labeller(queue, cur, ids)
    if il:
        sec["inter_labeller"] = il
    if labels or conflicts:
        sec["status"] = "ok"
    return sec


# ---------------------------------------------------------------- pairs
def load_model_pair_labels():
    """{model: {pid: label}} from the lab's pairlabels_<model>.jsonl files (read only)."""
    out = {}
    for m in PAIR_MODELS:
        f = config.lab_out() / f"pairlabels_{m}.jsonl"
        if not f.exists():
            continue
        d = {}
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                d.setdefault(r.get("pid"), r.get("label"))  # first line per pid wins, as in the benchmark
        out[m] = d
    return out


def write_human_pairs_csv(labels, who, order):
    """pid,label,labeller: the file pipeline/23_match_eval.py reads. Written to review/results/ (always) and to
    <lab>/out/citypulse/human_labels.csv (when the lab folder exists)."""
    rows = [(p, labels[p]["relation"], who.get(p, "")) for p in order if p in labels]
    written = []
    targets = [config.results_dir() / "human_labels.csv"]
    if config.lab_out().is_dir():
        targets.append(config.lab_out() / "human_labels.csv")
    for f in targets:
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["pid", "label", "labeller"])
            w.writerows(rows)
        written.append(str(f))
    return written


def run_benchmark(human_csv: Path, timeout=1800):
    """Run `python -I pipeline/23_match_eval.py human` in a temporary shadow of the lab folder.
    The shadow links the lab's input files and leaves out the files the script writes, so the lab is not changed."""
    lab_out = config.lab_out()
    script = config.REPO / "pipeline" / "32_eval_v2.py"   # the benchmark of the product matcher (v2)
    if not lab_out.is_dir():
        return {"status": "skipped", "message": f"lab folder not found: {lab_out} (set CITYPULSE_LAB)"}
    if not script.exists():
        return {"status": "skipped", "message": f"benchmark script not found: {script}"}
    tmp = Path(tempfile.mkdtemp(prefix="citypulse_bench_"))
    try:
        out = tmp / "out" / "citypulse"
        out.mkdir(parents=True)
        def link(src, dst):
            """Symlink where allowed; plain copy where not (Windows without Developer Mode). Read-only inputs either way."""
            try:
                os.symlink(src.resolve(), dst, target_is_directory=src.is_dir())
            except OSError:
                (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
        for f in lab_out.iterdir():
            if f.is_file() and not f.name.startswith(BENCHMARK_OUTPUTS):
                link(f, out / f.name)
            elif f.is_dir() and f.name == "v2":      # training / evaluation pair files and model scores (read only)
                link(f, out / f.name)
        shutil.copy(human_csv, out / "human_labels.csv")
        (tmp / "pipeline").mkdir()
        for f in script.parent.glob("*.py"):
            if f.name != script.name:
                link(f, tmp / "pipeline" / f.name)
        run_script = tmp / "pipeline" / script.name
        cmd = [sys.executable, "-I", "pipeline/32_eval_v2.py", "human"]
        res_file = out / "eval_v2_human.json"
        source = script.read_text(encoding="utf-8")
        attempts = [("pipeline/23_match_eval.py (unmodified)", source)]
        if KNOWN_BUG in source:
            attempts.append((KNOWN_BUG_NOTE, source.replace(KNOWN_BUG, KNOWN_BUG_FIX)))
        first_error, used, p = None, None, None
        for used, text in attempts:
            run_script.write_text(text, encoding="utf-8")
            try:
                p = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                return {"status": "failed", "message": f"benchmark did not finish within {timeout} seconds"}
            if p.returncode == 0 and res_file.exists():
                break
            if first_error is None:
                first_error = [l for l in p.stderr.splitlines() if l.strip()][-3:]
        if p.returncode != 0 or not res_file.exists():
            errs = [l for l in p.stderr.splitlines() if l.strip()][-6:]
            return {"status": "failed", "message": "benchmark script stopped with an error; no benchmark numbers reported",
                    "stderr_tail": errs, "stdout_tail": [l for l in p.stdout.splitlines() if l.strip()][-40:]}
        raw = _clean(json.loads(res_file.read_text(encoding="utf-8")))
        config.results_dir().mkdir(parents=True, exist_ok=True)
        (config.results_dir() / "eval_results_human.json").write_text(json.dumps(raw, indent=1), encoding="utf-8")
        keep = ("method", "precision", "recall", "f1", "f1_lo", "f1_hi", "ap", "auroc", "share_sent_to_llm")
        methods = [{k: (round(r[k], 4) if isinstance(r.get(k), float) else r.get(k)) for k in keep}
                   for r in raw.get("pair_matching_test", [])]
        notes = list(BENCHMARK_NOTES)
        if used != attempts[0][0]:
            notes.append(used)
        return {"status": "ok", "generated_at": store.now(), "reference": "human",
                "command": "python -I pipeline/32_eval_v2.py human", "script": used,
                "unmodified_script_error": first_error,
                "n_test_pairs": raw.get("n_test_pairs"), "test_same_rate": raw.get("test_same_rate"),
                "label_counts_test": raw.get("label_counts_test"), "selected_method": next((r["method"] for r in raw.get("pair_matching_test", []) if "PRODUCT" in r["method"] and "two-stage" not in r["method"]), None),
                "selected": next((m for m in methods if "PRODUCT" in m["method"] and "two-stage" not in m["method"]), None),
                "methods": methods, "human_vs_sonnet": raw.get("annotator_agreement_test"),
                "full_result_file": str(config.results_dir() / "eval_results_human.json"), "notes": notes}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def eval_pairs(labeller=None, benchmark=None, previous=None, min_pairs=MIN_PAIRS_FOR_BENCHMARK):
    sec, q, cur = _base("pairs", labeller)
    if q is None:
        return sec
    labels, conflicts, who = consensus("pairs", cur, set(q.ids), labeller)
    _finish(sec, "pairs", q, cur, labels, conflicts, labeller)
    stale = config.lab_out() / "human_labels.csv"
    if not labels:
        if stale.exists():
            sec["warning"] = f"{stale} exists but the annotation store has no pair labels; that file is not from this store"
        return sec
    human = {p: l["relation"] for p, l in labels.items()}
    sec["label_counts"] = {k: sum(v == k for v in human.values()) for k in queues.RELATIONS}
    sec["human_labels_csv"] = write_human_pairs_csv(labels, who, q.ids)
    models = load_model_pair_labels()
    if not models:
        sec["human_vs_model"] = []
        sec["model_labels"] = f"unavailable: no pairlabels_*.jsonl in {config.lab_out()} (set CITYPULSE_LAB)"
    else:
        rows = []
        for m, ml in models.items():
            ids = [p for p in q.ids if p in human and ml.get(p) in queues.RELATIONS]
            h, a = [human[p] for p in ids], [ml[p] for p in ids]
            rows.append({"model": m, "n": len(ids), "agreement": agreement(h, a), "kappa_4way": kappa(h, a),
                         "kappa_same": kappa([x == "same" for x in h], [x == "same" for x in a])})
        sec["human_vs_model"] = rows
        if "opus" in models:
            by = []
            for why in sorted({q.rows[p].get("why") for p in q.ids if q.rows[p].get("why")}):
                ids = [p for p in q.ids if p in human and q.rows[p].get("why") == why and models["opus"].get(p)]
                by.append({"why": why, "n": len(ids),
                           "agreement_with_opus": agreement([human[p] for p in ids], [models["opus"][p] for p in ids])})
            sec["by_why"] = by
    # matcher precision / recall / F1 against the human labels: the benchmark script
    if benchmark:
        if len(labels) < min_pairs:
            sec["benchmark"] = {"status": "skipped",
                                "message": f"only {len(labels)} pairs labelled; the benchmark needs at least {min_pairs}"}
        else:
            sec["benchmark"] = run_benchmark(config.results_dir() / "human_labels.csv")
            if sec["benchmark"].get("status") == "ok":
                sec["benchmark"]["n_labels_at_run"] = len(labels)
    elif previous and previous.get("status") == "ok":
        sec["benchmark"] = dict(previous, carried_over=True,
                                stale=previous.get("n_labels_at_run") != len(labels))
    else:
        sec["benchmark"] = {"status": "not run", "message": "run: python -m citypulse.review.evaluate"}
    return sec


# ---------------------------------------------------------------- stance
def model_stance(s):
    """Model vocabulary -> the four human stance values. 'unclear' is folded into 'mixed' (as in pipeline/06_eval.py);
    'na' and missing have no counterpart and are left out of comparisons."""
    if s == "unclear":
        return "mixed"
    return s if s in queues.STANCES else None


def _vs(name, pairs):
    h, m = [a for a, _ in pairs], [b for _, b in pairs]
    return {"model": name, "n": len(pairs), "accuracy": agreement(h, m), "kappa": kappa(h, m)}


def eval_stance(labeller=None):
    sec, q, cur = _base("stance", labeller)
    if q is None:
        return sec
    labels, conflicts, _ = consensus("stance", cur, set(q.ids), labeller)
    _finish(sec, "stance", q, cur, labels, conflicts, labeller)
    model_counts = Counter(q.rows[i].get("model_stance") for i in q.ids)
    sec["model_stance_counts"] = dict(model_counts)
    if not labels:
        return sec
    sec["about_counts"] = {k: sum(l["about"] == k for l in labels.values()) for k in queues.ABOUT}
    sec["human_stance_counts"] = {k: sum(l.get("stance") == k for l in labels.values()) for k in queues.STANCES}
    # model label vs human label, on posts the human says are about the project (so a stance exists)
    cmp_ids = [i for i in q.ids if i in labels and labels[i].get("stance") and model_stance(q.rows[i].get("model_stance"))]
    rows = [_vs("pipeline label (all sources)", [(labels[i]["stance"], model_stance(q.rows[i]["model_stance"])) for i in cmp_ids])]
    for src in sorted({q.rows[i].get("label_source") for i in q.ids if q.rows[i].get("label_source")}):
        ids = [i for i in cmp_ids if q.rows[i].get("label_source") == src]
        rows.append(_vs(f"pipeline label from {src}", [(labels[i]["stance"], model_stance(q.rows[i]["model_stance"])) for i in ids]))
    try:  # the disputes queue carries one label per model for the posts it shares with this queue
        dq = queues.load("disputes")
        for m in dq.model_names:
            pr = [(labels[i]["stance"], model_stance(dq.rows[i].get(f"{m}_stance"))) for i in dq.ids
                  if i in labels and labels[i].get("stance") and model_stance(dq.rows[i].get(f"{m}_stance"))]
            rows.append(dict(_vs(m, pr), subset="disputed posts only"))
    except queues.QueueUnavailable:
        pass
    sec["model_vs_human"] = rows
    sec["stance_mapping_note"] = "model label 'unclear' is compared as 'mixed'; posts the human marked 'not about' have no stance and are left out"
    # the model said every post in this queue is about the Heilbronn cable car
    n = len(labels)
    sec["relevance"] = {"n": n, "model_said_about": n, "human_confirms_about": sum(l["about"] != "no" for l in labels.values()),
                        "share_confirmed": round(sum(l["about"] != "no" for l in labels.values()) / n, 4)}
    # corrected counts for the Heilbronn posts: human label where reviewed, model label otherwise
    corrected, changed, not_about, passing = Counter(), 0, 0, 0
    for i in q.ids:
        ms = q.rows[i].get("model_stance")
        if i not in labels:
            corrected[ms] += 1
            continue
        l = labels[i]
        if l["about"] == "no":
            not_about += 1
            continue
        passing += l["about"] == "passing"
        corrected[l["stance"]] += 1
        changed += l["stance"] != model_stance(ms)
    sided = corrected["support"] + corrected["oppose"]
    sec["stance_counts"] = {
        "model": dict(model_counts), "corrected": dict(corrected), "n_reviewed": n, "n_unreviewed": len(q) - n,
        "n_changed": changed, "n_not_about": not_about, "n_passing": passing,
        "opposition_share_of_sided": {"value": round(corrected["oppose"] / sided, 4) if sided else None, "n": sided},
        "note": "corrected = human label where reviewed, model label otherwise; posts marked 'not about' are removed"}
    return sec


# ---------------------------------------------------------------- events
def eval_events(labeller=None):
    sec, q, cur = _base("events", labeller)
    if q is None:
        return sec
    labels, conflicts, who = consensus("events", cur, set(q.ids), labeller)
    _finish(sec, "events", q, cur, labels, conflicts, labeller)
    if not labels:
        return sec
    sec["verdict_counts"] = {k: sum(l["verdict"] == k for l in labels.values()) for k in queues.VERDICTS}
    prev = {}
    for i, l in labels.items():
        prev.setdefault(str(q.rows[i].get("verified")), Counter())[l["verdict"]] += 1
    sec["by_previous_verified_flag"] = {k: dict(v) for k, v in sorted(prev.items())}
    notes = {i: r.get("note", "") for (l, i), r in cur.items() if i in labels and l in who.get(i, "").split("+")}
    sec["to_fix"] = [{"item_id": i, "date": q.rows[i].get("date"), "project": q.rows[i].get("project"),
                      "verdict": labels[i]["verdict"], "correct_date": labels[i].get("correct_date"),
                      "note": notes.get(i, "")}
                     for i in q.ids if i in labels and labels[i]["verdict"] != "confirmed"]
    return sec


# ---------------------------------------------------------------- disputes
def eval_disputes(labeller=None):
    sec, q, cur = _base("disputes", labeller)
    if q is None:
        return sec
    labels, conflicts, _ = consensus("disputes", cur, set(q.ids), labeller)
    _finish(sec, "disputes", q, cur, labels, conflicts, labeller)
    if not labels:
        return sec
    sec["about_counts"] = {k: sum(l["about"] == k for l in labels.values()) for k in queues.ABOUT}
    sec["stance_counts"] = {k: sum(l.get("stance") == k for l in labels.values()) for k in queues.STANCES}
    rows = []
    for m in q.model_names:
        st = [(labels[i]["stance"], model_stance(q.rows[i].get(f"{m}_stance"))) for i in q.ids
              if i in labels and labels[i].get("stance") and model_stance(q.rows[i].get(f"{m}_stance"))]
        ab = [(labels[i]["about"] != "no", q.rows[i].get(f"{m}_project") == queues.TARGET_PROJECT) for i in q.ids
              if i in labels and q.rows[i].get(f"{m}_project")]
        rows.append({"model": m, "n_stance": len(st), "stance_agreement": agreement([a for a, _ in st], [b for _, b in st]),
                     "n_about": len(ab), "about_agreement": agreement([a for a, _ in ab], [b for _, b in ab])})
    sec["human_sided_with"] = rows
    sec["n_no_model_had_the_stance"] = sum(
        1 for i in q.ids if i in labels and labels[i].get("stance")
        and all(model_stance(q.rows[i].get(f"{m}_stance")) != labels[i]["stance"] for m in q.model_names))
    return sec


# ---------------------------------------------------------------- all together
def evaluate(run_benchmark=True, labeller=None, write=True, min_pairs=MIN_PAIRS_FOR_BENCHMARK):
    """Compute every section. Returns the result dict and (by default) writes review/results/latest.json."""
    latest = config.results_dir() / "latest.json"
    previous = None
    if latest.exists():
        try:
            previous = json.loads(latest.read_text(encoding="utf-8")).get("pairs", {}).get("benchmark")
        except (json.JSONDecodeError, AttributeError):
            previous = None
    if labeller:
        labeller = store.normalise_labeller(labeller)
    res = {"generated_at": store.now(), "provisional": True, "labeller_filter": labeller,
           "pairs": eval_pairs(labeller, run_benchmark, previous, min_pairs), "stance": eval_stance(labeller),
           "events": eval_events(labeller), "disputes": eval_disputes(labeller)}
    res["n_labelled_total"] = sum(res[k]["n_labelled"] for k in queues.ORDER)
    res["n_annotations"] = sum(len(store.current(k)) for k in queues.ORDER)
    res["labellers"] = sorted({l for k in queues.ORDER for l in store.labellers(k)})
    res["complete"] = all(res[k].get("complete") for k in queues.ORDER)
    if res["n_labelled_total"] == 0 and res["n_annotations"] == 0:
        res["message"] = NO_LABELS
    elif not res["complete"]:
        res["message"] = "human review in progress; numbers below cover the labelled items only"
    else:
        res["message"] = "all four queues are fully labelled"
    res["provisional_note"] = ("Every accuracy number elsewhere in CityPulse is agreement with AI labels. "
                               "Only the numbers in this file compare against human labels, and only for the items labelled so far.")
    res = _clean(res)
    if write:
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(json.dumps(res, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return res


def _f(x, pct=False):
    if x is None:
        return "n/a"
    return f"{x:.1%}" if pct else f"{x:.3f}"


def render(res) -> str:
    """Plain-text summary for the terminal."""
    L = [f"CityPulse human verification   {res['generated_at']}"]
    if res.get("labeller_filter"):
        L.append(f"labeller filter: {res['labeller_filter']}")
    L.append(f"status: {res['message']}   labellers: {', '.join(res['labellers']) or 'none'}")
    L.append("")
    for name in queues.ORDER:
        s = res[name]
        L.append(f"== {name}: {s['n_labelled']} of {s['n_items']} labelled  [{s['status']}]")
        if s.get("queue_file"):
            L.append(f"   queue file {s['queue_file']}")
        if s.get("warning"):
            L.append(f"   warning: {s['warning']}")
        if s.get("n_conflicts"):
            L.append(f"   {s['n_conflicts']} items left out: labellers disagree with no majority")
        if s["status"] != "ok" or not s["n_labelled"]:
            continue
        if name == "pairs":
            L.append(f"   human labels: {s['label_counts']}")
            for r in s.get("human_vs_model", []):
                L.append(f"   human vs {r['model']:7s} n={r['n']:3d}  agreement {_f(r['agreement'], True)}  "
                         f"kappa (4 labels) {_f(r['kappa_4way'])}  kappa (same or not) {_f(r['kappa_same'])}")
            if s.get("model_labels"):
                L.append(f"   model labels {s['model_labels']}")
            for r in s.get("by_why", []):
                L.append(f"   pairs picked as '{r['why']}': n={r['n']}  agreement with opus {_f(r['agreement_with_opus'], True)}")
            b = s.get("benchmark", {})
            if b.get("status") == "ok":
                L.append(f"   matcher benchmark against human labels (n={b['n_test_pairs']} pairs"
                         f"{', carried over from ' + b['generated_at'] if b.get('carried_over') else ''}"
                         f"{', STALE: labels changed since' if b.get('stale') else ''}):")
                for m in b["methods"]:
                    star = "*" if m["method"] == b.get("selected_method") else " "
                    L.append(f"    {star} {m['method'][:44]:44s} precision {_f(m['precision'])}  recall {_f(m['recall'])}  "
                             f"F1 {_f(m['f1'])} [{_f(m.get('f1_lo'))}, {_f(m.get('f1_hi'))}]")
                L.append("     (* = the matcher selected on the calibration data)")
                for n_ in b.get("notes", []):
                    L.append(f"     note: {n_}")
            else:
                L.append(f"   matcher benchmark: {b.get('status')}: {b.get('message', '')}")
                for l in b.get("stderr_tail", []):
                    L.append(f"     {l}")
        elif name == "stance":
            L.append(f"   about the Heilbronn cable car: {s['about_counts']}")
            for r in s["model_vs_human"]:
                sub = f"  ({r['subset']})" if r.get("subset") else ""
                L.append(f"   {r['model']:30s} n={r['n']:3d}  accuracy {_f(r['accuracy'], True)}  kappa {_f(r['kappa'])}{sub}")
            c = s["stance_counts"]
            L.append(f"   Heilbronn stance counts, model:     {c['model']}")
            L.append(f"   Heilbronn stance counts, corrected: {c['corrected']}  "
                     f"(reviewed {c['n_reviewed']}, changed {c['n_changed']}, not about {c['n_not_about']}, passing {c['n_passing']})")
        elif name == "events":
            L.append(f"   verdicts: {s['verdict_counts']}")
            for t in s["to_fix"]:
                L.append(f"   fix event {t['item_id']} ({t['date']}): {t['verdict']}"
                         f"{' -> ' + t['correct_date'] if t.get('correct_date') else ''}  {t['note']}")
        elif name == "disputes":
            L.append(f"   adjudicated about: {s['about_counts']}   stance: {s['stance_counts']}")
            for r in s["human_sided_with"]:
                L.append(f"   human agrees with {r['model']:7s} stance {_f(r['stance_agreement'], True)} (n={r['n_stance']})  "
                         f"about {_f(r['about_agreement'], True)} (n={r['n_about']})")
        for r in s.get("inter_labeller", []):
            parts = [f"{k} agreement {_f(v['agreement'], True)} kappa {_f(v['kappa'])} (n={v['n']})"
                     for k, v in r.items() if isinstance(v, dict)]
            L.append(f"   labellers {r['a']} vs {r['b']}: " + "; ".join(parts))
    L.append("")
    L.append(res["provisional_note"])
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Score the AI labels against the stored human labels.")
    ap.add_argument("--no-benchmark", action="store_true", help="skip pipeline/23_match_eval.py (fast)")
    ap.add_argument("--labeller", default=None, help="use only this labeller's labels")
    ap.add_argument("--min-pairs", type=int, default=MIN_PAIRS_FOR_BENCHMARK,
                    help="smallest number of labelled pairs for which the benchmark is run")
    a = ap.parse_args(argv)
    res = evaluate(run_benchmark=not a.no_benchmark, labeller=a.labeller, min_pairs=a.min_pairs)
    print(render(res))
    print(f"\nwritten: {config.results_dir() / 'latest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
