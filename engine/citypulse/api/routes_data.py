"""Endpoints answered from the store alone: health, meta, overview, trends, posts, argument families, cross-city statistics."""
import pandas as pd
from fastapi import APIRouter, Depends, Query

from . import meta as meta_mod
from . import stats
from .common import (CODEBOOK, ApiError, Filters, S, check_project, claim_cards, filter_claims, filter_posts, has_arguments,
                     no_arguments_note, post_cards)

router = APIRouter(prefix="/api")


@router.get("/health", tags=["status"])
def health():
    return meta_mod.health(S())


@router.get("/meta", tags=["status"])
def meta():
    return meta_mod.meta(S())


@router.get("/overview", tags=["statistics"])
def overview(f: Filters = Depends()):
    st = S()
    return stats.overview(st, f.validate(st))


@router.get("/trends", tags=["statistics"])
def trends(f: Filters = Depends(), granularity: str = Query("week", description="week | month")):
    st = S()
    if granularity not in stats.PEAK_PARAMS:
        raise ApiError(422, "invalid_parameter", f"'granularity' must be week or month; got '{granularity}'.")
    return stats.trends(st, f.validate(st), granularity)


@router.get("/crosscity", tags=["statistics"])
def crosscity(f: Filters = Depends()):
    st = S()
    return stats.crosscity(st, f.validate(st))


# ---------------------------------------------------------------- posts

@router.get("/posts", tags=["posts"])
def posts(f: Filters = Depends(), q: str | None = Query(None, description="words that must appear in title or excerpt"),
          limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
          unique: bool = Query(False, description="true: leave out re-published copies")):
    st = S()
    df = filter_posts(st, f.validate(st))
    if unique:
        df = df[df.is_first_copy]
    q = (q or "").strip()
    if q:
        for word in q.split():
            df = df[df.title.fillna("").str.contains(word, case=False, regex=False) | df.excerpt.fillna("").str.contains(word, case=False, regex=False)]
    total = int(len(df))
    page = df.sort_values(["published_at", "doc_id"], ascending=[False, True]).iloc[offset:offset + limit]
    out = {"total": total, "limit": limit, "offset": offset, "items": post_cards(page), "filters": {**f.active(), **({"q": q} if q else {})}}
    if f.project and not has_arguments(st, f.project):
        out["has_arguments"] = False
        out["notes"] = [no_arguments_note(st, f.project)]
    return out


def post_detail(st, doc_id: str) -> dict:
    if doc_id not in st.posts_by_id.index:
        raise ApiError(404, "unknown_post", f"No post with doc_id '{doc_id}'.")
    row = st.posts[st.posts.doc_id == doc_id].head(1)
    card = post_cards(row)[0]
    r = row.iloc[0]
    claims = st.claims[st.claims.doc_id == doc_id].sort_values("cid")
    copies = st.posts[(st.posts.dup_key == r.dup_key) & (st.posts.doc_id != doc_id)]
    card["claims"] = claim_cards(claims)
    card["classifications"] = {"project": card["project"], "project_name": card.get("project_name"), "stance": card["stance"], "tone": card["tone"],
                               "passing": card["passing"], "label_source": card["label_source"], "codebook": CODEBOOK,
                               "note": "AI labels, not human-validated."}
    card["duplicates"] = int(len(copies))
    card["duplicate_doc_ids"] = copies.doc_id.head(50).tolist()
    card["is_first_copy"] = bool(r.is_first_copy)
    card["published_at"] = r.published_at.isoformat() if not pd.isna(r.published_at) else None
    card["has_arguments"] = has_arguments(st, r.project)
    card["notes"] = [] if card["has_arguments"] else [no_arguments_note(st, r.project)]
    return card


@router.get("/posts/{doc_id:path}", tags=["posts"])
def post(doc_id: str):
    return post_detail(S(), doc_id)


# ---------------------------------------------------------------- argument families

@router.get("/arguments/families", tags=["arguments"])
def families(f: Filters = Depends(), q: str | None = Query(None, description="words in the family name or in one of its claims"),
             limit: int = Query(500, ge=1, le=2000)):
    st = S()
    f.validate(st)
    claims = filter_claims(st, f)
    spread = filter_claims(st, f.without("project"))            # by_project always shows the spread over all projects
    rows = stats.family_table(st, claims, spread=spread)
    q = (q or "").strip().lower()
    if q:
        fam_claims = claims[stats.is_family(claims)]
        text = fam_claims.groupby("family_id").claim.agg(lambda s: " \n ".join(s)).str.lower()
        rows = [r for r in rows if all(w in r["name"].lower() or w in text.get(r["family_id"], "") for w in q.split())]
    out = {"total": len(rows), "items": rows[:limit], "filters": {**f.active(), **({"q": q} if q else {})},
           "notes": stats.ARGUMENT_NOTES + ["n, pro, contra, first_seen and last_seen describe the claims inside the filters; "
                                            "by_project shows the family's claims in every project."]}
    out["has_arguments"] = has_arguments(st, f.project) if f.project else bool(len(st.claims))
    if f.project and not out["has_arguments"]:
        out["notes"].insert(0, no_arguments_note(st, f.project))
    return out


@router.get("/arguments/families/{family_id:path}", tags=["arguments"])
def family(family_id: str, project: str | None = Query(None, description="only list claims of this project")):
    st = S()
    check_project(st, project)
    claims = st.claims[st.claims.family_id == family_id]
    if len(claims) == 0:
        raise ApiError(404, "unknown_family", f"No argument family with id '{family_id}'.")
    row = stats.family_table(st, claims, only_families=False)[0]
    row["is_family"] = not family_id.startswith("solo:")
    shown = claims[claims.project == project] if project else claims
    row["claims"] = claim_cards(shown.sort_values(["date", "cid"]))
    row["n_claims_listed"] = len(row["claims"])
    row["notes"] = list(stats.ARGUMENT_NOTES)
    return row
