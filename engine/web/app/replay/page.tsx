"use client";

import { useEffect, useMemo, useState } from "react";
import { apiPost, useAction, useApi, withQuery } from "@/lib/api";
import type { ClaimCard, Concern, Cutoffs, LiveCheck, Replay, ReplayCutoffs, ReplayStep } from "@/lib/types";
import { bestMatch, fmtDate, fmtDateTime, num, score, shortPeriod } from "@/lib/format";
import { useApp } from "@/components/AppContext";
import { MatchScores, VoiceTag, useEvidence } from "@/components/Evidence";
import { ColumnChart, type BarDatum } from "@/components/charts";
import { Badge, Button, DataState, Empty, Legend, Loading, N, PageHeader, Panel, ScoreScale, Select, cx } from "@/components/ui";

const DECISION: Record<string, { label: string; tone: string }> = {
  familiar: { label: "Matched to a known argument", tone: "gray" },
  joins_new: { label: "Joins a new concern", tone: "amber" },
  opens_new: { label: "Opens a new concern", tone: "amber" },
  ambiguous: { label: "Ambiguous: needs review", tone: "violet" },
};

type LiveConcern = {
  id: string;
  label: string;
  claims: ClaimCard[];
  voices: Set<string>;
  openedAt: number;
  lastAt: number;
  raisedAt: number | null;
  firstDecision: string;
  final?: Concern;
};

function buildState(steps: ReplayStep[], pos: number, finals: Map<string, Concern>) {
  const live = new Map<string, LiveConcern>();
  const counts: Record<string, number> = { familiar: 0, joins_new: 0, opens_new: 0, ambiguous: 0 };
  const ensure = (id: string, i: number, s: ReplayStep) => {
    let c = live.get(id);
    if (!c) {
      const final = finals.get(id);
      const known = id.startsWith("f:") || s.decision === "familiar";
      const label = final?.label ?? (known ? (s.matched?.family_name ?? s.claim?.family_name) : undefined) ?? s.claim?.claim ?? id;
      c = { id, label, claims: [], voices: new Set(), openedAt: i, lastAt: i, raisedAt: null, firstDecision: s.decision ?? "", final };
      live.set(id, c);
    }
    return c;
  };
  for (let i = 0; i < pos && i < steps.length; i++) {
    const s = steps[i];
    const d = s.decision ?? "";
    counts[d] = (counts[d] ?? 0) + 1;
    if (s.concern_id) {
      const c = ensure(s.concern_id, i, s);
      if (s.claim) {
        c.claims.push(s.claim);
        if (s.claim.voice) c.voices.add(s.claim.voice);
      }
      c.lastAt = i;
    }
    for (const id of s.raised ?? []) {
      const c = ensure(id, i, s);
      if (c.raisedAt === null) c.raisedAt = i;
    }
  }
  return { live: Array.from(live.values()), counts };
}

function LiveCheckBox({ cid }: { cid: string }) {
  const [state, run] = useAction<LiveCheck>();
  if (!state.data && !state.error) {
    return (
      <Button small onClick={() => run(() => apiPost<LiveCheck>("/api/replay/live-check", { cid }))} disabled={state.loading} title="Score this claim again with the model loaded on this machine and compare with the cached scores">
        {state.loading ? "Running the model…" : "Re-run live"}
      </Button>
    );
  }
  if (state.error) {
    return <span className="text-xs text-red-800">Live check failed: {state.error.message}</span>;
  }
  const d = state.data as LiveCheck;
  const cached = d.cached ?? [];
  const liveBy = new Map((d.live ?? []).map((r) => [r.cand, r.p_same]));
  if (d.available === false) {
    return (
      <div className="rounded border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-700">
        <span className="font-medium">Model not loaded on this machine.</span> {d.message ?? "A live re-run is not possible here; these are the cached scores."}
        {cached.length ? (
          <span className="ml-1 tabular-nums">
            Cached same-argument scores against {cached.length} earlier claims: highest {score(Math.max(...cached.map((r) => r.p_same ?? 0)))}.
          </span>
        ) : null}
      </div>
    );
  }
  const rows = cached.length ? cached : (d.live ?? []);
  return (
    <div className="rounded border border-teal-200 bg-teal-50 px-2.5 py-2 text-xs text-slate-800">
      <div className="mb-1 font-medium">
        Live model run vs cached scores
        {d.max_abs_diff !== null && d.max_abs_diff !== undefined ? <span className="ml-2 font-normal tabular-nums">largest difference {Number(d.max_abs_diff).toFixed(4)}</span> : null}
      </div>
      {rows.length ? (
        <table className="tabular-nums">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="pr-4 font-normal">Earlier claim</th>
              <th className="pr-4 font-normal">Cached</th>
              <th className="font-normal">Live</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 10).map((r, i) => (
              <tr key={i}>
                <td className="pr-4 font-mono">{r.cand}</td>
                <td className="pr-4">{cached.length ? score(r.p_same) : "–"}</td>
                <td>{score(liveBy.get(r.cand))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <span>No candidate pairs returned.</span>
      )}
      {rows.length > 10 ? <div className="mt-1 text-slate-500">{rows.length - 10} more pairs not shown</div> : null}
    </div>
  );
}

function StepRow({ step, index, labelOf, stateOf, cutoffs, current }: { step: ReplayStep; index: number; labelOf: (id: string) => string; stateOf: (id: string) => string | undefined; cutoffs?: Cutoffs; current: boolean }) {
  const openEvidence = useEvidence();
  const d = DECISION[step.decision ?? ""] ?? { label: step.decision ?? "No decision", tone: "gray" };
  const claim = step.claim;
  const m = step.matched;
  return (
    <li className={cx("cp-in rounded-md border bg-white p-3", current ? "border-slate-800 shadow-sm" : "border-slate-200")}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600">
        <span className="tabular-nums text-slate-400">#{index + 1}</span>
        <span className="font-semibold tabular-nums text-slate-900">{fmtDateTime(step.ts ?? claim?.date)}</span>
        {claim?.domain ? <span>{claim.domain}</span> : null}
        <VoiceTag voice={claim?.voice} />
        <span className="ml-auto">
          <Badge tone={d.tone}>{d.label}</Badge>
        </span>
      </div>
      <p className={cx("mt-1.5 font-medium leading-snug text-slate-900", current ? "text-lg" : "text-[0.95rem]")}>“{claim?.claim ?? "(claim text missing)"}”</p>

      <div className="mt-2 border-l-2 border-slate-200 pl-3 text-sm text-slate-700">
        {step.decision === "familiar" ? (
          m ? (
            <div>
              <div>
                Same argument as an earlier claim{m.date ? ` from ${fmtDate(m.date)}` : ""}: <span className="text-slate-900">“{m.claim}”</span>
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-2">
                {m.family_name ? <span className="text-xs text-slate-500">family: {m.family_name}</span> : null}
                <MatchScores m={m} />
              </div>
            </div>
          ) : (
            <div>Matched to a known argument (the matched claim was not sent by the data service).</div>
          )
        ) : null}
        {step.decision === "joins_new" ? (
          <div>
            Same argument as a claim that itself arrived after the cut-off{m ? <>: <span className="text-slate-900">“{m.claim}”</span>{m.date ? ` (${fmtDate(m.date)})` : ""}</> : null}. Joins the new concern “{step.concern_id ? labelOf(step.concern_id) : "?"}”.
            {m ? (
              <span className="mt-0.5 block">
                <MatchScores m={m} />
              </span>
            ) : null}
          </div>
        ) : null}
        {step.decision === "opens_new" ? <div>No equivalent among earlier claims. Opens a new concern: one voice so far.</div> : null}
        {step.decision === "ambiguous" ? (
          <div>
            The best match lies between the two cut-offs. A person should decide.
            {m ? <span className="mt-0.5 block text-slate-600">Closest earlier claim: “{m.claim}” <MatchScores m={m} /></span> : null}
          </div>
        ) : null}
        {(step.raised ?? []).map((id) => (
          <div key={id} className="mt-1 rounded bg-amber-100 px-2 py-1 font-medium text-amber-900">
            {stateOf(id) === "ambiguous"
              ? <>A second independent voice: “{labelOf(id)}” is flagged for review. It may be a variant of a known argument.</>
              : <>A second independent voice: “{labelOf(id)}” is now flagged as a potential new argument.</>}
          </div>
        ))}
      </div>

      <div className="mt-2 grid items-end gap-2 sm:grid-cols-[minmax(0,16rem)_1fr]">
        <div>
          <div className="mb-0.5 flex justify-between text-[11px] text-slate-500">
            <span>closest earlier claim: same-argument score</span>
            <span className="font-semibold tabular-nums text-slate-800">{score(bestMatch(step))}</span>
          </div>
          <ScoreScale value={bestMatch(step)} cutoffs={cutoffs} compact />
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {claim ? (
            <Button
              small
              kind="ghost"
              onClick={() =>
                openEvidence({
                  title: claim.claim,
                  subtitle: `${d.label} · arrived ${fmtDateTime(step.ts ?? claim.date)}`,
                  sections: [
                    { kind: "claims", heading: "Arriving claim", claims: [claim] },
                    ...(m ? [{ kind: "claims" as const, heading: step.decision === "familiar" ? "Matched earlier claim" : "Closest earlier claim", claims: [m] }] : []),
                  ],
                })
              }
            >
              Evidence
            </Button>
          ) : null}
          {claim?.cid ? <LiveCheckBox cid={claim.cid} /> : null}
        </div>
      </div>
    </li>
  );
}

function LiveConcernCard({ c, pos }: { c: LiveConcern; pos: number }) {
  const openEvidence = useEvidence();
  const raised = c.raisedAt !== null;
  const justRaised = raised && c.raisedAt === pos - 1;
  const justGrew = c.lastAt === pos - 1;
  const stateLabel = raised
    ? c.firstDecision === "ambiguous"
      ? "EMERGING: 2+ independent voices. Needs review: may be a variant of a known argument"
      : "EMERGING: potential new argument (2+ independent voices)"
    : c.firstDecision === "ambiguous"
      ? "Needs review: may be a variant of a known argument"
      : c.firstDecision === "familiar"
        ? "Known argument seen again"
        : "Candidate: one voice so far";
  return (
    <button
      onClick={() =>
        openEvidence({
          title: c.label,
          subtitle: `Simulation state after step ${pos}: ${c.claims.length} claims, ${c.voices.size} voices. Later claims are not shown.`,
          sections: [{ kind: "claims", heading: "Claims that have arrived so far", claims: c.claims }],
        })
      }
      className={cx(
        "w-full rounded-lg border border-l-4 p-3 text-left transition-colors",
        raised ? "border-amber-300 border-l-amber-500 bg-amber-50" : "border-slate-200 border-l-slate-300 bg-white",
        justRaised && "cp-flash",
        !justRaised && justGrew && "ring-2 ring-slate-300",
      )}
    >
      <div className={cx("text-[11px] font-semibold uppercase tracking-wide", raised ? "text-amber-800" : "text-slate-500")}>{stateLabel}</div>
      <div className="mt-0.5 text-[0.95rem] font-semibold leading-snug text-slate-900">{c.label}</div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600 tabular-nums">
        <span>
          claims <span className="text-sm font-semibold text-slate-900">{c.claims.length}</span>
        </span>
        <span>
          voices <span className="text-sm font-semibold text-slate-900">{c.voices.size}</span>
        </span>
        <span className="flex gap-0.5" aria-hidden>
          {Array.from({ length: Math.min(c.claims.length, 14) }).map((_, i) => (
            <span key={i} className={cx("inline-block h-2.5 w-2.5 rounded-sm", raised ? "bg-amber-500" : "bg-slate-400")} />
          ))}
        </span>
        <span>opened at step {c.openedAt + 1}</span>
        {raised ? <span className="font-medium text-amber-900">flagged at step {(c.raisedAt as number) + 1}</span> : null}
      </div>
    </button>
  );
}

function Player({ replay }: { replay: Replay }) {
  const openEvidence = useEvidence();
  const steps = useMemo(() => replay.steps ?? [], [replay.steps]);
  const total = steps.length;
  const [pos, setPos] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState("2");
  const [showAll, setShowAll] = useState(false);
  const active = playing && pos < total;

  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setPos((p) => Math.min(total, p + 1)), 1000 / Number(speed));
    return () => clearInterval(t);
  }, [active, speed, total]);

  const toggle = () => {
    if (pos >= total) {
      setPos(0);
      setPlaying(true);
    } else {
      setPlaying(!active);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && /^(INPUT|SELECT|TEXTAREA|BUTTON|A)$/.test(el.tagName)) return;
      if (e.key === "ArrowRight") {
        setPlaying(false);
        setPos((p) => Math.min(total, p + 1));
      } else if (e.key === "ArrowLeft") {
        setPlaying(false);
        setPos((p) => Math.max(0, p - 1));
      } else if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [total]);

  const finals = useMemo(() => new Map((replay.concerns ?? []).map((c) => [c.concern_id, c])), [replay.concerns]);
  const cutoffs = useMemo(
    () => (replay.thresholds?.new !== undefined && replay.thresholds?.familiar !== undefined ? { new: replay.thresholds.new, familiar: replay.thresholds.familiar } : (replay.concerns ?? []).find((c) => c.uncertainty?.cutoffs)?.uncertainty?.cutoffs),
    [replay.thresholds, replay.concerns],
  );
  const { live, counts } = useMemo(() => buildState(steps, pos, finals), [steps, pos, finals]);
  const labelOf = (id: string) => finals.get(id)?.label ?? live.find((c) => c.id === id)?.label ?? id;
  const stateOf = (id: string) => finals.get(id)?.state;

  const sorted = useMemo(
    () =>
      [...live].sort((a, b) => {
        const ra = a.raisedAt !== null ? 1 : 0;
        const rb = b.raisedAt !== null ? 1 : 0;
        if (ra !== rb) return rb - ra;
        if (ra && rb) return (b.raisedAt as number) - (a.raisedAt as number);
        if (b.claims.length !== a.claims.length) return b.claims.length - a.claims.length;
        return b.lastAt - a.lastAt;
      }),
    [live],
  );
  const isKnown = (c: LiveConcern) => c.raisedAt === null && (c.id.startsWith("f:") || c.firstDecision === "familiar");
  const newOnes = sorted.filter((c) => !isKnown(c));
  const knownOnes = sorted.filter(isKnown);
  const nRaised = live.filter((c) => c.raisedAt !== null).length;

  const current = pos > 0 ? steps[pos - 1] : undefined;
  const nowTs = current?.ts ?? current?.claim?.date;

  const activity = useMemo(() => replay.activity ?? [], [replay.activity]);
  const cursor = useMemo(() => {
    if (!activity.length) return null;
    if (!nowTs) return 0;
    const t = Date.parse(nowTs);
    if (Number.isNaN(t)) return null;
    let idx = 0;
    for (let i = 0; i < activity.length; i++) {
      const w = Date.parse(String(activity[i].week));
      if (!Number.isNaN(w) && w <= t) idx = i;
    }
    const start = Date.parse(String(activity[idx].week));
    const frac = Number.isNaN(start) ? 0 : Math.min(1, Math.max(0, (t - start) / (7 * 86400000)));
    return idx + frac;
  }, [activity, nowTs]);

  const bars: BarDatum[] = activity.map((a, i) => {
    const n = Number(a.n ?? 0);
    const nw = Number(a.new ?? 0);
    const fam = Number(a.familiar ?? 0);
    const rest = a.ambiguous !== undefined ? Number(a.ambiguous) : Math.max(0, n - nw - fam);
    return {
      key: String(a.week ?? i),
      label: shortPeriod(a.week),
      total: Math.max(n, nw + fam + rest),
      parts: [
        { name: "matched to known", value: fam, color: "#94a3b8" },
        { name: "new", value: nw, color: "#d97706" },
        { name: "ambiguous", value: rest, color: "#8b5cf6" },
      ],
      dim: cursor !== null && i >= Math.ceil(cursor ?? 0) && !(pos >= total),
    };
  });

  const jumpToWeek = (week: string) => {
    const end = Date.parse(week) + 7 * 86400000;
    if (Number.isNaN(end)) return;
    const n = steps.filter((s) => {
      const t = Date.parse(String(s.ts ?? s.claim?.date ?? ""));
      return !Number.isNaN(t) && t < end;
    }).length;
    setPlaying(false);
    setPos(n);
  };

  const kb = replay.known_before;
  const feed = steps.slice(Math.max(0, pos - 25), pos).map((s, k) => ({ s, i: Math.max(0, pos - 25) + k })).reverse();
  const shownConcerns = showAll ? newOnes : newOnes.slice(0, 8);

  return (
    <div className="space-y-4">
      <Panel
        title={`Known before ${fmtDate(replay.cutoff)}`}
        hint="The engine only knows these. Every later claim is compared with what was published before it, never with anything after."
      >
        <div className="grid gap-4 md:grid-cols-[auto_1fr]">
          <div className="flex gap-6">
            <div>
              <div className="text-3xl font-semibold tabular-nums text-slate-900">{num(kb?.n_claims)}</div>
              <div className="text-sm text-slate-500">claims known</div>
            </div>
            <div>
              <div className="text-3xl font-semibold tabular-nums text-slate-900">{num(kb?.n_posts)}</div>
              <div className="text-sm text-slate-500">posts known</div>
            </div>
            <div>
              <div className="text-3xl font-semibold tabular-nums text-slate-900">{num(total)}</div>
              <div className="text-sm text-slate-500">claims arrive later</div>
            </div>
          </div>
          {(kb?.top_families ?? []).length ? (
            <div className="min-w-0">
              <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">Largest known arguments</div>
              <div className="flex flex-wrap gap-1.5">
                {(kb?.top_families ?? []).slice(0, 8).map((f) => (
                  <button
                    key={f.family_id}
                    onClick={() => openEvidence({ title: f.name ?? f.family_id, subtitle: "Known argument family (all dates)", sections: [{ kind: "family", family_id: f.family_id }] })}
                    className="max-w-full truncate rounded-full border border-slate-300 bg-white px-2.5 py-1 text-left text-xs text-slate-700 hover:border-teal-500"
                  >
                    {f.name ?? f.family_id} <span className="text-slate-400 tabular-nums">n = {num(f.n)}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </Panel>

      {total === 0 ? (
        <Empty>No claims arrive after this cut-off for this project, so there is nothing to replay.</Empty>
      ) : (
        <>
          <div className="sticky top-[53px] z-20 rounded-lg border border-slate-300 bg-white p-3 shadow-sm lg:top-[53px]">
            <div className="flex flex-wrap items-center gap-2">
              <Button kind="primary" onClick={toggle} title="Space">
                {active ? "❚❚ Pause" : pos >= total ? "↺ Play again" : "▶ Play"}
              </Button>
              <Button onClick={() => { setPlaying(false); setPos((p) => Math.max(0, p - 1)); }} disabled={pos === 0} title="Left arrow">
                ◀ Step
              </Button>
              <Button onClick={() => { setPlaying(false); setPos((p) => Math.min(total, p + 1)); }} disabled={pos >= total} title="Right arrow">
                Step ▶
              </Button>
              <Button onClick={() => { setPlaying(false); setPos(0); }} disabled={pos === 0}>
                Reset
              </Button>
              <Button onClick={() => { setPlaying(false); setPos(total); }} disabled={pos >= total}>
                To end
              </Button>
              <Select
                label="Speed"
                value={speed}
                onChange={setSpeed}
                options={[
                  { value: "0.5", label: "slow" },
                  { value: "1", label: "1 claim/s" },
                  { value: "2", label: "2 claims/s" },
                  { value: "5", label: "5 claims/s" },
                  { value: "15", label: "15 claims/s" },
                ]}
              />
              <div className="ml-auto text-right">
                <div className="text-[11px] uppercase tracking-wide text-slate-400">Simulated date</div>
                <div className="text-lg font-semibold tabular-nums leading-tight text-slate-900">{nowTs ? fmtDate(nowTs) : `${fmtDate(replay.cutoff)} (cut-off)`}</div>
              </div>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <input
                type="range"
                min={0}
                max={total}
                value={pos}
                onChange={(e) => {
                  setPlaying(false);
                  setPos(Number(e.target.value));
                }}
                aria-label="Position in the replay"
                className="h-2 w-full cursor-pointer accent-teal-700"
              />
              <span className="text-sm tabular-nums whitespace-nowrap text-slate-700">
                claim {pos} of {total}
              </span>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-5">
              {[
                ["Matched to known", counts.familiar ?? 0],
                ["Opened a new concern", counts.opens_new ?? 0],
                ["Joined a new concern", counts.joins_new ?? 0],
                ["Ambiguous", counts.ambiguous ?? 0],
              ].map(([l, v]) => (
                <div key={l} className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
                  <div className="text-xs text-slate-500">{l}</div>
                  <div className="text-lg font-semibold tabular-nums leading-tight text-slate-900">{v}</div>
                </div>
              ))}
              <div className={cx("rounded border px-2 py-1", nRaised ? "border-amber-300 bg-amber-100" : "border-slate-200 bg-slate-50")}>
                <div className={cx("text-xs", nRaised ? "text-amber-900" : "text-slate-500")} title="Concerns that reached 2 or more independent voices: potential new arguments plus variants that need review">Flagged (2+ voices)</div>
                <div className="text-lg font-semibold tabular-nums leading-tight text-slate-900">{nRaised}</div>
              </div>
            </div>
          </div>

          <Panel
            title="Claims arriving per week"
            hint="The line is the simulated date. Click a week to jump to its end."
            right={<Legend items={[{ label: "Matched to known", color: "#94a3b8" }, { label: "New", color: "#d97706" }, { label: "Ambiguous", color: "#8b5cf6" }]} />}
          >
            {bars.length ? <ColumnChart data={bars} height={130} cursor={pos === 0 ? 0 : pos >= total ? bars.length : cursor} unit="claims" onSelect={(d) => jumpToWeek(d.key)} /> : <Empty>The data service sent no weekly activity.</Empty>}
          </Panel>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
            <Panel title="Live feed" hint="Each arriving claim and what the matcher decided. Newest first." right={<N n={pos} label="arrived" />}>
              {pos === 0 ? (
                <Empty>Press Play, or Step, to let the first claim after the cut-off arrive.</Empty>
              ) : (
                <ol className="space-y-2">
                  {feed.map(({ s, i }) => (
                    <StepRow key={i} step={s} index={i} labelOf={labelOf} stateOf={stateOf} cutoffs={cutoffs} current={i === pos - 1} />
                  ))}
                  {pos > feed.length ? <li className="text-center text-xs text-slate-500">{pos - feed.length} earlier claims not shown. Step back or use the slider to see them.</li> : null}
                </ol>
              )}
            </Panel>

            <Panel title="Concerns so far" hint="Cards appear when a claim opens a concern and grow as more claims join." right={<N n={newOnes.length} label="concerns" />}>
              {newOnes.length === 0 ? (
                <Empty>No new concern has been opened yet.</Empty>
              ) : (
                <div className="space-y-2">
                  {shownConcerns.map((c) => (
                    <LiveConcernCard key={c.id} c={c} pos={pos} />
                  ))}
                  {newOnes.length > 8 ? (
                    <Button small onClick={() => setShowAll(!showAll)}>
                      {showAll ? "Show fewer" : `Show all ${newOnes.length}`}
                    </Button>
                  ) : null}
                </div>
              )}
              {knownOnes.length ? (
                <details className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                  <summary className="cursor-pointer text-sm font-medium text-slate-800">
                    Known arguments seen again <N n={knownOnes.length} />
                  </summary>
                  <ul className="mt-2 space-y-1">
                    {knownOnes.map((c) => (
                      <li key={c.id}>
                        <button
                          onClick={() => openEvidence({ title: c.label, subtitle: `Known argument: ${c.claims.length} new claims so far in this replay`, sections: [{ kind: "claims", heading: "Claims that have arrived so far", claims: c.claims }] })}
                          className={cx("flex w-full items-baseline justify-between gap-2 rounded px-1.5 py-1 text-left text-sm hover:bg-white", c.lastAt === pos - 1 && "bg-white ring-1 ring-slate-300")}
                        >
                          <span className="min-w-0 text-slate-800">{c.label}</span>
                          <span className="text-xs whitespace-nowrap text-slate-500 tabular-nums">+{c.claims.length} claims · {c.voices.size} voices</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}

export default function ReplayPage() {
  const { project, projects, projectName } = useApp();
  const cutoffs = useApi<ReplayCutoffs>("/api/replay/cutoffs");
  const [picked, setPicked] = useState("");
  const list = cutoffs.data?.cutoffs ?? [];
  const cutoff = picked || list[0] || cutoffs.data?.earliest_allowed || "";
  const replay = useApi<Replay>(cutoffs.loading ? null : withQuery("/api/replay", { project, cutoff }));
  const noArguments = projects.find((p) => p.id === project)?.has_arguments === false;

  return (
    <>
      <div className="mb-4 rounded-lg border-2 border-slate-800 bg-white px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-2xl font-bold tracking-[0.12em] text-slate-900 sm:text-3xl">HISTORICAL SIMULATION</div>
            <p className="mt-0.5 max-w-3xl text-sm text-slate-600">
              A replay of past data, not live monitoring. The clock is set back to the cut-off date, then the later claims arrive in their real order.
            </p>
            {replay.data?.label ? <p className="mt-0.5 max-w-3xl text-xs text-slate-500">{replay.data.label.replace(/^historical simulation:\s*/i, "").replace(/^./, (c) => c.toUpperCase())}</p> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {replay.data?.mode ? (
              <Badge tone={/cached/i.test(replay.data.mode) ? "sky" : "teal"} title={`mode: ${replay.data.mode}`}>
                {/cached/i.test(replay.data.mode) ? "cached model scores" : replay.data.mode}
              </Badge>
            ) : null}
            {replay.data?.model_version ? <Badge tone="white">model {replay.data.model_version}</Badge> : null}
          </div>
        </div>
      </div>

      <PageHeader
        title={`Historical Replay: ${projectName(project)}`}
        right={
          list.length ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-sm text-slate-600">Freeze knowledge on</span>
              {list.map((c) => (
                <button
                  key={c}
                  onClick={() => setPicked(c)}
                  className={cx("rounded-md border px-2.5 py-1.5 text-sm font-medium tabular-nums", c === cutoff ? "border-teal-700 bg-teal-700 text-white" : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50")}
                >
                  {fmtDate(c)}
                </button>
              ))}
            </div>
          ) : null
        }
      />
      {cutoffs.data?.reason ? (
        <p className="-mt-3 mb-4 text-xs text-slate-500">
          Earliest cut-off allowed: {fmtDate(cutoffs.data.earliest_allowed)}, because {cutoffs.data.reason}.
        </p>
      ) : null}
      {cutoffs.error ? <p className="-mt-3 mb-4 text-xs text-red-800">Cut-off dates could not be loaded ({cutoffs.error.message}). Using the data service default.</p> : null}

      {noArguments ? <p className="mb-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">No arguments are extracted for this project, so its replay is empty. Choose another project at the top.</p> : null}
      {cutoffs.loading ? (
        <Loading label="Loading cut-off dates" />
      ) : (
        <DataState state={replay} what="the replay" rows={5}>
          {(r) => <Player key={`${r.project}|${r.cutoff}|${(r.steps ?? []).length}`} replay={r} />}
        </DataState>
      )}
    </>
  );
}
