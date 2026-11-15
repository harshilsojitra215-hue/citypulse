"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { apiUrl, useApi, withQuery } from "@/lib/api";
import { fmtDateTime, humanize, num } from "@/lib/format";
import { useStoredValue } from "@/components/AppContext";
import { Accuracy } from "@/components/review/Accuracy";
import { Labeller, type ReviewQueue } from "@/components/review/Labeller";
import { PostBrowser } from "@/components/review/PostBrowser";
import { Badge, Button, DataState, PageHeader, Panel, cx } from "@/components/ui";

type QueuesResponse = { queues?: ReviewQueue[]; labellers?: string[]; provisional_note?: string };

const TABS = [
  { id: "posts", label: "Source posts" },
  { id: "review", label: "Human review" },
  { id: "accuracy", label: "Accuracy so far" },
];

const NAME_RE = /^[a-z0-9_.-]{1,40}$/;

function LabellerName({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [draft, setDraft] = useState(value);
  const [editing, setEditing] = useState(!value);
  const clean = draft.trim().toLowerCase();
  const valid = NAME_RE.test(clean);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    onChange(clean);
    setEditing(false);
  };
  if (!editing && value) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
        Labelling as <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono font-medium text-slate-900">{value}</span>
        <button
          onClick={() => {
            setDraft(value);
            setEditing(true);
          }}
          className="text-teal-800 underline underline-offset-2"
        >
          change
        </button>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
      <label className="text-sm text-slate-700" htmlFor="labeller">
        Your labeller name
      </label>
      <input
        id="labeller"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="e.g. first name"
        autoComplete="off"
        className="w-44 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
      />
      <Button type="submit" kind="primary" disabled={!valid}>
        Use this name
      </Button>
      {draft && !valid ? <span className="text-xs text-orange-800">Use 1 to 40 letters, digits, dot, dash or underscore.</span> : <span className="text-xs text-slate-500">Stored with every label you save. Kept in this browser.</span>}
    </form>
  );
}

function ReviewTab() {
  const router = useRouter();
  const sp = useSearchParams();
  const active = sp.get("queue");
  const [labeller, setLabeller] = useStoredValue("citypulse.labeller", "");
  const state = useApi<QueuesResponse>(withQuery("/api/review/queues", { labeller: labeller || undefined }));
  const openQueue = (q: string | null) => router.push(q ? `/review?tab=review&queue=${encodeURIComponent(q)}` : "/review?tab=review");

  return (
    <DataState state={state} what="the review queues" isEmpty={(d) => !(d.queues ?? []).length} empty="The data service lists no review queues.">
      {(d) => {
        const queues = d.queues ?? [];
        const current = queues.find((q) => q.queue === active);
        if (current && labeller && current.available !== false) {
          return (
            <Panel>
              <Labeller key={`${current.queue}|${labeller}`} queue={current} labeller={labeller} onExit={() => {
                  state.reload();
                  openQueue(null);
                }}
                onChanged={() => undefined}
              />
            </Panel>
          );
        }
        return (
          <div className="space-y-4">
            <Panel>
              <div className="space-y-2">
                <p className="max-w-3xl text-[0.95rem] leading-relaxed text-slate-700">
                  People check a sample of what the AI models decided. Every label is stored with the name of the person and the time. Earlier labels are kept when a label is corrected.
                </p>
                {d.provisional_note ? <p className="rounded border border-orange-200 bg-orange-50 px-3 py-1.5 text-sm text-orange-950">{d.provisional_note}</p> : null}
                <LabellerName key={labeller} value={labeller} onChange={setLabeller} />
                {(d.labellers ?? []).length ? <p className="text-xs text-slate-500">Labellers so far: {(d.labellers ?? []).join(", ")}</p> : <p className="text-xs text-slate-500">No labels have been stored yet.</p>}
              </div>
            </Panel>
            <div className="grid gap-3 md:grid-cols-2">
              {queues.map((q, i) => {
                const mine = q.my_progress;
                const total = mine?.total ?? q.n_items ?? 0;
                const done = mine?.done ?? 0;
                const others = (q.progress ?? []).filter((p) => p.labeller !== labeller);
                return (
                  <div key={q.queue} className={cx("flex flex-col rounded-lg border bg-white p-4", q.available === false ? "border-slate-200 opacity-70" : "border-slate-200")}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-lg font-semibold text-slate-900">
                        {i + 1}. {q.title ?? humanize(q.queue)}
                      </h3>
                      <span className="flex gap-1.5">
                        {q.blind ? <Badge tone="violet">blind</Badge> : <Badge tone="white">model labels shown</Badge>}
                        {q.available === false ? <Badge tone="red">not available</Badge> : null}
                      </span>
                    </div>
                    {q.description ? <p className="mt-1 flex-1 text-sm text-slate-600">{q.description}</p> : <div className="flex-1" />}
                    <div className="mt-2 text-sm tabular-nums text-slate-700">
                      n = {num(q.n_items)} items{q.estimated_minutes ? ` · about ${q.estimated_minutes} minutes` : ""}
                    </div>
                    {labeller ? (
                      <div className="mt-2">
                        <div className="flex justify-between text-xs text-slate-500 tabular-nums">
                          <span>your progress</span>
                          <span>
                            {num(done)} of {num(total)}
                          </span>
                        </div>
                        <div className="mt-0.5 h-1.5 w-full rounded-full bg-slate-200">
                          <div className="h-1.5 rounded-full bg-teal-700" style={{ width: `${total ? Math.min(100, (done / total) * 100) : 0}%` }} />
                        </div>
                      </div>
                    ) : null}
                    {others.length ? (
                      <div className="mt-1 text-xs text-slate-500">
                        Others: {others.map((p) => `${p.labeller} ${num(p.done)}/${num(p.total)}${p.last_ts ? ` (last ${fmtDateTime(p.last_ts)})` : ""}`).join(", ")}
                      </div>
                    ) : null}
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      <Button kind="primary" disabled={!labeller || q.available === false} onClick={() => openQueue(q.queue)} title={!labeller ? "Enter your labeller name first" : undefined}>
                        {done > 0 && done < total ? "Continue" : done >= total && total > 0 ? "Review again" : "Start"}
                      </Button>
                      {!labeller ? <span className="text-xs text-slate-500">Enter your name above first.</span> : null}
                      <a href={apiUrl(withQuery("/api/review/export", { queue: q.queue, format: "csv" }))} className="text-sm font-medium text-teal-800 underline underline-offset-2">
                        Export labels (.csv)
                      </a>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      }}
    </DataState>
  );
}

export default function ReviewPage() {
  const router = useRouter();
  const sp = useSearchParams();
  const tab = TABS.some((t) => t.id === sp.get("tab")) ? (sp.get("tab") as string) : "posts";
  return (
    <>
      <PageHeader title="Evidence & Review" lead="Look at the source material behind every number, and check the AI labels by hand. Until people have labelled the review queues, all accuracy numbers are provisional." />
      <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => router.push(`/review?tab=${t.id}`)}
            className={cx("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[0.95rem] font-medium", tab === t.id ? "border-teal-700 text-teal-900" : "border-transparent text-slate-600 hover:text-slate-900")}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "posts" ? <PostBrowser /> : null}
      {tab === "review" ? <ReviewTab /> : null}
      {tab === "accuracy" ? <Accuracy /> : null}
    </>
  );
}
