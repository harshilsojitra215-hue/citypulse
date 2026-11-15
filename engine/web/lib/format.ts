import type { Share } from "./types";

export function humanize(s: string | null | undefined): string {
  if (!s) return "";
  const t = String(s).replace(/[_-]+/g, " ").trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function num(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  return new Intl.NumberFormat("en-GB").format(n);
}

export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  return `${(v * 100).toFixed(digits)}%`;
}

export function score(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  return v.toFixed(2);
}

export function shareText(s: Share | null | undefined): string {
  if (!s || s.value === null || s.value === undefined) return "–";
  const iv = s.lo !== null && s.lo !== undefined && s.hi !== null && s.hi !== undefined ? ` (${pct(s.lo)}–${pct(s.hi)})` : "";
  return `${pct(s.value)}${iv}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-07-26" -> "26 Jul 2026"; "2026-07" -> "Jul 2026"; ISO timestamps keep the day only. */
export function fmtDate(d: string | null | undefined): string {
  if (!d) return "–";
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(String(d));
  if (!m) return String(d);
  const mon = MONTHS[Number(m[2]) - 1] ?? m[2];
  return m[3] ? `${Number(m[3])} ${mon} ${m[1]}` : `${mon} ${m[1]}`;
}

export function fmtDateTime(d: string | null | undefined): string {
  if (!d) return "–";
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(String(d));
  if (!m) return fmtDate(d);
  return `${fmtDate(d)}, ${m[4]}:${m[5]}`;
}

export function shortPeriod(p: string | null | undefined): string {
  if (!p) return "";
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(String(p));
  if (!m) return String(p);
  const mon = MONTHS[Number(m[2]) - 1] ?? m[2];
  return m[3] ? `${Number(m[3])} ${mon}` : `${mon} ${m[1].slice(2)}`;
}

/** First and last day covered by a period label ("2026-07" month or "2026-07-06" week start). */
export function periodRange(p: string): { from: string; to: string } | null {
  const month = /^(\d{4})-(\d{2})$/.exec(p);
  if (month) {
    const y = Number(month[1]);
    const mo = Number(month[2]);
    const last = new Date(Date.UTC(y, mo, 0)).getUTCDate();
    return { from: `${month[1]}-${month[2]}-01`, to: `${month[1]}-${month[2]}-${String(last).padStart(2, "0")}` };
  }
  const day = /^(\d{4})-(\d{2})-(\d{2})/.exec(p);
  if (day) {
    const start = new Date(Date.UTC(Number(day[1]), Number(day[2]) - 1, Number(day[3])));
    const end = new Date(start.getTime() + 6 * 86400000);
    return { from: start.toISOString().slice(0, 10), to: end.toISOString().slice(0, 10) };
  }
  return null;
}

export function isHttpUrl(u: string | null | undefined): u is string {
  return !!u && /^https?:\/\//i.test(u);
}

export function isVerified(v: string | boolean | null | undefined): boolean {
  return v === true || v === "yes" || v === "true" || v === "verified";
}

export function secs(s: number | null | undefined): string {
  if (s === null || s === undefined) return "–";
  if (s < 10) return `${s.toFixed(1)} s`;
  if (s < 90) return `${Math.round(s)} s`;
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

// Plain-language names for the concern states (decided wording).
export const STATE_ORDER = ["new_emerging", "ambiguous", "new_single", "gaining", "recurring"] as const;   // "needs review" before one-voice candidates: flagged variants (2+ voices) come first

export const STATE_INFO: Record<string, { title: string; short: string; help: string; tone: string }> = {
  new_emerging: {
    title: "Potential new argument (2+ independent voices)",
    short: "Potential new argument",
    help: "No equivalent among earlier claims, and at least two independent voices have raised it.",
    tone: "amber",
  },
  new_single: {
    title: "Candidate: one voice so far",
    short: "Candidate: one voice",
    help: "No equivalent among earlier claims, but only one independent voice so far. Watch, do not act.",
    tone: "slate",
  },
  ambiguous: {
    title: "Needs review: may be a variant of a known argument",
    short: "Needs review",
    help: "The match score lies between the two cut-offs. A person should decide.",
    tone: "violet",
  },
  gaining: {
    title: "Known argument gaining visibility",
    short: "Gaining visibility",
    help: "A known argument that appears significantly more often than in its own past.",
    tone: "sky",
  },
  recurring: {
    title: "Recurring argument",
    short: "Recurring",
    help: "A known argument that was seen again.",
    tone: "gray",
  },
};

export function stateInfo(state: string | undefined) {
  return STATE_INFO[state ?? ""] ?? { title: humanize(state) || "Unclassified", short: humanize(state) || "Unclassified", help: "", tone: "gray" };
}

/**
 * The two cut-offs ("new", "familiar") apply to the best same-argument score
 * against earlier claims. The API sends that score directly where it can
 * (best_older_p_same / best_p_same) and otherwise a novelty score = 1 - best.
 */
export function bestMatch(u: { best_older_p_same?: number | null; best_p_same?: number | null; novelty_score?: number | null; score?: number | null } | null | undefined): number | null {
  if (!u) return null;
  const direct = u.best_older_p_same ?? u.best_p_same;
  if (direct !== null && direct !== undefined) return direct;
  const nov = u.novelty_score ?? u.score;
  if (nov === null || nov === undefined) return null;
  return Math.round((1 - nov) * 10000) / 10000;
}
