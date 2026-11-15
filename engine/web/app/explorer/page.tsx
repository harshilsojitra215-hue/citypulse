"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { apiPost, useAction, useApi, withQuery } from "@/lib/api";
import type { ClaimDetail, FamiliesList, FamilyDetail, MatchResult, SearchResult } from "@/lib/types";
import { bestMatch, fmtDate, humanize, num } from "@/lib/format";
import { useApp } from "@/components/AppContext";
import { CaseCard, ClaimEvidenceCard, PostEvidenceCard } from "@/components/Evidence";
import { MatchList, splitByRelation } from "@/components/MatchList";
import { Badge, Button, DataState, Empty, ErrorBox, Loading, ModeBadge, N, PageHeader, Panel, POLARITY_COLOR, ScoreScale, Select, SplitBar, cx } from "@/components/ui";

const NOVELTY: Record<string, { label: string; tone: string; text: string }> = {
  familiar: { label: "Known argument", tone: "gray", text: "An equivalent claim already exists." },
  ambiguous: { label: "Needs review", tone: "violet", text: "It may be a variant of a known argument. The score lies between the two cut-offs." },
  new: { label: "No equivalent found", tone: "amber", text: "Nothing in the collected debate makes this argument yet." },
  unknown: { label: "Cannot be decided on this machine", tone: "orange", text: "The matcher model is needed to decide whether this is a known argument. Only the most similar claims can be shown." },
};

function CheckNewArgument({ project }: { project: string }) {
  const { projectName } = useApp();
  const [text, setText] = useState("");
  const [state, run, reset] = useAction<MatchResult>();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    run(() => apiPost<MatchResult>("/api/match", project ? { text: t, project } : { text: t }));
  };
  const d = state.data;
  const nov = d?.novelty;
  const info = NOVELTY[nov?.state ?? ""] ?? { label: humanize(nov?.state) || "No state returned", tone: "gray", text: "" };
  const split = splitByRelation(d?.matches);
  const scored = nov?.state !== "unknown" || split.equivalent.length + split.related.length > 0;
  return (
    <Panel title="Check a new argument" hint={`Type an argument you heard. It is compared with all collected claims${project ? ` (project: ${projectName(project)})` : ""}.`}>
      <form onSubmit={submit} className="space-y-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          maxLength={1000}
          placeholder="One sentence, in English or German"
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-[0.95rem] text-slate-900 placeholder:text-slate-400 focus:border-teal-600 focus:outline-none"
        />
        <div className="flex items-center gap-2">
          <Button type="submit" kind="primary" disabled={state.loading || !text.trim()}>
            {state.loading ? "Checking…" : "Check"}
          </Button>
          {d || state.error ? (
            <Button
              kind="ghost"
              onClick={() => {
                reset();
                setText("");
              }}
            >
              Clear
            </Button>
          ) : null}
        </div>
      </form>
      {state.loading ? (
        <div className="mt-3">
          <Loading label="Comparing with known claims" rows={2} />
        </div>
      ) : null}
      {state.error ? (
        <div className="mt-3">
          <ErrorBox error={state.error} what="the check" />
        </div>
      ) : null}
      {d ? (
        <div className="mt-4 space-y-4">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-slate-600">Result</span>
              <Badge tone={info.tone}>{info.label}</Badge>
              <ModeBadge mode={d.mode} prefix="scores" />
            </div>
            {info.text ? <p className="mt-1 text-sm text-slate-700">{info.text}</p> : null}
            {nov?.note ? <p className="mt-1 text-xs text-slate-500">Data service: {nov.note}</p> : null}
            {bestMatch(nov) !== null ? (
              <div className="mt-2 max-w-md">
                <ScoreScale value={bestMatch(nov)} cutoffs={nov?.cutoffs} />
              </div>
            ) : null}
          </div>
          {scored ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <MatchList title="Equivalent claims" note="Same argument." items={split.equivalent} tone="teal" emptyText="No equivalent claim found." />
              <MatchList title="Related claims" note="Same sub-issue, a different point." items={split.related} tone="sky" emptyText="No related claim found." />
            </div>
          ) : null}
          {split.other.length ? <MatchList title={scored ? "Other similar claims" : "Most similar claims"} note="Ranked by similarity only. Not judged as equivalent or related." items={split.other} /> : null}
          <div>
            <h3 className="mb-2 flex items-baseline gap-2 text-base font-semibold text-slate-900">
              Seen in other cities <N n={(d.elsewhere ?? []).length} label="cases" />
            </h3>
            {(d.elsewhere ?? []).length ? (
              <div className="grid gap-2 lg:grid-cols-2">
                {(d.elsewhere ?? []).map((c, i) => (
                  <CaseCard key={i} c={c} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">No similar claim from another project.</p>
            )}
          </div>
        </div>
      ) : null}
    </Panel>
  );
}

function SearchResults({ q, project, topic }: { q: string; project: string; topic: string }) {
  const state = useApi<SearchResult>(withQuery("/api/search", { q, project, topic, k: 20 }));
  return (
    <Panel title={`Search: “${q}”`} hint="Claims closest in meaning to the search text.">
      <DataState state={state} what="search results" isEmpty={(d) => !(d.results ?? []).length} empty="No claims found for this search.">
        {(d) => {
          const s = splitByRelation(d.results);
          const semantic = d.mode === "semantic";
          return (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
                <Badge tone={semantic ? "teal" : "orange"} title={`search mode: ${d.mode}`}>
                  {semantic ? "semantic search" : d.mode === "keyword-fallback" ? "keyword search (semantic model not available)" : `search mode: ${d.mode ?? "not reported"}`}
                </Badge>
                {d.matcher_mode ? <Badge tone="white">matcher: {d.matcher_mode}</Badge> : null}
                <N n={(d.results ?? []).length} label="results" />
              </div>
              {s.equivalent.length ? <MatchList title="Equivalent to the search text" note="The matcher scores these as the same argument." items={s.equivalent} tone="teal" /> : null}
              {s.related.length ? <MatchList title="Related to the search text" note="Same sub-issue, a different point." items={s.related} tone="sky" /> : null}
              {s.other.length ? <MatchList title={s.equivalent.length || s.related.length ? "Other results" : "Results"} note="Ranked by similarity. No relation assigned." items={s.other} /> : null}
            </div>
          );
        }}
      </DataState>
    </Panel>
  );
}

function FamilyView({ familyId }: { familyId: string }) {
  const { projectName } = useApp();
  const state = useApi<FamilyDetail>(`/api/arguments/families/${encodeURIComponent(familyId)}`);
  return (
    <Panel title="Argument family">
      <DataState state={state} what="the argument family">
        {(f) => (
          <div className="space-y-4">
            <div>
              <h2 className="text-xl font-semibold leading-snug text-slate-900">{f.name ?? f.family_id}</h2>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-600">
                <N n={f.n ?? f.claims?.length} label="claims" />
                <Badge tone="teal">pro {num(f.pro ?? 0)}</Badge>
                <Badge tone="orange">contra {num(f.contra ?? 0)}</Badge>
                {f.neutral !== undefined ? <Badge tone="gray">neutral {num(f.neutral)}</Badge> : null}
                {f.n_voices !== undefined ? <N n={f.n_voices} label="voices" /> : null}
                {f.main_topic ? <Badge tone="white">{humanize(f.main_topic)}</Badge> : null}
                {f.first_seen ? (
                  <span>
                    first seen {fmtDate(f.first_seen)} · last seen {fmtDate(f.last_seen)}
                  </span>
                ) : null}
              </div>
              {Object.keys(f.by_project ?? {}).length ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(f.by_project ?? {}).map(([p, n]) => (
                    <Badge key={p} tone="white">
                      {projectName(p)}: n = {num(n)}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </div>
            <MatchList title="Claims in this family" note="Click a claim to see its equivalent and related claims." items={f.claims ?? []} limit={100} emptyText="This family has no claims for the current data." />
          </div>
        )}
      </DataState>
    </Panel>
  );
}

function ClaimView({ cid }: { cid: string }) {
  const state = useApi<ClaimDetail>(`/api/claims/${encodeURIComponent(cid)}`);
  return (
    <Panel title="Claim" right={<ModeBadge mode={state.data?.mode} prefix="scores" />}>
      <DataState state={state} what="the claim">
        {(d) => (
          <div className="space-y-5">
            {d.note ? <p className="text-xs text-slate-500">{d.note}</p> : null}
            {d.claim ? (
              <div className="space-y-2">
                <ClaimEvidenceCard claim={d.claim} autoPost={!d.post} onOpenClaim={false} />
                {d.post ? <PostEvidenceCard post={d.post} /> : null}
                {d.claim.family_id ? (
                  <Link href={`/explorer?family=${encodeURIComponent(d.claim.family_id)}`} className="inline-block text-sm font-medium text-teal-800 underline underline-offset-2">
                    Go to its argument family: {d.claim.family_name ?? d.claim.family_id} →
                  </Link>
                ) : null}
              </div>
            ) : (
              <Empty>The claim itself was not returned.</Empty>
            )}
            <div className="grid gap-5 lg:grid-cols-2">
              <MatchList title="Equivalent claims" note="Same argument: an analyst would count these together." items={d.equivalent ?? []} tone="teal" emptyText="No equivalent claim found." />
              <MatchList title="Related claims" note="Same sub-issue, a different point. Not counted as the same argument." items={d.related ?? []} tone="sky" emptyText="No related claim found." />
            </div>
            <div>
              <h3 className="mb-2 flex items-baseline gap-2 text-base font-semibold text-slate-900">
                Seen in other cities <N n={(d.elsewhere ?? []).length} label="cases" />
              </h3>
              {(d.elsewhere ?? []).length ? (
                <div className="grid gap-2 lg:grid-cols-2">
                  {(d.elsewhere ?? []).map((c, i) => (
                    <CaseCard key={i} c={c} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">No similar claim from another project.</p>
              )}
            </div>
          </div>
        )}
      </DataState>
    </Panel>
  );
}

export default function ExplorerPage() {
  const { project: globalProject, projects, projectName, meta } = useApp();
  const router = useRouter();
  const sp = useSearchParams();
  const q = sp.get("q") ?? "";
  const topic = sp.get("topic") ?? "";
  const pParam = sp.get("p");
  const project = pParam === null ? globalProject : pParam === "all" ? "" : pParam;
  const family = sp.get("family");
  const claim = sp.get("claim");

  const [draft, setDraft] = useState(q);
  const [famFilter, setFamFilter] = useState("");

  const go = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    const s = next.toString();
    router.push(s ? `/explorer?${s}` : "/explorer");
  };

  const families = useApi<FamiliesList>(withQuery("/api/arguments/families", { project, topic }));
  const topics = meta.data?.topics ?? [];

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    go({ q: draft.trim() || null, family: null, claim: null });
  };

  return (
    <>
      <PageHeader title="Argument Explorer" lead="Search the collected claims by meaning, browse argument families, and see which claims are the same argument and which are only related." />

      <div className="space-y-4">
        <Panel>
          <form onSubmit={onSearch} className="flex flex-wrap items-center gap-2">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Search claims by meaning, e.g. cost compared with other public spending"
              aria-label="Search claims"
              className="min-w-[14rem] flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-[0.95rem] text-slate-900 placeholder:text-slate-400 focus:border-teal-600 focus:outline-none"
            />
            <Button type="submit" kind="primary">
              Search
            </Button>
            {q ? (
              <Button
                kind="ghost"
                onClick={() => {
                  setDraft("");
                  go({ q: null });
                }}
              >
                Clear search
              </Button>
            ) : null}
            <Select label="Topic" value={topic} onChange={(v) => go({ topic: v || null })} options={[{ value: "", label: "All topics" }, ...topics.map((t) => ({ value: t, label: humanize(t) }))]} />
            <Select
              label="Project"
              value={project}
              onChange={(v) => go({ p: v === "" ? "all" : v })}
              options={[{ value: "", label: "All projects" }, ...projects.map((p) => ({ value: p.id, label: p.name ?? p.id })), ...(project && !projects.some((p) => p.id === project) ? [{ value: project, label: projectName(project) }] : [])]}
            />
          </form>
        </Panel>

        <CheckNewArgument project={project} />

        <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <Panel title="Argument families" hint={`${projectName(project)}${topic ? ` · ${humanize(topic)}` : ""}`} right={families.data ? <N n={(families.data.items ?? []).length} /> : null}>
            <input
              value={famFilter}
              onChange={(e) => setFamFilter(e.target.value)}
              placeholder="Filter by name"
              aria-label="Filter families by name"
              className="mb-2 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
            />
            <DataState state={families} what="argument families" isEmpty={(d) => !(d.items ?? []).length} empty="No argument families for this project and topic. Arguments are only extracted for some projects.">
              {(d) => {
                const items = (d.items ?? []).filter((f) => !famFilter || (f.name ?? "").toLowerCase().includes(famFilter.toLowerCase()));
                const max = Math.max(1, ...items.map((f) => f.n ?? 0));
                return items.length ? (
                  <ul className="max-h-[70vh] space-y-1 overflow-y-auto pr-1">
                    {items.map((f) => (
                      <li key={f.family_id}>
                        <button
                          onClick={() => go({ family: f.family_id, claim: null, q: null })}
                          className={cx("w-full rounded-md border px-2.5 py-2 text-left", family === f.family_id ? "border-teal-600 bg-teal-50" : "border-transparent hover:bg-slate-50")}
                        >
                          <div className="text-sm leading-snug text-slate-900">{f.name ?? f.family_id}</div>
                          <div className="mt-1 grid grid-cols-[1fr_auto] items-center gap-2">
                            <SplitBar parts={{ pro: f.pro, contra: f.contra, neutral: f.neutral ?? Math.max(0, (f.n ?? 0) - (f.pro ?? 0) - (f.contra ?? 0)) }} colors={POLARITY_COLOR} max={max} />
                            <span className="text-xs text-slate-500 tabular-nums">
                              n = {num(f.n)} · pro {num(f.pro ?? 0)} · contra {num(f.contra ?? 0)}
                            </span>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty>No family name contains “{famFilter}”.</Empty>
                );
              }}
            </DataState>
          </Panel>

          <div className="min-w-0 space-y-4">
            {claim ? <ClaimView key={claim} cid={claim} /> : null}
            {!claim && family ? <FamilyView key={family} familyId={family} /> : null}
            {!claim && !family && q ? <SearchResults q={q} project={project} topic={topic} /> : null}
            {!claim && !family && !q ? (
              <Panel>
                <Empty>Search for a claim, or choose an argument family on the left, to see its claims and how they relate.</Empty>
              </Panel>
            ) : null}
            {(claim || family) && q ? (
              <button onClick={() => go({ claim: null, family: null })} className="text-sm font-medium text-teal-800 underline underline-offset-2">
                ← Back to search results for “{q}”
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}
