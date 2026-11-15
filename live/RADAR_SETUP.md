# Radar setup: "scan the internet for today and see the report"

Written 14 Nov 2026. Prices and limits were read from the vendors' pages that day; check them once before relying on them.
Expected total cost of a stage scan: **0 EUR** on the free tiers. The 10 EUR is a reserve, not a need.

## Accounts to create (you do this, in your browser; I never create accounts or see keys)

| Service | Sign-up URL | Free tier | Card? | Env variable |
|---|---|---|---|---|
| Exa | https://dashboard.exa.ai (sign up, then API Keys) | 10 USD credits, resets monthly | no | `EXA_API_KEY` |
| Tavily | https://app.tavily.com (sign up, key shown on the dashboard) | 1000 credits per month | no | `TAVILY_API_KEY` |
| YouTube Data API v3 | https://console.cloud.google.com : new project, then "APIs & Services", enable "YouTube Data API v3", then "Credentials", "Create credentials", "API key" | 10,000 units per day, search limited to 100 calls per day | no (Google account only) | `YOUTUBE_API_KEY` |
| Apify (optional, off by default) | https://console.apify.com/sign-up , then Settings, "API & Integrations", copy the personal token | 5 USD credits per month | no | `APIFY_TOKEN` |

Not used: Brave Search API (needs a card, standard plan does not allow storing results), Firecrawl and Perplexity (not needed for discovery), SerpApi (Google and Reddit lawsuits are open), Reddit API (approval needed, not set up).

## Put the keys in without pasting them into chat

1. In PowerShell: `notepad C:\Users\Harshil\Desktop\win\live\.env` (say yes to create the file).
2. Type these lines, with your keys after the `=`, no quotes, then save:
```
EXA_API_KEY=
TAVILY_API_KEY=
YOUTUBE_API_KEY=
APIFY_TOKEN=
```
3. `live/.env` is gitignored (checked: `git check-ignore -v live/.env` points at `.gitignore` line 5). Keys are read at run time, sent only in a request header (the YouTube API requires its key as a URL parameter, which we never print), and never logged. A source with no key is skipped and the receipt says so.

## The one command on stage

```
python -I -X utf8 C:\Users\Harshil\Desktop\win\live\run_collect.py --radar --since 2026-11-01
```

It runs every enabled source for all 11 projects, prints one line per source and project, and writes `live/out/radar_<run_id>.md` (the report) and `receipt_<run_id>.md` (the receipt). Open the radar file. Pass `--project heilbronn_cablecar` for a faster single-project demo (about one minute).
Apify stays off until you set `enabled: true` under `sources.apify` in `projects.yaml` and `APIFY_TOKEN` exists.

## Expected cost per scan (11 projects)

- Exa: 10 searches per project (3 normal, 7 site-scoped) = 110 searches, about 0.45 USD plus highlights about 1 USD. The free 10 USD cover about 6 scans a month.
- Tavily: about 13 credits per project = 143 credits. The free 1000 cover about 7 scans a month.
- YouTube: at most 60 searches per run (cap in `projects.yaml`; the API allows 100 a day, so do not run more than one full scan a day) plus a few hundred comment calls out of 10,000 units.
- Apify (if switched on): about 110 search pages, estimated under 0.3 USD, hard stop at 4 USD per run (`max_total_usd`).

## Apify token in one line

Create the account at the URL above, copy the personal API token into `APIFY_TOKEN`; the adapter uses only `apify/google-search-scraper` for link, title and snippet discovery, never an actor that logs into or downloads from a social platform. Platform terms in one sentence: Apify's own docs say its Website Content Crawler ignores robots.txt rules and a Google results scraper reads pages Google's terms restrict, so we keep Apify off by default and use Exa and Tavily (licensed APIs) as the main discovery.

## What the report shows

Per project: new items by kind (news, city / official, forum / petition, blog, video, video comment, social link, Bluesky or Mastodon post), "Found on Reddit / Facebook / Instagram / X / TikTok / YouTube: N links, open to read", topic words from the snippets, top 5 new titles, then which sources ran, were skipped (for example "youtube: no key") or failed, and a fixed statement of what it cannot see (closed platforms, paywalls, robots.txt pages).

## Rules built in (kept simple)

- Social platforms: only the link, title, snippet and date that a search service returned (`kind: social_link`, `text_scope: snippet`). We never open or download those pages.
- Other pages: full text only if robots.txt allows our user agent, else snippet only.
- YouTube: video and comment text, date, link, hashed author id. No names, handles or channel links. YouTube's developer policy limits storing this data to 30 days, then delete or refresh it. A purge command is not built yet. Before relying on the YouTube comments beyond the demo, delete `youtube` rows older than 30 days from `data/live.db`.
- Exa and Tavily terms on keeping results: Tavily's terms (read 14 Nov 2026) do not forbid storage but limit use to internal business purposes and bar reselling. Exa's terms PDF could not be read as text by me, so its storage clause is unverified: read https://exa.ai/terms before the city keeps Exa results.
- Search hits without a publish date are kept with `date_known: false` and shown as "date unknown".
