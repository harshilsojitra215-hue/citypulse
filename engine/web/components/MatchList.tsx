"use client";

import Link from "next/link";
import type { ClaimCard, Match } from "@/lib/types";
import { fmtDate, humanize } from "@/lib/format";
import { useApp } from "./AppContext";
import { MatchScores, VoiceTag, useEvidence } from "./Evidence";
import { Badge, N, cx } from "./ui";

export function ClaimRow({ claim, showRelation }: { claim: ClaimCard | Match; showRelation?: boolean }) {
  const { projectName } = useApp();
  const openEvidence = useEvidence();
  const m = claim as Match;
  return (
    <li className="rounded-md border border-slate-200 bg-white p-2.5">
      <Link href={`/explorer?claim=${encodeURIComponent(claim.cid)}`} className="block text-[0.95rem] font-medium leading-snug text-slate-900 hover:text-teal-800">
        “{claim.claim}”
      </Link>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600">
        <span className="font-medium tabular-nums text-slate-800">{fmtDate(claim.date)}</span>
        {claim.project ? <Badge tone="white">{claim.project_name || projectName(claim.project)}</Badge> : null}
        {claim.domain ? <span>{claim.domain}</span> : null}
        {claim.topic ? <span>{humanize(claim.topic)}</span> : null}
        {claim.polarity ? <Badge tone={claim.polarity === "contra" ? "orange" : claim.polarity === "pro" ? "teal" : "gray"}>{claim.polarity}</Badge> : null}
        {showRelation && m.relation && m.relation !== "unscored" ? <Badge tone={m.relation === "equivalent" ? "teal" : m.relation === "related" ? "sky" : "gray"}>{humanize(m.relation)}</Badge> : null}
        <VoiceTag voice={claim.voice} />
        <MatchScores m={m} />
        <button
          onClick={() => openEvidence({ title: claim.claim, subtitle: "Claim and its source post", sections: [{ kind: "claims", claims: [claim] }] })}
          className="ml-auto font-medium text-teal-800 underline underline-offset-2"
        >
          Evidence
        </button>
      </div>
    </li>
  );
}

export function MatchList({
  title,
  note,
  items,
  tone,
  emptyText,
  limit = 30,
}: {
  title: string;
  note?: string;
  items: (ClaimCard | Match)[];
  tone?: "teal" | "sky" | "gray";
  emptyText?: string;
  limit?: number;
}) {
  const head = { teal: "border-teal-600", sky: "border-sky-500", gray: "border-slate-300" }[tone ?? "gray"];
  return (
    <section className="min-w-0">
      <div className={cx("mb-2 border-l-4 pl-2", head)}>
        <h3 className="flex items-baseline gap-2 text-base font-semibold text-slate-900">
          {title} <N n={items.length} />
        </h3>
        {note ? <p className="text-xs text-slate-500">{note}</p> : null}
      </div>
      {items.length ? (
        <ul className="space-y-1.5">
          {items.slice(0, limit).map((c, i) => (
            <ClaimRow key={`${c.cid}-${i}`} claim={c} />
          ))}
          {items.length > limit ? <li className="text-xs text-slate-500">{items.length - limit} more not shown</li> : null}
        </ul>
      ) : (
        <p className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-3 py-3 text-sm text-slate-500">{emptyText ?? "None found."}</p>
      )}
    </section>
  );
}

/** Splits matcher results by relation so equivalent and related are never shown in one list. */
export function splitByRelation(items: Match[] | undefined) {
  const all = items ?? [];
  return {
    equivalent: all.filter((m) => m.relation === "equivalent"),
    related: all.filter((m) => m.relation === "related"),
    other: all.filter((m) => m.relation !== "equivalent" && m.relation !== "related"),
  };
}
