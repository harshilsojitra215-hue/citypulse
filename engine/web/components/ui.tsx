"use client";

import type { ReactNode } from "react";
import type { ApiError } from "@/lib/api";
import type { Cutoffs, Share } from "@/lib/types";
import { humanize, num, pct, score, stateInfo } from "@/lib/format";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

const TONES: Record<string, string> = {
  amber: "bg-amber-100 text-amber-900 border-amber-300",
  slate: "bg-slate-100 text-slate-700 border-slate-300",
  violet: "bg-violet-100 text-violet-900 border-violet-300",
  sky: "bg-sky-100 text-sky-900 border-sky-300",
  gray: "bg-gray-100 text-gray-700 border-gray-300",
  teal: "bg-teal-100 text-teal-900 border-teal-300",
  orange: "bg-orange-100 text-orange-900 border-orange-300",
  red: "bg-red-100 text-red-800 border-red-300",
  green: "bg-emerald-100 text-emerald-900 border-emerald-300",
  white: "bg-white text-slate-700 border-slate-300",
};

export function Badge({ tone = "slate", children, title }: { tone?: string; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cx("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONES[tone] ?? TONES.slate)}
    >
      {children}
    </span>
  );
}

export function StateBadge({ state, long }: { state?: string; long?: boolean }) {
  const info = stateInfo(state);
  return (
    <Badge tone={info.tone} title={info.help}>
      {long ? info.title : info.short}
    </Badge>
  );
}

/** Sample size tag. Shown next to every number. */
export function N({ n, label = "n" }: { n: number | null | undefined; label?: string }) {
  return (
    <span className="text-xs text-slate-500 tabular-nums whitespace-nowrap">
      {label} = {num(n)}
    </span>
  );
}

export function PageHeader({ title, lead, right }: { title: string; lead?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-[1.7rem]">{title}</h1>
        {lead ? <p className="mt-1 max-w-3xl text-[0.95rem] leading-relaxed text-slate-600">{lead}</p> : null}
      </div>
      {right ? <div className="flex flex-wrap items-center gap-2">{right}</div> : null}
    </div>
  );
}

export function Panel({
  title,
  hint,
  right,
  children,
  className,
}: {
  title?: ReactNode;
  hint?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cx("rounded-lg border border-slate-200 bg-white", className)}>
      {title || right ? (
        <header className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-slate-900">{title}</h2>
            {hint ? <p className="mt-0.5 text-sm text-slate-500">{hint}</p> : null}
          </div>
          {right ? <div className="flex flex-wrap items-center gap-2">{right}</div> : null}
        </header>
      ) : null}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Loading({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-2 py-1">
      <span className="text-sm text-slate-500">{label}…</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="cp-skeleton h-4 rounded bg-slate-200" style={{ width: `${88 - i * 14}%` }} />
      ))}
    </div>
  );
}

export function ErrorBox({ error, onRetry, what }: { error: ApiError; onRetry?: () => void; what?: string }) {
  const offline = error.status === 0;
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-900">
      <div className="font-medium">{offline ? "The data service is not reachable" : `Could not load ${what ?? "this panel"}`}</div>
      <div className="mt-0.5 text-red-800">
        {error.message}
        {!offline && error.code ? <span className="ml-1 text-red-700/80">({error.code})</span> : null}
      </div>
      {onRetry ? (
        <button onClick={onRetry} className="mt-2 rounded border border-red-300 bg-white px-2.5 py-1 text-sm font-medium text-red-900 hover:bg-red-100">
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-3 py-5 text-center text-sm text-slate-600">{children}</div>;
}

/** Standard loading / error / empty wrapper for one API panel. */
export function DataState<T>({
  state,
  what,
  isEmpty,
  empty,
  children,
  rows,
}: {
  state: { data: T | undefined; error: ApiError | undefined; loading: boolean; reload: () => void };
  what?: string;
  isEmpty?: (d: T) => boolean;
  empty?: ReactNode;
  children: (d: T) => ReactNode;
  rows?: number;
}) {
  if (state.loading) return <Loading label={`Loading ${what ?? "data"}`} rows={rows} />;
  if (state.error && state.data === undefined) return <ErrorBox error={state.error} onRetry={state.reload} what={what} />;
  if (state.data === undefined || state.data === null) return <Empty>No data.</Empty>;
  if (isEmpty && isEmpty(state.data)) return <Empty>{empty ?? "Nothing to show for this selection."}</Empty>;
  return <>{children(state.data)}</>;
}

export function Button({
  children,
  onClick,
  disabled,
  kind = "default",
  type = "button",
  title,
  small,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  kind?: "default" | "primary" | "ghost";
  type?: "button" | "submit";
  title?: string;
  small?: boolean;
}) {
  const kinds = {
    default: "border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
    primary: "border-teal-700 bg-teal-700 text-white hover:bg-teal-800",
    ghost: "border-transparent bg-transparent text-teal-800 hover:bg-teal-50",
  };
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-md border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        small ? "px-2 py-1 text-xs" : "px-3 py-1.5 text-sm",
        kinds[kind],
      )}
    >
      {children}
    </button>
  );
}

export function Select({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  label: string;
  className?: string;
}) {
  return (
    <label className={cx("inline-flex items-center gap-1.5 text-sm text-slate-600", className)}>
      <span className="whitespace-nowrap">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="max-w-[16rem] rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900 focus:border-teal-600 focus:outline-none"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Stat({ label, value, sub, onClick }: { label: string; value: ReactNode; sub?: ReactNode; onClick?: () => void }) {
  const body = (
    <>
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-0.5 text-3xl font-semibold tabular-nums tracking-tight text-slate-900">{value}</div>
      {sub ? <div className="mt-0.5 text-xs text-slate-500">{sub}</div> : null}
    </>
  );
  if (onClick) {
    return (
      <button onClick={onClick} className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-left hover:border-teal-500">
        {body}
      </button>
    );
  }
  return <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">{body}</div>;
}

/** A share drawn with its interval. The dark tick is the value, the band is lo–hi. */
export function ShareBar({ share, color = "#c2410c" }: { share: Share | null | undefined; color?: string }) {
  const v = share?.value;
  const has = v !== null && v !== undefined;
  const lo = share?.lo ?? v ?? 0;
  const hi = share?.hi ?? v ?? 0;
  return (
    <div className="w-full">
      <div className="relative h-3 w-full rounded-full bg-slate-100" aria-hidden>
        {has ? (
          <>
            <div className="absolute top-0 h-3 rounded-full opacity-30" style={{ left: `${lo * 100}%`, width: `${Math.max(0.5, (hi - lo) * 100)}%`, background: color }} />
            <div className="absolute top-[-3px] h-[18px] w-[3px] rounded" style={{ left: `calc(${(v as number) * 100}% - 1.5px)`, background: color }} />
          </>
        ) : null}
        <div className="absolute top-[-2px] left-1/2 h-4 w-px bg-slate-300" />
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-slate-400 tabular-nums">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
    </div>
  );
}

export function ShareLabel({ share }: { share: Share | null | undefined }) {
  if (!share || share.value === null || share.value === undefined) {
    return (
      <span className="text-sm text-slate-500">
        Not enough data <N n={share?.n ?? 0} />
      </span>
    );
  }
  const hasIv = share.lo !== null && share.lo !== undefined && share.hi !== null && share.hi !== undefined;
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-2">
      <span className="text-lg font-semibold tabular-nums text-slate-900">{pct(share.value)}</span>
      {hasIv ? (
        <span className="text-sm text-slate-600 tabular-nums" title="Uncertainty interval reported by the API">
          interval {pct(share.lo)}–{pct(share.hi)}
        </span>
      ) : null}
      <N n={share.n} />
    </span>
  );
}

/**
 * Where a match score sits against the two cut-offs.
 * Below "new": no equivalent known. Between: needs review. Above "familiar": known argument.
 */
export function ScoreScale({ value, cutoffs, compact }: { value: number | null | undefined; cutoffs?: Cutoffs; compact?: boolean }) {
  // `value` is the best same-argument score against earlier claims (0 = nothing alike, 1 = identical argument).
  const cNew = cutoffs?.new;
  const cFam = cutoffs?.familiar;
  const has = value !== null && value !== undefined && !Number.isNaN(value);
  const clamp = (x: number) => Math.min(1, Math.max(0, x));
  return (
    <div className="w-full">
      {!compact ? (
        <div className="mb-1 flex items-baseline justify-between gap-2 text-xs text-slate-600">
          <span>Closest earlier claim: same-argument score</span>
          <span className="font-semibold tabular-nums text-slate-900">{score(value)}</span>
        </div>
      ) : null}
      <div className="relative h-2.5 w-full overflow-visible rounded-full bg-slate-100">
        {cNew !== undefined && cFam !== undefined ? (
          <>
            <div className="absolute inset-y-0 left-0 rounded-l-full bg-amber-200" style={{ width: `${clamp(cNew) * 100}%` }} />
            <div className="absolute inset-y-0 bg-violet-200" style={{ left: `${clamp(cNew) * 100}%`, width: `${(clamp(cFam) - clamp(cNew)) * 100}%` }} />
            <div className="absolute inset-y-0 right-0 rounded-r-full bg-slate-300" style={{ width: `${(1 - clamp(cFam)) * 100}%` }} />
          </>
        ) : null}
        {has ? (
          <div
            className="absolute top-[-4px] h-[18px] w-[4px] rounded bg-slate-900"
            style={{ left: `calc(${clamp(value as number) * 100}% - 2px)` }}
            title={`score ${score(value)}`}
          />
        ) : null}
      </div>
      {cNew !== undefined && cFam !== undefined ? (
        <div className="mt-1 flex justify-between text-[11px] text-slate-500 tabular-nums">
          <span>no equivalent &lt; {score(cNew)}</span>
          <span>review</span>
          <span>same argument &gt; {score(cFam)}</span>
        </div>
      ) : (
        <div className="mt-1 text-[11px] text-slate-400">cut-offs not provided</div>
      )}
    </div>
  );
}

export const POLARITY_COLOR: Record<string, string> = { pro: "#0f766e", contra: "#c2410c", neutral: "#94a3b8" };
export const STANCE_COLOR: Record<string, string> = { support: "#0f766e", oppose: "#c2410c", neutral: "#94a3b8", mixed: "#7c3aed" };

/** Horizontal split bar (e.g. pro / contra / neutral). Counts are printed, not just drawn. */
export function SplitBar({ parts, colors, max }: { parts: Record<string, number | undefined>; colors: Record<string, string>; max?: number }) {
  const entries = Object.entries(parts).filter(([, v]) => (v ?? 0) > 0) as [string, number][];
  const total = entries.reduce((a, [, v]) => a + v, 0);
  const scale = max && max > 0 ? total / max : 1;
  if (total === 0) return <div className="h-3 w-full rounded bg-slate-100" />;
  return (
    <div className="h-3 w-full rounded bg-slate-100">
      <div className="flex h-3 overflow-hidden rounded" style={{ width: `${Math.max(2, scale * 100)}%` }}>
        {entries.map(([k, v]) => (
          <div key={k} title={`${humanize(k)}: ${v}`} style={{ width: `${(v / total) * 100}%`, background: colors[k] ?? "#64748b" }} />
        ))}
      </div>
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600">
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

export function PolarityCounts({ polarity }: { polarity?: Record<string, number> }) {
  const entries = Object.entries(polarity ?? {}).filter(([, v]) => v > 0);
  if (!entries.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {entries.map(([k, v]) => (
        <Badge key={k} tone={k === "contra" ? "orange" : k === "pro" ? "teal" : "gray"}>
          {humanize(k)} {v}
        </Badge>
      ))}
    </span>
  );
}

export function ModeBadge({ mode, prefix }: { mode?: string; prefix?: string }) {
  if (!mode) return null;
  const cached = /cached/i.test(mode);
  const fallback = /fallback|baseline|keyword/i.test(mode);
  return (
    <Badge tone={fallback ? "orange" : cached ? "sky" : "teal"} title="How the scores on this panel were produced">
      {prefix ? `${prefix}: ` : ""}
      {cached ? "cached model scores" : humanize(mode).toLowerCase()}
    </Badge>
  );
}

export function Notes({ notes, title = "Notes on this data" }: { notes?: string[]; title?: string }) {
  if (!notes?.length) return null;
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700">
      <div className="font-medium text-slate-800">{title}</div>
      <ul className="mt-1 list-disc space-y-0.5 pl-5">
        {notes.map((n, i) => (
          <li key={i}>{n}</li>
        ))}
      </ul>
    </div>
  );
}
