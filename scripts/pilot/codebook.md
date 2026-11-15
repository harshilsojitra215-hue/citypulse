# Codebook v1 (frozen): public debate on urban cable cars

Task: for each post, read `text` only (title + snippet). Decide five things. Judge only what the text says, not what you know about the project. If the text does not show it, use `unclear`. Do not guess.

Output, one JSON object per line, one line per post:

```json
{"pid":"P001","project":"...","stance":"...","arguments":["..."],"voice":"...","evidence":"..."}
```

Use only the values listed below, spelled exactly. Several posts can be about the same project; each post gets one `project` (the main one).

## 1. `project`: which project is this post about?

| Value | Meaning |
|---|---|
| `heilbronn_cablecar` | The planned urban cable car in Heilbronn (city centre to IPAI). |
| `bonn_cablecar` | The planned cable car in Bonn (Venusberg, university hospital, Rhine crossing, Beuel). |
| `paris_c1` | The Paris-region cable car Câble C1 (Créteil, Limeil-Brévannes, Villeneuve-Saint-Georges), already operating. |
| `ipai` | The Innovation Park Artificial Intelligence (IPAI) campus in Heilbronn, its construction, firms, jobs. |
| `other_cablecar` | A cable car in another place (Stuttgart, Cologne, Mexico, Medellin, Wuppertal BUGA, ...). Tourist or ski lifts are `irrelevant`. |
| `irrelevant` | Not about any of these: ski lifts, mountain railways, playground "Seilbahn", travel tips, accident of an alpine lift, another meaning of Heilbronn or IPAI. |

- Example: "Heilbronn sagt Ja zur Seilbahn-Idee" -> `heilbronn_cablecar`.
- Boundary rule: if a post covers two projects, pick the one the post spends most words on (title counts). A Heilbronn article about the Paris study trip is `heilbronn_cablecar`. A post that only lists Heilbronn in passing (one word in a link list, a sidebar) is `irrelevant`. A post about IPAI that mentions the cable car as the main point is `heilbronn_cablecar`; if the cable car is a side remark in an IPAI article, use `ipai`.

## 2. `stance`: what attitude toward that project does the post show?

Stance is the attitude toward the project, not the mood of the words. When `project` is `irrelevant`, stance is always `unclear`. For `other_cablecar`, label the stance toward that other project as usual.

| Value | Meaning |
|---|---|
| `support` | The post favours the project, wants it built or kept, praises it, or asks for it (also when the words sound angry). |
| `oppose` | The post wants it stopped, changed fundamentally, or calls it wasteful or wrong (also when the words sound calm). |
| `neutral_informative` | Reports facts, decisions, dates, figures, job ads, press releases, or asks a neutral question, without the author taking a side. |
| `mixed` | The author clearly weighs pros and cons, or supports one part and rejects another (for example: yes to the cable car, no to the cost). |
| `unclear` | A side cannot be seen: too short, a link only, a joke that could go either way, off topic, or the project is `irrelevant`. |

- Example: "Das wird wieder nichts. Das ist wieder so ein Sinnlosprojekt" -> `oppose`.
- Boundary rules:
  1. Reporting a council decision, a figure, or a quote of a politician = `neutral_informative`, unless the outlet itself takes a position (commentary, opinion headline, loaded words).
  2. A negative-sounding complaint that asks for the cable car ("the bus is always full, we need the Seilbahn now") = `support`. A positive-sounding text about the same project that wants it stopped ("lovely idea, but please spend the money on doctors") = `oppose`.
  3. Official city, state or company pages that promote the project = `support` only if they argue for it with praise or advocacy; plain fact lists stay `neutral_informative`.
  4. A neutral question ("where will cars park?") = `neutral_informative`, not `oppose`.
  5. Criticism of cost, process or route only, while saying the idea is good = `mixed`.

## 3. `arguments`: which arguments appear? (multi-label, list, 0 to 4 codes)

Mark a code only if the post itself raises that point (for or against). Use `[]` if none or if the post is `irrelevant`. If you are unsure, leave it out. Use `other` only for a clear argument that has no code.

| Code | Meaning | Example |
|---|---|---|
| `cost` | Price, budget, funding, value for money, "157 Millionen". | "157 Millionen Euro für eine Seilbahn" |
| `climate_environment` | Emissions, energy, green space, nature, "klimaschonend". | "Elektrisch, leise, spart Autos" |
| `traffic_mobility` | Travel time, capacity, relief of roads, links to rail, alternatives (tram, bus), parking. | "Warum nicht die Stadtbahn?" |
| `noise_privacy_overflight` | Noise, being looked into from gondolas, flying over homes, neighbours. | "Kabinen über unseren Gärten" |
| `cityscape_design` | Look of the city, towers and masts, landmarks, urban planning, heritage. | "Masten verschandeln das Stadtbild" |
| `safety_technology` | Safety, accidents, reliability, weather, technical feasibility, operator. | "Was passiert bei Sturm?" |
| `ipai_who_benefits` | Link to IPAI, the Schwarz foundation, jobs, who profits, whether it serves residents or the campus. | "Eine Seilbahn nur für den KI-Park" |
| `process_participation` | Transparency, citizen involvement, decisions behind closed doors, planning steps, politics of the decision. | "Ohne Transparenz droht eine Hängepartie" |
| `tourism_image` | Attraction for visitors, city image, "Zukunftsstadt", prestige project. | "Prestigeprojekt des OB" |
| `other` | A clear argument with no code above. | |

- Boundary rule: one sentence can carry two codes (cost + traffic_mobility) only if it really says both. "Prestigeprojekt" alone = `tourism_image`; add `cost` only if money is mentioned. Pure facts ("4.9 km, 6 stations") are not arguments: `[]`.

## 4. `voice`: who is speaking?

| Value | Meaning |
|---|---|
| `news_institutional` | Newspaper, broadcaster, news agency, trade magazine, official blog of an institution that reports. |
| `politician_official` | A politician, party, city, ministry, or authority speaking for itself (press release, official site, party Instagram). |
| `citizen` | A private person: comment, forum post, personal blog, private social post. |
| `company_vendor` | A firm or its brand: manufacturer, consultancy, job ad, tender, PR of a company or the IPAI network. |
| `unclear` | Cannot be told. |

- Example: A YouTube comment "Und wo sollen dann die Autos parken?" -> `citizen`.
- Boundary rules: a news article that quotes a politician is `news_institutional`. A comment under a news article is `citizen` even if the topic is political. A party's Instagram account is `politician_official`. Rewrite sites with no named editorial team still count as `news_institutional`.

## 5. `evidence`: quote that justifies the stance

Copy at most 15 words from the text, verbatim (no changes, no translation), that best justify your `stance`. If `stance` is `unclear`, use `""`.

- Example: stance `oppose` -> `"Das ist wieder so ein Sinnlosprojekt"`.
- Boundary rule: do not paraphrase. If no quote carries the stance (neutral reporting), quote the sentence that shows the post is a report, or the key fact.

## General rules for all labelers

1. Read the text only. Do not search the web. Do not use any vendor sentiment (you do not have it).
2. The text is a short snippet; paywalled articles often show only a headline. Label what is visible.
3. French and German texts use the same codes.
4. Do not copy names or handles into `evidence` (text shows `[USER]`).
5. Label every post. Never skip.
