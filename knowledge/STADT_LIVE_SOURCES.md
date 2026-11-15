# Stadt Heilbronn "Riding the Sentiment": live source map

14 Nov 2026. Owner: Harshil (live data). Code: `live/`. Earlier research: `STADT_TECH_LIVE.md` section A (this file extends it, it does not repeat it).
Labels: CONFIRMED = I called it or read it on 14 Nov 2026. REPORTED = from a search result or third-party page, not checked at the source. NOT KNOWN = no evidence found.
Hard rule for everything below: no login bypass, no CAPTCHA or proof-of-work solving, no paywall bypass, no proxies, no fake user agent, no scraping of Instagram, Facebook, LinkedIn, TikTok, WhatsApp, X, Quora, Reddit HTML. Closed sources get a legal route, a cost and a lead time instead.

## 1. Verdicts at a glance

| Verdict | Sources |
|---|---|
| **Now (built in `live/`)** | Heilbronn OParl council papers, official RSS (heilbronn.de), outlet RSS (SWR, GA, franceinfo, 20 Minutes), Bluesky public search, Mastodon hashtag timelines, Google News RSS (with a robots.txt caveat), GDELT DOC API (built, but our network got HTTP 429 on every call, see 3) |
| **Now, small manual or later** | Official city and IDFM pages as dated events, YouTube transcripts of city videos, planning PDFs reached through OParl file links, Common Crawl News (batch, not live) |
| **With a key (free, needs Harshil's own account)** | YouTube Data API v3 comments, Mastodon status search (token), Reddit Data API (approval, not a simple key) |
| **With a contract or research access** | Meta Content Library (Instagram, Facebook; academic or non-profit only), TikTok Research API (non-profit research bodies only), X API (pay per use), the city's own media-monitoring vendor (production route) |
| **No** | Instagram, Facebook, LinkedIn, TikTok, X, Quora, WhatsApp and Reddit by scraping; Bonn OParl through the gate; Stimme and echo24 pages or feeds; Le Parisien feed |

## 2. Source by source

### 2.1 News

| Source | Legal status | Auth, cost | Volume for our topics | Freshness | Fields | Effort | Verdict |
|---|---|---|---|---|---|---|---|
| **GDELT DOC 2.0 API** `api.gdeltproject.org/api/v2/doc/doc` | Free, open, cite GDELT [https://www.gdeltproject.org/about.html]. Asks for 1 request per 5 s [response text CONFIRMED] | None, free | Expected: tens per project and month, all outlets (German, French, English) | About 15 min | url, title, seendate, domain, language, sourcecountry. No text | Done (`adapters/gdelt.py`) | **Now**. Caveat: from this network every call returned HTTP 429 (about 15 calls over 40 minutes, spaced 6 s or more). NOT live-verified |
| **Google News RSS** `news.google.com/rss/search` | Feed offered to readers, personal non-commercial use, attribute Google News and the publisher [https://www.google.com/intl/en_us/terms_google_news.html]. **`news.google.com/robots.txt` has `Disallow: /` for `User-agent: *` with no allow for `/rss`** [CONFIRMED 14 Nov 2026]. The team's `s12_live.py` already uses it | None, free | CONFIRMED: Heilbronn cable car 4 to 5 items in 60 days, Bonn 4 to 5, Paris C1 16 to 28, IPAI 18 to 22 (60 days, title-only, see 3) | Hours | title, link, date, outlet, no text. Max about 100 per query | Done (`adapters/gnews.py`) | **Now, flagged**. Team decision: keep, or drop and rely on GDELT. Not for a commercial city service without Google's OK |
| **Outlet RSS** | Per outlet, below | None | Few per month per outlet | Real time, **but a feed holds only the latest 8 to 82 items** (CONFIRMED), so a monthly run misses most of it. Only useful if run daily, or as a trigger | title, summary, link, date | Done (`adapters/rss.py`, feeds in `projects.yaml`) | **Now, weak**. Google News and GDELT are the real news route |
| Heilbronn city news `heilbronn.de/startseite.xml` | Official, robots.txt allows (`Disallow` only `/shop-und-gastrofinder/buchstabe/`) [CONFIRMED] | None | 1 to 3 per month on the cable car | Real time, 30 items held | title, teaser, link, date | Done | **Now** |
| SWR BW feed `swr.de/~rss/swraktuell-bw-100.xml` | robots.txt allows [CONFIRMED]. Public broadcaster feed | None | A few per month, Baden-Württemberg wide | Real time, 82 items held | same | Done | **Now** |
| General-Anzeiger Bonn `ga.de/feed.rss` | robots.txt for `*` disallows only `/api/`, `/suche/`, `/sso/` and similar [CONFIRMED]. Many AI bots named and blocked, we are not one | None | 8 items held (very short window) | Real time | same | Done | **Now, weak**. Bonn coverage comes mostly through Google News (CONFIRMED 4 items about Venusberg, none about the cable car itself in the window) |
| franceinfo and 20 Minutes | Public feeds, robots.txt checked at run time | None | Rarely carry Câble C1 | Real time | same | Done | **Now, weak** |
| Heilbronner Stimme `stimme.de` | Paywall (Stimme+). robots.txt has `Disallow: /storage/rss/`. No public feed found (`/rss` 404) [CONFIRMED]. echo24.de (same group): robots.txt states automated access needs permission, contact `nutzungsrechte@stimme-mediengruppe.de` [CONFIRMED text] | Licence needed | Several per month | | | | **No** direct. Headline, date and link through Google News or GDELT only. **With contract**: ask the Stimme Mediengruppe for a feed licence, or use the city's press-clipping licence (see 2.8) |
| Le Parisien | Feed URL returned 403 Access Denied [CONFIRMED]. Paywall | | | | | | **No**. Headlines through Google News or GDELT. actu.fr and Le Parisien both appeared in Google News for Câble C1 |
| actu.fr | robots.txt lists sitemaps and `sitemap-news.xml` [CONFIRMED]. No per-topic RSS found | None | Câble C1 stories appear (CONFIRMED in Google News) | | | 2 h for a news-sitemap reader | **Later**, only if Google News coverage proves thin |
| Common Crawl News (CC-NEWS) | Public WARC files, anonymous HTTPS [https://data.commoncrawl.org/crawl-data/CC-NEWS/index.html, REPORTED free]. Publisher copyright still applies | None | Large: about 5.8 TiB compressed in 2025 [REPORTED] | Daily files, delay of days | Full HTML of articles, including paywall pages the crawler saw | 1 to 2 days, heavy | **Now, but batch and not for this weekend.** Useful for back-fill and article text. Copyright and paywall stubs make it a research route, not a dashboard feed |

### 2.2 Official pages, council and participation

| Source | Legal status | Auth, cost | Volume | Freshness | Fields | Effort | Verdict |
|---|---|---|---|---|---|---|---|
| **Heilbronn OParl** `heilbronn-sitzungsdienst.komm.one/oparl/system` | Open data, licence `dl-de/zero-2-0` stated in the API [CONFIRMED]. SOMACOS Session, OParl 1.x. robots.txt of the host does not block us | None, free | CONFIRMED: 800 papers modified since 27 Oct; cable-car related 2 (Vorprojekt 061/2025, Machbarkeit 193/2026) and 5 IPAI related in the 60-day window | Real time (modified_since filter) | Paper name, reference, date, type, consultations, files | Done (`adapters/oparl.py`) | **Now**. Institutional voice, good as timeline events and as "what the council is deciding next" |
| **Bonn OParl** `bonn.sitzung-online.de/public/oparl/system` | City says OParl 1.1, data CC0 [https://opendata.bonn.de/dataset/ratsinformationssystem-oparl-api]. Since Feb 2026 the host serves a "Zugriff prüfen" page with an ALTCHA proof-of-work gate [CONFIRMED today, also REPORTED in a GitHub issue of mandariOSS]. A proof-of-work gate is a technical access restriction: **we do not solve it** | None would be needed | | | | | **No** until the city lifts the gate. Legal routes: (a) ask the Bonn digital office to allow-list our client or give a key (cost 0, lead time unknown); (b) use the public mirror `oparl.bonn.machdenstaat.de` (third party, "incomplete, filled by backfill runs" [REPORTED]; we did not find a JSON endpoint, only a web app); (c) the same data in the city's open-data portal. The adapter asks once per run and logs "gated" |
| Heilbronn press and Seilbahn page `heilbronn.de/umwelt-mobilitaet/mobilitaet/seilbahn.html` | Public, robots.txt allows | None | Few updates | | HTML | 1 h per page by hand | **Now (manual)**, as dated events. Feed `startseite.xml` covers new press releases |
| Bonn press releases `bonn.de/pressemitteilungen/` | Public. No RSS found [CONFIRMED: no alternate link, `/rss` 404]. robots.txt for `*` not read in full | None | Few per year on the cable car | | HTML | 1 h | **Now (manual)** as events |
| IDFM Câble C1 `iledefrance-mobilites.fr/le-reseau/projets/cablec1` | Public, robots.txt `Disallow:` empty (allows all) [CONFIRMED]. No RSS found | None | Few per month | | HTML | 1 h | **Now (manual)** as events |
| Participation platforms: Bonn `bonn-macht-mit.de` (loads, 200); Heilbronn `heilbronn.de/rathaus/buergerbeteiligung.html` (200) | Public pages, terms not read. Comments are by named or pseudonymous citizens | None | NOT KNOWN | | | 2 to 3 h | **Ask the cities**. A comment export from the platform operator is better than scraping, and it is the voice of real residents. Cost 0, lead time weeks |
| Planning and academic reports (PDF) | Public; OParl `files` link to the council PDFs (Machbarkeitsstudie etc.); IDFM concertation reports | None | Few, long | | Full text | 0.5 day for download plus text extraction | **Now**, for the context layer (costs, route, milestones), not for sentiment |

### 2.3 Petitions

| Source | Legal status | Auth, cost | Volume | Fields | Effort | Verdict |
|---|---|---|---|---|---|---|
| openPetition | robots.txt allows `/suche` and `/petition/online/`, disallows `/petition/unterzeichner/` and `/petition/kommentare/`, `Crawl-delay: 1` [CONFIRMED]. The search page is rendered by JavaScript (empty without a browser), no public search API found. The public sitemap lists only about 2,000 petitions (8,000 URLs) | None | CONFIRMED 0 relevant: the only "Seilbahn" petition in the sitemap is about Königshöhe (another place) | | | **Now (manual check)**. Sitemap slug check is 10 lines, not built. A partner API exists on request [NOT KNOWN: terms] |
| change.org | robots.txt disallows `/api-proxy/`, `/u/`, signing pages [CONFIRMED]. Terms not read | None | NOT KNOWN | | | **Later**. Manual search for "Seilbahn Heilbronn / Bonn" once, record any petition as an event |

### 2.4 Social media with open, documented, free access

| Source | Legal status | Auth, cost | Volume (60 days, CONFIRMED) | Fields we keep | Effort | Verdict |
|---|---|---|---|---|---|---|
| **Bluesky search** `api.bsky.app/xrpc/app.bsky.feed.searchPosts` | Official public AppView API. Works without login at `api.bsky.app` (200). `public.api.bsky.app` returned 403 [CONFIRMED], so we use the first. Reports of cursor paging needing login were not seen in 3 pages | None | Heilbronn cable car 0, Bonn 0, Paris C1 2, IPAI 2 | text, date, URL, hashed author id, counts | Done | **Now**. Small German audience, so expect near zero. French event spikes show up (C1 closure 6 to 9 Nov) |
| **Mastodon hashtag timelines** (`mastodon.social`, `troet.cafe`) | Public API, no token for tag timelines. Status full-text search returned empty without a token [CONFIRMED]. Instance rules apply [https://docs.joinmastodon.org/methods/timelines/] | None | Heilbronn 1, Bonn 1, Paris 0, IPAI 0. `troet.cafe` answered HTTP 422 for the tags cablec1, telepherique, ipai | text, date, URL, hashed author id, counts | Done | **Now**, tiny. Mastodon search with a token: **with key** (account on an instance, free, Harshil's call) |
| YouTube Data API v3 comments | Official, allowed under the developer policies. Stored non-authorised data must be refreshed or deleted within 30 days, no mixing with own metrics [https://developers.google.com/youtube/terms/developer-policies, from STADT_TECH_LIVE A2] | API key, free, quota 10,000 units per day; search.list 100 units per call, commentThreads.list 1 unit [https://developers.google.com/youtube/v3/determine_quota_cost] | NOT KNOWN. The dataset has 2,335 YouTube comments and 4,458 videos, so YouTube is the biggest live social voice | comment text, date, video id, like count; author name must be dropped | 3 to 4 h | **With key**. Needs Harshil's own Google Cloud project. Highest value per hour among the social routes. Ask Harshil |
| Podcasts and video transcripts | YouTube captions through the official API need the video owner's permission; auto-captions via unofficial libraries are a ToS grey area. ARD and ZDF Mediathek have their own terms | | NOT KNOWN | | Whisper on audio we may legally download (city's own videos): 1 day | **Case by case**, not automated |
| Telegram public channels | Official API needs an account and a phone number; web preview pages `t.me/s/` | | 5 Telegram records in the dataset | | | **No** for now |

### 2.5 Social media that is closed (legal route, cost, lead time)

| Platform | Why closed | Legal route | Eligibility, cost | Lead time | Verdict |
|---|---|---|---|---|---|
| **Instagram, Facebook** (2,391 Instagram and 334 Facebook records in the city dataset, so the city's vendor reached them) | Meta terms forbid scraping. No public search API | **Meta Content Library and API.** Page updated 30 Apr 2026: applications through Meta Research Tools Manager, reviewed by CASD [https://transparency.meta.com/researchtools/meta-content-library/] | Academic or not-for-profit research affiliation only, not companies or cities. **TUM could apply** with a research proposal. Fees: free per Bellingcat summary [REPORTED], one source warns of fees. Data must stay inside the secure environment, no local download [REPORTED] | Weeks to months [NOT KNOWN] | **With contract** (research access). For the city's own live tool: use the vendor (2.8) |
| **TikTok** (20 records in the dataset) | Terms forbid scraping | **TikTok Research API.** Non-profit and independent research bodies in the EU (and US); proposal, funding disclosure, ethics evidence [https://developers.tiktok.com/products/research-api, REPORTED; sources disagree on regions] | Free; not for commercial or city operations | 3 to 4 weeks reply [REPORTED] | **With contract** (research access). Likely not for the city |
| **X (Twitter)** (no X domain in the dataset) | Terms forbid scraping | **X API pay per use**. About $0.005 per post read, cap about 3 million reads per month, full-archive search needs an upgrade or Enterprise (about $42,000 per month) [REPORTED, third-party blogs; check developer.x.com] | Any developer, pay as you go | Same day to a few days | **With key (paid)**. Low value for this topic (German cable car talk on X is not in the dataset), skip |
| **Reddit** (68 records) | HTML scraping and scraper vendors are risky (Reddit sued SerpApi, Perplexity and others, see STADT_TECH_LIVE A1) | **Reddit Data API**, free for approved non-commercial use, about 100 queries per minute per client [REPORTED]. Commercial use needs an agreement. "Reddit for Researchers" for academic projects [REPORTED]. Two sources say new access requests closed 31 Oct 2026 [REPORTED, unconfirmed] | Approval needed, not a key | Weeks | **With contract**. Our search found no Heilbronn Reddit threads, so low value |
| **LinkedIn** (27 records) | No public keyword search API. Community Management API covers organisation pages with approval, "member read" is closed [REPORTED] | None for public discussion. Vendor products that index Google-visible posts exist but are outside LinkedIn's API | | | **No** |
| **Quora** | No public API and no data programme found; terms forbid scraping | None known | | | **No** (NOT KNOWN whether a licence exists) |
| **WhatsApp** | Private messaging, no public content | None | | | **No** |

### 2.6 The city's existing vendor

The city's export is named `FSI_Heilbronn_Medienbeiträge (1).json`. Fields: `mention_id` (looks like `25694641,15827`), `media_type_id` and `media_type_name` (12 types: News, Other, YouTube Video, Pictures, YouTube Comments, Forums, Blog, Comments, Social Network, Microblog, Video, Consumer), `source_name`, `url`, `country_code`, `language_code`, `sentiment` (1, 0, -1, -99), `reach`, `engagements`, `authors`, `title`, `content`.
**Which vendor produced it is NOT KNOWN.** I found no public schema that matches these type names and the `mention_id` pattern (a search listed Determ, Talkwalker and Brandwatch only as general examples, none matched). "FSI" is unexplained. This is open question 7 and 8 in `KNOWLEDGE_STADT_HEILBRONN.md`. **Action for Sunday: ask the city's contact one question: "Which tool made the FSI export, and does your licence include its API?"**
If the city has a social-listening or press-monitoring licence, its API is the production route and the best answer for Instagram, Facebook, TikTok, Reddit, LinkedIn and YouTube comments, because the vendor already holds the platform agreements. Reference prices if the city has none and wants one (REPORTED, quote based): Meltwater about $10k (Starter), $25k (Pro) per year, API on Enterprise and Agency tiers only; Talkwalker median about $13k to $27k per year with a credit-based Search API; Brandwatch about $50k per year with the API as a contract item.

### 2.7 Summary of legal gaps

| Gap | Today (open sources) | Closed by |
|---|---|---|
| Instagram and Facebook | 0 | City vendor API; Meta Content Library (research) |
| YouTube comments | 0 | YouTube Data API key (free, 3 to 4 h) |
| TikTok, Reddit, LinkedIn, X | 0 | Vendor API; research programmes; skip X and LinkedIn |
| Stimme and echo24 text | headlines via Google News | Stimme Mediengruppe feed licence |
| Bonn council papers | none (gated) | Bonn digital office allow-list or lifted gate |
| Citizen participation comments | none | Operator export |

## 3. Test volumes (60 days, since 15 Sep 2026, no-key legal sources)

Run: `python run_collect.py --since 2026-09-15 --db data/volume_test.db --examples 3` on 14 Nov 2026 (RSS, OParl, Bluesky, Mastodon, Google News; GDELT failed with HTTP 429). Counts are items kept by the collector. For Google News "title hit" means the headline itself names the project (Google matched the article body, the collector sees only the headline); the rest are possible, not confirmed, project items and go to the team's pipeline for the relevance label.

| Source | Heilbronn cable car | Bonn cable car | Paris C1 | IPAI | Date range | Example titles (3 max) |
|---|---|---|---|---|---|---|
| GDELT | not available (429) | not available | not available | not available | | not tested live |
| Google News RSS | 4 (0 title hits) | 4 (0 title hits) | 16 (6 title hits) | 18 (3 title hits) | 15 Sep to 11 Nov | HN: "Mit der Seilbahn durch die Stadt – Bald auch in Deutschland?" (SWR); Paris: "Câble C1 : une cavité près d'un pylône, trois stations à l'arrêt" (laclepublique.fr); IPAI: "Ipai in Heilbronn wächst rasant: Land fördert KI-Projekt mit zehn Millionen Euro" (Stimme) |
| Outlet and city RSS (5 feeds) | 0 | 0 | 0 | 0 | feeds hold only the latest 8 to 82 items; all 5 answered OK | |
| Heilbronn OParl | 2 papers | gated | n/a | 5 papers | 2024-06 to 2026-09 (paper dates; all modified after 15 Sep) | "Urbane Seilbahn: Ergebnisse der Machbarkeitsstudie und Planungsvereinbarung (193/2026)"; "Urbane Seilbahn Heilbronn: Vorprojektbeschluss (061/2025)"; IPAI: "Benennung eines Areals ... im Innovationspark Steinäcker (241/2026)" |
| Bluesky | 0 | 0 | 2 | 2 | 16 Sep to 9 Nov | Paris: "Val-de-Marne : le câble C1 interrompu après un incident sur un chantier voisin" (news post) |
| Mastodon (2 instances, tags) | 1 | 1 | 0 | 0 | 14 to 20 Oct | one German post each, both only loosely about the project (noise) |
| openPetition (sitemap) | 0 | 0 | n/a | 0 | | none relevant |

Reading: the open, free, legal sources give a **handful of items per project and month**, mostly news headlines. The city dataset had thousands of social items. Almost all of the missing social volume sits behind Meta, TikTok, Reddit and YouTube, so the live tool without a vendor feed will show news, official events and council papers, not the social debate.

## 4. Real run since 27 Oct 2026

See the end of this file (section 6), filled from `live/out/run_log.jsonl`.

## 5. Scheduling and health

See `live/README.md`. Short version: run every 14 days with `--since` 45 days back (the store is idempotent), run `--health` after it, review the log. RSS feeds hold only a few days of items, so for outlet feeds a daily run is better than a monthly one, or accept that Google News and GDELT carry the news coverage.

## 6. Real run counts

Run: `python run_collect.py --since 2026-10-27 --examples 3`, 14 Nov 2026, about 19:15 IST. Output `live/out/raw_live.json` (27 records), store `live/data/live.db`, log `live/out/run_log.jsonl`. Checked: the team's `normalise()` from `pipeline/stages/s01_ingest.py` accepts the file unchanged (27 rows, 25 flagged `new_since_dataset`; the 2 others are 27 Oct before 12:29 UTC). A second run created 0 new rows (idempotent, 34 rows in the store).

| Source | Heilbronn cable car | Bonn cable car | Paris C1 | IPAI | Errors |
|---|---|---|---|---|---|
| GDELT | not available | not available | skipped | skipped | HTTP 429 on every call from this network |
| Google News RSS | 1 (0 title hits) | 1 (0 title hits) | 12 (6 title hits) | 11 (0 title hits) | none |
| Outlet and city RSS | 0 | 0 | 0 | 0 | none, 5 of 5 feeds OK |
| Heilbronn OParl | 2 papers (dated before 27 Oct, kept in the store, not in the export) | gated | 0 | 5 papers (same) | Bonn gated, not bypassed |
| Bluesky | 0 | 0 | 2 | 0 | none |
| Mastodon | 0 | 0 | not run | not run | `troet.cafe` HTTP 422 on tag timelines; `mastodon.social` answered with 0 matches since 27 Oct |
| **Exported total** | **1** | **1** | **14** | **11** | 27 |

Reading, with limits:
- Only Paris C1 shows a clear live signal: 8 items whose headline names the project (closure and cavity near a pylon, 6 to 11 Nov, Le Parisien, actu.fr, La Clépublique, 2 Bluesky news posts). This matches the event found in `STADT_TECH_LIVE.md` A3.
- Heilbronn and Bonn cable car: 0 headline-level items since 27 Oct. The two Google News hits are false positives (ETH professors for Heilbronn; a San Francisco museum). "No news" is **not proven**: GDELT, the second news source, was not reachable, and the Heilbronn Stimme sits behind a paywall that Google News shows only as a headline.
- IPAI: 11 Google News items, none with the project name in the headline (event listings, Stimme "Roboter-Hotspot"). They are weak candidates for the team's relevance label.
- Social: 2 posts in total, both news posts. No citizen voice came from the open sources. This is the gap to close (section 2.5).
- Google News wide net: the collector keeps items whose body matched but the headline did not, flagged `title_hit=false` in the export, so the team's pipeline or the dashboard can filter them.
