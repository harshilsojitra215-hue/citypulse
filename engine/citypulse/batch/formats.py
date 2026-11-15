"""Reading and validating an uploaded batch file (JSON array or CSV), and the template shown to users.

Two record layouts are accepted and may even be mixed in one file:
  simple            id, title, text, url, published_at, source_name, media_type, language, author
  challenge export  mention_id, title, content, url, published_at, media_type_name, source_name, language_code, authors
Every valid record is turned into the challenge-export layout, because that is what pipeline/01_build_base.py reads.
Unknown fields are ignored. A record without text or without a readable ISO date is rejected with a message; the
rest of the file is still processed.
"""
import csv, io, json
from datetime import datetime, timezone

MAX_RECORDS = 20000

FIELDS = [
    dict(name="text", required=True, aliases=["content"], description="The post itself: article body, comment or social post. Plain text or HTML."),
    dict(name="published_at", required=True, aliases=["date"], description="ISO date or date-time, e.g. 2026-11-03 or 2026-11-03T18:40:00Z. Without a time zone UTC is assumed."),
    dict(name="id", required=False, aliases=["mention_id"], description="Your own stable id. If missing, an id is derived from url + text, so the same post always gets the same id."),
    dict(name="title", required=False, aliases=[], description="Headline, if the post has one."),
    dict(name="url", required=False, aliases=[], description="Link to the post. The publishing domain is taken from it."),
    dict(name="source_name", required=False, aliases=[], description="Name of the outlet, channel or forum."),
    dict(name="media_type", required=False, aliases=["media_type_name"], description="News, Blog, Forums, Comments, YouTube Comments, Social Network, Microblog, Other. Decides the channel (news / social / other_web)."),
    dict(name="language", required=False, aliases=["language_code", "lang"], description="Language code, e.g. de or fr."),
    dict(name="author", required=False, aliases=["authors"], description="Author name or handle. Only used to count independent voices: it is replaced by a salted hash on ingest and never stored."),
]

EXAMPLE = [
    {"id": "example-1", "title": "Seilbahn: Gemeinderat vertagt Entscheidung", "text": "Der Heilbronner Gemeinderat hat die Entscheidung über die Seilbahn zum Bildungscampus vertagt. Kritiker halten die Kosten für zu hoch.",
     "url": "https://news.example/heilbronn/seilbahn-vertagt", "published_at": "2026-11-03T18:40:00Z", "source_name": "Example News",
     "media_type": "News", "language": "de", "author": "Redaktion"},
    {"text": "Eine Stadtbahn wäre für Heilbronn sinnvoller als diese Seilbahn.", "published_at": "2026-11-04",
     "url": "https://forum.example/t/123#p9", "media_type": "Forums", "language": "de", "author": "nutzer_42"},
]


class UnusableFile(Exception):
    """The whole upload cannot be processed (not JSON/CSV, empty, no record list)."""


def template() -> dict:
    cols = [f["name"] for f in FIELDS]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for r in EXAMPLE:
        w.writerow({c: r.get(c, "") for c in cols})
    return dict(
        formats=["json", "csv"],
        fields=FIELDS,
        notes=["JSON: one array of objects. CSV: UTF-8 with a header row (comma or semicolon separated).",
               "Unknown fields are ignored. Records without text or without a readable date are rejected one by one; the rest is processed.",
               "The original challenge export (mention_id, title, content, url, published_at, media_type_name, source_name, language_code, authors) is accepted unchanged.",
               "The uploaded file is deleted after processing. Only its SHA-256 and file name are kept."],
        example=EXAMPLE, example_csv=buf.getvalue(), filename="citypulse_batch_template.json")


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UnusableFile("the file is not UTF-8 text. Save it as UTF-8 JSON or CSV and upload again.")


def read_records(data: bytes, filename: str = "") -> list:
    """bytes -> list of raw records (dicts; anything else is reported per record by validate())."""
    text = _decode(data).strip()
    if not text:
        raise UnusableFile("the file is empty.")
    name = (filename or "").lower()
    as_json = name.endswith(".json") or (not name.endswith((".csv", ".tsv", ".txt")) and text[0] in "[{")
    if as_json:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise UnusableFile(f"the file is not valid JSON ({e.msg}, line {e.lineno}). Expected one JSON array of records.")
        if isinstance(obj, dict):  # tolerate {"records": [...]} style wrappers
            lists = [v for v in obj.values() if isinstance(v, list)]
            if len(lists) != 1:
                raise UnusableFile("the JSON file must be an array of records: [ {\"text\": …, \"published_at\": …}, … ].")
            obj = lists[0]
        if not isinstance(obj, list):
            raise UnusableFile("the JSON file must be an array of records.")
        records = obj
    else:
        head = text[:4096]
        try:
            delim = csv.Sniffer().sniff(head, delimiters=",;\t").delimiter
        except csv.Error:
            delim = ","
        csv.field_size_limit(50_000_000)
        rd = csv.DictReader(io.StringIO(text, newline=""), delimiter=delim)
        if not rd.fieldnames or len(rd.fieldnames) < 2:
            raise UnusableFile("the CSV file needs a header row with at least the columns text and published_at.")
        records = [{(k or "").strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k is not None} for row in rd]
        records = [r for r in records if any(v not in (None, "") for v in r.values())]
    if not records:
        raise UnusableFile("the file contains no records.")
    if len(records) > MAX_RECORDS:
        raise UnusableFile(f"the file has {len(records)} records; the limit per upload is {MAX_RECORDS}. Split it into smaller files.")
    return records


def _first(r, *keys):
    for k in keys:
        v = r.get(k)
        if v is None or (isinstance(v, float) and v != v):
            continue
        if isinstance(v, str):
            v = v.strip()
            if not v:
                continue
        return v
    return None


def parse_date(v) -> str:
    """ISO date / date-time -> ISO UTC string. Raises ValueError with a message meant for the uploader."""
    if isinstance(v, bool) or not isinstance(v, str):
        raise ValueError(f"published_at {v!r} is not an ISO date (expected e.g. 2026-11-03 or 2026-11-03T18:40:00Z)")
    try:
        d = datetime.fromisoformat(v.strip())
    except ValueError:
        raise ValueError(f"published_at {v.strip()[:40]!r} is not an ISO date (expected e.g. 2026-11-03 or 2026-11-03T18:40:00Z)")
    d = d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    if not 1990 <= d.year <= 2100:
        raise ValueError(f"published_at {v.strip()[:40]!r} is outside the plausible range (1990 to 2100)")
    return d.isoformat()


def _authors(r) -> list:
    v = _first(r, "authors", "author")
    if v is None:
        return []
    if isinstance(v, str) and v.startswith("["):   # a list that went through CSV
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            pass
    if isinstance(v, (list, tuple)):
        return [str(a).strip() for a in v if a is not None and str(a).strip()]
    return [str(v)]


def validate(records: list):
    """-> (valid, errors). valid: records in challenge-export layout plus '_row' (1-based position in the file) and
    '_id' (the uploader's id or None). errors: [{record, step, message}]."""
    valid, errors = [], []
    for i, r in enumerate(records, 1):
        if not isinstance(r, dict):
            errors.append(dict(record=f"row {i}", step="validate", message="record is not an object with named fields"))
            continue
        rid = _first(r, "id", "mention_id")
        rid = None if rid is None else str(rid)
        label = rid or f"row {i}"
        text = _first(r, "text", "content")
        if text is None or not str(text).strip():
            errors.append(dict(record=label, step="validate", message="missing text (field 'text' or 'content'): record skipped"))
            continue
        raw_date = _first(r, "published_at", "date")
        if raw_date is None:
            errors.append(dict(record=label, step="validate", message="missing published_at: record skipped (an ISO date such as 2026-11-03 is required)"))
            continue
        try:
            when = parse_date(raw_date)
        except ValueError as e:
            errors.append(dict(record=label, step="validate", message=f"{e}: record skipped"))
            continue
        s = lambda *k: (None if _first(r, *k) is None else str(_first(r, *k)))
        sent = _first(r, "sentiment")
        try:
            sent = int(sent) if sent is not None else None
        except (TypeError, ValueError):
            sent = None
        valid.append(dict(mention_id=str(i), title=s("title"), content=str(text), url=s("url") or "", published_at=when,
                          media_type_name=s("media_type", "media_type_name"), source_name=s("source_name"),
                          language_code=s("language", "language_code", "lang"), authors=_authors(r), sentiment=sent,
                          _row=i, _id=rid))
    return valid, errors
