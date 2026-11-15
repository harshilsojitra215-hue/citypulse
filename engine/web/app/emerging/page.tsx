"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useApi, withQuery } from "@/lib/api";
import type { Concern, EmergingResult, ReplayCutoffs, Run } from "@/lib/types";
import { fmtDate, STATE_INFO, STATE_ORDER, stateInfo } from "@/lib/format";
import { useApp } from "@/components/AppContext";
import { ConcernCard } from "@/components/ConcernCard";
import { DataState, Empty, ModeBadge, N, Notes, PageHeader, Select, cx } from "@/components/ui";

function Groups({ concerns, cutoff, showProject, stateFilter }: { concerns: Concern[]; cutoff?: string; showProject: boolean; stateFilter: string }) {
  const known = new Set<string>(STATE_ORDER);
  const states = [...STATE_ORDER, ...Array.from(new Set(concerns.map((c) => c.state ?? "").filter((s) => !known.has(s))))];
  const shown = states.filter((s) => (stateFilter ? s === stateFilter : true));
  if (!concerns.length) return <Empty>No concerns for this selection.</Empty>;
  return (
    <div className="space-y-7">
      {shown.map((s) => {
        const list = concerns
          .filter((c) => (c.state ?? "") === s)
          .sort((a, b) => Number(!!b.flagged_at) - Number(!!a.flagged_at) || (b.n_voices ?? 0) - (a.n_voices ?? 0) || (b.n_claims ?? 0) - (a.n_claims ?? 0) || String(b.first_seen ?? "").localeCompare(String(a.first_seen ?? "")));
        const info = stateInfo(s);
        const limit = s === "new_emerging" || s === "gaining" ? 24 : s === "ambiguous" ? 8 : 6;
        return <Group key={s} title={info.title} help={info.help} list={list} cutoff={cutoff} showProject={showProject} initialLimit={limit} tone={info.tone} />;
      })}
    </div>
  );
}

const DOT: Record<string, string> = { amber: "bg-amber-500", slate: "bg-slate-400", violet: "bg-violet-500", sky: "bg-sky-500", gray: "bg-gray-300" };

function Group({ title, help, list, cutoff, showProject, initialLimit, tone }: { title: string; help: string; list: Concern[]; cutoff?: string; showProject: boolean; initialLimit: number; tone: string }) {
  const [limit, setLimit] = useState(initialLimit);
  return (
    <section>
      <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-900">
          <span className={cx("inline-block h-3 w-3 rounded-full", DOT[tone] ?? DOT.gray)} />
          {title}
        </h2>
        <N n={list.length} label="concerns" />
        <span className="text-sm text-slate-500">{help}</span>
      </div>
      {list.length === 0 ? (
        <p className="rounded-md border border-dashed border-slate-300 bg-white px-3 py-3 text-sm text-slate-500">None in this selection.</p>
      ) : (
        <>
          <div className="grid gap-3 xl:grid-cols-2">
            {list.slice(0, limit).map((c) => (
              <ConcernCard key={c.concern_id} concern={c} cutoff={cutoff} showProject={showProject} />
            ))}
          </div>
          {list.length > limit ? (
            <button onClick={() => setLimit(list.length)} className="mt-2 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50">
              Show all {list.length}
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}

function FromRun({ runId }: { runId: string }) {
  const run = useApi<Run>(`/api/batches/${encodeURIComponent(runId)}`);
  const [stateFilter, setStateFilter] = useState("");
  return (
    <>
      <PageHeader
        title="Emerging Concerns"
        lead={
          <>
            Showing only what upload run <span className="font-mono text-slate-800">{runId}</span> found.{" "}
            <Link href="/emerging" className="font-medium text-teal-800 underline underline-offset-2">
              Show all concerns
            </Link>{" "}
            ·{" "}
            <Link href={`/new-data?run=${encodeURIComponent(runId)}`} className="font-medium text-teal-800 underline underline-offset-2">
              Back to the run
            </Link>
          </>
        }
        right={<StateSelect value={stateFilter} onChange={setStateFilter} />}
      />
      <DataState state={run} what="the run findings">
        {(r) => (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              File {r.filename ?? "(unnamed)"}, uploaded {fmtDate(r.created_at)}, status {r.status ?? "unknown"}.
            </p>
            <Groups concerns={r.findings?.concerns ?? []} showProject stateFilter={stateFilter} />
          </div>
        )}
      </DataState>
    </>
  );
}

function StateSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <Select label="Show" value={value} onChange={onChange} options={[{ value: "", label: "All states" }, ...STATE_ORDER.map((s) => ({ value: s, label: STATE_INFO[s].short }))]} />;
}

function AllConcerns() {
  const { project, projectName } = useApp();
  const [cutoff, setCutoff] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const cutoffs = useApi<ReplayCutoffs>("/api/replay/cutoffs");
  const emerging = useApi<EmergingResult>(withQuery("/api/emerging", { project, cutoff }));
  const cutoffOptions = [{ value: "", label: "default" }, ...(cutoffs.data?.cutoffs ?? []).map((c) => ({ value: c, label: fmtDate(c) }))];

  return (
    <>
      <PageHeader
        title={`Emerging Concerns: ${projectName(project)}`}
        lead="Arguments that appeared after the cut-off date and how they compare with everything known before it. Each card opens its evidence."
        right={
          <>
            <Select label="Known before" value={cutoff} onChange={setCutoff} options={cutoffOptions} />
            <StateSelect value={stateFilter} onChange={setStateFilter} />
          </>
        }
      />
      <DataState state={emerging} what="emerging concerns" rows={5}>
        {(d) => (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
              <span>
                Everything before <span className="font-medium text-slate-900">{fmtDate(d.cutoff ?? cutoff)}</span> counts as known.
              </span>
              <N n={(d.concerns ?? []).length} label="concerns" />
              <ModeBadge mode={d.mode} />
              {cutoffs.data?.reason ? <span className="text-xs text-slate-500">Earliest cut-off {fmtDate(cutoffs.data.earliest_allowed)}: {cutoffs.data.reason}.</span> : null}
            </div>
            <Groups concerns={d.concerns ?? []} cutoff={d.cutoff ?? (cutoff || undefined)} showProject={!project} stateFilter={stateFilter} />
            <Notes notes={d.notes} title="How to read these concerns" />
          </div>
        )}
      </DataState>
    </>
  );
}

export default function EmergingPage() {
  const runId = useSearchParams().get("run_id");
  return runId ? <FromRun runId={runId} /> : <AllConcerns />;
}
