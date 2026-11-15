"""Step 1: raw JSON -> clean, deduplicated, pseudonymised base table.

Usage: python -I src/01_build_base.py <raw.json> data/base.parquet
- author handles never leave this script: only a salted hash (to count distinct voices) is kept
- exact duplicates (syndicated copies) are grouped, not dropped: dup_group + dup_count
"""
import sys, json, re, hashlib, html, unicodedata
from urllib.parse import urlparse, parse_qs
import pandas as pd

SALT = "fch2026-cablecar"  # fixed so ids are stable across runs; never published


def clean(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = unicodedata.normalize("NFC", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_for_dup(s):
    s = s.lower()
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"[^\w]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def yt_ids(url):
    try:
        u = urlparse(url)
    except Exception:
        return None, None
    q = parse_qs(u.query)
    vid = (q.get("v") or [None])[0]
    if not vid and "youtu.be" in u.netloc:
        vid = u.path.strip("/").split("/")[0] or None
    if not vid and "/shorts/" in u.path:
        vid = u.path.split("/shorts/")[1].split("/")[0]
    lc = (q.get("lc") or [None])[0]
    return vid, lc


def main(src, dst):
    raw = json.load(open(src, encoding="utf-8"))
    rows = []
    for r in raw:
        title, content = clean(r.get("title")), clean(r.get("content"))
        if content.startswith(title[: max(20, len(title) - 3)].rstrip(".… ")) and title:
            text = content
        else:
            text = (title + "\n" + content).strip()
        url = r.get("url") or ""
        vid, lc = yt_ids(url) if "youtu" in url else (None, None)
        authors = [a for a in (r.get("authors") or []) if a]
        rows.append(dict(
            mention_id=r.get("mention_id"),
            published_at=r.get("published_at"),
            media_type=r.get("media_type_name"),
            source_name=r.get("source_name"),
            url=url,
            domain=urlparse(url).netloc.lower().removeprefix("www."),
            country=r.get("country_code"),
            lang=r.get("language_code"),
            tool_sentiment=r.get("sentiment"),
            reach=r.get("reach"),
            engagements=r.get("engagements"),
            title=title,
            content=content,
            text=text,
            n_chars=len(text),
            yt_video_id=vid,
            yt_comment_id=lc,
            author_hash=hashlib.sha256((SALT + authors[0]).encode()).hexdigest()[:12] if authors else None,
            n_authors=len(authors),
        ))
    df = pd.DataFrame(rows)
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df["date"] = df["published_at"].dt.date
    df["month"] = df["published_at"].dt.strftime("%Y-%m")
    df["week"] = df["published_at"].dt.to_period("W-MON").dt.start_time.dt.date
    df["dup_key"] = df["text"].map(lambda t: hashlib.md5(norm_for_dup(t).encode()).hexdigest())
    df = df.sort_values("published_at", kind="stable")
    df["dup_count"] = df.groupby("dup_key")["mention_id"].transform("size")
    df["is_first_copy"] = ~df.duplicated("dup_key", keep="first")
    # social vs news split used throughout (readme: "Do social media discussions differ from news coverage?")
    social = {"YouTube Comments", "Comments", "Forums", "Social Network", "Microblog", "Pictures", "YouTube Video"}
    df["channel"] = df["media_type"].map(lambda m: "social" if m in social else ("news" if m == "News" else "other_web"))
    df.to_parquet(dst, index=False)
    print(f"rows={len(df)} unique_texts={df['is_first_copy'].sum()} dup_rows={(~df['is_first_copy']).sum()}")
    print(df["channel"].value_counts().to_string())
    print("yt comments with video id:", df.loc[df.media_type == "YouTube Comments", "yt_video_id"].notna().sum())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
