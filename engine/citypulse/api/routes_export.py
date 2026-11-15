"""/api/export/briefing: a briefing assembled from the current data at request time.

Nothing in the text is a stored conclusion: every number is computed by the same functions that serve /api/overview and
/api/emerging, each share carries n and its interval, and each concern links to the posts it rests on.
"""
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

from . import meta as meta_mod
from . import stats
from .common import ApiError, Filters, S, clean, engine_call, project_name
from .routes_engine import CONCERN_STATES, check_cutoff, check_project

router = APIRouter(prefix="/api")

STATE_TEXT = {
    "new_emerging": "New arguments raised by two or more independent voices",
    "gaining": "Known arguments that are significantly more frequent than in their own past",
    "new_single": "New arguments with one voice so far (candidates, not findings)",
    "ambiguous": "Needs review: may be new or a variant of a known argument",
    "recurring": "Known arguments seen again",
}
STATE_ORDER = ["new_emerging", "gaining", "new_single", "ambiguous", "recurring"]
MAX_PER_STATE_MD, MAX_EVIDENCE_MD = 10, 4


def _pct(x):
    return "n/a" if x is None else f"{x:.0%}"


def _count(n, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _share(s: dict) -> str:
    if not s or not s.get("n"):
        return "no share (n = 0)"
    return f"{_pct(s['value'])} (95% interval {_pct(s['lo'])} to {_pct(s['hi'])}, n = {s['n']})"


def _filters(project) -> Filters:
    f = Filters.__new__(Filters)
    f.project, f.from_, f.to, f.channel, f.topic, f.stance, f.run_id = project, None, None, None, None, None, None
    return f


def build(st, project, cutoff, base_url="") -> dict:
    ov = stats.overview(st, _filters(project))
    post_link = lambda doc_id: f"{base_url}/api/posts/{quote(str(doc_id), safe='')}"
    concerns_block = {"available": False, "cutoff": cutoff, "by_state": {}, "counts": {}, "message": None}
    arguments_ok = project is None or ov.get("has_arguments")
    if not arguments_ok:
        concerns_block["message"] = f"No arguments have been extracted for {project_name(st, project)}; emerging concerns cannot be computed."
    else:
        try:
            items = clean(engine_call("replay", "concerns", project=project, cutoff=cutoff), st)
            concerns_block["available"] = True
            for s in STATE_ORDER + sorted({c.get("state") for c in items} - set(STATE_ORDER) - {None}):
                group = []
                for c in (x for x in items if x.get("state") == s):
                    ev = [{"cid": m.get("cid"), "claim": m.get("claim"), "date": m.get("date"), "domain": m.get("domain"), "doc_id": m.get("doc_id"),
                           "url": m.get("url"), "post": post_link(m.get("doc_id"))} for m in c.get("claims", []) if isinstance(m, dict)]
                    group.append({"concern_id": c.get("concern_id"), "state": s, "label": c.get("label"), "project": c.get("project"),
                                  "project_name": project_name(st, c.get("project")), "first_seen": c.get("first_seen"), "flagged_at": c.get("flagged_at"),
                                  "n_claims": c.get("n_claims"), "n_voices": c.get("n_voices"), "polarity": c.get("polarity"),
                                  "uncertainty": c.get("uncertainty"), "new_anywhere": c.get("new_anywhere"), "evidence": ev,
                                  "n_cases_elsewhere": len(c.get("elsewhere") or [])})
                concerns_block["by_state"][s] = group
                concerns_block["counts"][s] = len(group)
        except ApiError as e:
            concerns_block["message"] = f"Emerging concerns are not available right now: {e.message}"
    data = {"title": "CityPulse briefing", "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_version": st.data_version, "project": project, "project_name": project_name(st, project) if project else "All projects",
            "cutoff": cutoff, "period": {"from": st.posts.date.min(), "to": st.posts.date.max()},
            "overview": {k: ov[k] for k in ("n_posts", "n_unique_posts", "n_voices", "n_counted", "n_with_stance", "stance_counts", "opposition_share",
                                            "support_share", "channel_counts", "top_sources", "n_claims", "has_arguments")},
            "topic_shares": ov["topic_shares"], "top_arguments": ov["top_arguments"], "concerns": concerns_block,
            "state_definitions": STATE_TEXT, "limitations": meta_mod.limitations(st),
            "definitions": stats.STANCE_NOTES + stats.ARGUMENT_NOTES,
            "sources": {"overview": "/api/overview" + (f"?project={project}" if project else ""),
                        "concerns": f"/api/emerging?cutoff={cutoff}" + (f"&project={project}" if project else ""), "posts": "/api/posts/{doc_id}"}}
    data["markdown"] = markdown(data)
    return data


def markdown(d: dict) -> str:
    o, L = d["overview"], []
    L += [f"# CityPulse briefing: {d['project_name']}", "",
          f"Generated {d['generated_at']} from data version {d['data_version']} (posts from {d['period']['from']} to {d['period']['to']}). "
          f"All figures below were computed from the stored data when this briefing was requested.", "",
          "> Observable online debate, not a representative poll. Labels and scores come from AI models and are provisional "
          "(agreement with AI reference labels, not human-validated).", ""]
    L += ["## The debate in numbers", "",
          f"- Posts collected: {o['n_posts']} ({o['n_unique_posts']} unique texts, {o['n_voices']} independent voices).",
          f"- Unique posts that are about the project (not passing mentions): {o['n_counted']}. "
          + ", ".join(f"{k} {v}" for k, v in o["stance_counts"].items()) + ".",
          f"- Posts that take a side (support, oppose or mixed): {o['n_with_stance']}.",
          f"- Opposition share among posts that take a side: {_share(o['opposition_share'])}.",
          f"- Support share among posts that take a side: {_share(o['support_share'])}.",
          "- Channels: " + (", ".join(f"{k} {v}" for k, v in o["channel_counts"].items()) or "none") + ".",
          "- Most frequent sources: " + (", ".join(f"{s['domain']} ({s['n']})" for s in o["top_sources"][:5]) or "none") + ".", ""]
    L += ["## Arguments", ""]
    if not o["has_arguments"]:
        L += ["No arguments have been extracted for this selection.", ""]
    else:
        L += [f"{o['n_claims']} claims were extracted from these posts.", "", "| Topic | Claims | Pro | Contra | Neutral |", "|---|---:|---:|---:|---:|"]
        L += [f"| {t['topic']} | {t['n']} | {t['pro']} | {t['contra']} | {t['neutral']} |" for t in d["topic_shares"]]
        L += ["", "Largest argument families (number of claims):", ""]
        L += [f"- {a['name']}: {a['n']} claims ({a['pro']} pro, {a['contra']} contra), first seen {a['first_seen']}, last seen {a['last_seen']}." for a in d["top_arguments"]]
        L += [""]
    c = d["concerns"]
    L += [f"## Current concerns (replay from {d['cutoff']})", ""]
    if not c["available"]:
        L += [c["message"] or "Not available.", ""]
    else:
        L += ["The system was frozen at the cutoff date; later claims were then compared with everything published before them. "
              "Counts per state: " + ", ".join(f"{s} {n}" for s, n in c["counts"].items()) + ".", ""]
        for s, group in c["by_state"].items():
            L += [f"### {STATE_TEXT.get(s, s)} ({len(group)})", ""]
            if not group:
                L += ["None.", ""]
                continue
            for g in group[:MAX_PER_STATE_MD]:
                u = g.get("uncertainty") or {}
                bits = [_count(g["n_claims"], "claim"), _count(g["n_voices"], "voice"), f"first seen {g['first_seen']}"]
                if g.get("flagged_at"):
                    bits.append(f"flagged {g['flagged_at']}")
                if u.get("novelty_score") is not None:
                    bits.append(f"novelty score {u['novelty_score']}")
                if u.get("p_value") is not None:
                    bits.append(f"p = {u['p_value']}")
                L.append(f"- **{g['label']}** ({g['project_name']}; {', '.join(bits)})" + (f". Note: {u['note']}." if u.get("note") else ""))
                for e in g["evidence"][:MAX_EVIDENCE_MD]:
                    L.append(f"  - {e['date']}, {e['domain']}: \"{e['claim']}\" [source]({e['url']}) · [stored post]({e['post']})")
                if len(g["evidence"]) > MAX_EVIDENCE_MD:
                    L.append(f"  - and {len(g['evidence']) - MAX_EVIDENCE_MD} more claims (see the JSON format).")
            if len(group) > MAX_PER_STATE_MD:
                L.append(f"- and {len(group) - MAX_PER_STATE_MD} more in this state (see the JSON format or /api/emerging).")
            L.append("")
    L += ["## Limitations", ""] + [f"- {x}" for x in d["limitations"]] + [""]
    L += ["## How the numbers are defined", ""] + [f"- {x}" for x in d["definitions"]] + [""]
    return "\n".join(L)


@router.get("/export/briefing", tags=["export"])
def briefing(request: Request, project: str | None = None, cutoff: str | None = None, format: str = Query("md", description="md | json")):
    st = S()
    if format not in ("md", "json"):
        raise ApiError(422, "invalid_parameter", f"'format' must be md or json; got '{format}'.")
    project = check_project(st, project or None)
    cutoff = check_cutoff(st, cutoff)
    data = build(st, project, cutoff, base_url=str(request.base_url).rstrip("/"))
    if format == "json":
        return data
    name = f"citypulse_briefing_{project or 'all'}_{cutoff}.md"
    return PlainTextResponse(data["markdown"], media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'inline; filename="{name}"'})
