"use client";

import { useState } from "react";
import { apiUrl, useApi, withQuery } from "@/lib/api";
import type { EventRef, Overview, PeriodRow, Trends } from "@/lib/types";
import { fmtDate, humanize, num, periodRange, shortPeriod } from "@/lib/format";
import { useApp } from "@/components/AppContext";
import { useEvidence } from "@/components/Evidence";
import { ColumnChart, type BarDatum } from "@/components/charts";
import { Badge, DataState, Empty, Legend, N, Notes, PageHeader, Panel, POLARITY_COLOR, STANCE_COLOR, Select, ShareBar, ShareLabel, SplitBar, Stat } from "@/components/ui";

const STANCES = ["support", "oppose", "neutral", "mixed"] as const;

function toBars(rows: PeriodRow[], peaks: Set<string>): BarDatum[] {
  return rows.map((r) => {
    const key = String(r.period ?? r.month ?? "");
    const parts: BarDatum["parts"] = STANCES.map((s) => ({ name: s, value: Number(r[s] ?? 0), color: STANCE_COLOR[s] }));
    const labelled = parts.reduce((a, p) => a + p.value, 0);
    const total = Number(r.n ?? labelled);
    if (total > labelled) parts.push({ name: "no stance label", value: total - labelled, color: "#cbd5e1" });
    return { key, label: shortPeriod(key), parts, total, marked: peaks.has(key) };
  });
}

export default function OverviewPage() {
  const { project, projectName, meta } = useApp();
  const openEvidence = useEvidence();
  const [channel, setChannel] = useState("");
  const [granularity, setGranularity] = useState("month");
  const filters = { project, channel };

  const overview = useApi<Overview>(withQuery("/api/overview", filters));
  const trends = useApi<Trends>(withQuery("/api/trends", { granularity, ...filters }));

  const name = projectName(project);
  const channels = meta.data?.channels ?? [];
  const pm = meta.data?.projects?.find((p) => p.id === project);

  const openPosts = (title: string, extra: Record<string, string | undefined>, subtitle?: string) =>
    openEvidence({ title, subtitle: subtitle ?? `${name}: source posts`, sections: [{ kind: "posts", query: { ...filters, ...extra } }] });

  return (
    <>
      <PageHeader
        title={`Overview: ${name}`}
        lead={
          <>
            What the collected online debate contains{pm?.first_date ? `, ${fmtDate(pm.first_date)} to ${fmtDate(pm.last_date)}` : ""}. Click any bar or row to see the posts behind it.
          </>
        }
        right={
          <>
            {channels.length ? (
              <Select label="Channel" value={channel} onChange={setChannel} options={[{ value: "", label: "All channels" }, ...channels.map((c) => ({ value: c, label: humanize(c) }))]} />
            ) : null}
            <a
              href={apiUrl(withQuery("/api/export/briefing", { project, format: "md" }))}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
            >
              Export briefing
            </a>
          </>
        }
      />

      <div className="space-y-4">
        <DataState state={overview} what="the overview" rows={4}>
          {(o) => (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Stat label="Posts collected" value={num(o.n_posts)} sub="incl. republished copies" onClick={() => openPosts("All collected posts", {})} />
                <Stat label="Unique posts" value={num(o.n_unique_posts)} sub="republished copies counted once" />
                <Stat label="Independent voices" value={num(o.n_voices)} sub="anonymous authors or publishing domains" />
                <Stat label="Posts that take a position" value={num(o.n_with_stance)} sub={`of ${num(o.n_unique_posts ?? o.n_posts)} posts`} />
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <Panel title="Opposition among posts that take a side" hint="Share of posts labelled “oppose”. The band is the uncertainty interval from the data service.">
                  <button className="block w-full text-left" onClick={() => openPosts("Posts labelled as opposing", { stance: "oppose" })}>
                    <ShareLabel share={o.opposition_share} />
                    <div className="mt-3">
                      <ShareBar share={o.opposition_share} />
                    </div>
                  </button>
                  {(o.opposition_share?.n ?? 0) > 0 && (o.opposition_share?.n ?? 0) < 50 ? (
                    <p className="mt-2 rounded border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-sm text-amber-900">Small sample: read the interval, not the single number.</p>
                  ) : null}
                </Panel>

                <Panel title="Stance labels" hint="AI-assigned. Click a row for the posts.">
                  {Object.keys(o.stance_counts ?? {}).length ? (
                    <div className="space-y-2">
                      {Object.entries(o.stance_counts ?? {}).map(([k, v]) => {
                        const max = Math.max(1, ...Object.values(o.stance_counts ?? {}));
                        return (
                          <button key={k} onClick={() => openPosts(`Posts labelled “${k}”`, { stance: k })} className="grid w-full grid-cols-[6.5rem_1fr_auto] items-center gap-2 rounded px-1 py-0.5 text-left hover:bg-slate-50">
                            <span className="text-sm text-slate-700">{humanize(k)}</span>
                            <SplitBar parts={{ [k]: v }} colors={STANCE_COLOR} max={max} />
                            <N n={v} />
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <Empty>No stance labels for this selection.</Empty>
                  )}
                </Panel>
              </div>
            </>
          )}
        </DataState>

        <Panel
          title="Activity over time"
          hint="Posts per period, split by stance label. A dot marks a period that is unusually busy."
          right={
            <Select
              label="Per"
              value={granularity}
              onChange={setGranularity}
              options={[
                { value: "month", label: "month" },
                { value: "week", label: "week" },
              ]}
            />
          }
        >
          <DataState state={trends} what="the activity chart" isEmpty={(t) => !(t.series ?? []).length} empty="No dated posts for this selection.">
            {(t) => {
              const peaks = new Set((t.peaks ?? []).map((p) => String(p.period ?? "")));
              const bars = toBars(t.series ?? [], peaks);
              const total = bars.reduce((a, b) => a + b.total, 0);
              return (
                <div className="space-y-3">
                  <ColumnChart
                    data={bars}
                    onSelect={(d) => {
                      const r = periodRange(d.key);
                      openPosts(`Posts in ${d.label}`, r ? { from: r.from, to: r.to } : {}, `${name}: ${d.total} posts in this ${granularity}`);
                    }}
                  />
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Legend items={[...STANCES.map((s) => ({ label: humanize(s), color: STANCE_COLOR[s] })), { label: "No stance label", color: "#cbd5e1" }]} />
                    <N n={total} label="posts in chart" />
                  </div>
                  {(t.peaks ?? []).length ? (
                    <div>
                      <h3 className="mb-1 text-sm font-semibold text-slate-900">Unusually busy periods</h3>
                      <ul className="space-y-1">
                        {(t.peaks ?? []).map((p, i) => {
                          const ev = typeof p.event === "string" ? p.event : (p.event as EventRef | null | undefined)?.title;
                          const r = periodRange(String(p.period ?? ""));
                          return (
                            <li key={i}>
                              <button
                                onClick={() => openPosts(`Posts in ${shortPeriod(p.period)}`, r ? { from: r.from, to: r.to } : {})}
                                className="flex w-full flex-wrap items-baseline gap-x-2 rounded px-1 py-0.5 text-left text-sm hover:bg-slate-50"
                              >
                                <span className="font-medium tabular-nums text-slate-900">{fmtDate(p.period)}</span>
                                <N n={p.n} />
                                {p.expected !== undefined && p.expected !== null ? <span className="text-xs text-slate-500">expected about {Number(p.expected).toFixed(1)}</span> : null}
                                {p.p_value !== undefined && p.p_value !== null ? <span className="text-xs text-slate-500">p = {Number(p.p_value) < 0.001 ? "<0.001" : Number(p.p_value).toFixed(3)}</span> : null}
                                {p.headline ? <span className="text-slate-700">{p.headline}</span> : null}
                                {ev ? <Badge tone="white">event: {ev}</Badge> : null}
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ) : null}
                  {(t.events ?? []).length ? (
                    <details className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                      <summary className="cursor-pointer text-sm font-medium text-slate-800">
                        Project timeline events <N n={(t.events ?? []).length} />
                      </summary>
                      <ul className="mt-2 space-y-1">
                        {(t.events ?? []).map((e, i) => (
                          <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                            <span className="font-medium tabular-nums text-slate-800">{fmtDate(e.date)}</span>
                            <span className="text-slate-700">{e.title}</span>
                            {e.event_type ? <Badge tone="white">{humanize(e.event_type)}</Badge> : null}
                            <Badge tone={e.verified === "yes" || e.verified === true ? "green" : "white"}>{e.verified === "yes" || e.verified === true ? "verified" : "not verified"}</Badge>
                            {e.source_url && /^https?:/.test(e.source_url) ? (
                              <a href={e.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-teal-800 underline underline-offset-2">
                                source ↗
                              </a>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                  <Notes notes={t.notes} title="How to read this chart" />
                </div>
              );
            }}
          </DataState>
        </Panel>

        <DataState state={overview} what="topics and arguments" rows={4}>
          {(o) => (
            <>
              <div className="grid gap-4 xl:grid-cols-2">
                <Panel title="Most frequent arguments" hint="Argument families by number of claims. Click for the claims and their sources." right={<Legend items={[{ label: "Pro", color: POLARITY_COLOR.pro }, { label: "Contra", color: POLARITY_COLOR.contra }, { label: "Neutral", color: POLARITY_COLOR.neutral }]} />}>
                  {(o.top_arguments ?? []).length ? (
                    <ul className="divide-y divide-slate-100">
                      {(o.top_arguments ?? []).map((a) => {
                        const max = Math.max(1, ...(o.top_arguments ?? []).map((x) => x.n ?? 0));
                        return (
                          <li key={a.family_id}>
                            <button
                              onClick={() => openEvidence({ title: a.name ?? a.family_id, subtitle: "Argument family: claims and source posts", sections: [{ kind: "family", family_id: a.family_id }] })}
                              className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 px-1 py-2 text-left hover:bg-slate-50"
                            >
                              <span className="col-span-2 text-[0.95rem] leading-snug text-slate-900">{a.name ?? a.family_id}</span>
                              <SplitBar parts={{ pro: a.pro, contra: a.contra, neutral: a.neutral ?? Math.max(0, (a.n ?? 0) - (a.pro ?? 0) - (a.contra ?? 0)) }} colors={POLARITY_COLOR} max={max} />
                              <span className="text-xs text-slate-500 tabular-nums whitespace-nowrap">
                                n = {num(a.n)} · pro {num(a.pro ?? 0)} · contra {num(a.contra ?? 0)}
                              </span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <Empty>No argument families for this selection. Arguments are only extracted for some projects.</Empty>
                  )}
                </Panel>

                <Panel title="Topics" hint="What the claims are about. Click for the posts." right={<Legend items={[{ label: "Pro", color: POLARITY_COLOR.pro }, { label: "Contra", color: POLARITY_COLOR.contra }, { label: "Neutral", color: POLARITY_COLOR.neutral }]} />}>
                  {(o.topic_shares ?? []).length ? (
                    <ul className="space-y-1">
                      {(o.topic_shares ?? []).map((t) => {
                        const max = Math.max(1, ...(o.topic_shares ?? []).map((x) => x.n ?? 0));
                        return (
                          <li key={t.topic}>
                            <button onClick={() => openPosts(`Topic: ${humanize(t.topic)}`, { topic: t.topic })} className="grid w-full grid-cols-[minmax(7rem,11rem)_1fr_auto] items-center gap-2 rounded px-1 py-1 text-left hover:bg-slate-50">
                              <span className="truncate text-sm text-slate-800">{humanize(t.topic)}</span>
                              <SplitBar parts={{ pro: t.pro, contra: t.contra, neutral: t.neutral }} colors={POLARITY_COLOR} max={max} />
                              <N n={t.n} />
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <Empty>No topics for this selection.</Empty>
                  )}
                </Panel>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <Panel title="Where the debate takes place" hint="Posts per channel.">
                  {Object.keys(o.channel_counts ?? {}).length ? (
                    <div className="space-y-2">
                      {Object.entries(o.channel_counts ?? {}).map(([k, v]) => {
                        const max = Math.max(1, ...Object.values(o.channel_counts ?? {}));
                        return (
                          <button key={k} onClick={() => openPosts(`Channel: ${humanize(k)}`, { channel: k })} className="grid w-full grid-cols-[6.5rem_1fr_auto] items-center gap-2 rounded px-1 py-0.5 text-left hover:bg-slate-50">
                            <span className="text-sm text-slate-700">{humanize(k)}</span>
                            <SplitBar parts={{ x: v }} colors={{ x: "#475569" }} max={max} />
                            <N n={v} />
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <Empty>No channel data.</Empty>
                  )}
                </Panel>
                <Panel title="Most frequent sources" hint="Publishing domains by number of posts.">
                  {(o.top_sources ?? []).length ? (
                    <ol className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
                      {(o.top_sources ?? []).map((s) => (
                        <li key={s.domain} className="flex items-baseline justify-between gap-2 border-b border-slate-100 py-1 text-sm">
                          <span className="truncate text-slate-800">{s.domain}</span>
                          <N n={s.n} />
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <Empty>No source data.</Empty>
                  )}
                </Panel>
              </div>

              <Notes notes={o.notes} />
            </>
          )}
        </DataState>

        <Notes notes={meta.data?.limitations} title="Known limits of this tool" />
      </div>
    </>
  );
}
