"""Step 7: attention peaks, decay ("does it return to normal?") and event linking.

python -I src/07_peaks.py <labelled.parquet> <project_col> [events.csv]
labelled.parquet needs: published_at, <project_col>, title, dup_count, media_type, channel (+ optional stance)
Method (all transparent, no black box):
  1. daily mention counts per project (all copies = attention)
  2. baseline = mean of the previous 28 days (+0.1/day)
  3. peak day: Poisson P(X >= count | baseline) < 0.001 and count >= 4; adjacent peak days (gap <= 2) form one episode
  4. half-life: days from the episode's top day until the daily count falls below baseline + 50% of the excess
  5. lasting change: median weekly volume 8 weeks before vs 8 weeks after (excluding +-1 week around the episode)
  6. event link: most-syndicated headline inside the episode + nearest dated event from events.csv (+-7 days)
"""
import sys
import numpy as np, pandas as pd

src, col = sys.argv[1], sys.argv[2]
events = pd.read_csv(sys.argv[3], parse_dates=["date"]) if len(sys.argv) > 3 else None
FREQ = sys.argv[4] if len(sys.argv) > 4 else "D"  # "D" daily, "W" weekly (better for low-volume projects)
UNIT = pd.Timedelta(days=1) if FREQ == "D" else pd.Timedelta(weeks=1)
WIN, MINC, GAP = (28, 4, 2) if FREQ == "D" else (12, 5, 1)
df = pd.read_parquet(src)
df["day"] = pd.to_datetime(df.published_at).dt.tz_localize(None).dt.normalize()
PROJ_EVENT = {"heilbronn_cablecar": "heilbronn_cablecar", "paris_c1": "paris_c1", "bonn_cablecar": "bonn_cablecar", "ipai": "ipai"}
rows = []
for proj in [p for p in PROJ_EVENT if p in set(df[col])]:
    d = df[df[col] == proj]
    s = d.groupby("day").size().reindex(pd.date_range(df.day.min(), df.day.max()), fill_value=0)
    if FREQ == "W":
        s = s.resample("W-MON", label="left", closed="left").sum()
    # low counts (0-3 a day) make median/MAD useless, so use a Poisson surprise test instead:
    # lam = mean of the previous 28 days (+0.1/day floor); peak day if P(X >= count | lam) < 0.001 and count >= 4
    from scipy.stats import poisson
    med = (s.shift(1).rolling(WIN, min_periods=4).mean().fillna(0) + 0.1)
    pval = pd.Series(poisson.sf(s.values - 1, med.values), index=s.index)
    hit = (pval < 0.001) & (s >= MINC)
    days = list(s.index[hit])
    eps, cur = [], []
    for day in days:
        if cur and (day - cur[-1]) > GAP * UNIT:
            eps.append(cur); cur = []
        cur.append(day)
    if cur:
        eps.append(cur)
    wk = s.resample("W-MON").sum() if FREQ == "D" else s
    for ep in eps:
        top = s.loc[ep[0]:ep[-1]].idxmax()
        base, peak = med.loc[top], s.loc[top]
        after = s.loc[top + UNIT:]
        back = after[after <= base + 0.5 * (peak - base)]
        decay = (back.index[0] - top).days if len(back) else None  # attention half-life in days (weekly mode: multiples of 7)
        pre = wk.loc[top - pd.Timedelta(weeks=9): top - pd.Timedelta(weeks=1)]
        post = wk.loc[top + pd.Timedelta(weeks=1): top + pd.Timedelta(weeks=9)]
        win = d[(d.day >= ep[0] - pd.Timedelta(days=1)) & (d.day < ep[-1] + UNIT + pd.Timedelta(days=1))]
        news = win[win.media_type == "News"].sort_values(["dup_count", "reach"], ascending=False)
        headline = news.title.iloc[0][:110] if len(news) else (win.title.iloc[0][:110] if len(win) else "")
        ev = ""
        if events is not None:
            e = events[(events.project == PROJ_EVENT[proj]) & ((events.date - top).abs() <= pd.Timedelta(days=7))]
            if len(e):
                e = e.iloc[(e.date - top).abs().argsort()[:1]]
                ev = f"{e.date.dt.date.iloc[0]} {e.title_en.iloc[0]}"
        st = ""
        if "stance" in d.columns:
            w = win[win.stance.isin(["support", "oppose", "neutral", "mixed"])]
            if len(w):
                st = f"sup {np.mean(w.stance == 'support'):.0%} / opp {np.mean(w.stance == 'oppose'):.0%}"
        social = (win.channel == "social").mean() if len(win) else np.nan
        rows.append(dict(project=proj, start=ep[0].date(), top=top.date(), peak=int(peak), baseline=round(float(base), 1),
                         episode_mentions=int(s.loc[ep[0]:ep[-1]].sum()), half_life_days=decay,
                         wk_before=float(pre.median()) if len(pre) else None, wk_after=float(post.median()) if len(post) else None,
                         social_share=round(float(social), 2), stance=st, top_headline=headline, linked_event=ev))
res = pd.DataFrame(rows).sort_values(["project", "top"])
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 70)
print(res.to_string(index=False))
res.to_csv(f"out/peaks_{col}_{FREQ}.csv", index=False)
