"""Step 12: the numbers behind the insights. python -I src/12_insights.py data/labelled.parquet"""
import sys, numpy as np, pandas as pd
from statsmodels.stats.proportion import proportion_confint as ci

df = pd.read_parquet(sys.argv[1])
P = ["heilbronn_cablecar", "bonn_cablecar", "paris_c1", "ipai", "other_urban_cablecar"]
pd.set_option("display.width", 220)


def pct(k, n):
    if n == 0:
        return "-"
    lo, hi = ci(k, n, method="wilson")
    return f"{k/n:.0%} [{lo:.0%}-{hi:.0%}]"


print("== funnel ==")
print("raw mentions", len(df), "| unique texts", int(df.is_first_copy.sum()), "| sent to LLM (unique)", int(df[df.project != 'not_reviewed'].is_first_copy.sum()))
print(df[df.project != "not_reviewed"].groupby("project").agg(mentions=("mention_id", "size"), unique=("is_first_copy", "sum")).sort_values("mentions", ascending=False).to_string())

print("\n== per project: voices, channel, stance (unique texts, target not passing) ==")
rows = []
for p in P:
    d = df[(df.project == p)]
    u = d[d.is_first_copy & ~d.passing]
    op = u[u.stance.isin(["support", "oppose", "mixed"])]
    soc = u[u.channel == "social"]
    sop = soc[soc.stance.isin(["support", "oppose", "mixed"])]
    rows.append(dict(project=p, mentions=len(d), unique=len(u), social=len(soc), authors=d.author_hash.nunique(),
                     opinionated=len(op), support_of_opinion=pct((op.stance == "support").sum(), len(op)),
                     oppose_of_opinion=pct((op.stance == "oppose").sum(), len(op)),
                     social_oppose_of_opinion=pct((sop.stance == "oppose").sum(), len(sop)),
                     news_neutral=pct((u[u.channel == "news"].stance == "neutral").sum(), (u.channel == "news").sum())))
print(pd.DataFrame(rows).to_string(index=False))

print("\n== provided sentiment vs LLM stance on relevant posts ==")
r = df[df.project.isin(P) & df.is_first_copy & ~df.passing]
print("tool sentiment = -99 (missing):", pct((r.tool_sentiment == -99).sum(), len(r)))
x = r[r.tool_sentiment != -99]
print(pd.crosstab(x.tool_sentiment, x.stance, margins=True).to_string())
opp = r[r.stance == "oppose"]
print("opposing posts with NO usable tool sentiment (-99) or non-negative tool sentiment:", pct(((opp.tool_sentiment == -99) | (opp.tool_sentiment >= 0)).sum(), len(opp)))

print("\n== Paris C1 before vs after opening (13 Dec 2025) ==")
pa = df[(df.project == "paris_c1") & df.is_first_copy & ~df.passing].copy()
pa["phase"] = np.where(pd.to_datetime(pa.published_at).dt.tz_localize(None) < "2025-12-13", "before", "after")
for ph, g in pa.groupby("phase"):
    op = g[g.stance.isin(["support", "oppose", "mixed"])]
    topics = pd.Series([a.get("topic") for L in g.arguments if isinstance(L, (list, np.ndarray)) for a in L if isinstance(a, dict)]).value_counts(normalize=True).head(5).round(2).to_dict()
    print(f"{ph}: n={len(g)} opinionated={len(op)} support={pct((op.stance=='support').sum(), len(op))} oppose={pct((op.stance=='oppose').sum(), len(op))} topics={topics}")

print("\n== Heilbronn by quarter ==")
h = df[(df.project == "heilbronn_cablecar") & df.is_first_copy].copy()
h["q"] = pd.to_datetime(h.published_at).dt.tz_localize(None).dt.to_period("Q")
print(h.groupby("q").agg(n=("mention_id", "size"), social=("channel", lambda s: (s == "social").sum()),
                          support=("stance", lambda s: (s == "support").sum()), oppose=("stance", lambda s: (s == "oppose").sum())).to_string())

print("\n== contra arguments by project (share of unique target posts raising each) ==")
rows = []
for p in P[:4]:
    g = df[(df.project == p) & df.is_first_copy]
    c = pd.Series([a.get("topic") for L in g.arguments if isinstance(L, (list, np.ndarray)) for a in {(x.get("topic"), x.get("polarity")): x for x in L if isinstance(x, dict) and x.get("polarity") == "contra"}.values()])
    rows.append((c.value_counts() / len(g)).round(3).rename(p))
print(pd.concat(rows, axis=1).fillna(0).to_string())

print("\n== loud voices: share of social posts from the top 5 authors ==")
for p in P:
    s = df[(df.project == p) & (df.channel == "social") & df.author_hash.notna()]
    if len(s):
        top = s.author_hash.value_counts()
        print(f"{p}: social posts {len(s)}, authors {len(top)}, top-5 share {top.head(5).sum()/len(s):.0%}")
