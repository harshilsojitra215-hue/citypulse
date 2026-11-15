"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  code: string;
  body: unknown;
  constructor(status: number, code: string, message: string, body?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

type Params = Record<string, string | number | boolean | null | undefined>;

/** Build "/api/x?a=1" and drop empty parameters. */
export function withQuery(path: string, params?: Params): string {
  if (!params) return path;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `${path}${path.includes("?") ? "&" : "?"}${s}` : path;
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

function describe(body: unknown, status: number): { code: string; message: string } {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    const err = b.error;
    if (err && typeof err === "object") {
      const e = err as Record<string, unknown>;
      return { code: String(e.code ?? `http_${status}`), message: String(e.message ?? `Request failed (${status})`) };
    }
    if (typeof b.detail === "string") return { code: `http_${status}`, message: b.detail };
    if (b.detail && typeof b.detail === "object") {
      const d = b.detail as Record<string, unknown>;
      const inner = (d.error && typeof d.error === "object" ? d.error : d) as Record<string, unknown>;
      if (inner.message || inner.code) {
        return { code: String(inner.code ?? `http_${status}`), message: String(inner.message ?? `Request failed (${status})`) };
      }
      return { code: `http_${status}`, message: JSON.stringify(b.detail).slice(0, 300) };
    }
  }
  return { code: `http_${status}`, message: `The API answered with HTTP ${status}.` };
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { ...init, headers: { Accept: "application/json", ...(init?.headers || {}) } });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "network", `Cannot reach the CityPulse API at ${API_BASE}. Is the backend running?`);
  }
  const text = await res.text();
  let body: unknown = undefined;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    const d = describe(body, res.status);
    throw new ApiError(res.status, d.code, d.message, body);
  }
  return body as T;
}

export function apiPost<T>(path: string, json: unknown, signal?: AbortSignal): Promise<T> {
  return apiFetch<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(json),
    signal,
  });
}

export function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  return new ApiError(0, "client", e instanceof Error ? e.message : "Unexpected error");
}

type State<T> = { key: string; data?: T; error?: ApiError };

export type ApiState<T> = {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  reload: () => void;
};

/**
 * GET a path. `path === null` means "do not fetch".
 * `pollMs` re-fetches quietly on an interval (no loading flicker).
 * `pollWhile` can stop the polling once the data says the work is finished.
 */
export function useApi<T>(path: string | null, pollMs?: number | null, pollWhile?: (data: T | undefined) => boolean): ApiState<T> {
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<State<T>>({ key: "" });
  const key = path === null ? "" : `${path}#${nonce}`;
  const whileRef = useRef(pollWhile);
  useEffect(() => {
    whileRef.current = pollWhile;
  });

  useEffect(() => {
    if (path === null) return;
    const ctrl = new AbortController();
    let alive = true;
    let latest: T | undefined = undefined;
    const load = () =>
      apiFetch<T>(path, { signal: ctrl.signal })
        .then((data) => {
          latest = data;
          if (alive) setState({ key, data });
        })
        .catch((e) => {
          if (!alive || ctrl.signal.aborted) return;
          // keep the last good data while polling
          setState((prev) => ({ key, error: toApiError(e), data: prev.key === key ? prev.data : undefined }));
        });
    load();
    const timer = pollMs
      ? setInterval(() => {
          if (!whileRef.current || whileRef.current(latest)) load();
        }, pollMs)
      : null;
    return () => {
      alive = false;
      ctrl.abort();
      if (timer) clearInterval(timer);
    };
  }, [path, key, pollMs]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const current = path !== null && state.key === key ? state : undefined;
  return {
    data: current?.data,
    error: current?.error,
    loading: path !== null && !current,
    reload,
  };
}

export type PostState<T> = { data?: T; error?: ApiError; loading: boolean };

/** A POST (or any one-off call) triggered by the user. */
export function useAction<T>(): [PostState<T>, (run: () => Promise<T>) => Promise<T | undefined>, () => void] {
  const [state, setState] = useState<PostState<T>>({ loading: false });
  const run = useCallback(async (fn: () => Promise<T>) => {
    setState({ loading: true });
    try {
      const data = await fn();
      setState({ loading: false, data });
      return data;
    } catch (e) {
      setState({ loading: false, error: toApiError(e) });
      return undefined;
    }
  }, []);
  const reset = useCallback(() => setState({ loading: false }), []);
  return [state, run, reset];
}
