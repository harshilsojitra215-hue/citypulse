"""Step 2: rule layer. Adds transparent regex flags, a candidate bucket and a keyword-in-context
snippet (what an LLM / human sees when judging relevance).

Usage: python -I src/02_candidates.py data/base.parquet data/candidates.parquet
"""
import sys, re
import pandas as pd

R = {  # every rule is listed here so a reviewer can read exactly why a post was picked up
    "kw_seilbahn": r"seilbahn|gondelbahn|urbane?n? seilb|cable[ -]car",
    "kw_tele": r"t[ée]l[ée]ph[ée]rique|t[ée]l[ée]cabine|c[âa]ble ?c?1\b|c[âa]ble c1|\bc1 (?:cable|câble)",
    "kw_ipai": r"\bipai\b|innovation park artificial intelligence|innovationspark k[üu]nstliche",
    "geo_heilbronn": r"heilbronn|k[äa]thchenstadt|bildungscampus|steinäcker|lerchenberg|neckarsulm",
    "geo_paris_c1": r"c[âa]ble ?c?1\b|c[âa]ble a\b(?! [a-zé]{3,})|t[ée]l[ée]val|cr[ée]teil|villeneuve-saint-georges|limeil|valenton|val-de-marne",
    "geo_paris_any": r"\bparis\b|[iî]le-de-france|\bidfm\b|francilien",
    "geo_bonn": r"\bbonn(?:er)?\b|venusberg|ramersdorf|hindenburgplatz|uni-?klinik bonn",
    "urban_ctx": r"[öo]pnv|nahverkehr|stadtbahn|verkehrsmittel|urban|innenstadt|pendler|machbarkeitsstudie|stadtrat|gemeinderat|transport (?:en )?commun|transports? urbain|mobilit[ée]",
}
KW = r"seilbahn|gondel|t[ée]l[ée]ph[ée]rique|t[ée]l[ée]cabine|c[âa]ble|ipai|heilbronn|bonn|cr[ée]teil"


def kwic(text, width=260, max_snips=3, head=350):
    """First `head` chars + up to `max_snips` windows around keyword hits (deduplicated)."""
    out, last_end = [text[:head]], head
    for m in re.finditer(KW, text, flags=re.I):
        if m.start() < last_end:
            continue
        a, b = max(0, m.start() - width), min(len(text), m.end() + width)
        out.append("… " + text[a:b] + " …")
        last_end = b
        if len(out) > max_snips:
            break
    return "\n".join(out)


def split_sents(t):
    return [x.strip() for x in re.split(r"(?<=[.!?|])\s+|\s+[|•·]\s+", t) if x.strip()]


def strip_boilerplate(df, min_docs=15):
    """Remove sentences that repeat in >= min_docs different posts and contain no topic keyword
    (paywall banners, cookie notices, photo-licence lines, newsletter blurbs)."""
    import collections
    cnt = collections.Counter()
    for t in df.loc[df.is_first_copy, "text"]:
        cnt.update({x for x in split_sents(t) if len(x) >= 25})
    topic_kw = r"seilbahn|gondel|t[ée]l[ée]ph[ée]rique|t[ée]l[ée]cabine|c[âa]ble|ipai"  # not place names: "Heilbronner Stimme GmbH" is boilerplate
    boiler = {x for x, n in cnt.items() if n >= min_docs and not re.search(topic_kw, x, flags=re.I)}
    out = df["text"].map(lambda t: " ".join(x for x in split_sents(t) if x not in boiler))
    print(f"boilerplate sentences removed: {len(boiler)}; chars before {df.text.str.len().sum():,} after {out.str.len().sum():,}")
    return out


def main(src, dst):
    df = pd.read_parquet(src)
    df["text_clean"] = strip_boilerplate(df)
    low = df["text"].str.lower()
    for k, p in R.items():
        df[k] = low.str.contains(p, regex=True)
    cable = df.kw_seilbahn | df.kw_tele
    df["bucket"] = "background"
    df.loc[cable & df.urban_ctx, "bucket"] = "other_urban_cand"
    df.loc[df.kw_tele & df.geo_paris_any, "bucket"] = "paris_loose_cand"
    df.loc[df.kw_ipai, "bucket"] = "ipai_cand"
    df.loc[cable & df.geo_bonn, "bucket"] = "bonn_cand"
    df.loc[df.kw_tele & df.geo_paris_c1, "bucket"] = "paris_c1_cand"
    df.loc[cable & df.geo_heilbronn, "bucket"] = "heilbronn_cand"
    df["snippet"] = df["text_clean"].map(kwic)
    df.to_parquet(dst, index=False)
    print(df["bucket"].value_counts().to_string())
    print("unique texts per bucket:\n" + df[df.is_first_copy]["bucket"].value_counts().to_string())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
