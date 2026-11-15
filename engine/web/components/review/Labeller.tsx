"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiPost, toApiError, useApi, withQuery } from "@/lib/api";
import { fmtDate, humanize, isHttpUrl, num } from "@/lib/format";
import { useApp } from "@/components/AppContext";
import { Badge, Button, DataState, Empty, ErrorBox, cx } from "@/components/ui";

export type SchemaEntry = {
  required?: boolean;
  values?: string[];
  format?: string;
  required_when?: Record<string, string[]>;
  allowed_when?: Record<string, string[]>;
};
export type Progress = { labeller?: string; done?: number; total?: number; last_ts?: string | null };
export type ReviewQueue = {
  queue: string;
  title?: string;
  description?: string;
  blind?: boolean;
  available?: boolean;
  n_items?: number;
  estimated_minutes?: number;
  label_schema?: Record<string, SchemaEntry>;
  guidelines?: string;
  progress?: Progress[];
  my_progress?: Progress | null;
};
type Annotation = { label?: Record<string, string | null> | null; note?: string; ts?: string; rev?: number };
type Item = {
  queue?: string;
  item_id: string;
  position?: number;
  data?: Record<string, unknown>;
  my_annotation?: Annotation | null;
  revealed?: Record<string, unknown> | null;
  history?: Annotation[];
};
type NextResponse = { progress?: Progress; item?: Item | null } & Partial<Item>;
type SaveResponse = { ok?: boolean; annotation?: Annotation; progress?: Progress; item?: Item; next_item_id?: string | null };

function condOk(cond: Record<string, string[]> | undefined, sel: Record<string, string>): boolean {
  if (!cond) return true;
  return Object.entries(cond).every(([k, allowed]) => allowed.includes(sel[k] ?? ""));
}

function str(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

function PostBox({ d }: { d: Record<string, unknown> }) {
  const url = str(d.url);
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-600">
        <span className="font-semibold text-slate-900">{fmtDate(str(d.date))}</span>
        <span className="font-medium text-slate-800">{str(d.domain) || "unknown source"}</span>
        {d.channel ? <span>{humanize(str(d.channel))}</span> : null}
        {isHttpUrl(url) ? (
          <a href={url} target="_blank" rel="noopener noreferrer" className="ml-auto font-medium text-teal-800 underline underline-offset-2">
            Open source ↗
          </a>
        ) : null}
      </div>
      {d.title ? <div className="mt-2 text-base font-semibold text-slate-900">{str(d.title)}</div> : null}
      <p className="mt-1.5 text-[0.95rem] leading-relaxed whitespace-pre-line text-slate-800">{str(d.excerpt) || "No excerpt."}</p>
    </div>
  );
}

function ItemData({ queue, d }: { queue: string; d: Record<string, unknown> }) {
  const { projectName } = useApp();
  if (queue === "pairs" || ("q_claim" in d && "c_claim" in d)) {
    return (
      <div className="grid gap-3 md:grid-cols-2">
        {[
          ["Claim A", d.q_claim, d.q_project],
          ["Claim B", d.c_claim, d.c_project],
        ].map(([label, claim, project]) => (
          <div key={str(label)} className="rounded-md border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between gap-2 text-xs text-slate-500">
              <span className="font-semibold uppercase tracking-wide">{str(label)}</span>
              {project ? <Badge tone="white">{projectName(str(project))}</Badge> : null}
            </div>
            <p className="mt-2 text-lg font-medium leading-snug text-slate-900">“{str(claim)}”</p>
          </div>
        ))}
      </div>
    );
  }
  if (queue === "events" || "event_id" in d) {
    const url = str(d.source_url);
    return (
      <div className="rounded-md border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <span className="text-base font-semibold text-slate-900">{fmtDate(str(d.date))}</span>
          {d.date_precision ? <span className="text-xs">precision: {str(d.date_precision)}</span> : null}
          {d.project ? <Badge tone="white">{projectName(str(d.project))}</Badge> : null}
          {d.event_type ? <Badge tone="white">{humanize(str(d.event_type))}</Badge> : null}
          <Badge tone={d.verified === "yes" ? "green" : "white"}>{d.verified === "yes" ? "marked verified" : "not verified yet"}</Badge>
        </div>
        <div className="mt-2 text-lg font-semibold leading-snug text-slate-900">{str(d.title_en) || str(d.title)}</div>
        {d.detail ? <p className="mt-1 text-[0.95rem] leading-relaxed text-slate-700">{str(d.detail)}</p> : null}
        <div className="mt-2 text-sm">
          {isHttpUrl(url) ? (
            <a href={url} target="_blank" rel="noopener noreferrer" className="font-medium text-teal-800 underline underline-offset-2">
              Open the source{d.source_name ? `: ${str(d.source_name)}` : ""} ↗
            </a>
          ) : (
            <span className="text-slate-500">No source link recorded.</span>
          )}
        </div>
      </div>
    );
  }
  if ("excerpt" in d || "doc_id" in d) {
    const models = Array.isArray(d.models) ? (d.models as Record<string, unknown>[]) : [];
    return (
      <div className="space-y-3">
        <PostBox d={d} />
        {models.length ? (
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">The models disagree on this post</div>
            <table className="text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500">
                  <th className="pr-6 font-medium">Model</th>
                  <th className="pr-6 font-medium">About</th>
                  <th className="font-medium">Stance</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m, i) => (
                  <tr key={i}>
                    <td className="pr-6 font-medium text-slate-800">{str(m.model)}</td>
                    <td className="pr-6 text-slate-700">{m.project ? projectName(str(m.project)) : "no label"}</td>
                    <td className="text-slate-700">{str(m.stance) || "no label"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    );
  }
  return (
    <dl className="grid gap-x-4 gap-y-1 rounded-md border border-slate-200 bg-white p-4 text-sm sm:grid-cols-[10rem_1fr]">
      {Object.entries(d).map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-slate-500">{humanize(k)}</dt>
          <dd className="text-slate-900">{typeof v === "object" ? JSON.stringify(v) : str(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function ItemForm({
  queue,
  item,
  labeller,
  saved,
  onSaved,
  onNext,
  onBack,
  canBack,
}: {
  queue: ReviewQueue;
  item: Item;
  labeller: string;
  saved: SaveResponse | null;
  onSaved: (r: SaveResponse) => void;
  onNext: () => void;
  onBack: () => void;
  canBack: boolean;
}) {
  const { projectName } = useApp();
  const schema = queue.label_schema ?? {};
  const keys = Object.keys(schema);
  const prior = item.my_annotation?.label ?? null;
  const [sel, setSel] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const [k, v] of Object.entries(prior ?? {})) if (v !== null && v !== undefined) init[k] = String(v);
    return init;
  });
  const [note, setNote] = useState(item.my_annotation?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const visible = (k: string) => condOk(schema[k].required_when, sel) && condOk(schema[k].allowed_when, sel);
  const needed = (k: string) => schema[k].required === true || (!!schema[k].required_when && condOk(schema[k].required_when, sel));
  const noteNeeded = sel.verdict === "wrong_content" || sel.verdict === "source_dead";
  const single = keys.length === 1 && !!schema[keys[0]].values;

  const buildLabel = (s: Record<string, string>) => {
    const label: Record<string, string> = {};
    for (const k of keys) {
      const ok = condOk(schema[k].required_when, s) && condOk(schema[k].allowed_when, s);
      if (ok && s[k]) label[k] = s[k];
    }
    return label;
  };
  const complete = (s: Record<string, string>) => keys.every((k) => !(schema[k].required === true || (!!schema[k].required_when && condOk(schema[k].required_when, s))) || !!s[k]);

  const save = useCallback(
    async (s: Record<string, string>, n: string) => {
      setBusy(true);
      setError(null);
      try {
        const res = await apiPost<SaveResponse>("/api/review/annotations", { queue: queue.queue, item_id: item.item_id, label: buildLabel(s), labeller, note: n });
        onSaved(res);
      } catch (e) {
        setError(toApiError(e));
      } finally {
        setBusy(false);
      }
    },
    // buildLabel only depends on the schema of this queue
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queue.queue, item.item_id, labeller, onSaved],
  );

  const choose = (k: string, v: string) => {
    if (saved || busy) return;
    const next = { ...sel, [k]: v };
    setSel(next);
    if (single) void save(next, note);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (saved) {
        if (e.key === "Enter" || e.key === "ArrowRight") {
          e.preventDefault();
          onNext();
        }
        return;
      }
      if (e.key === "ArrowLeft" && canBack) {
        onBack();
        return;
      }
      if (single && !busy) {
        const values = schema[keys[0]].values ?? [];
        const idx = Number(e.key) - 1;
        if (Number.isInteger(idx) && idx >= 0 && idx < values.length) {
          const next = { ...sel, [keys[0]]: values[idx] };
          setSel(next);
          void save(next, note);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const revealed = saved?.item?.revealed ?? item.revealed;
  const current = saved?.annotation ?? item.my_annotation;

  return (
    <div className="space-y-4">
      <ItemData queue={queue.queue} d={item.data ?? {}} />

      {item.my_annotation && !saved ? (
        <p className="rounded border border-sky-200 bg-sky-50 px-3 py-1.5 text-sm text-sky-950">
          You already labelled this item (revision {item.my_annotation.rev ?? 1}). Saving again records a correction; the earlier label stays in the history.
        </p>
      ) : null}

      <div className="space-y-3 rounded-md border border-slate-200 bg-slate-50 p-3">
        {keys.map((k) => {
          const entry = schema[k];
          if (!visible(k)) return null;
          return (
            <div key={k}>
              <div className="mb-1 text-sm font-medium text-slate-800">
                {humanize(k)} {needed(k) ? null : <span className="font-normal text-slate-400">(optional)</span>}
              </div>
              {entry.values ? (
                <div className="flex flex-wrap gap-2">
                  {entry.values.map((v, i) => (
                    <button
                      key={v}
                      type="button"
                      disabled={!!saved || busy}
                      onClick={() => choose(k, v)}
                      className={cx(
                        "rounded-md border px-3 py-2 text-[0.95rem] font-medium disabled:cursor-not-allowed",
                        sel[k] === v ? "border-teal-700 bg-teal-700 text-white" : "border-slate-300 bg-white text-slate-800 hover:bg-slate-100 disabled:opacity-50",
                      )}
                    >
                      {single ? <span className={cx("mr-1.5 rounded px-1 text-xs tabular-nums", sel[k] === v ? "bg-teal-900/40" : "bg-slate-100 text-slate-500")}>{i + 1}</span> : null}
                      {k === "project" ? projectName(v) : humanize(v)}
                    </button>
                  ))}
                  {!needed(k) && sel[k] && !saved ? (
                    <button type="button" onClick={() => setSel((prev) => Object.fromEntries(Object.entries(prev).filter(([key]) => key !== k)))} className="text-sm text-slate-500 underline underline-offset-2">
                      clear
                    </button>
                  ) : null}
                </div>
              ) : (
                <input
                  value={sel[k] ?? ""}
                  disabled={!!saved || busy}
                  onChange={(e) => setSel({ ...sel, [k]: e.target.value })}
                  placeholder={entry.format === "date" ? "YYYY-MM-DD" : ""}
                  className="w-48 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
                />
              )}
            </div>
          );
        })}
        <div>
          <div className="mb-1 text-sm font-medium text-slate-800">
            Note {noteNeeded ? <span className="font-normal text-orange-800">(please say what is wrong, or give a working link)</span> : <span className="font-normal text-slate-400">(optional)</span>}
          </div>
          <textarea
            value={note}
            disabled={!!saved || busy}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            maxLength={2000}
            className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus:border-teal-600 focus:outline-none disabled:bg-slate-100"
          />
        </div>
        {!saved ? (
          <div className="flex flex-wrap items-center gap-2">
            {!single || noteNeeded || item.my_annotation ? (
              <Button kind="primary" disabled={busy || !complete(sel) || (noteNeeded && !note.trim())} onClick={() => void save(sel, note)}>
                {busy ? "Saving…" : item.my_annotation ? "Save correction" : "Save label"}
              </Button>
            ) : (
              <span className="text-sm text-slate-500">{busy ? "Saving…" : "Click a label or press its number. It is saved at once."}</span>
            )}
            <Button onClick={onBack} disabled={!canBack || busy} title="Left arrow">
              ← Previous item
            </Button>
          </div>
        ) : null}
        {error ? <ErrorBox error={error} what="the save result" /> : null}
      </div>

      {saved ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
          <div className="text-sm font-medium text-emerald-950">
            Saved{current?.rev && current.rev > 1 ? ` as revision ${current.rev}` : ""}: {Object.entries(current?.label ?? {}).map(([k, v]) => `${humanize(k).toLowerCase()} = ${v}`).join(", ") || "label retracted"}
          </div>
          {revealed && Object.keys(revealed).length ? (
            <div className="mt-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-emerald-900">Now revealed: what the models said</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {Object.entries(revealed).map(([k, v]) => (
                  <Badge key={k} tone="white">
                    {humanize(k)}: {k.endsWith("project") ? projectName(str(v)) : str(v)}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button kind="primary" onClick={onNext} title="Enter">
              Next item →
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function Labeller({ queue, labeller, onExit, onChanged }: { queue: ReviewQueue; labeller: string; onExit: () => void; onChanged: () => void }) {
  const [targetId, setTargetId] = useState<string | null>(null);
  const [saved, setSaved] = useState<{ id: string; res: SaveResponse } | null>(null);
  const [trail, setTrail] = useState<string[]>([]);
  const base = `/api/review/queues/${encodeURIComponent(queue.queue)}`;
  const path = targetId ? withQuery(`${base}/items/${encodeURIComponent(targetId)}`, { labeller }) : withQuery(`${base}/next`, { labeller });
  const state = useApi<NextResponse>(path);

  const d = state.data;
  const item: Item | null = d ? ("item" in d ? (d.item ?? null) : d.item_id ? (d as Item) : null) : null;
  const progress = (saved?.res.progress ?? d?.progress ?? queue.my_progress) as Progress | undefined | null;
  const done = progress?.done ?? 0;
  const total = progress?.total ?? queue.n_items ?? 0;

  const goNext = () => {
    setSaved(null);
    if (targetId) setTargetId(null);
    else state.reload();
  };
  const idx = item ? trail.indexOf(item.item_id) : -1;
  const prevId = idx > 0 ? trail[idx - 1] : idx === -1 && trail.length ? trail[trail.length - 1] : null;
  const goBack = () => {
    if (!prevId) return;
    setSaved(null);
    setTargetId(prevId);
  };
  const onSaved = (res: SaveResponse) => {
    if (!item) return;
    setSaved({ id: item.item_id, res });
    setTrail((t) => (t.includes(item.item_id) ? t : [...t, item.item_id]));
    onChanged();
  };
  const savedForItem = saved && item && saved.id === item.item_id ? saved.res : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">{queue.title ?? humanize(queue.queue)}</h2>
          {queue.description ? <p className="text-sm text-slate-600">{queue.description}</p> : null}
        </div>
        <div className="flex items-center gap-2">
          {queue.blind ? <Badge tone="violet" title="Model labels stay hidden until you have labelled the item">blind: model labels hidden until you decide</Badge> : <Badge tone="white">model labels shown</Badge>}
          <Button onClick={onExit}>All queues</Button>
        </div>
      </div>

      <div>
        <div className="flex justify-between text-sm text-slate-600">
          <span>
            Labeller <span className="font-mono font-medium text-slate-900">{labeller}</span>
          </span>
          <span className="tabular-nums">
            {num(done)} of {num(total)} done
          </span>
        </div>
        <div className="mt-1 h-2 w-full rounded-full bg-slate-200">
          <div className="h-2 rounded-full bg-teal-700 transition-all" style={{ width: `${total ? Math.min(100, (done / total) * 100) : 0}%` }} />
        </div>
      </div>

      {queue.guidelines ? (
        <details className="rounded-md border border-slate-200 bg-white px-3 py-2">
          <summary className="cursor-pointer text-sm font-medium text-slate-800">Labelling rules for this queue</summary>
          <div className="mt-2 max-h-80 overflow-y-auto text-sm leading-relaxed whitespace-pre-wrap text-slate-700">{queue.guidelines}</div>
        </details>
      ) : null}

      <DataState state={state} what="the next item">
        {() =>
          item ? (
            <div>
              <div className="mb-2 text-xs text-slate-500">
                Item {item.position !== undefined ? item.position + 1 : "?"} of {num(queue.n_items)} {targetId ? "· revisiting an earlier item" : ""}
              </div>
              <ItemForm key={`${item.item_id}|${item.my_annotation?.rev ?? 0}`} queue={queue} item={item} labeller={labeller} saved={savedForItem} onSaved={onSaved} onNext={goNext} onBack={goBack} canBack={!!prevId} />
            </div>
          ) : (
            <Empty>
              <p className="text-base font-medium text-slate-800">This queue is finished for {labeller}.</p>
              <p className="mt-1">All {num(total)} items have a label. Corrections are still possible from the item list of the queue.</p>
              <div className="mt-3 flex justify-center gap-2">
                {prevId ? <Button onClick={goBack}>← Revisit the last item</Button> : null}
                <Button kind="primary" onClick={onExit}>
                  Back to all queues
                </Button>
              </div>
            </Empty>
          )
        }
      </DataState>
    </div>
  );
}
