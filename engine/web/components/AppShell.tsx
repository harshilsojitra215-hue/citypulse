"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, type ReactNode } from "react";
import { API_BASE } from "@/lib/api";
import { num } from "@/lib/format";
import { AppProvider, DEFAULT_PROJECT, useApp } from "./AppContext";
import { EvidenceProvider } from "./Evidence";
import { Loading, cx } from "./ui";

export const NAV = [
  { href: "/", label: "Overview" },
  { href: "/emerging", label: "Emerging Concerns" },
  { href: "/replay", label: "Historical Replay" },
  { href: "/explorer", label: "Argument Explorer" },
  { href: "/cross-city", label: "Cross-City" },
  { href: "/review", label: "Evidence & Review" },
  { href: "/new-data", label: "New Data" },
];

function ProjectSelector() {
  const { project, setProject, projects, meta } = useApp();
  const options = projects.length ? projects.map((p) => ({ id: p.id, name: p.name ?? p.id })) : [{ id: DEFAULT_PROJECT, name: "Heilbronn" }];
  const known = project === "" || options.some((o) => o.id === project);
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="hidden text-slate-500 sm:inline">Project</span>
      <select
        aria-label="Project"
        value={project}
        onChange={(e) => setProject(e.target.value)}
        className="max-w-[13rem] rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-medium text-slate-900 focus:border-teal-600 focus:outline-none"
      >
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
        {!known ? <option value={project}>{project}</option> : null}
        <option value="">All projects</option>
      </select>
      {meta.error ? <span className="hidden text-xs text-red-700 md:inline">project list unavailable</span> : null}
    </label>
  );
}

function HealthStatus() {
  const { health } = useApp();
  const h = health.data;
  const down = !!health.error && !h;
  return (
    <div className="space-y-1 text-xs text-slate-500">
      <div className="flex items-center gap-1.5">
        <span className={cx("inline-block h-2 w-2 rounded-full", down ? "bg-red-500" : h ? "bg-emerald-500" : "bg-slate-300")} />
        <span className="font-medium text-slate-700">{down ? "Data service offline" : h ? "Data service online" : "Checking data service"}</span>
      </div>
      {down ? <div className="break-all">{API_BASE}</div> : null}
      {h ? (
        <>
          <div>
            {num(h.n_posts)} posts · {num(h.n_claims)} claims
          </div>
          {h.data_version ? <div>data {h.data_version}</div> : null}
          {h.matcher ? <div>matcher: {h.matcher.available === false ? "not available" : (h.matcher.mode ?? "available")}</div> : null}
          {h.embedder ? <div>search: {h.embedder.available === false ? "keyword only" : (h.embedder.backend ?? "available")}</div> : null}
        </>
      ) : null}
    </div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  return (
    <div className="flex min-h-screen flex-col">
      <div className="bg-slate-800 px-4 py-1.5 text-center text-[13px] leading-snug text-slate-100" role="note">
        Observable online debate, not a representative poll. AI-assigned labels, human validation pending.
      </div>
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 px-4 py-2.5">
          <Link href="/" className="flex min-w-0 items-baseline gap-2">
            <span className="text-lg font-semibold tracking-tight text-slate-900">CityPulse</span>
            <span className="hidden truncate text-sm text-slate-500 md:inline">Public debate and argument intelligence</span>
          </Link>
          <ProjectSelector />
        </div>
        <nav className="flex gap-1 overflow-x-auto border-t border-slate-100 px-2 py-1.5 lg:hidden" aria-label="Screens">
          {NAV.map((n, i) => (
            <Link
              key={n.href}
              href={n.href}
              className={cx("whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm", isActive(n.href) ? "bg-teal-700 font-medium text-white" : "text-slate-700 hover:bg-slate-100")}
            >
              {i + 1} {n.label}
            </Link>
          ))}
        </nav>
      </header>
      <div className="flex flex-1">
        <aside className="hidden w-60 shrink-0 border-r border-slate-200 bg-white lg:block">
          <div className="sticky top-[53px] flex h-[calc(100vh-53px-32px)] flex-col justify-between p-3">
            <nav className="space-y-0.5" aria-label="Screens">
              {NAV.map((n, i) => (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={isActive(n.href) ? "page" : undefined}
                  className={cx(
                    "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[0.95rem]",
                    isActive(n.href) ? "bg-teal-50 font-semibold text-teal-900" : "text-slate-700 hover:bg-slate-50",
                  )}
                >
                  <span className={cx("flex h-5 w-5 items-center justify-center rounded text-xs tabular-nums", isActive(n.href) ? "bg-teal-700 text-white" : "bg-slate-100 text-slate-500")}>
                    {i + 1}
                  </span>
                  {n.label}
                </Link>
              ))}
            </nav>
            <div className="border-t border-slate-100 pt-3">
              <HealthStatus />
            </div>
          </div>
        </aside>
        <main className="min-w-0 flex-1 px-4 py-5 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-[1400px]">
            <Suspense fallback={<Loading label="Loading screen" />}>{children}</Suspense>
          </div>
        </main>
      </div>
    </div>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <AppProvider>
      <EvidenceProvider>
        <Shell>{children}</Shell>
      </EvidenceProvider>
    </AppProvider>
  );
}
