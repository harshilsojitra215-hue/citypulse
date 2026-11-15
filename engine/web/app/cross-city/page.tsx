"use client";

import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { apiFetch, apiPost, useAction, useApi, withQuery } from "@/lib/api";
import type { CrossCity, SimilarResult } from "@/lib/types";
import { humanize, num } from "@/lib/format";
import { useApp } from "@/components/AppContext";
import { CaseCard, useEvidence } from "@/components/Evidence";
import { Button, DataState, Empty, ErrorBox, Legend, Loading, ModeBadge, N, Notes, PageHeader, Panel, POLARITY_COLOR, Select, ShareBar, ShareLabel, SplitBar, cx } from "@/components/ui";

function SimilarFinder({ initialCid }: { initialCid: string }) {
  const { project, projectName } = useApp();
  const openEvidence = useEvidence();
  const [text, setText] = useState(initialCid);
  const [state, run] = useAction<SimilarResult>();
  const [asked, setAsked] = useState("");

  const find = (raw: string) => {
    const t = raw.trim();
    if (!t) return;
    setAsked(t);
    const isCid = /^c\d+$/i.test(t);
    run(() => (isCid ? apiFetch<SimilarResult>(withQuery("/api/crosscity/similar", { cid: t })) : apiPost<SimilarResult>("/api/crosscity/similar", project ? { text: t, project } : { text: t })));
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    find(text);
  };

  return (
    <Panel
      title="Find similar historical claims"
      hint={`Type an argument, or a claim id such as c3148. The search looks in the other projects${project ? ` (not ${projectName(project)})` : ""} and shows what stage they were in and what happened next.`}
    >
      <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="An argument in one sentence, or a claim id"
          aria-label="Argument text or claim id"
          maxLength={1000}
          className="min-w-[14rem] flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-[0.95rem] text-slate-900 placeholder:text-slate-400 focus:border-teal-600 focus:outline-none"
        />
        <Button type="submit" kind="primary" disabled={state.loading || !text.trim()}>
          {state.loading ? "Searching…" : "Find similar cases"}
        </Button>
      </form>
      <div className="mt-3">
        {state.loading ? <Loading label="Searching other projects" rows={2} /> : null}
        {state.error ? <ErrorBox error={state.error} what="similar cases" onRetry={() => find(asked)} /> : null}
        {state.data ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
              <span>
                Cases for “{asked}”
              </span>
              <N n={(state.data.cases ?? []).length} label="cases" />
              <ModeBadge mode={state.data.mode} prefix="scores" />
            </div>
            {state.data.note || state.data.novelty?.note ? <p className="text-xs text-slate-500">Data service: {state.data.note ?? state.data.novelty?.note}</p> : null}
            {(state.data.cases ?? []).length ? (
              <div className="grid gap-2 xl:grid-cols-2">
                {(state.data.cases ?? []).map((c, i) => (
                  <CaseCard
                    key={i}
                    c={c}
                    onEvidence={c.claim ? () => openEvidence({ title: c.claim?.claim ?? "", subtitle: "Historical case from another project: claim and source post", sections: [{ kind: "claims", claims: c.claim ? [c.claim] : [] }] }) : undefined}
                  />
                ))}
              </div>
            ) : (
              <Empty>No similar claim was found in another project.</Empty>
            )}
          </div>
        ) : null}
        {!state.loading && !state.error && !state.data ? <p className="text-sm text-slate-500">Results are historical cases, not forecasts for this project.</p> : null}
      </div>
    </Panel>
  );
}

export default function CrossCityPage() {
  const { project, projectName, meta } = useApp();
  const openEvidence = useEvidence();
  const initialCid = useSearchParams().get("cid") ?? "";
  const [topic, setTopic] = useState("");
  const [showAllShared, setShowAllShared] = useState(false);
  const state = useApi<CrossCity>(withQuery("/api/crosscity", { topic }));
  const topics = meta.data?.topics ?? [];

  return (
    <>
      <PageHeader
        title="Cross-City"
        lead="How the same kind of project was debated elsewhere. The projects differ in size, stage and data volume, so compare with care."
        right={topics.length ? <Select label="Topic" value={topic} onChange={setTopic} options={[{ value: "", label: "All topics" }, ...topics.map((t) => ({ value: t, label: humanize(t) }))]} /> : null}
      />

      <div className="space-y-4">
        <SimilarFinder key={initialCid} initialCid={initialCid} />

        <DataState state={state} what="the project comparison" rows={5}>
          {(d) => {
            const projects = d.projects ?? [];
            const allTopics = Array.from(new Set(projects.flatMap((p) => (p.topic_shares ?? []).map((t) => t.topic))));
            const shared = d.shared_arguments ?? [];
            const projIds = projects.length ? projects.map((p) => p.id) : Array.from(new Set(shared.flatMap((s) => Object.keys(s.by_project ?? {}))));
            return (
              <>
                <Panel title="Opposition among posts that take a side" hint="Share of posts labelled “oppose”, with the interval and sample size from the data service. Click a row for the posts.">
                  {projects.length ? (
                    <div className="divide-y divide-slate-100">
                      {projects.map((p) => (
                        <button
                          key={p.id}
                          onClick={() => openEvidence({ title: `${p.name ?? projectName(p.id)}: posts labelled as opposing`, subtitle: "Source posts", sections: [{ kind: "posts", query: { project: p.id, stance: "oppose", topic } }] })}
                          className={cx("grid w-full grid-cols-1 items-center gap-x-4 gap-y-1 px-1 py-3 text-left hover:bg-slate-50 md:grid-cols-[12rem_minmax(0,1fr)_minmax(0,1.2fr)]", p.id === project && "bg-teal-50/60")}
                        >
                          <div>
                            <div className="text-base font-semibold text-slate-900">{p.name ?? projectName(p.id)}</div>
                            <div className="text-xs text-slate-500 tabular-nums">
                              posts n = {num(p.n_posts)} · with stance n = {num(p.n_with_stance)}
                            </div>
                          </div>
                          <ShareLabel share={p.opposition_share} />
                          <ShareBar share={p.opposition_share} />
                        </button>
                      ))}
                    </div>
                  ) : (
                    <Empty>No projects returned.</Empty>
                  )}
                </Panel>

                <Panel title="What each debate is about" hint="Number of claims per topic and project. Bars are scaled within each project." right={<Legend items={[{ label: "Pro", color: POLARITY_COLOR.pro }, { label: "Contra", color: POLARITY_COLOR.contra }, { label: "Neutral", color: POLARITY_COLOR.neutral }]} />}>
                  {allTopics.length ? (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[36rem] border-separate border-spacing-x-3 border-spacing-y-1 text-sm">
                        <thead>
                          <tr className="text-left text-xs text-slate-500">
                            <th className="font-medium">Topic</th>
                            {projects.map((p) => (
                              <th key={p.id} className="font-medium">
                                {p.name ?? projectName(p.id)}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {allTopics.map((t) => (
                            <tr key={t}>
                              <td className="whitespace-nowrap text-slate-800">{humanize(t)}</td>
                              {projects.map((p) => {
                                const ts = (p.topic_shares ?? []).find((x) => x.topic === t);
                                const max = Math.max(1, ...(p.topic_shares ?? []).map((x) => x.n ?? 0));
                                return (
                                  <td key={p.id} className="min-w-[7rem]">
                                    {ts ? (
                                      <button
                                        onClick={() => openEvidence({ title: `${p.name ?? projectName(p.id)}: ${humanize(t)}`, subtitle: "Source posts", sections: [{ kind: "posts", query: { project: p.id, topic: t } }] })}
                                        className="grid w-full grid-cols-[1fr_auto] items-center gap-2 rounded px-0.5 py-0.5 hover:bg-slate-50"
                                      >
                                        <SplitBar parts={{ pro: ts.pro, contra: ts.contra, neutral: ts.neutral }} colors={POLARITY_COLOR} max={max} />
                                        <span className="text-xs text-slate-500 tabular-nums">n = {num(ts.n)}</span>
                                      </button>
                                    ) : (
                                      <span className="text-xs text-slate-300">n = 0</span>
                                    )}
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty>No topic data returned.</Empty>
                  )}
                </Panel>

                <Panel title="Arguments made in more than one city" hint="Argument families with claims from several projects. The numbers are claims per project. Click a row for the claims." right={<N n={shared.length} label="families" />}>
                  {shared.length ? (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[40rem] text-sm">
                        <thead>
                          <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                            <th className="py-1.5 pr-3 font-medium">Argument</th>
                            {projIds.map((id) => (
                              <th key={id} className="px-2 py-1.5 text-right font-medium">
                                {projectName(id)}
                              </th>
                            ))}
                            <th className="px-2 py-1.5 text-right font-medium">Pro</th>
                            <th className="px-2 py-1.5 text-right font-medium">Contra</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(showAllShared ? shared : shared.slice(0, 15)).map((s) => (
                            <tr
                              key={s.family_id}
                              onClick={() => openEvidence({ title: s.name ?? s.family_id, subtitle: "Argument family across projects: claims and source posts", sections: [{ kind: "family", family_id: s.family_id }] })}
                              className="cursor-pointer border-b border-slate-100 hover:bg-slate-50"
                            >
                              <td className="py-2 pr-3 text-[0.95rem] leading-snug text-slate-900">
                                <button className="text-left">{s.name ?? s.family_id}</button>
                              </td>
                              {projIds.map((id) => {
                                const n = s.by_project?.[id] ?? 0;
                                return (
                                  <td key={id} className={cx("px-2 py-2 text-right tabular-nums", n ? "font-semibold text-slate-900" : "text-slate-300")}>
                                    {n}
                                  </td>
                                );
                              })}
                              <td className="px-2 py-2 text-right tabular-nums text-teal-800">{num(s.pro ?? 0)}</td>
                              <td className="px-2 py-2 text-right tabular-nums text-orange-800">{num(s.contra ?? 0)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {shared.length > 15 ? (
                        <div className="mt-2">
                          <Button small onClick={() => setShowAllShared(!showAllShared)}>
                            {showAllShared ? "Show the first 15" : `Show all ${shared.length}`}
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <Empty>No shared argument families{topic ? " for this topic" : ""}.</Empty>
                  )}
                </Panel>

                <Notes notes={d.notes} />
              </>
            );
          }}
        </DataState>
      </div>
    </>
  );
}
