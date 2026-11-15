"use client";

import { useState, type FormEvent } from "react";
import { useApi, withQuery } from "@/lib/api";
import type { PostsList } from "@/lib/types";
import { humanize, num } from "@/lib/format";
import { useApp } from "@/components/AppContext";
import { PostEvidenceCard, useEvidence } from "@/components/Evidence";
import { Button, DataState, Panel, Select } from "@/components/ui";

const PAGE = 20;

export function PostBrowser() {
  const { project, projectName, meta } = useApp();
  const openEvidence = useEvidence();
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const [channel, setChannel] = useState("");
  const [stance, setStance] = useState("");
  const [topic, setTopic] = useState("");
  const [offset, setOffset] = useState(0);

  const state = useApi<PostsList>(withQuery("/api/posts", { project, q, channel, stance, topic, limit: PAGE, offset }));
  const opt = (list: string[] | undefined, all: string) => [{ value: "", label: all }, ...(list ?? []).map((v) => ({ value: v, label: humanize(v) }))];
  const set = (fn: (v: string) => void) => (v: string) => {
    fn(v);
    setOffset(0);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setQ(draft.trim());
    setOffset(0);
  };

  return (
    <Panel title={`Source posts: ${projectName(project)}`} hint="Every collected post with its AI-assigned labels. Open a post to see the claims extracted from it.">
      <form onSubmit={submit} className="mb-3 flex flex-wrap items-center gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Search in post text"
          aria-label="Search posts"
          className="min-w-[12rem] flex-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
        />
        <Button type="submit" kind="primary">
          Search
        </Button>
        <Select label="Channel" value={channel} onChange={set(setChannel)} options={opt(meta.data?.channels, "All")} />
        <Select label="Stance" value={stance} onChange={set(setStance)} options={opt(meta.data?.stances, "All")} />
        <Select label="Topic" value={topic} onChange={set(setTopic)} options={opt(meta.data?.topics, "All")} />
      </form>
      <DataState state={state} what="posts" isEmpty={(d) => !(d.items ?? []).length} empty="No posts match these filters.">
        {(d) => {
          const items = d.items ?? [];
          const total = d.total ?? items.length;
          return (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-600">
                <span className="tabular-nums">
                  Posts {num(offset + 1)}–{num(offset + items.length)} of n = {num(total)}
                </span>
                <span className="flex gap-2">
                  <Button small disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                    ← Previous
                  </Button>
                  <Button small disabled={offset + items.length >= total} onClick={() => setOffset(offset + PAGE)}>
                    Next →
                  </Button>
                </span>
              </div>
              {items.map((p) => (
                <div key={p.doc_id}>
                  <PostEvidenceCard post={p} />
                  <div className="mt-0.5 text-right">
                    <button
                      onClick={() => openEvidence({ title: p.title || p.domain || "Post", subtitle: "Post, its labels and the claims extracted from it", sections: [{ kind: "post", doc_id: p.doc_id }] })}
                      className="text-xs font-medium text-teal-800 underline underline-offset-2"
                    >
                      Claims from this post (n = {num(p.n_claims ?? 0)}) →
                    </button>
                  </div>
                </div>
              ))}
            </div>
          );
        }}
      </DataState>
    </Panel>
  );
}
