"use client";

import type { Concern } from "@/lib/types";
import { bestMatch, fmtDate, humanize, num, stateInfo } from "@/lib/format";
import { useApp } from "./AppContext";
import { useEvidence } from "./Evidence";
import { Badge, PolarityCounts, ScoreScale, cx } from "./ui";

const BORDER: Record<string, string> = {
  amber: "border-l-amber-500",
  slate: "border-l-slate-400",
  violet: "border-l-violet-500",
  sky: "border-l-sky-500",
  gray: "border-l-gray-300",
};

export function ConcernCard({ concern, cutoff, showProject }: { concern: Concern; cutoff?: string; showProject?: boolean }) {
  const { projectName } = useApp();
  const openEvidence = useEvidence();
  const info = stateInfo(concern.state);
  const cases = concern.elsewhere ?? [];
  const firstCase = cases[0];
  const u = concern.uncertainty;

  const open = () =>
    openEvidence({
      title: concern.label ?? concern.concern_id,
      subtitle: info.title,
      sections: [{ kind: "concern", concern_id: concern.concern_id, project: concern.project, cutoff, fallback: concern }],
    });

  return (
    <article className={cx("flex flex-col rounded-lg border border-l-4 border-slate-200 bg-white", BORDER[info.tone] ?? BORDER.gray)}>
      <button onClick={open} className="flex-1 p-4 text-left hover:bg-slate-50/60">
        <div className="flex flex-wrap items-center gap-2">
          {showProject && concern.project ? <Badge tone="white">{projectName(concern.project)}</Badge> : null}
          {concern.topic ? <Badge tone="white">{humanize(concern.topic)}</Badge> : null}
          <PolarityCounts polarity={concern.polarity} />
          {concern.flagged_at && (concern.n_voices ?? 0) >= 2 ? <Badge tone="amber">2+ independent voices</Badge> : null}
        </div>
        <h3 className="mt-1.5 text-lg font-semibold leading-snug text-slate-900">{concern.label ?? "(no label)"}</h3>

        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
          <div>
            <dt className="text-xs text-slate-500">First seen</dt>
            <dd className="text-sm font-medium tabular-nums text-slate-900">{fmtDate(concern.first_seen)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Flagged</dt>
            <dd className="text-sm font-medium tabular-nums text-slate-900">{concern.flagged_at ? fmtDate(concern.flagged_at) : "not flagged"}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Claims</dt>
            <dd className="text-sm font-semibold tabular-nums text-slate-900">n = {num(concern.n_claims)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Independent voices</dt>
            <dd className="text-sm font-semibold tabular-nums text-slate-900">n = {num(concern.n_voices)}</dd>
          </div>
        </dl>

        <div className="mt-3">
          <ScoreScale value={bestMatch(u)} cutoffs={u?.cutoffs} />
          {u?.note ? <p className="mt-1 text-xs text-slate-600">{u.note}</p> : null}
        </div>

        {concern.events_nearby?.length ? (
          <p className="mt-2 text-sm text-slate-700">
            <span className="text-xs uppercase tracking-wide text-slate-400">Event nearby </span>
            {fmtDate(concern.events_nearby[0].date)}: {concern.events_nearby[0].title}
            {concern.events_nearby.length > 1 ? ` (+${concern.events_nearby.length - 1} more)` : ""}
          </p>
        ) : null}
      </button>

      <div className="border-t border-slate-100 bg-slate-50 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Seen in other cities</span>
          {cases.length ? <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-white">Historical case, not a forecast</span> : null}
        </div>
        {firstCase ? (
          <div className="mt-1.5 text-sm text-slate-700">
            <div>
              <span className="font-medium text-slate-900">{firstCase.claim?.project_name || projectName(firstCase.claim?.project)}</span>, {fmtDate(firstCase.claim?.date)}{firstCase.relation ? ` (${firstCase.relation})` : ""}: “{firstCase.claim?.claim}”
            </div>
            {firstCase.timeline_available === false ? (
              <div className="mt-1 text-xs text-slate-600">No event timeline is recorded for that project.</div>
            ) : (
              <>
                <div className="mt-1 text-xs text-slate-600">
                  Project stage then: {firstCase.stage ? `${firstCase.stage.title} (${fmtDate(firstCase.stage.date)})` : "not recorded"}
                </div>
                <div className="text-xs text-slate-600">
                  Later there: {firstCase.after?.length ? firstCase.after.map((e) => `${e.title} (${fmtDate(e.date)})`).join("; ") : "no later events recorded"}
                </div>
              </>
            )}
            {cases.length > 1 ? <div className="mt-1 text-xs text-slate-500">+{cases.length - 1} more {cases.length - 1 === 1 ? "case" : "cases"}</div> : null}
          </div>
        ) : (
          <p className="mt-1 text-sm text-slate-600">{concern.new_anywhere ? "No equivalent claim in any other project so far." : "No similar case from another project attached."}</p>
        )}
        <button onClick={open} className="mt-2 text-sm font-medium text-teal-800 underline underline-offset-2">
          Open evidence: claims, source posts, closest earlier claims →
        </button>
      </div>
    </article>
  );
}
