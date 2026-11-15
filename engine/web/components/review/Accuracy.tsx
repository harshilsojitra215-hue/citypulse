"use client";

import type { ReactNode } from "react";
import { apiPost, useAction, useApi } from "@/lib/api";
import { fmtDateTime, humanize, num } from "@/lib/format";
import { useApp } from "@/components/AppContext";
import { Badge, Button, DataState, Empty, ErrorBox, N, Panel, cx } from "@/components/ui";

type Row = Record<string, unknown>;

function isObj(v: unknown): v is Row {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

function cell(v: unknown): string {
  if (v === null || v === undefined) return "–";
  if (typeof v === "number") return Number.isInteger(v) ? num(v) : v.toFixed(2);
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function Provisional() {
  return (
    <Badge tone="orange" title="Agreement with an AI reference, not human-validated">
      provisional
    </Badge>
  );
}

function Table({ rows, columns, highlight }: { rows: Row[]; columns: { key: string; label: string; render?: (r: Row) => ReactNode }[]; highlight?: (r: Row) => boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[34rem] text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
            {columns.map((c) => (
              <th key={c.key} className="px-2 py-1.5 font-medium first:pl-0">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={cx("border-b border-slate-100", highlight?.(r) && "bg-teal-50 font-medium")}>
              {columns.map((c) => (
                <td key={c.key} className="px-2 py-1.5 tabular-nums text-slate-800 first:pl-0">
                  {c.render ? c.render(r) : cell(r[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Renders any JSON section without knowing its fields in advance. */
function AutoView({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-sm text-slate-400">none</span>;
    if (value.every(isObj)) {
      const keys = Array.from(new Set(value.flatMap((r) => Object.keys(r as Row)))).filter((k) => value.some((r) => typeof (r as Row)[k] !== "object" || (r as Row)[k] === null));
      return <Table rows={value as Row[]} columns={keys.map((k) => ({ key: k, label: humanize(k) }))} />;
    }
    return <span className="text-sm text-slate-700">{value.map(cell).join(", ")}</span>;
  }
  if (isObj(value)) {
    const scalars = Object.entries(value).filter(([, v]) => typeof v !== "object" || v === null);
    const nested = Object.entries(value).filter(([, v]) => typeof v === "object" && v !== null);
    return (
      <div className="space-y-2">
        {scalars.length ? (
          <div className="flex flex-wrap gap-1.5">
            {scalars.map(([k, v]) => (
              <span key={k} className="rounded border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-700">
                {humanize(k)}: <span className="font-semibold tabular-nums text-slate-900">{cell(v)}</span>
              </span>
            ))}
          </div>
        ) : null}
        {depth < 3
          ? nested.map(([k, v]) => (
              <div key={k}>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{humanize(k)}</div>
                <AutoView value={v} depth={depth + 1} />
              </div>
            ))
          : null}
      </div>
    );
  }
  return <span className="text-sm text-slate-700">{cell(value)}</span>;
}

function f1WithInterval(r: Row): ReactNode {
  const lo = r.f1_lo;
  const hi = r.f1_hi;
  return (
    <>
      {cell(r.f1)}
      {typeof lo === "number" && typeof hi === "number" ? <span className="ml-1 text-xs font-normal text-slate-500">({lo.toFixed(2)}–{hi.toFixed(2)})</span> : null}
    </>
  );
}

function ReferenceBlock({ name, data }: { name: string; data: Row }) {
  const ref = data;
  const pm = isObj(ref.pair_matching) ? ref.pair_matching : null;
  const nov = isObj(ref.novelty) ? ref.novelty : null;
  const selectedName = String(ref.selected_method ?? (isObj(pm?.selected) ? (pm?.selected as Row).method : ""));
  const pmRows = pm ? ([pm.baseline, pm.selected].filter(isObj) as Row[]) : [];
  const pmAll = pm && Array.isArray(pm.all_methods) ? (pm.all_methods.filter(isObj) as Row[]) : [];
  const novRows = nov ? [...(Array.isArray(nov.baseline) ? nov.baseline : []), ...(Array.isArray(nov.selected) ? nov.selected : [])].filter(isObj) : [];
  const pmCols = [
    { key: "method", label: "Method" },
    { key: "precision", label: "Precision" },
    { key: "recall", label: "Recall" },
    { key: "f1", label: "F1 (interval)", render: f1WithInterval },
  ];
  return (
    <div className="space-y-4 rounded-md border border-slate-200 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-slate-900">Measured against AI reference “{name}”</h3>
        <Provisional />
      </div>
      {pmRows.length ? (
        <div>
          <div className="mb-1 flex flex-wrap items-baseline gap-2 text-sm font-medium text-slate-800">
            Is a pair of claims the same argument? <N n={typeof ref.n_test_pairs === "number" ? ref.n_test_pairs : undefined} label="test pairs" />
          </div>
          <Table rows={pmRows} columns={pmCols} highlight={(r) => String(r.method) === selectedName} />
          {pmAll.length > pmRows.length ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-teal-800 underline underline-offset-2">All {pmAll.length} methods that were compared</summary>
              <div className="mt-1">
                <Table rows={pmAll} columns={pmCols} highlight={(r) => String(r.method) === selectedName} />
              </div>
            </details>
          ) : null}
        </div>
      ) : null}
      {novRows.length ? (
        <div>
          <div className="mb-1 text-sm font-medium text-slate-800">Is a claim new?</div>
          <Table
            rows={novRows}
            highlight={(r) => String(r.method) === selectedName}
            columns={[
              { key: "scope", label: "Scope" },
              { key: "method", label: "Method" },
              { key: "n", label: "n claims" },
              { key: "n_novel", label: "of which new" },
              { key: "precision", label: "Precision" },
              { key: "recall", label: "Recall" },
              { key: "f1", label: "F1" },
              { key: "familiar_wrongly_flagged", label: "Known claims wrongly flagged" },
            ]}
          />
        </div>
      ) : null}
      {!pmRows.length && !novRows.length ? <AutoView value={ref} /> : null}
    </div>
  );
}

export function Accuracy() {
  const { meta } = useApp();
  const results = useApi<Row>("/api/review/results");
  const [evalState, runEval] = useAction<Row>();
  const human = (evalState.data ?? results.data) as Row | undefined;
  const queues = human ? Object.entries(human).filter(([, v]) => isObj(v) && "n_items" in (v as Row)) : [];

  return (
    <div className="space-y-4">
      <Panel
        title="Agreement with human labels"
        hint="Computed from the labels people have entered in the review queues. This is the only place where the system is compared with people."
        right={
          <Button
            onClick={async () => {
              await runEval(() => apiPost<Row>("/api/review/evaluate", {}));
              results.reload();
            }}
            disabled={evalState.loading}
          >
            {evalState.loading ? "Recomputing…" : "Recompute from current labels"}
          </Button>
        }
      >
        {evalState.error ? (
          <div className="mb-3">
            <ErrorBox error={evalState.error} what="the evaluation" />
          </div>
        ) : null}
        <DataState state={{ ...results, data: human, loading: results.loading && !human }} what="human review results">
          {(h) =>
            h.available === false ? (
              <Empty>{String(h.message ?? "No evaluation has been run yet.")}</Empty>
            ) : (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
                  {h.generated_at ? <span>computed {fmtDateTime(String(h.generated_at))}</span> : null}
                  {typeof h.n_annotations === "number" ? <N n={h.n_annotations} label="stored labels" /> : null}
                  {h.complete !== true ? <Provisional /> : <Badge tone="green">all queues fully labelled</Badge>}
                  {h.message ? <span>{String(h.message)}</span> : null}
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {queues.map(([name, v]) => {
                    const sec = v as Row;
                    const nItems = Number(sec.n_items ?? 0);
                    const nLab = Number(sec.n_labelled ?? 0);
                    const status = sec.status;
                    const rest = Object.fromEntries(Object.entries(sec).filter(([k]) => !["status", "n_items", "n_labelled", "complete"].includes(k)));
                    return (
                      <div key={name} className="rounded-md border border-slate-200 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h3 className="text-base font-semibold text-slate-900">{humanize(name)}</h3>
                          {nLab < nItems ? <Provisional /> : <Badge tone="green">complete</Badge>}
                        </div>
                        <div className="mt-1 text-sm tabular-nums text-slate-700">
                          {num(nLab)} of {num(nItems)} items labelled by a person
                        </div>
                        <div className="mt-1 h-1.5 w-full rounded-full bg-slate-200">
                          <div className="h-1.5 rounded-full bg-teal-700" style={{ width: `${nItems ? Math.min(100, (nLab / nItems) * 100) : 0}%` }} />
                        </div>
                        {status && status !== "ok" ? <p className="mt-2 text-sm text-slate-500">{String(status)}</p> : null}
                        {nLab > 0 ? (
                          <div className="mt-2">
                            <AutoView value={rest} />
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
                {h.provisional_note ? <p className="text-xs text-slate-500">{String(h.provisional_note)}</p> : null}
              </div>
            )
          }
        </DataState>
      </Panel>

      <Panel title="Benchmark numbers so far" hint="How the matcher scores on held-out test data, judged by AI reference labels." right={<Provisional />}>
        <DataState state={meta} what="benchmark numbers">
          {(m) => {
            const metrics = (m.metrics ?? {}) as Row;
            const refs = isObj(metrics.references) ? Object.entries(metrics.references).filter(([, v]) => isObj(v)) : [];
            const agreement = isObj(metrics.annotator_agreement) ? metrics.annotator_agreement : null;
            if (!Object.keys(metrics).length) return <Empty>The data service sent no benchmark numbers.</Empty>;
            return (
              <div className="space-y-4">
                <div className="rounded-md border border-orange-200 bg-orange-50 px-3 py-2 text-sm text-orange-950">
                  <span className="font-semibold">Provisional: agreement with an AI reference, not human-validated.</span> {metrics.explanation ? String(metrics.explanation) : metrics.note ? String(metrics.note) : ""}
                </div>
                {refs.map(([name, v]) => (
                  <ReferenceBlock key={name} name={name} data={v as Row} />
                ))}
                {agreement ? (
                  <div className="rounded-md border border-slate-200 p-3">
                    <h3 className="text-base font-semibold text-slate-900">How much the two AI references agree with each other</h3>
                    <div className="mt-2">
                      <AutoView value={agreement} />
                    </div>
                  </div>
                ) : null}
                {!refs.length ? <AutoView value={metrics} /> : null}
                {m.model ? (
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                    <span>Matcher model:</span>
                    {Object.entries(m.model)
                      .filter(([, v]) => v !== null && typeof v !== "object")
                      .map(([k, v]) => (
                        <Badge key={k} tone="white">
                          {humanize(k)}: {String(v)}
                        </Badge>
                      ))}
                  </div>
                ) : null}
              </div>
            );
          }}
        </DataState>
      </Panel>
    </div>
  );
}
