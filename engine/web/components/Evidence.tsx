"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useApi, withQuery } from "@/lib/api";
import type { ClaimCard, ClaimDetail, Concern, CrossCase, EventRef, FamilyDetail, Match, PostCard, PostDetail, PostsList } from "@/lib/types";
import { bestMatch, fmtDate, humanize, isHttpUrl, isVerified, num, score } from "@/lib/format";
import { useApp } from "./AppContext";
import { Badge, Button, DataState, Empty, N, PolarityCounts, ScoreScale, StateBadge } from "./ui";

/* ---------- what a drawer can show ---------- */

export type EvidenceSection =
  | { kind: "posts"; heading?: string; query: Record<string, string | number | undefined | null> }
  | { kind: "post"; heading?: string; doc_id: string }
  | { kind: "claims"; heading?: string; note?: string; claims: (ClaimCard | Match)[] }
  | { kind: "family"; family_id: string }
  | { kind: "claim"; cid: string }
  | { kind: "concern"; concern_id: string; project?: string; cutoff?: string; fallback?: Concern }
  | { kind: "cases"; heading?: string; cases: CrossCase[] };

export type EvidenceSpec = { title: string; subtitle?: string; sections: EvidenceSection[] };

const EvidenceCtx = createContext<{ open: (spec: EvidenceSpec) => void } | null>(null);

export function useEvidence() {
  const c = useContext(EvidenceCtx);
  if (!c) throw new Error("useEvidence must be used inside EvidenceProvider");
  return c.open;
}

/* ---------- small pieces ---------- */

function SourceLink({ url }: { url?: string }) {
  if (!isHttpUrl(url)) return <span className="text-xs text-slate-400">no link</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="text-xs font-medium text-teal-800 underline underline-offset-2 hover:text-teal-900">
      Open source ↗
    </a>
  );
}

export function VoiceTag({ voice }: { voice?: string }) {
  if (!voice) return null;
  return (
    <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600" title="Anonymous voice id (salted hash). Author names are never shown.">
      voice {voice}
    </span>
  );
}

export function RelationBadge({ relation }: { relation?: string }) {
  if (!relation || relation === "unscored") return null;
  return <Badge tone={relation === "equivalent" ? "teal" : relation === "related" ? "sky" : "gray"}>{humanize(relation)}</Badge>;
}

export function MatchScores({ m }: { m: Match }) {
  const parts: string[] = [];
  if (m.p_same !== null && m.p_same !== undefined) parts.push(`same ${score(m.p_same)}`);
  if (m.p_related !== null && m.p_related !== undefined) parts.push(`related ${score(m.p_related)}`);
  if (m.cos !== null && m.cos !== undefined) parts.push(`cosine ${score(m.cos)}`);
  if (!parts.length) return null;
  return (
    <span className="text-[11px] text-slate-500 tabular-nums">
      {parts.join(" · ")}
      {m.score_source ? <span className="ml-1 rounded bg-slate-100 px-1 py-0.5">{m.score_source}</span> : null}
    </span>
  );
}

/** One source post: date, domain, excerpt, link, classifications, label source. */
export function PostEvidenceCard({ post }: { post: PostCard | PostDetail }) {
  const { projectName } = useApp();
  const cls = (post as PostDetail).classifications;
  const stance = cls?.stance ?? post.stance;
  const tone = cls?.tone ?? post.tone;
  const project = cls?.project ?? post.project;
  const passing = cls?.passing ?? post.passing;
  const labelSource = cls?.label_source ?? post.label_source;
  const dups = (post as PostDetail).duplicates ?? (post.dup_count && post.dup_count > 1 ? post.dup_count - 1 : 0);
  return (
    <article className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600">
        <span className="font-semibold text-slate-900">{fmtDate(post.date)}</span>
        <span className="font-medium text-slate-800">{post.domain || post.source_name || "unknown source"}</span>
        {post.media_type || post.channel ? <span>{post.media_type || humanize(post.channel)}</span> : null}
        {post.lang ? <span className="uppercase">{post.lang}</span> : null}
        <VoiceTag voice={post.voice} />
        <span className="ml-auto">
          <SourceLink url={post.url} />
        </span>
      </div>
      {post.title ? <div className="mt-1.5 text-sm font-medium text-slate-900">{post.title}</div> : null}
      {post.excerpt ? <p className="mt-1 text-sm leading-relaxed text-slate-700">{post.excerpt}</p> : <p className="mt-1 text-sm text-slate-400">No excerpt available.</p>}
      <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-2">
        <span className="text-[11px] uppercase tracking-wide text-slate-400">AI labels</span>
        {project ? <Badge tone="white">{projectName(project)}</Badge> : null}
        {stance ? <Badge tone={stance === "oppose" ? "orange" : stance === "support" ? "teal" : "gray"}>stance: {stance}</Badge> : null}
        {tone ? <Badge tone="white">tone: {tone}</Badge> : null}
        {passing ? <Badge tone="white">mentioned in passing</Badge> : null}
        {labelSource ? (
          <Badge tone="violet" title="Which model assigned these labels. Not human-validated.">
            labelled by {labelSource}
          </Badge>
        ) : (
          <Badge tone="white">label source not given</Badge>
        )}
        {cls?.codebook ? <span className="text-[11px] text-slate-400">{cls.codebook}</span> : null}
        {dups > 0 ? <span className="text-[11px] text-slate-500">+{dups} republished {dups === 1 ? "copy" : "copies"} (counted once)</span> : null}
        {post.run_id ? <span className="text-[11px] text-slate-400">run {post.run_id}</span> : null}
      </div>
    </article>
  );
}

function LazyPost({ docId, auto }: { docId: string; auto: boolean }) {
  const [want, setWant] = useState(auto);
  const state = useApi<PostDetail>(want ? `/api/posts/${encodeURIComponent(docId)}` : null);
  if (!want) {
    return (
      <Button small kind="ghost" onClick={() => setWant(true)}>
        Show source post
      </Button>
    );
  }
  return (
    <DataState state={state} what="the source post" rows={2}>
      {(p) => <PostEvidenceCard post={p} />}
    </DataState>
  );
}

/** One claim with its own metadata, and the post it was extracted from. */
export function ClaimEvidenceCard({ claim, autoPost = true, onOpenClaim }: { claim: ClaimCard | Match; autoPost?: boolean; onOpenClaim?: boolean }) {
  const { projectName } = useApp();
  const m = claim as Match;
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-[0.95rem] font-medium leading-snug text-slate-900">“{claim.claim}”</p>
        <RelationBadge relation={m.relation} />
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600">
        <span className="font-medium text-slate-800">{fmtDate(claim.date)}</span>
        {claim.domain ? <span>{claim.domain}</span> : null}
        {claim.project ? <span>{claim.project_name || projectName(claim.project)}</span> : null}
        {claim.topic ? <Badge tone="white">{humanize(claim.topic)}</Badge> : null}
        {claim.polarity ? <Badge tone={claim.polarity === "contra" ? "orange" : claim.polarity === "pro" ? "teal" : "gray"}>{claim.polarity}</Badge> : null}
        <VoiceTag voice={claim.voice} />
        <MatchScores m={m} />
        <span className="font-mono text-[11px] text-slate-400">{claim.cid}</span>
      </div>
      {claim.family_name ? (
        <div className="mt-1 text-xs text-slate-500">
          Argument family: <span className="text-slate-700">{claim.family_name}</span>
        </div>
      ) : null}
      <div className="mt-2">
        {claim.doc_id ? (
          <LazyPost docId={claim.doc_id} auto={autoPost} />
        ) : (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            Source post id not provided. <SourceLink url={claim.url} />
          </div>
        )}
      </div>
      {onOpenClaim !== false ? (
        <div className="mt-2">
          <Link href={`/explorer?claim=${encodeURIComponent(claim.cid)}`} className="text-xs font-medium text-teal-800 underline underline-offset-2">
            Equivalent and related claims in the Argument Explorer →
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function EventLine({ e, label }: { e: EventRef; label?: string }) {
  const src = e.source ?? e.source_url;
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
      {label ? <span className="text-xs uppercase tracking-wide text-slate-400">{label}</span> : null}
      <span className="font-medium tabular-nums text-slate-800">{fmtDate(e.date)}</span>
      <span className="text-slate-700">{e.title ?? "(no title)"}</span>
      <Badge tone={isVerified(e.verified) ? "green" : "white"}>{isVerified(e.verified) ? "verified event" : "event not verified"}</Badge>
      {isHttpUrl(src) ? (
        <a href={src} target="_blank" rel="noopener noreferrer" className="text-xs text-teal-800 underline underline-offset-2">
          source ↗
        </a>
      ) : null}
    </div>
  );
}

export function EventList({ events, empty }: { events?: EventRef[]; empty?: string }) {
  if (!events?.length) return empty ? <p className="text-sm text-slate-500">{empty}</p> : null;
  return (
    <div className="space-y-1">
      {events.map((e, i) => (
        <EventLine key={i} e={e} />
      ))}
    </div>
  );
}

/** A similar claim in another project, with that project's stage then and what happened afterwards. */
export function CaseCard({ c, onEvidence }: { c: CrossCase; onEvidence?: () => void }) {
  const { projectName } = useApp();
  const claim = c.claim;
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="white">{claim?.project_name || projectName(claim?.project)}</Badge>
        <span className="font-medium text-slate-700">{fmtDate(claim?.date)}</span>
        <RelationBadge relation={c.relation} />
        {c.p_same !== null && c.p_same !== undefined ? <span className="text-slate-500 tabular-nums">same-argument score {score(c.p_same)}</span> : null}
        <span className="ml-auto rounded bg-slate-800 px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-white">Historical case, not a forecast</span>
      </div>
      <p className="mt-1.5 text-[0.95rem] font-medium leading-snug text-slate-900">“{claim?.claim ?? "(claim text missing)"}”</p>
      <div className="mt-2 space-y-1 border-l-2 border-slate-200 pl-3">
        {c.note ? <p className="text-sm text-slate-600">{c.note}</p> : null}
        {c.timeline_available === false ? (
          <p className="text-sm text-slate-500">No event timeline is recorded for this project, so its stage and later events cannot be shown.</p>
        ) : c.stage ? (
          <EventLine e={c.stage} label="Project stage then" />
        ) : (
          <p className="text-sm text-slate-500">Project stage at that time: not recorded.</p>
        )}
        {c.timeline_available === false ? null : c.after?.length ? (
          <>
            <div className="pt-1 text-xs uppercase tracking-wide text-slate-400">What happened there later</div>
            {c.after.map((e, i) => (
              <EventLine key={i} e={e} />
            ))}
          </>
        ) : (
          <p className="text-sm text-slate-500">No later events recorded for that project.</p>
        )}
      </div>
      {claim && onEvidence ? (
        <div className="mt-2">
          <Button small kind="ghost" onClick={onEvidence}>
            Source post
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/* ---------- drawer sections ---------- */

function ClaimsBlock({ heading, note, claims }: { heading?: string; note?: string; claims: (ClaimCard | Match)[] }) {
  const [limit, setLimit] = useState(25);
  return (
    <div>
      {heading ? (
        <h3 className="mb-1 flex items-baseline gap-2 text-sm font-semibold text-slate-900">
          {heading} <N n={claims.length} />
        </h3>
      ) : null}
      {note ? <p className="mb-2 text-xs text-slate-500">{note}</p> : null}
      {claims.length === 0 ? (
        <Empty>No claims in this list.</Empty>
      ) : (
        <div className="space-y-2">
          {claims.slice(0, limit).map((c, i) => (
            <ClaimEvidenceCard key={`${c.cid}-${i}`} claim={c} autoPost={i < 6} />
          ))}
          {claims.length > limit ? (
            <Button small onClick={() => setLimit((l) => l + 25)}>
              Show more ({claims.length - limit} left)
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}

function PostsBlock({ heading, query }: { heading?: string; query: Record<string, string | number | undefined | null> }) {
  const [limit, setLimit] = useState(20);
  const state = useApi<PostsList>(withQuery("/api/posts", { ...query, limit, offset: 0 }));
  return (
    <div>
      {heading ? <h3 className="mb-2 text-sm font-semibold text-slate-900">{heading}</h3> : null}
      <DataState state={state} what="source posts" isEmpty={(d) => !(d.items ?? []).length} empty="No posts match this selection.">
        {(d) => (
          <div className="space-y-2">
            <div className="text-xs text-slate-500">
              Showing {num((d.items ?? []).length)} of {num(d.total ?? (d.items ?? []).length)} posts
            </div>
            {(d.items ?? []).map((p) => (
              <PostEvidenceCard key={p.doc_id} post={p} />
            ))}
            {(d.total ?? 0) > (d.items ?? []).length ? (
              <Button small onClick={() => setLimit((l) => l + 20)}>
                Show more
              </Button>
            ) : null}
          </div>
        )}
      </DataState>
    </div>
  );
}

function PostBlock({ heading, doc_id }: { heading?: string; doc_id: string }) {
  const state = useApi<PostDetail>(`/api/posts/${encodeURIComponent(doc_id)}`);
  return (
    <div>
      {heading ? <h3 className="mb-2 text-sm font-semibold text-slate-900">{heading}</h3> : null}
      <DataState state={state} what="the source post">
        {(p) => (
          <div className="space-y-3">
            <PostEvidenceCard post={p} />
            {p.claims?.length ? (
              <div>
                <h4 className="mb-1 text-sm font-semibold text-slate-900">
                  Claims extracted from this post <N n={p.claims.length} />
                </h4>
                <ul className="space-y-1">
                  {p.claims.map((c) => (
                    <li key={c.cid} className="rounded border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-sm">
                      “{c.claim}”{" "}
                      <Link href={`/explorer?claim=${encodeURIComponent(c.cid)}`} className="text-xs text-teal-800 underline underline-offset-2">
                        open
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        )}
      </DataState>
    </div>
  );
}

function FamilyBlock({ family_id }: { family_id: string }) {
  const state = useApi<FamilyDetail>(`/api/arguments/families/${encodeURIComponent(family_id)}`);
  return (
    <DataState state={state} what="the argument family">
      {(f) => (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <N n={f.n ?? f.claims?.length} label="claims" />
            <PolarityCounts polarity={{ pro: f.pro ?? 0, contra: f.contra ?? 0 }} />
            {f.first_seen ? (
              <span>
                first seen {fmtDate(f.first_seen)}, last {fmtDate(f.last_seen)}
              </span>
            ) : null}
            <Link href={`/explorer?family=${encodeURIComponent(family_id)}`} className="font-medium text-teal-800 underline underline-offset-2">
              Open in Argument Explorer →
            </Link>
          </div>
          <ClaimsBlock heading="Claims in this family" claims={f.claims ?? []} />
        </div>
      )}
    </DataState>
  );
}

function ClaimBlock({ cid }: { cid: string }) {
  const state = useApi<ClaimDetail>(`/api/claims/${encodeURIComponent(cid)}`);
  return (
    <DataState state={state} what="the claim">
      {(d) => (
        <div className="space-y-4">
          {d.claim ? <ClaimEvidenceCard claim={d.claim} autoPost={!d.post} /> : null}
          {d.post ? <PostEvidenceCard post={d.post} /> : null}
          <ClaimsBlock heading="Equivalent claims" note="The matcher scores these as the same argument." claims={d.equivalent ?? []} />
          <ClaimsBlock heading="Related claims" note="Same sub-issue, a different point. Not counted as the same argument." claims={d.related ?? []} />
        </div>
      )}
    </DataState>
  );
}

export function ConcernEvidence({ concern }: { concern: Concern }) {
  const { projectName } = useApp();
  const u = concern.uncertainty;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
        <StateBadge state={concern.state} long />
        <span>{projectName(concern.project)}</span>
        <span>first seen {fmtDate(concern.first_seen)}</span>
        <span>{concern.flagged_at ? `flagged ${fmtDate(concern.flagged_at)}` : "not flagged yet"}</span>
        <N n={concern.n_claims} label="claims" />
        <N n={concern.n_voices} label="voices" />
        <PolarityCounts polarity={concern.polarity} />
      </div>
      <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
        <ScoreScale value={bestMatch(u)} cutoffs={u?.cutoffs} />
        {u?.note ? <p className="mt-1.5 text-xs text-slate-600">{u.note}</p> : null}
      </div>
      <ClaimsBlock heading="Claims in this concern" claims={concern.claims ?? []} />
      {concern.related_new_claims?.length ? (
        <ClaimsBlock heading="Related new claims" note="Same sub-issue, a different point. Not counted in this concern." claims={concern.related_new_claims} />
      ) : null}
      {concern.closest_older?.length ? (
        <ClaimsBlock heading="Closest earlier claims" note="The nearest claims published before. Shown so a person can check the decision." claims={concern.closest_older} />
      ) : null}
      {concern.events_nearby?.length ? (
        <div>
          <h3 className="mb-1 text-sm font-semibold text-slate-900">Timeline events nearby</h3>
          <EventList events={concern.events_nearby} />
        </div>
      ) : null}
      <div>
        <h3 className="mb-1 text-sm font-semibold text-slate-900">
          Seen in other cities <N n={concern.elsewhere?.length ?? 0} label="cases" />
        </h3>
        {concern.elsewhere?.length ? (
          <div className="space-y-2">
            {concern.elsewhere.map((c, i) => (
              <CaseCard key={i} c={c} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-500">{concern.new_anywhere ? "No equivalent claim found in any other project." : "No similar case from another project attached."}</p>
        )}
      </div>
    </div>
  );
}

function ConcernBlock({ concern_id, project, cutoff, fallback }: { concern_id: string; project?: string; cutoff?: string; fallback?: Concern }) {
  const state = useApi<Concern>(withQuery(`/api/emerging/${encodeURIComponent(concern_id)}`, { project, cutoff }));
  if (state.loading && fallback) return <ConcernEvidence concern={fallback} />;
  if (state.error && fallback) {
    return (
      <div className="space-y-2">
        <p className="rounded border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900">Full evidence could not be loaded ({state.error.message}). Showing what the list already contained.</p>
        <ConcernEvidence concern={fallback} />
      </div>
    );
  }
  return (
    <DataState state={state} what="the concern">
      {(c) => <ConcernEvidence concern={{ ...(fallback ?? {}), ...c }} />}
    </DataState>
  );
}

function Section({ s }: { s: EvidenceSection }) {
  switch (s.kind) {
    case "posts":
      return <PostsBlock heading={s.heading} query={s.query} />;
    case "post":
      return <PostBlock heading={s.heading} doc_id={s.doc_id} />;
    case "claims":
      return <ClaimsBlock heading={s.heading} note={s.note} claims={s.claims} />;
    case "family":
      return <FamilyBlock family_id={s.family_id} />;
    case "claim":
      return <ClaimBlock cid={s.cid} />;
    case "concern":
      return <ConcernBlock concern_id={s.concern_id} project={s.project} cutoff={s.cutoff} fallback={s.fallback} />;
    case "cases":
      return (
        <div>
          {s.heading ? <h3 className="mb-2 text-sm font-semibold text-slate-900">{s.heading}</h3> : null}
          {s.cases.length ? (
            <div className="space-y-2">
              {s.cases.map((c, i) => (
                <CaseCard key={i} c={c} />
              ))}
            </div>
          ) : (
            <Empty>No similar historical cases.</Empty>
          )}
        </div>
      );
  }
}

/* ---------- the drawer ---------- */

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [spec, setSpec] = useState<EvidenceSpec | null>(null);
  const [seq, setSeq] = useState(0);
  const open = useCallback((s: EvidenceSpec) => {
    setSpec(s);
    setSeq((n) => n + 1);
  }, []);
  const close = useCallback(() => setSpec(null), []);
  const value = useMemo(() => ({ open }), [open]);

  useEffect(() => {
    if (!spec) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [spec, close]);

  return (
    <EvidenceCtx.Provider value={value}>
      {children}
      {spec ? (
        <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={`Evidence: ${spec.title}`}>
          <button aria-label="Close evidence" className="absolute inset-0 bg-slate-900/40" onClick={close} />
          <aside className="relative flex h-full w-full max-w-2xl flex-col bg-white shadow-2xl">
            <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
              <div className="min-w-0">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-teal-800">Evidence</div>
                <h2 className="text-lg font-semibold leading-snug text-slate-900">{spec.title}</h2>
                {spec.subtitle ? <p className="mt-0.5 text-sm text-slate-600">{spec.subtitle}</p> : null}
              </div>
              <Button onClick={close}>Close</Button>
            </header>
            <div key={seq} className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
              {spec.sections.map((s, i) => (
                <Section key={i} s={s} />
              ))}
              <p className="border-t border-slate-100 pt-3 text-xs text-slate-500">
                Labels and matches are assigned by AI models and are not human-validated. Author names are never shown; “voice” is an anonymous id for one independent source.
              </p>
            </div>
          </aside>
        </div>
      ) : null}
    </EvidenceCtx.Provider>
  );
}
