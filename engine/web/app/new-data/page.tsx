"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState, type DragEvent } from "react";
import { ApiError, apiFetch, apiUrl, toApiError, useApi } from "@/lib/api";
import type { Run, RunsList } from "@/lib/types";
import { fmtDateTime, humanize, num, secs, STATE_ORDER, stateInfo } from "@/lib/format";
import { Badge, Button, DataState, Empty, ErrorBox, N, PageHeader, Panel, cx } from "@/components/ui";

const ACTIVE = new Set(["queued", "running", "pending", "processing"]);
const isActive = (s: string | undefined) => ACTIVE.has(s ?? "");

function StatusBadge({ status }: { status?: string }) {
  const tone = status === "done" ? "green" : status === "failed" ? "red" : status === "done_with_errors" ? "amber" : isActive(status) ? "sky" : "gray";
  return (
    <Badge tone={tone}>
      {isActive(status) ? <span className="cp-skeleton mr-1 inline-block h-1.5 w-1.5 rounded-full bg-sky-700" /> : null}
      {status === "done_with_errors" ? "done, with errors" : (status ?? "unknown")}
    </Badge>
  );
}

function TemplateInfo() {
  const [open, setOpen] = useState(false);
  const state = useApi<unknown>(open ? "/api/batches/template" : null);
  const d = state.data as Record<string, unknown> | undefined;
  const fields = d && Array.isArray(d.fields) ? (d.fields as unknown[]) : null;
  return (
    <div className="text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <a href={apiUrl("/api/batches/template")} target="_blank" rel="noopener noreferrer" className="font-medium text-teal-800 underline underline-offset-2">
          Open the file template ↗
        </a>
        <button onClick={() => setOpen(!open)} className="font-medium text-teal-800 underline underline-offset-2">
          {open ? "Hide field list" : "Show field list"}
        </button>
      </div>
      {open ? (
        <div className="mt-2">
          <DataState state={state} what="the template">
            {() => (
              <div className="space-y-2">
                {fields ? (
                  <ul className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                    {fields.map((f, i) => {
                      if (typeof f === "string") return <li key={i} className="font-mono text-xs text-slate-800">{f}</li>;
                      const o = (f ?? {}) as Record<string, unknown>;
                      return (
                        <li key={i} className="text-xs text-slate-700">
                          <span className="font-mono font-semibold text-slate-900">{String(o.name ?? o.field ?? i)}</span>
                          {o.required ? <span className="ml-1 text-orange-800">required</span> : <span className="ml-1 text-slate-400">optional</span>}
                          {Array.isArray(o.aliases) && o.aliases.length ? <span className="ml-1 text-slate-500">(also: {o.aliases.map(String).join(", ")})</span> : null}
                          {o.description || o.note ? <span className="ml-1">{String(o.description ?? o.note)}</span> : null}
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
                {d && Array.isArray(d.notes) ? (
                  <ul className="list-disc pl-5 text-xs text-slate-600">
                    {(d.notes as unknown[]).map((n, i) => (
                      <li key={i}>{String(n)}</li>
                    ))}
                  </ul>
                ) : null}
                <div className="flex flex-wrap gap-3 text-xs">
                  {d && d.example !== undefined ? (
                    <a download="citypulse_template.json" href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(d.example, null, 2))}`} className="font-medium text-teal-800 underline underline-offset-2">
                      Download example .json
                    </a>
                  ) : null}
                  {d && typeof d.example_csv === "string" ? (
                    <a download="citypulse_template.csv" href={`data:text/csv;charset=utf-8,${encodeURIComponent(d.example_csv)}`} className="font-medium text-teal-800 underline underline-offset-2">
                      Download example .csv
                    </a>
                  ) : null}
                </div>
                <details className="rounded border border-slate-200 bg-slate-50 px-2.5 py-1.5">
                  <summary className="cursor-pointer text-xs text-slate-600">{fields ? "Example file" : "Template as sent by the data service"}</summary>
                  <pre className="mt-1 max-h-72 overflow-auto text-[11px] leading-snug whitespace-pre-wrap text-slate-800">
                    {typeof state.data === "string" ? state.data : JSON.stringify(fields && d ? (d.example ?? d.records ?? d) : state.data, null, 2)}
                  </pre>
                </details>
              </div>
            )}
          </DataState>
        </div>
      ) : null}
    </div>
  );
}

function Uploader({ onUploaded }: { onUploaded: (runId: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [duplicateOf, setDuplicateOf] = useState<string | null>(null);

  const pick = (f: File | null | undefined) => {
    setError(null);
    setDuplicateOf(null);
    setFile(f ?? null);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    pick(e.dataTransfer.files?.[0]);
  };
  const badType = file && !/\.(json|csv)$/i.test(file.name);

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setDuplicateOf(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiFetch<{ run_id: string; status?: string }>("/api/batches", { method: "POST", body: fd });
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onUploaded(res.run_id);
    } catch (e) {
      const err = toApiError(e);
      if (err.status === 409) {
        const body = err.body as { error?: { run_id?: string }; run_id?: string; detail?: { error?: { run_id?: string }; run_id?: string } } | undefined;
        const rid = body?.error?.run_id ?? body?.run_id ?? body?.detail?.error?.run_id ?? body?.detail?.run_id ?? null;
        setDuplicateOf(rid ?? "");
      } else {
        setError(err);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="Upload new posts" hint="A JSON array or a CSV file. Each record needs the post text and its publication date. Author names are hashed on arrival and then dropped.">
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={cx("flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-7 text-center", over ? "border-teal-600 bg-teal-50" : "border-slate-300 bg-slate-50 hover:border-slate-400")}
      >
        <input ref={inputRef} type="file" accept=".json,.csv,application/json,text/csv" className="sr-only" onChange={(e) => pick(e.target.files?.[0])} />
        {file ? (
          <>
            <span className="text-base font-semibold text-slate-900">{file.name}</span>
            <span className="text-sm text-slate-500">{num(Math.max(1, Math.round(file.size / 1024)))} KB · click to choose another file</span>
          </>
        ) : (
          <>
            <span className="text-base font-medium text-slate-800">Drop a JSON or CSV file here, or click to choose</span>
            <span className="text-sm text-slate-500">The file stays on this machine and is processed locally.</span>
          </>
        )}
      </label>
      {badType ? <p className="mt-2 text-sm text-amber-800">This does not look like a .json or .csv file. The data service may reject it.</p> : null}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <Button kind="primary" onClick={upload} disabled={!file || busy}>
          {busy ? "Uploading…" : "Upload and process"}
        </Button>
        <TemplateInfo />
      </div>
      {duplicateOf !== null ? (
        <div role="status" className="mt-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2.5 text-sm text-sky-950">
          <div className="font-medium">This exact file was already processed.</div>
          <div className="mt-0.5">
            Nothing was uploaded again, so no post is counted twice.{" "}
            {duplicateOf ? (
              <Link href={`/new-data?run=${encodeURIComponent(duplicateOf)}`} className="font-medium underline underline-offset-2">
                Open the earlier run {duplicateOf} →
              </Link>
            ) : (
              "Find the earlier run in the history below."
            )}
          </div>
        </div>
      ) : null}
      {error ? (
        <div className="mt-3">
          <ErrorBox error={error} what="the upload result" />
        </div>
      ) : null}
    </Panel>
  );
}

function StepIcon({ status }: { status?: string }) {
  const s = status ?? "";
  if (s === "done" || s === "ok" || s === "completed") return <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-600 text-xs font-bold text-white">✓</span>;
  if (s === "failed" || s === "error") return <span className="flex h-6 w-6 items-center justify-center rounded-full bg-red-600 text-xs font-bold text-white">!</span>;
  if (s === "running") return <span className="cp-skeleton flex h-6 w-6 items-center justify-center rounded-full bg-sky-600 text-xs font-bold text-white">…</span>;
  if (s === "skipped") return <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-200 text-xs text-slate-500">–</span>;
  return <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-slate-300 bg-white" />;
}

function RunDetail({ runId }: { runId: string }) {
  const state = useApi<Run>(`/api/batches/${encodeURIComponent(runId)}`, 1500, (d) => !d || isActive(d.status));
  return (
    <Panel title={`Run ${runId}`} right={state.data ? <StatusBadge status={state.data.status} /> : null}>
      <DataState state={state} what="the run">
        {(r) => {
          const steps = r.steps ?? [];
          const errors = r.errors ?? [];
          const concerns = r.findings?.concerns ?? [];
          const counts = Object.entries(r.counts ?? {});
          const finished = !isActive(r.status);
          const totalSecs = steps.reduce((a, s) => a + (s.secs ?? 0), 0);
          return (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
                <span>
                  File <span className="font-medium text-slate-900">{r.filename ?? "(unnamed)"}</span>
                </span>
                <span>uploaded {fmtDateTime(r.created_at)}</span>
                {r.sha256 ? <span className="font-mono text-xs text-slate-400" title={r.sha256}>sha256 {r.sha256.slice(0, 12)}…</span> : null}
                {!finished ? <span className="text-sky-800">Updating every 1.5 seconds</span> : <span>total processing time {secs(totalSecs)}</span>}
                {state.error ? <span className="text-red-800">Last update failed: {state.error.message}</span> : null}
              </div>

              <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-900">Processing steps</h3>
                {steps.length ? (
                  <ol className="space-y-1">
                    {steps.map((s, i) => (
                      <li key={`${s.name}-${i}`} className={cx("grid grid-cols-[auto_1fr] items-center gap-x-3 rounded-md border px-3 py-2 sm:grid-cols-[auto_9rem_1fr_auto]", s.status === "running" ? "border-sky-300 bg-sky-50" : s.status === "failed" ? "border-red-200 bg-red-50" : "border-slate-200 bg-white")}>
                        <StepIcon status={s.status} />
                        <div className="text-[0.95rem] font-medium text-slate-900">
                          {i + 1}. {humanize(s.name)}
                        </div>
                        <div className="col-span-2 text-sm text-slate-600 sm:col-span-1">
                          {s.status === "pending" || s.status === "queued" || !s.status ? (
                            <span className="text-slate-400">waiting</span>
                          ) : (
                            <span className="tabular-nums">
                              {num(s.n_in)} in → {num(s.n_out)} out
                            </span>
                          )}
                          {s.message ? <span className="ml-2 text-slate-500">{s.message}</span> : null}
                        </div>
                        <div className="col-span-2 text-right text-xs tabular-nums text-slate-500 sm:col-span-1">{s.status === "pending" || !s.status ? "" : secs(s.secs)}</div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <Empty>{finished ? "This run has no recorded steps." : "Waiting for the first step to start."}</Empty>
                )}
              </div>

              {counts.length ? (
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-slate-900">Counts</h3>
                  <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                    {counts.map(([k, v]) => (
                      <div key={k} className="rounded border border-slate-200 bg-slate-50 px-2.5 py-1.5">
                        <dt className="text-xs text-slate-500">{humanize(k)}</dt>
                        <dd className="text-xl font-semibold tabular-nums text-slate-900">{num(v)}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ) : null}

              <div>
                <h3 className="mb-2 flex items-baseline gap-2 text-sm font-semibold text-slate-900">
                  Records with errors <N n={errors.length} />
                </h3>
                {errors.length ? (
                  <div className="max-h-72 overflow-auto rounded-md border border-red-200">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-red-50 text-left text-xs text-red-900">
                        <tr>
                          <th className="px-2.5 py-1.5 font-medium">Record</th>
                          <th className="px-2.5 py-1.5 font-medium">Step</th>
                          <th className="px-2.5 py-1.5 font-medium">What went wrong</th>
                        </tr>
                      </thead>
                      <tbody>
                        {errors.map((e, i) => (
                          <tr key={i} className="border-t border-red-100">
                            <td className="px-2.5 py-1.5 font-mono text-xs text-slate-800">{String(e.record ?? "–")}</td>
                            <td className="px-2.5 py-1.5 text-slate-700">{humanize(e.step) || "–"}</td>
                            <td className="px-2.5 py-1.5 text-slate-800">{e.message ?? "–"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-sm text-slate-500">{finished ? "No record was rejected." : "None so far."}</p>
                )}
              </div>

              <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                <h3 className="flex items-baseline gap-2 text-sm font-semibold text-slate-900">
                  Findings from this run <N n={concerns.length} label="concerns" />
                </h3>
                {concerns.length ? (
                  <>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {[...STATE_ORDER, ...Array.from(new Set(concerns.map((c) => c.state ?? ""))).filter((s) => !(STATE_ORDER as readonly string[]).includes(s))].map((s) => {
                        const n = concerns.filter((c) => (c.state ?? "") === s).length;
                        return n ? (
                          <Badge key={s} tone={stateInfo(s).tone}>
                            {stateInfo(s).short}: {n}
                          </Badge>
                        ) : null;
                      })}
                    </div>
                    <Link href={`/emerging?run_id=${encodeURIComponent(r.run_id ?? runId)}`} className="mt-2 inline-block rounded-md border border-teal-700 bg-teal-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-teal-800">
                      See these in Emerging Concerns →
                    </Link>
                  </>
                ) : (
                  <p className="mt-1 text-sm text-slate-500">{finished ? "This run produced no concerns." : "Findings appear when the run has finished."}</p>
                )}
              </div>

              {Object.keys(r.models ?? {}).length ? (
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                  <span>Models used:</span>
                  {Object.entries(r.models ?? {}).map(([k, v]) => (
                    <Badge key={k} tone="white">
                      {k}: {String(v)}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </div>
          );
        }}
      </DataState>
    </Panel>
  );
}

export default function NewDataPage() {
  const router = useRouter();
  const selected = useSearchParams().get("run");
  const history = useApi<RunsList>("/api/batches", 4000, (d) => !d || (d.runs ?? []).some((r) => isActive(r.status)));

  const onUploaded = (runId: string) => {
    history.reload();
    router.push(`/new-data?run=${encodeURIComponent(runId)}`);
  };

  return (
    <>
      <PageHeader title="New Data" lead="Add newly collected posts. They are cleaned, labelled, split into claims and compared with every earlier claim. Results appear under Emerging Concerns." />
      <div className="space-y-4">
        <Uploader onUploaded={onUploaded} />
        {selected ? <RunDetail key={selected} runId={selected} /> : null}
        <Panel title="Run history" hint="Newest first." right={history.data ? <N n={(history.data.runs ?? []).length} label="runs" /> : null}>
          <DataState state={history} what="the run history" isEmpty={(d) => !(d.runs ?? []).length} empty="No file has been uploaded yet.">
            {(d) => (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[40rem] text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                      <th className="py-1.5 pr-3 font-medium">Uploaded</th>
                      <th className="py-1.5 pr-3 font-medium">File</th>
                      <th className="py-1.5 pr-3 font-medium">Status</th>
                      <th className="py-1.5 pr-3 text-right font-medium">Records</th>
                      <th className="py-1.5 pr-3 text-right font-medium">Claims</th>
                      <th className="py-1.5 pr-3 text-right font-medium">New</th>
                      <th className="py-1.5 pr-3 text-right font-medium">Errors</th>
                      <th className="py-1.5 font-medium" />
                    </tr>
                  </thead>
                  <tbody>
                    {(d.runs ?? []).map((r) => (
                      <tr key={r.run_id} className={cx("border-b border-slate-100", selected === r.run_id && "bg-teal-50")}>
                        <td className="py-2 pr-3 tabular-nums whitespace-nowrap text-slate-800">{fmtDateTime(r.created_at)}</td>
                        <td className="max-w-[16rem] truncate py-2 pr-3 text-slate-900">{r.filename ?? "(unnamed)"}</td>
                        <td className="py-2 pr-3">
                          <StatusBadge status={r.status} />
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">{num(r.counts?.records)}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{num(r.counts?.claims)}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{num(r.counts?.new)}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{r.errors ? num(r.errors.length) : "–"}</td>
                        <td className="py-2 text-right whitespace-nowrap">
                          <Link href={`/new-data?run=${encodeURIComponent(r.run_id)}`} className="font-medium text-teal-800 underline underline-offset-2">
                            Details
                          </Link>
                          {!isActive(r.status) && r.status !== "failed" ? (
                            <Link href={`/emerging?run_id=${encodeURIComponent(r.run_id)}`} className="ml-3 font-medium text-teal-800 underline underline-offset-2">
                              Concerns
                            </Link>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </DataState>
        </Panel>
      </div>
    </>
  );
}
