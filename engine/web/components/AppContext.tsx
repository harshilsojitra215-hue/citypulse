"use client";

import { createContext, useCallback, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { useApi, type ApiState } from "@/lib/api";
import type { Health, Meta, ProjectMeta } from "@/lib/types";
import { humanize } from "@/lib/format";

export const DEFAULT_PROJECT = "heilbronn_cablecar";
const KEY = "citypulse.project";
const EVT = "citypulse:project";

function subscribe(cb: () => void) {
  window.addEventListener(EVT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVT, cb);
    window.removeEventListener("storage", cb);
  };
}

function readProject(): string {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === null ? DEFAULT_PROJECT : v;
  } catch {
    return DEFAULT_PROJECT;
  }
}

/** A small localStorage-backed value that is safe during server rendering. */
export function useStoredValue(key: string, fallback: string): [string, (v: string) => void] {
  const sub = useCallback(
    (cb: () => void) => {
      const evt = `citypulse:${key}`;
      window.addEventListener(evt, cb);
      window.addEventListener("storage", cb);
      return () => {
        window.removeEventListener(evt, cb);
        window.removeEventListener("storage", cb);
      };
    },
    [key],
  );
  const value = useSyncExternalStore(
    sub,
    () => {
      try {
        return window.localStorage.getItem(key) ?? fallback;
      } catch {
        return fallback;
      }
    },
    () => fallback,
  );
  const set = useCallback(
    (v: string) => {
      try {
        window.localStorage.setItem(key, v);
      } catch {
        /* storage blocked: value stays for this render only */
      }
      window.dispatchEvent(new Event(`citypulse:${key}`));
    },
    [key],
  );
  return [value, set];
}

type Ctx = {
  /** Selected project id. "" means all projects. */
  project: string;
  setProject: (id: string) => void;
  projects: ProjectMeta[];
  projectName: (id: string | undefined | null) => string;
  meta: ApiState<Meta>;
  health: ApiState<Health>;
};

const AppCtx = createContext<Ctx | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const project = useSyncExternalStore(subscribe, readProject, () => DEFAULT_PROJECT);
  const setProject = useCallback((id: string) => {
    try {
      window.localStorage.setItem(KEY, id);
    } catch {
      /* ignore */
    }
    window.dispatchEvent(new Event(EVT));
  }, []);

  const meta = useApi<Meta>("/api/meta");
  const health = useApi<Health>("/api/health", 15000);

  const value = useMemo<Ctx>(() => {
    const projects = meta.data?.projects ?? [];
    const names = new Map(projects.map((p) => [p.id, p.name ?? humanize(p.id)]));
    return {
      project,
      setProject,
      projects,
      projectName: (id) => (id ? (names.get(id) ?? humanize(id)) : "All projects"),
      meta,
      health,
    };
  }, [project, setProject, meta, health]);

  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApp(): Ctx {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp must be used inside AppProvider");
  return c;
}
