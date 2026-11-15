"use client";

import { shortPeriod } from "@/lib/format";
import { cx } from "./ui";

export type BarDatum = {
  key: string;
  label?: string;
  /** stacked parts in drawing order (bottom first) */
  parts: { name: string; value: number; color: string }[];
  total: number;
  marked?: boolean;
  dim?: boolean;
};

/**
 * Stacked column chart built from plain HTML boxes, so text keeps its size on a
 * projector and on a phone. Every column is a button that opens its evidence.
 */
export function ColumnChart({
  data,
  height = 180,
  onSelect,
  cursor,
  unit = "posts",
}: {
  data: BarDatum[];
  height?: number;
  onSelect?: (d: BarDatum) => void;
  /** 0..data.length position of a vertical cursor line (replay) */
  cursor?: number | null;
  unit?: string;
}) {
  const max = Math.max(1, ...data.map((d) => d.total));
  const every = Math.max(1, Math.ceil(data.length / 12));
  const ticks = [max, Math.round(max / 2)].filter((v, i, a) => v > 0 && a.indexOf(v) === i);
  return (
    <div className="w-full">
      <div className="flex gap-2">
        <div className="relative w-8 shrink-0 text-right text-[11px] text-slate-400 tabular-nums" style={{ height }}>
          {ticks.map((t) => (
            <span key={t} className="absolute right-0 -translate-y-1/2" style={{ top: `${(1 - t / max) * 100}%` }}>
              {t}
            </span>
          ))}
          <span className="absolute right-0 bottom-0">0</span>
        </div>
        <div className="relative min-w-0 flex-1">
          <div className="relative flex items-end gap-[2px] border-b border-slate-300" style={{ height }}>
            {ticks.map((t) => (
              <div key={t} className="pointer-events-none absolute inset-x-0 border-t border-dashed border-slate-200" style={{ top: `${(1 - t / max) * 100}%` }} />
            ))}
            {data.map((d) => {
              const h = (d.total / max) * 100;
              const title = `${d.label ?? d.key}: ${d.total} ${unit}${d.parts.length > 1 ? ` (${d.parts.filter((p) => p.value > 0).map((p) => `${p.name} ${p.value}`).join(", ")})` : ""}`;
              return (
                <button
                  key={d.key}
                  type="button"
                  title={title}
                  aria-label={title}
                  onClick={onSelect ? () => onSelect(d) : undefined}
                  disabled={!onSelect}
                  className={cx("group relative flex h-full min-w-0 flex-1 flex-col justify-end", onSelect && "cursor-pointer")}
                >
                  {d.marked ? <span className="absolute left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-slate-900" style={{ bottom: `calc(${h}% + 4px)` }} /> : null}
                  <span
                    className={cx("flex w-full flex-col-reverse overflow-hidden rounded-t-[2px] transition-opacity", d.dim ? "opacity-25" : "opacity-100", onSelect && "group-hover:opacity-75")}
                    style={{ height: `${h}%`, minHeight: d.total > 0 ? 2 : 0 }}
                  >
                    {d.parts.map((p) => (p.value > 0 ? <span key={p.name} style={{ flexGrow: p.value, background: p.color }} /> : null))}
                  </span>
                </button>
              );
            })}
            {cursor !== null && cursor !== undefined && data.length ? (
              <div
                className="pointer-events-none absolute top-[-6px] bottom-0 w-[2px] bg-slate-900 transition-[left] duration-200"
                style={{ left: `${Math.min(100, Math.max(0, (cursor / data.length) * 100))}%` }}
              >
                <span className="absolute top-[-4px] left-[-4px] h-2.5 w-2.5 rounded-full bg-slate-900" />
              </div>
            ) : null}
          </div>
          <div className="mt-1 flex gap-[2px]">
            {data.map((d, i) => (
              <div key={d.key} className="min-w-0 flex-1 overflow-visible text-center text-[11px] whitespace-nowrap text-slate-500">
                {i % every === 0 ? <span className="inline-block">{d.label ?? shortPeriod(d.key)}</span> : null}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
