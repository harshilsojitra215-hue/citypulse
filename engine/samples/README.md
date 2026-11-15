# Sample upload files

## `demo_batch_synthetic.json`

Ten short German posts about the Heilbronn cable car, **written by hand for the demo. They are not real posts.**
Every record has `source_name: "SYNTHETIC DEMO"`, a `synthetic-demo.example` link and `"synthetic": true`.
All are dated November 2026, after the last post of the historical data.

| id | what it shows |
|---|---|
| demo-01 | known argument: the cable car costs too much |
| demo-02 | known argument: extend the Stadtbahn instead |
| demo-03 | known argument: fast link to the IPAI campus |
| demo-04, demo-05, demo-06 | three different authors raise one concern that the historical Heilbronn debate does not contain: a wind shutdown leaves evening-shift workers without a way home |
| demo-07 | noise that passes the keyword rules (a ski-area cable car); the model labels it as leisure and it is not stored |
| demo-08 | noise without any keyword (an alpine hut); it is never sent to the model |
| demo-09 | exact copy of demo-01 on another site; grouped with it, counted once |
| demo-10 | no date; rejected with a message, the other nine are still processed |

Run it:

```
.venv/bin/python -m citypulse.batch samples/demo_batch_synthetic.json
```

or upload it in the application (`POST /api/batches`). The same file cannot be processed twice: the second upload
answers with the run id of the first.

## The two accepted layouts

A file is a JSON array of records, or a CSV with a header row (UTF-8, comma or semicolon). Both layouts work in both
file types and can be mixed. Unknown fields are ignored.

**Simple layout**

| field | required | meaning |
|---|---|---|
| `text` | yes | the post (plain text or HTML) |
| `published_at` | yes | ISO date or date-time, `2026-11-03` or `2026-11-03T18:40:00Z`; UTC if no time zone is given |
| `id` | no | your stable id; without it the id is a hash of url + text |
| `title` | no | headline |
| `url` | no | link; the publishing domain is taken from it |
| `source_name` | no | outlet, channel or forum |
| `media_type` | no | `News`, `Blog`, `Forums`, `Comments`, `YouTube Comments`, `Social Network`, `Microblog`, `Other` |
| `language` | no | `de`, `fr`, ... |
| `author` | no | name or handle; replaced by a salted hash on ingest, never stored |

```json
[{"id": "a-1", "title": "Seilbahn: Entscheidung vertagt", "text": "Der Gemeinderat hat ...", "url": "https://news.example/a-1",
  "published_at": "2026-11-03T18:40:00Z", "source_name": "Example News", "media_type": "News", "language": "de", "author": "Redaktion"}]
```

```csv
id,title,text,url,published_at,source_name,media_type,language,author
a-1,Seilbahn: Entscheidung vertagt,"Der Gemeinderat hat ...",https://news.example/a-1,2026-11-03T18:40:00Z,Example News,News,de,Redaktion
```

**Challenge export layout** (the format of the hackathon dataset, accepted unchanged)

`mention_id, title, content, url, published_at, media_type_name, source_name, language_code, authors`

Here `content` is the text, `mention_id` the id and `authors` a list of names (the first one is hashed).

```json
[{"mention_id": "123,456", "title": "…", "content": "…", "url": "https://…", "published_at": "2026-11-03T18:40:00Z",
  "media_type_name": "News", "source_name": "…", "language_code": "de", "authors": ["…"]}]
```

## What is rejected

- a record without `text` / `content`, or without a readable ISO date in `published_at`: that record only, with a message in the run's `errors`
- a file that is not UTF-8 JSON or CSV, or has no records: the whole run ends as `failed`

## What happens to the file

It is read once and deleted when processing has finished. The run keeps the file name and its SHA-256, the cleaned
posts that are relevant to one of the projects, and their extracted arguments. Author names are never stored.
