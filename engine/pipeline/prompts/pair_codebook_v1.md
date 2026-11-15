You compare short claims taken from public online posts about urban cable car projects (Heilbronn, Bonn, Paris Câble C1, other cities). Each claim is a one-line English summary of one argument or fact in a post. The project it was made about is shown in [brackets].

For each QUERY claim you get several CANDIDATE claims. Give every candidate exactly one label: what is its relation to the query?

- "same": both express the same argument or the same fact. A city analyst would file them under one heading and count them together. Wording, level of detail and language of the original do not matter.
  - For arguments (reasons for or against, concerns, hopes): the city does NOT matter. "Too expensive for what it delivers" about Bonn and about Heilbronn is the same argument.
  - For factual reports (a decision, a date, a cost figure, an incident): it must be the SAME fact or event. "Council approved planning" in Heilbronn and in Wuppertal are two different events, so they are "related", not "same". Two different cost figures are "related".
- "opposing": both address the same specific point but assert opposite things, or one directly rebuts the other. Example: "Cable car will relieve road traffic" vs "Cable car will not reduce car traffic"; "157 million is well spent" vs "157 million is excessive".
- "related": same sub-issue or closely connected, but a different point, a different fact, or only partial overlap. Example: "Project costs 157 million" vs "State pays most of the cost".
- "unrelated": different issue.

Rules
- Judge the point being made, not the wording. Shared words alone (a city name, "cable car", "cost") do not make claims the same.
- A general claim and a more specific version of the same point are "same" only if the specific one adds no new reason. "Money should go elsewhere" and "Money goes to the cable car while the hospital closes" are "related": the second names a new, concrete grievance.
- A neutral report that an actor holds a view ("Transport club prefers the Stadtbahn") and that view stated directly ("Extend the Stadtbahn instead") are "same".
- An opposite overall attitude is not enough for "opposing": the two claims must disagree about the same specific point. "A club criticises the plans" vs "The cable car is climate-friendly" is "related" at most. Only two overall verdicts with no specific point ("the project is a great opportunity" vs "the project is nonsense") count as "opposing".
- Sharing a theme (climate, cost, traffic) is not enough for "same": the reason given must be the same.
- If unsure between "same" and "related", choose "related".
- Do not use outside knowledge about how the projects turned out.

Output: only a JSON array, one object per query, no prose:
[{"q": "<query number>", "labels": {"a": "same|opposing|related|unrelated", "b": "...", ...}}, ...]
Every candidate letter of every query must appear.
