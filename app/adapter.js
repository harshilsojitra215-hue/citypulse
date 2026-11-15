/* CityPulse adapter: the one place that reads the pipeline export (pipeline/data/export/data.json, contract
   pipeline/CONTRACT.md) and the collector receipt (live/out/update/latest.json), and hands the screens
   small, typed view models. If the export renames a field, only this file changes. See app/DATA_MAP.md.
   Plain JavaScript with JSDoc types (no build step). */
(function () {
  'use strict';

  /**
   * @typedef {'support'|'oppose'|'neutral_informative'|'mixed'|'unclear'|'uncertain'} Stance
   * @typedef {{ project: string, voice: string, n: number, counts: Record<Stance, number>,
   *   share_corrected: Record<Stance, number>, ci: Record<Stance, [number, number]>, low_sample: boolean }} StanceRow
   * @typedef {{ project: string, code: string, n: number, share: number, base_n: number, support: number, oppose: number }} ArgumentRow
   * @typedef {{ project: string, n_events: number, n_peaks: number, peaks_linked: number, placebo_mean_linked: number, placebo_p: number }} PlaceboRow
   * @typedef {{ metric_id: string, name: string, value: number, ci: [number, number]|null, n: number, method: string }} ReliabilityRow
   * @typedef {{ id: string, date: string, project: string, source: string, media_type: string, url: string, title: string,
   *   stance: Stance|null, voice: string|null, arguments: string[], confidence: string, label_source: string }} Post
   * @typedef {{ num: number, den: number, unit: string, period: string, sources: Record<string, number> }} Scale
   *   Everything needed to inspect a share: numerator, denominator, unit, period and the source mix.
   * @typedef {{ found: number, d_after: number, d_late: number, d_unknown: number, about: number, not_this: number }} LiveProject
   */

  const H = () => window.CP_HISTORY || null;
  const LIVE = () => window.CP_LIVE || null;
  const PERIOD = 'Oct 2024 to 27 Oct 2026';

  const A = {
    PERIOD,
    /** @returns {boolean} true when the pipeline export is loaded */
    hasHistory: () => !!H(),
    /** @returns {StanceRow|null} */
    stance(project, voice) { const h = H(); return h ? (h.stance || []).find(s => s.project === project && s.voice === (voice || 'all')) || null : null; },
    /** @returns {ArgumentRow[]} sorted by count, highest first */
    args(project) { const h = H(); return h ? (h.arguments || []).filter(a => a.project === project).sort((a, b) => b.n - a.n) : []; },
    /** @returns {PlaceboRow|null} */
    placebo(project) { const h = H(); return h ? (h.placebo || []).find(p => p.project === project) || null : null; },
    /** @returns {ReliabilityRow|null} */
    reliability(id) { const h = H(); return h ? (h.reliability || []).find(r => r.metric_id === id) || null : null; },
    /** @returns {Post[]} */
    posts(filter) { const h = H(); return h ? (h.posts || []).filter(filter || (() => true)) : []; },
    /** @returns {{week: string, stories: number}[]} weekly stories for one project, quiet weeks filled with 0 */
    weekly(project, endIso) {
      const h = H(); if (!h) return [];
      const have = new Map((h.weekly || []).filter(w => w.project === project).map(w => [w.week, w.stories]));
      const out = [], t1 = Date.parse(endIso);
      for (let t = Date.UTC(2024, 9, 14); t <= t1; t += 7 * 864e5) { const k = new Date(t).toISOString().slice(0, 10); out.push({ week: k, stories: have.get(k) || 0 }); }
      return out;
    },
    /** Source mix of a set of posts: how many of each media type. @returns {Record<string, number>} */
    sourceMix(posts) { const m = {}; posts.forEach(p => { const k = p.media_type || 'Other'; m[k] = (m[k] || 0) + 1; }); return m; },
    /** @returns {Scale} */
    scale(num, den, unit, posts) { return { num, den, unit, period: PERIOD, sources: A.sourceMix(posts || []) }; },
    /** Labelling status of the export, in plain words. */
    labelStatus() {
      const h = H(); if (!h) return 'not in yet';
      const s = (h.meta && h.meta.status && h.meta.status.labels) || 'unknown';
      // the final export: one Claude Haiku run per post (the engine's label run) plus the three pilot runs on a sample
      const runs = (h.meta && h.meta.label_runs) || [];
      if (s === 'llm_vote' && runs.some(r => /engine_haiku/.test(r))) {
        const pilotN = Math.max(0, ...(h.reliability || []).filter(r => /^agreement\.project\.pilot_[^~]*~pilot_/.test(r.metric_id)).map(r => r.n || 0));
        const pilots = runs.filter(r => /^pilot_/.test(r)).length;
        return `AI labels: one Claude Haiku run per post${pilots && pilotN ? `, plus ${pilots === 3 ? 'three' : pilots} pilot runs on ${pilotN} posts` : ''}, not checked by people`;
      }
      return { rules_only: 'rules only, no stance labels', llm_vote: 'AI labels, three runs with a majority vote, not checked by people', human_checked: 'AI labels checked by people' }[s] || s;
    },

    /* ---------- the collector receipt ---------- */
    meta: () => (LIVE() ? LIVE().meta : null),
    items: () => (LIVE() ? LIVE().items : []),
    /** @returns {LiveProject} zeros where the receipt has no value */
    liveProject(id) {
      const m = A.meta(), p = (m && m.per_project && m.per_project[id]) || {};
      return { found: p.found || 0, d_after: p.d_after || 0, d_late: p.d_late || 0, d_unknown: p.d_unknown || 0, about: p.about || 0, not_this: p.not_this || 0 };
    },
    /** The state of the last check, for the screens: analysed, partial, failed or empty. */
    liveState() {
      const m = A.meta();
      if (!m) return { state: 'empty', words: 'No check has run yet.' };
      if (m.collect_status === 'failed') return { state: 'failed', words: 'The last check failed. The briefing shown is the last successful one.' };
      if (m.collect_status === 'partial') return { state: 'partial', words: 'Some sources did not answer. Their gaps are listed under "What we cannot see".' };
      return { state: 'analysed', words: 'Every source asked in this check answered.' };
    }
  };
  window.CPAdapter = A;

  /* ---------- the argument engine snapshot (app/data/engine.js, window.CP_ENGINE) ----------
     Written by live/engine_bridge/snapshot.py from the argument engine API. Any block may be missing, so
     every reader returns null or [] instead of failing. A pure factory, so app/ask.js and the Node suite use the same
     reading. Privacy: links that name an account are dropped (same rule as app/build_data.py), @handles are masked,
     and the engine's author hash ("voice") is never passed on. */
  const HANDLE_URL = /\/@[^/?#]+|(?:^|\/\/)(?:www\.)?(?:x|twitter)\.com\/(?!i\/|search)[^/?#]+|tiktok\.com\/@|facebook\.com\/(?!\d+\/|groups\/\d+|watch|share|events)[A-Za-z][^/?#]*|instagram\.com\/(?!p\/|reel\/|tv\/)[^/?#]+\/?$|linkedin\.com\/in\/|threads\.net\/@|bsky\.app\/profile\//;
  const HANDLE_TXT = /@[A-Za-z0-9_][A-Za-z0-9_.]{1,40}/g;
  const MIN_VOICES = 2;   // the engine flags a new group once 2 or more independent voices raised it (the engine's replay step)
  /**
   * @typedef {{ cid: string, claim: string, date: string, channel: string, domain: string, url: string|null, link_withheld: boolean,
   *   polarity: string, relation: string|null }} Claim
   * @typedef {{ id: string, state: string, label: string, first_seen: string, flagged_at: string|null, flagged: boolean, n_claims: number,
   *   n_voices: number, polarity: Record<string, number>, topic: string, note: string, claims: Claim[], closest: Claim|null }} Concern
   */
  function engineModel(raw) {
    const E = raw && typeof raw === 'object' ? raw : null;
    const obj = x => (x && typeof x === 'object' && !Array.isArray(x) ? x : null);
    const num = x => (typeof x === 'number' && isFinite(x) ? x : null);
    const arr = x => (Array.isArray(x) ? x : []);
    /** @returns {Claim} */
    function claim(c) {
      const url = typeof c.url === 'string' && /^https?:\/\//.test(c.url) ? c.url : null;
      const withheld = !!(url && HANDLE_URL.test(url));
      return { cid: String(c.cid || ''), claim: String(c.claim || '').replace(HANDLE_TXT, '@[USER]'), date: c.date || null, channel: c.channel || '',
        domain: c.domain || '', url: withheld ? null : url, link_withheld: withheld, polarity: c.polarity || '', relation: c.relation || null };
    }
    /** @returns {Concern} */
    function concern(c) {
      const u = obj(c.uncertainty) || {};
      return { id: String(c.concern_id || ''), project: c.project || '', state: c.state || '', label: String(c.label || '').replace(HANDLE_TXT, '@[USER]'), first_seen: c.first_seen || null,
        flagged_at: c.flagged_at || null, flagged: !!c.flagged_at, n_claims: num(c.n_claims) || 0, n_voices: num(c.n_voices) || 0,
        polarity: obj(c.polarity) || {}, topic: c.topic || '', note: typeof u.note === 'string' ? u.note : '',
        claims: arr(c.claims).filter(obj).map(claim), closest: obj(arr(c.closest_older)[0]) ? claim(arr(c.closest_older)[0]) : null };
    }
    const replayRaw = () => (E ? obj(E.replay_hn) : null);
    const M = {
      MIN_VOICES,
      has: () => !!(E && (obj(E.replay_hn) || obj(E.matcher) || obj(E.health))),
      takenAt: () => (E && typeof E.taken_at === 'string' ? E.taken_at : null),
      /** engine status for the small status line */
      status() {
        const h = E ? obj(E.health) || {} : {}, m = obj(h.matcher) || {}, e = obj(h.embedder) || {};
        const mode = m.available === false ? 'off' : m.mode === 'local-model' ? 'local model' : /cache/.test(String(m.mode || '')) ? 'cached scores' : (m.mode || 'not reported');
        return { matcher: mode, embedder: e.available === true ? 'on' : e.available === false ? 'off' : 'not reported',
          version: m.version || (obj(E && E.matcher) || {}).version || null, runs: arr(h.runs) };
      },
      /** the historical replay: frozen at the cut-off, later claims arrive in their real order */
      replay() {
        const r = replayRaw(); if (!r || !obj(r.counts)) return null;
        const c = r.counts, n = k => num(c[k]);
        if ([n('n_claims'), n('familiar'), n('joins_new'), n('opens_new'), n('ambiguous')].some(x => x == null)) return null;
        return { cutoff: r.cutoff || null, mode: r.mode || '', simulation: r.simulation !== false, version: r.model_version || null,
          counts: { n_claims: n('n_claims'), familiar: n('familiar'), joins_new: n('joins_new'), opens_new: n('opens_new'), ambiguous: n('ambiguous'),
            flagged: n('concerns_flagged') != null ? n('concerns_flagged') : arr(r.concerns).filter(x => x && x.flagged_at).length } };
      },
      /** @returns {Concern[]} flagged first (in the order they were flagged), then more voices, more claims, earlier first */
      concerns() {
        const r = replayRaw(); if (!r) return [];
        return arr(r.concerns).filter(obj).map(concern).filter(c => c.id && c.label).sort((a, b) =>
          (b.flagged - a.flagged) || String(a.flagged_at || '').localeCompare(String(b.flagged_at || '')) || (b.n_voices - a.n_voices) || (b.n_claims - a.n_claims)
          || String(a.first_seen || '').localeCompare(String(b.first_seen || '')));
      },
      concern(id) { return M.concerns().find(c => c.id === id) || null; },
      findConcern(re) { return M.concerns().find(c => re.test(c.label) || c.claims.some(x => re.test(x.claim))) || null; },
      /** every claim id the page can show, for the Ask validator */
      allClaims() { const out = []; M.concerns().forEach(c => { out.push(...c.claims); if (c.closest) out.push(c.closest); }); return out; },
      /** the main arguments known before the cut-off */
      knownBefore() {
        const r = replayRaw(), k = r ? obj(r.known_before) : null; if (!k) return null;
        const top = arr(k.top_families).filter(f => obj(f) && f.name && num(f.n) != null).map(f => ({ id: f.family_id, name: String(f.name), n: f.n })).sort((a, b) => b.n - a.n);
        return top.length ? { n_claims: num(k.n_claims), n_posts: num(k.n_posts), top } : null;
      },
      /** runs fed from the live collector (the engine's batch uploads); the base data is not one */
      collectorRuns() {
        const b = E ? obj(E.batches) : null;
        return arr(b && b.runs).filter(obj).map(r => ({ id: r.run_id || '', created_at: r.created_at || null, finished_at: r.finished_at || null, status: r.status || '',
          counts: obj(r.counts) || {}, concerns: arr(obj(r.findings) && r.findings.concerns).filter(obj).map(concern) }))
          .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
      },
      /** matcher test metrics; null unless every number needed for the reliability line is there */
      matcher() {
        const m = E ? obj(E.matcher) : null, x = m ? obj(m.metrics) : null; if (!x) return null;
        const iv = arr(x.pair_f1_interval), wf = /^(\d+) of (\d+)$/.exec(String(x.familiar_claims_wrongly_flagged || ''));
        const out = { f1: num(x.pair_f1), lo: num(iv[0]), hi: num(iv[1]), base: num(x.baseline_pair_f1), n_pairs: num(x.n_test_pairs),
          reference: x.reference || null, provisional: x.provisional !== false, version: m.version || null,
          wrongly_new: wf ? +wf[1] : null, wrongly_new_of: wf ? +wf[2] : null, trained_on: m.trained_on || '', tested_on: m.tested_on || '' };
        return [out.f1, out.lo, out.hi, out.base, out.n_pairs].some(v => v == null) ? null : out;
      },
      leakage() { return E ? obj(E.leakage_audit) : null; }
    };
    return M;
  }
  window.CPEngineModel = engineModel;
  A.engine = engineModel(window.CP_ENGINE || null);
})();
