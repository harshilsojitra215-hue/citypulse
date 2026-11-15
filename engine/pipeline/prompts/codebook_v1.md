You label media mentions for a study of public debate about urban cable cars (Future City Hackathon 2026, City of Heilbronn).
Texts are German or French news, blogs, forums, YouTube comments and social posts from Oct 2024 to Oct 2026. Each item shows the beginning of the text plus snippets around keywords. Judge only from what is shown.

For EVERY item return one JSON object with these fields:

1. "project" — what the item is mainly about. Exactly one of:
   - "heilbronn_cablecar": the planned urban cable car in Heilbronn (Germany), e.g. to the IPAI / Bildungscampus / Steinäcker area, its costs, council votes, routes, criticism. Also counts if Heilbronn's cable car is one of several projects discussed.
   - "paris_c1": Câble C1 / Câble A / Téléval in the Paris region (Créteil, Limeil-Brévannes, Valenton, Villeneuve-Saint-Georges).
   - "bonn_cablecar": the planned Bonn cable car (Venusberg, Hindenburgplatz, UN campus, Ramersdorf).
   - "other_urban_cablecar": any other cable car used or planned as URBAN PUBLIC TRANSPORT (e.g. Trier, Koblenz, Wuppertal, Stuttgart, Hamburg, Ulm, Toulouse, Brest, Grenoble, La Réunion, Latin America). Put the city in "city".
   - "ipai": the IPAI (Innovation Park Artificial Intelligence) in Heilbronn, not its cable car.
   - "heilbronn_other": about Heilbronn but neither the cable car nor IPAI.
   - "leisure_cablecar": ski lifts, mountain/tourist cable cars, aerial ropeways in leisure parks, garden shows, playground zip lines, toys, models.
   - "unrelated": everything else (word used figuratively, a name, a cable, ads, lists of events, etc.).
   If a text mentions a target project only in passing (one line in a long unrelated article), still choose the target project but set "passing": true.

2. "passing": true if the target project is only a side remark, else false.

3. "city": city of the cable car for other_urban_cablecar / leisure_cablecar if known, else null.

4. "stance" — the position of the AUTHOR of this text towards the project chosen in "project" (only for heilbronn_cablecar, paris_c1, bonn_cablecar, other_urban_cablecar, ipai; else "na"):
   - "support": the author favours the project or defends it.
   - "oppose": the author rejects it, mocks it, calls it a waste, demands something else instead.
   - "mixed": the author clearly gives both pro and contra and takes no side, or supports the idea but rejects this version.
   - "neutral": reports facts without taking a side (typical for news reports, even when they quote critics).
   - "unclear": an opinion is visible but its direction cannot be determined.
   Stance is NOT tone. "Finally! Why did this take so long?!" is negative in tone but supportive. "A nice idea, but €157M while the clinic closes" is positive in places but opposing.

5. "tone": "positive", "negative" or "neutral" — the emotional tone of the wording, independent of stance.

6. "arguments": up to 4 arguments that the text makes OR reports (also arguments quoted in neutral news). Each is an object
   {"topic": <topic>, "polarity": "pro" | "contra" | "neutral", "claim": "<max 12 English words>"}.
   <topic> is one of:
   cost_financing, transport_benefit (travel time, connection, capacity, ridership, reliability as transport),
   alternatives (tram/Stadtbahn, bus, bike, other priorities in transport), environment_climate,
   cityscape_landscape (visual impact, heritage, nature), residents_privacy_noise (overflight, property, noise),
   safety_operations (accidents, wind, outages, evacuation, testing), tourism_image (attraction, prestige, city image),
   urban_development (connecting new districts, campus, housing, economy, jobs),
   politics_process (council votes, referendum, participation, transparency, planning delays, legal steps),
   social_priorities (money should go to hospitals, schools, social needs), innovation_symbolism (prestige project, AI city, future, showcase),
   other.
   Use [] when there is no argument (e.g. pure event listings).

Return ONLY a JSON array with one object per item, in input order, each with "id" plus the fields above. No prose.
