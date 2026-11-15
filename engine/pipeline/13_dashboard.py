"""Step 13: build the offline dashboard (one self-contained HTML file).

python -I src/13_dashboard.py  ->  dashboard/cable_car_dashboard.html (simple demo)
                                   + dashboard/cable_car_details.html (method and detail)
Reads data/labelled.parquet, data/events_timeline.csv, out/argument_*.csv, out/peaks_project*.csv,
out/eval_summary.json and inlines them as JSON into dashboard/template.html.

Privacy: no author handles or source names for social posts. Authors are only counted via the salted
author_hash (shortened). @mentions, e-mails and URLs inside excerpts are masked. Links whose URL
contains a handle (Mastodon /@user, X, TikTok, LinkedIn, named Facebook pages, Reddit users) are withheld.
"""
import json, re, hashlib
from urllib.parse import urlparse
import numpy as np, pandas as pd

P = ["heilbronn_cablecar", "bonn_cablecar", "paris_c1", "ipai", "other_urban_cablecar"]
PNAME = {"heilbronn_cablecar": "Heilbronn cable car", "bonn_cablecar": "Bonn cable car",
         "paris_c1": "Paris Câble C1", "ipai": "IPAI Heilbronn", "other_urban_cablecar": "Other urban cable cars"}

df = pd.read_parquet("data/labelled.parquet")
ts = pd.to_datetime(df.published_at).dt.tz_localize(None)
df["d"] = ts.dt.strftime("%Y-%m-%d")
df["wk"] = (ts.dt.normalize() - pd.to_timedelta(ts.dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")

# ---- funnel -------------------------------------------------------------------------------
reviewed = df[df.project != "not_reviewed"]
funnel = {
    "raw": int(len(df)),
    "unique": int(df.is_first_copy.sum()),
    "sent_to_llm": int(reviewed.is_first_copy.sum()),
    "by_project": {k: int(v) for k, v in reviewed[reviewed.is_first_copy].project.value_counts().items()},
}

# ---- claims -> clusters -------------------------------------------------------------------
claims = pd.read_csv("out/argument_claims.csv", dtype={"id": str})
claim_cluster = {(r.id, r.claim): int(r.cluster) for r in claims.itertuples()}
clusters = pd.read_csv("out/argument_clusters.csv")

# ---- posts --------------------------------------------------------------------------------
MASK = [(re.compile(r"https?://\S+"), "[link]"), (re.compile(r"\S+@\S+\.\w+"), "[e-mail]"),
        (re.compile(r"(?<!\w)@[\w.\-]{2,}"), "@…")]
NO_LINK_DOMAINS = ("twitter.com", "x.com", "tiktok.com", "threads.net", "linkedin.com", "bsky.app")


def excerpt(r, n=300):
    s = (r.snippet or r.text_clean or "").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    t = re.sub(r"\s+", " ", r.title or "").strip()
    if r.channel != "social" and t and s.startswith(t):  # title is shown separately
        s = s[len(t):].strip(" -–|")
    for rx, rep in MASK:
        s = rx.sub(rep, s)
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " …"


def safe_link(r):
    u = r.url or ""
    if not u.startswith("http"):
        return ""
    if r.channel != "social":
        return u
    p = urlparse(u)
    host = p.netloc.lower().removeprefix("www.")
    first = p.path.strip("/").split("/")[0] if p.path.strip("/") else ""
    if "@" in u or host.endswith(NO_LINK_DOMAINS) or re.search(r"/(user|u|profile|people|in|channel|c)/", p.path):
        return ""
    if host.endswith("facebook.com") and not first.isdigit():
        return ""
    if host.endswith("youtube.com") and not p.path.startswith("/watch"):
        return ""
    return u


def short_author(h):
    return hashlib.sha1(str(h).encode()).hexdigest()[:6] if isinstance(h, str) and h else ""


rows = []
T = df[df.project.isin(P) & df.is_first_copy].sort_values("published_at")
for r in T.itertuples():
    args = []
    if isinstance(r.arguments, (list, np.ndarray)):
        for a in r.arguments:
            if isinstance(a, dict) and a.get("claim"):
                args.append([a.get("topic") or "other", a.get("polarity") or "neutral", a["claim"],
                             claim_cluster.get((r.id, a["claim"]), -1)])
    rows.append(dict(
        p=P.index(r.project), d=r.d, w=r.wk, ch=r.channel, mt=r.media_type,
        dom=(r.domain or ""), src=("" if r.channel == "social" else (r.source_name or "")),
        u=safe_link(r), st=(r.stance or "na"), pa=bool(r.passing), ts=int(r.tool_sentiment),
        dc=int(r.dup_count), a=short_author(r.author_hash), t=(r.title or "")[:160] if r.channel != "social" else "",
        x=excerpt(r), g=args, ls=r.label_source))

# ---- authors per project (all mentions, incl. copies) -----------------------------------
authors = {p: int(df[(df.project == p) & df.author_hash.notna()].author_hash.nunique()) for p in P}

# ---- events, peaks, eval -------------------------------------------------------------------
ev = pd.read_csv("data/events_timeline.csv").fillna("")
ev["project"] = ev.project.replace({"heilbronn_cablecar": "heilbronn_cablecar"})
events = ev[["date", "project", "event_type", "title_en", "detail", "source_url", "source_name", "verified"]].to_dict("records")

pk = []
for path, mode in [("out/peaks_project_W.csv", "W"), ("out/peaks_project.csv", "D")]:
    x = pd.read_csv(path).fillna("")
    # small projects: weekly peaks; large projects: daily peaks
    keep = ["heilbronn_cablecar", "bonn_cablecar"] if mode == "W" else ["paris_c1", "ipai"]
    x = x[x.project.isin(keep)]
    for q in x.itertuples():
        pk.append(dict(project=q.project, start=str(q.start), top=str(q.top), peak=int(q.peak), mode=mode,
                       wk_before=float(q.wk_before), wk_after=float(q.wk_after), stance=q.stance,
                       headline=q.top_headline, event=q.linked_event))

ev_sum = json.load(open("out/eval_summary.json"))
# Heilbronn-only stance kappa is printed by src/06_eval.py and recorded in REPORT.md section 2.
hb_kappa = {"llm:haiku": 0.78, "llm:sonnet": 0.84, "llm:qwen38-27b": 0.68}

cl = []
for c in clusters.itertuples():
    cl.append(dict(id=int(c.cluster), n=int(c.n), name=c.name, topic=c.main_topic, pro=float(c.pro), contra=float(c.contra),
                   by=[int(getattr(c, p)) if p in clusters.columns else 0 for p in P]))

data = dict(projects=P, pname=PNAME, funnel=funnel, posts=rows, authors=authors, events=events, peaks=pk,
            clusters=cl, n_claims=int(len(claims)), eval=ev_sum, hb_kappa=hb_kappa,
            built=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
            n_unlabelled=int((df.project == "not_reviewed").sum()))

blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
# simple demo dashboard (main) + the detailed one it links to
for tpl_path, out_path in [("dashboard/template_simple.html", "dashboard/cable_car_dashboard.html"),
                           ("dashboard/template.html", "dashboard/cable_car_details.html")]:
    out = open(tpl_path, encoding="utf-8").read().replace("/*__DATA__*/null", blob)
    open(out_path, "w", encoding="utf-8").write(out)
print(f"posts {len(rows)}, clusters {len(cl)}, events {len(events)}, peaks {len(pk)}, size {len(out)/1e6:.2f} MB")
print("links withheld on social:", sum(1 for r in rows if r['ch'] == 'social' and not r['u']), "of", sum(1 for r in rows if r['ch'] == 'social'))
