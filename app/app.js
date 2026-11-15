/* CityPulse website. Plain JavaScript, no libraries.
   Data comes from app/data/*.js (built by app/build_data.py from live/ and pipeline/ outputs).
   The historical part has three states: awaiting (the final run not in yet), pilot (the v1 export,
   marked provisional), final (the final export). See app/DATA_MAP.md. */
(function () {
  'use strict';

  /* ---------- inputs ---------- */
  const LIVE = window.CP_LIVE || null;
  const HIST = window.CP_HISTORY || null;
  const FACTS = (window.CP_FACTS || {}).figures || {};
  const CFG = window.CP_CONFIG || { history_mode: 'awaiting' };
  const qs = new URLSearchParams(location.search);
  let MODE = qs.get('history') || CFG.history_mode || 'awaiting';
  if (!HIST && MODE !== 'awaiting') MODE = 'awaiting';
  // "Final run" is shown only when the pipeline export itself says the run is final (meta.release = "final").
  // A config or URL switch alone can never make provisional numbers look final.
  const EXPORT_FINAL = !!(HIST && HIST.meta && HIST.meta.release === 'final');
  if (MODE === 'final' && !EXPORT_FINAL) MODE = 'pilot';
  const HAS_H = MODE !== 'awaiting';

  /* ---------- words ---------- */
  const CORE = ['heilbronn_cablecar', 'ipai', 'bonn_cablecar', 'paris_c1'];
  const PNAME = {
    heilbronn_cablecar: 'Heilbronn cable car', ipai: 'IPAI Heilbronn', bonn_cablecar: 'Bonn cable car', paris_c1: 'Paris Câble C1',
    berlin_cablecar: 'Berlin', hamburg_cablecar: 'Hamburg', koblenz_cablecar: 'Koblenz', koeln_cablecar: 'Köln',
    muenchen_cablecar: 'München', stuttgart_cablecar: 'Stuttgart', wuppertal_cablecar: 'Wuppertal'
  };
  const PNOTE = {
    heilbronn_cablecar: 'The planned line, in preliminary planning',
    ipai: 'The AI park the line would serve',
    bonn_cablecar: 'A German city planning a line',
    paris_c1: 'Opened Dec 2025, the newest urban line'
  };
  // History can show any of the four projects in the city's data; Heilbronn first
  const HCITIES = ['heilbronn_cablecar', 'bonn_cablecar', 'paris_c1', 'ipai'];
  const CITY = { heilbronn_cablecar: 'Heilbronn', bonn_cablecar: 'Bonn', paris_c1: 'Paris', ipai: 'IPAI' };
  const CITY_TAB = { heilbronn_cablecar: 'Heilbronn', bonn_cablecar: 'Bonn', paris_c1: 'Paris C1', ipai: 'IPAI' };
  let HP = 'heilbronn_cablecar';
  // titles from the sources keep their words; pictographs are dropped so the page stays calm
  const clean = t => String(t == null ? '' : t).replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{200D}]/gu, '').replace(/\s{2,}/g, ' ').trim();
  const STANCE = { support: 'Support', oppose: 'Oppose', neutral_informative: 'Report only', mixed: 'Mixed', unclear: 'Unclear', uncertain: 'Runs disagreed' };
  const STANCE_ORDER = ['support', 'oppose', 'neutral_informative', 'mixed', 'unclear'];
  const VOICE = { news_institutional: 'News and institutions', politician_official: 'Politicians and officials', citizen: 'Citizens', company_vendor: 'Companies', unclear: 'Speaker unclear' };
  const ARG = {
    cost: 'Cost', traffic_mobility: 'Traffic and mobility', tourism_image: 'Tourism and image', climate_environment: 'Climate and environment',
    ipai_who_benefits: 'Who benefits', noise_privacy_overflight: 'Noise and flying over homes', cityscape_design: 'Cityscape and design',
    process_participation: 'Process and participation', safety_technology: 'Safety and technology', other: 'Other'
  };
  const KIND = { news: 'News', official: 'Official page', council_paper: 'Council paper', web: 'Web page', social_link: 'Social media link',
    social_post: 'Social post', video: 'Video', video_comment: 'Video comment', forum: 'Forum' };
  const SOURCE = { rss: 'News feeds', pagewatch: 'City pages', bluesky: 'Bluesky', mastodon: 'Mastodon', youtube: 'YouTube', exa: 'Exa search',
    tavily: 'Tavily search', oparl: 'Council papers', date_recovery: 'Date recovery' };
  const DATECLASS = { after: 'Published after 27 Oct', late: 'Older, found late', unknown: 'Date unknown' };
  // Backtest of the live collector against the city's own monitoring tool (same days).
  // Source: live/experiments/exp10_recall_vs_city_tool.py, quoted in live/out/update/latest.md.
  const BACKTEST = { hn_found: 11, hn_total: 19, all_found: 39, all_total: 273 };
  const ARGS_BASE = 'Argument codes exist only for the pilot sample, so these are counts, not shares of all posts.';
  const DATASET = { records: 39361, start: 'Oct 2024', end: '27 Oct 2026', end_utc: '2026-10-27T12:29:00Z' };

  /* ---------- helpers ---------- */
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const nf = n => (n == null ? '–' : Number(n).toLocaleString('en-GB'));
  const pct = x => (x == null ? '–' : Math.round(x * 100) + '%');
  const TZ = 'Europe/Berlin';
  function when(iso, withTime) {
    if (!iso) return 'not known';
    const d = new Date(iso);
    const o = { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short' };
    if (withTime) Object.assign(o, { hour: '2-digit', minute: '2-digit', hour12: false });
    return d.toLocaleString('en-GB', o).replace(',', '');
  }
  function day(iso) {
    if (!iso) return 'date unknown';
    const d = new Date(iso.length <= 10 ? iso + 'T12:00:00Z' : iso);
    return d.toLocaleDateString('en-GB', { timeZone: TZ, day: 'numeric', month: 'short', year: 'numeric' });
  }
  function runIdToIso(id) { // 20261114T184537Z -> ISO
    if (!id) return null;
    const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(id);
    return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z` : null;
  }
  const plural = (n, one, many) => `${nf(n)} ${n === 1 ? one : many}`;
  // the same pages also run as a hosted copy (Vercel): there the live check and the analyst console stay on the presentation laptop
  const LOCAL = /^(127\.0\.0\.1|localhost|\[::1\])$/.test(location.hostname) || location.protocol === 'file:';
  const OFFLINE_HINT = LOCAL ? 'Needs app/serve.py' : '';
  const host = u => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (e) { return ''; } };

  /* ---------- derived live numbers ---------- */
  const SCAN_ISO = () => (LIVE && LIVE.meta ? runIdToIso(LIVE.meta.collect_run_id) : null);
  const LM = LIVE ? LIVE.meta : null;
  const LITEMS = LIVE ? LIVE.items : [];
  const AD = window.CPAdapter;
  function pp(id) { return AD.liveProject(id); }
  function sumCore(key) { return CORE.reduce((a, id) => a + (pp(id)[key] || 0), 0); }

  /* ---------- 01: the story so far ---------- */
  function hStance(project, voice) { return HAS_H ? AD.stance(project, voice) : null; }
  function hArgs(project) { return HAS_H ? AD.args(project) : []; }
  function hPlacebo(project) { return HAS_H ? AD.placebo(project) : null; }
  function hRel(id) { return HAS_H ? AD.reliability(id) : null; }
  function stanceAgreement() {
    const rs = HAS_H ? (HIST.reliability || []).filter(x => /^agreement\.stance_relevant/.test(x.metric_id)) : [];
    if (!rs.length) return 'agreement between runs not reported';
    const v = rs.map(r => r.value), lo = Math.min(...v).toFixed(2), hi = Math.max(...v).toFixed(2);
    return `independent AI runs agree on stance with kappa ${lo === hi ? lo : lo + ' to ' + hi} (${rs.length} pairs of runs, about ${rs[0].n} posts), not yet checked against people`;
  }

  // The 3 to 5 key findings. Each one is a question (shown in every state) and an answer computed from
  // the pipeline export (shown only when it is in). Wording of the answers is final only after the result review.
  const FINDINGS = [
    {
      q: 'Who takes a side, and who only reports?',
      measures: 'Share of posts that support, oppose or only report, with the sample size',
      why: 'Reporting is not opposition. The city should read the posts that take a side, not the volume of coverage.',
      next: 'Of the posts that take a side, how many come from residents rather than institutions?',
      answer() {
        const s = hStance(HP);
        if (!s) return null;
        const rep = s.counts.neutral_informative / Math.max(1, s.n), side = (s.counts.support + s.counts.oppose) / Math.max(1, s.n);
        const head = rep > 0.5 ? 'Most posts only report.' : side > 0.5 ? 'Most posts take a side.' : 'Reporting and taking a side are close.';
        return { t: `${head} ${s.counts.support} posts support, ${s.counts.oppose} oppose.`,
          m: `${s.counts.neutral_informative} of ${s.n} labelled ${CITY[HP]} posts take no side`,
          scale: [s.counts.support + s.counts.oppose, s.n, `labelled ${CITY[HP]} posts take a side`], small: s.low_sample };
      },
      evidence: () => ({ title: `${CITY[HP]} posts with a stance label`, filter: p => p.project === HP && p.stance })
    },
    {
      q: 'What do people raise most?',
      measures: 'The argument named most often, with its count',
      why: 'The argument raised most is the first one the city\'s communication should answer.',
      next: 'Does the city FAQ answer it, with current figures?',
      answer() {
        const a = hArgs(HP)[0];
        if (!a) return null;
        // argument codes exist only for the pilot sample, so this is a count, never a share of all labelled posts
        return { t: `In the pilot sample, ${(ARG[a.code] || a.code).toLowerCase()} comes up most.`, m: `${a.n} ${CITY[HP]} posts raise it. ${ARGS_BASE.replace(/\.$/, '')}`, code: a.code, small: true };
      },
      evidence() {
        const a = hArgs(HP)[0];
        const code = a ? a.code : null;
        return { title: `${CITY[HP]} posts that raise ${ARG[code] || code}`, filter: p => p.project === HP && (p.arguments || []).includes(code) };
      }
    },
    {
      q: 'When does attention rise, and what happened then?',
      measures: 'Weeks with unusual volume, and whether a documented city event falls in the same days',
      why: 'If attention rises around council decisions, the city can expect the next wave around the next decision and prepare for it.',
      next: 'Which decision comes next, and what should be ready before it?',
      answer() {
        const p = hPlacebo(HP);
        if (!p) return null;
        return { t: `${p.peaks_linked} of ${p.n_peaks} attention peaks fall on a documented city event.`, m: `Random dates link about ${(Math.round(p.placebo_mean_linked * 10) / 10).toLocaleString('en-GB')} on average. The event list was partly built from the data, so this is timing, not cause`,
          scale: [p.peaks_linked, p.n_peaks, 'weeks with unusual attention fall on a documented event'] };
      },
      evidence() {
        const weeks = new Set((HIST.peaks || []).filter(k => k.project === HP && !k.weak).map(k => k.week));
        return { title: `${CITY[HP]} posts in the peak weeks`, filter: p => p.project === HP && weeks.has(mondayOf(p.date)) };
      }
    },
    {
      q: 'Do citizens sound different from the news?',
      measures: 'Stance by speaker group: citizens, news, officials',
      why: 'Resident voices are few in this data. Most of the debate is media and institutions talking. Speaker labels exist only for the pilot sample.',
      next: 'Where can the city hear more residents directly, for example through its own survey or participation platform?',
      answer() {
        const c = hStance(HP, 'citizen');
        const n = hStance(HP, 'news_institutional');
        if (!c || !n) return null;
        const MIN = 10;     // fewer citizen posts than this: no direction is claimed
        const clear = (a, b) => a >= 2 * b && a - b >= 3;    // a clear lead, not a one-post difference
        // speaker labels exist only for the pilot sample: under 30 citizen posts no lean is claimed, the counts are given instead
        const lean = c.n < MIN ? `Too few citizen posts with a speaker label to say (n = ${c.n})`
          : c.n < 30 ? `Citizens: ${c.counts.oppose} of ${c.n} against, a small pilot sample`
          : clear(c.counts.oppose, c.counts.support) ? 'Citizens lean against'
          : clear(c.counts.support, c.counts.oppose) ? 'Citizens lean in favour' : 'Citizens are split';
        const news = n.n < MIN ? `too few news posts to say (n = ${n.n})` : n.counts.neutral_informative / n.n > 0.5 ? 'the news mostly reports' : 'the news often takes a side';
        return { t: `${lean}. ${news[0].toUpperCase() + news.slice(1)}.`, m: `Citizens: ${c.counts.oppose} of ${c.n} oppose${c.low_sample ? ' (small sample)' : ''}. News: ${n.counts.neutral_informative} of ${n.n} report only`,
          scale: [c.counts.oppose, c.n, 'labelled citizen posts oppose'], small: c.low_sample };
      },
      evidence: () => ({ title: `${CITY[HP]} posts by citizens`, filter: p => p.project === HP && p.voice === 'citizen' && p.stance })
    },
    {
      q: 'Does the tone of a post tell you its position?',
      measures: "How often the monitoring vendor's tone score matches the stance",
      why: 'A tone score from a monitoring tool cannot stand in for support or opposition. Reading it that way misleads.',
      next: 'Which of the city\'s current reports use tone as if it were opinion?',
      answer() {
        const r = hRel('vendor_vs_stance.match');
        if (!r) return null;
        return { t: r.value < 0.5 ? `No. Tone matched position in only ${pct(r.value)} of posts.` : `Only partly. Tone matched position in ${pct(r.value)} of posts.`, m: `${r.n} labelled posts; a negative-sounding news item can still be neutral`,
          scale: [Math.round(r.value * r.n), r.n, 'labelled posts where tone matched position'] };
      },
      evidence: () => ({ title: 'Posts with a stance label (all four projects)', filter: p => p.stance }), global: true
    }
  ];
  const sentenceUp = s => { s = String(s || ''); return s ? s[0].toUpperCase() + s.slice(1) + (/[.!?]$/.test(s) ? '' : '.') : ''; };
  function mondayOf(iso) {
    if (!iso) return '';
    const d = new Date(iso + 'T12:00:00Z');
    const k = (d.getUTCDay() + 6) % 7;
    d.setUTCDate(d.getUTCDate() - k);
    return d.toISOString().slice(0, 10);
  }
  function mixLine(posts) {
    const m = AD.sourceMix(posts);
    return Object.entries(m).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([k, v]) => `${esc(k)} ${v}`).join(' · ') || 'none';
  }
  function scaleCard(label, num, den, unit, posts, small) {
    return `<dl class="fcard7">
      <div><dt>Scale</dt><dd>${den == null ? `<b>${nf(num)}</b> ${esc(unit)} ${esc(AD.PERIOD)}.` : `<b>${nf(num)} of ${nf(den)}</b> ${esc(unit)} (${den ? pct(num / den) : '–'}), ${esc(AD.PERIOD)}`}${small ? (den == null ? ' Small sample: read it as a direction, not as a number.' : '. Small sample: read it as a direction, not as a number.') : ''}</dd></div>
      <div><dt>Source mix</dt><dd>${mixLine(posts)}</dd></div>
      <div><dt>Reliability</dt><dd>${esc(AD.labelStatus())}; ${esc(stanceAgreement())}.${MODE === 'pilot' ? ' Pilot run, provisional.' : ''}</dd></div>
    </dl>`;
  }
  function findingCard(f, a, posts) {
    const sc = a.scale || [null, null, ''];
    return `<dl class="fcard7">
      <div><dt>Finding</dt><dd><b>${esc(a.t)}</b></dd></div>
      <div><dt>Why it matters</dt><dd>${esc(f.why)}</dd></div>
      <div><dt>Scale</dt><dd>${sc[0] != null ? `<b>${nf(sc[0])} of ${nf(sc[1])}</b> ${esc(sc[2])}, ${esc(AD.PERIOD)}` : esc(a.m)}${a.small ? '. Small sample: read it as a direction, not as a number.' : ''}</dd></div>
      <div><dt>Context</dt><dd>Evidence below: ${nf(posts.length)} posts. Source mix: ${mixLine(posts)}</dd></div>
      <div><dt>Reliability</dt><dd>${esc(AD.labelStatus())}; ${esc(stanceAgreement())}.${MODE === 'pilot' ? ' Pilot run, provisional.' : ''}</dd></div>
      <div><dt>Next question</dt><dd>${esc(f.next)}</dd></div>
    </dl>`;
  }

  function awaitingNote(what) {
    return `<div class="await"><span class="pulse"></span>${esc(what)} appears here when the final analysis run is in.</div>`;
  }
  function provNote() { return MODE === 'pilot' ? '<p class="note">Pilot run, provisional. Bars show the share; the thin band is the likely range.</p>' : '<p class="note">The thin band is the likely range for each share.</p>'; }

  function panelStance(proj) {
    const s = hStance(proj);
    if (!s) {
      return awaitingNote('The split between support, opposition and neutral reporting')
        + `<div class="rows">${STANCE_ORDER.map(k => `<div class="row ph"><span class="k">${STANCE[k]}</span><span class="track"></span><span class="val">n –</span></div>`).join('')}</div>`
        + `<p class="note">Counts are posts, not people, and not a poll. Stance means for or against the project, not the tone of the text.</p>`;
    }
    const rows = STANCE_ORDER.map(k => {
      const sh = (s.share_corrected || {})[k] || 0; const ci = (s.ci || {})[k];
      const ciBand = ci ? `<span class="ci" style="left:${ci[0] * 100}%;width:${Math.max(0.5, (ci[1] - ci[0]) * 100)}%"></span>` : '';
      return `<div class="row" data-inspect="stance|${k}|${proj}" role="button" tabindex="0" title="Open the posts behind this share"><span class="k">${STANCE[k]}</span><span class="track"><span class="fill ${k === 'support' || k === 'oppose' ? '' : 'acc'}" style="width:${sh * 100}%;${k === 'neutral_informative' ? 'background:#c3ccd8' : ''}"></span>${ciBand}</span><span class="val">${pct(sh)} · ${s.counts[k] || 0}</span></div>`;
    }).join('');
    return `<p class="cap">${esc(PNAME[proj])}: ${s.n} labelled posts${s.low_sample ? ' (small sample: read as direction, not as a number)' : ''}.</p><div class="rows">${rows}</div>${provNote()}`;
  }

  function panelArgs(proj) {
    const a = hArgs(proj);
    if (!a.length) {
      return awaitingNote('Which arguments come up, and how often')
        + `<div class="rows">${['cost', 'traffic_mobility', 'climate_environment', 'tourism_image', 'cityscape_design'].map(k => `<div class="row ph"><span class="k">${ARG[k]}</span><span class="track"></span><span class="val">n –</span></div>`).join('')}</div>`
        + `<p class="note">Topic names come from the codebook. A post can raise several.</p>`;
    }
    const max = Math.max(...a.map(x => x.share));
    return `<p class="cap">${esc(PNAME[proj])}: posts that raise each argument. ${esc(ARGS_BASE)}</p><div class="rows">${a.map(x =>
      `<div class="row" data-inspect="arg|${x.code}|${proj}" role="button" tabindex="0" title="Open the posts behind this count"><span class="k">${esc(ARG[x.code] || x.code)}</span><span class="track"><span class="fill" style="width:${(x.share / max) * 100}%"></span></span><span class="val">${plural(x.n, 'post', 'posts')}</span></div>`).join('')}</div>${provNote()}`;
  }

  function panelTime(proj) {
    const W = 1000, H = 220, P = { l: 8, r: 8, t: 16, b: 28 };
    const t0 = Date.UTC(2024, 9, 1), t1 = Date.parse(DATASET.end_utc);
    const X = t => P.l + (t - t0) / (t1 - t0) * (W - P.l - P.r);
    const events = (HIST && HIST.events || []).filter(e => e.project === proj && !e.after_dataset);
    let series = '', peaks = '';
    if (HAS_H) {
      // The weekly table lists only weeks with posts; fill the quiet weeks with zero so the line stays honest
      const have = new Map((HIST.weekly || []).filter(w => w.project === proj).map(w => [w.week, w.stories]));
      const wk = [];
      for (let t = Date.UTC(2024, 9, 14); t <= t1; t += 7 * 864e5) { const k = new Date(t).toISOString().slice(0, 10); wk.push({ week: k, stories: have.get(k) || 0 }); }
      const max = Math.max(1, ...wk.map(w => w.stories));
      const Y = v => H - P.b - v / max * (H - P.t - P.b);
      if (wk.length) {
        let d = `M${X(Date.parse(wk[0].week)).toFixed(1)} ${Y(0)}`;
        wk.forEach(w => { d += ` L${X(Date.parse(w.week)).toFixed(1)} ${Y(w.stories).toFixed(1)}`; });
        const area = d + ` L${X(Date.parse(wk[wk.length - 1].week)).toFixed(1)} ${Y(0)} Z`;
        series = `<path d="${area}" fill="#eef1f6"/><path d="${d.replace(/^M[^L]+/, m => m)}" fill="none" stroke="#1b2433" stroke-width="1.5" stroke-linejoin="round"/>`;
        peaks = (HIST.peaks || []).filter(k => k.project === proj && !k.weak).map(k => {
          const x = X(Date.parse(k.week)); return `<circle cx="${x}" cy="${Y(k.stories)}" r="4" fill="#3b78f0"/>`;
        }).join('');
      }
    } else {
      series = `<line x1="${P.l}" x2="${W - P.r}" y1="${H - P.b - 40}" y2="${H - P.b - 40}" stroke="#dde3ec" stroke-dasharray="4 6"/>`;
    }
    const evMarks = events.map((e, i) => {
      const x = X(Date.parse(e.date));
      return `<line x1="${x}" x2="${x}" y1="${P.t}" y2="${H - P.b}" stroke="#9aa5b5" stroke-dasharray="2 4"/><text x="${x + 4}" y="${P.t + 10}" font-size="11" fill="#5f6b7e" font-family="JetBrains Mono, monospace">${i + 1}</text>`;
    }).join('');
    const ticks = [[2024, 9], [2025, 0], [2025, 3], [2025, 6], [2025, 9], [2026, 0], [2026, 3], [2026, 6], [2026, 9]].map(([y, m]) => {
      const x = X(Date.UTC(y, m, 1)); const lab = new Date(Date.UTC(y, m, 1)).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
      return `<text x="${x}" y="${H - 8}" font-size="11" fill="#9aa5b5" text-anchor="${m === 9 && y === 2024 ? 'start' : 'middle'}">${lab}</text>`;
    }).join('');
    const svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Weekly attention for ${esc(PNAME[proj])}">
      <line x1="${P.l}" x2="${W - P.r}" y1="${H - P.b}" y2="${H - P.b}" stroke="#e3e8f1"/>${series}${evMarks}${peaks}${ticks}</svg>`;
    const list = events.length ? `<ul class="events">${events.map((e, i) => `<li><span class="d">${i + 1} · ${esc(day(e.date))}</span><span class="p">${esc(e.type === 'other' ? 'Public moment' : e.type[0].toUpperCase() + e.type.slice(1))}</span>
      <a href="${esc(e.source_url)}" target="_blank" rel="noopener">${esc(e.title)} ↗</a></li>`).join('')}</ul>` : '<p class="note">No documented events for this project in the reference list.</p>';
    return (HAS_H ? `<p class="cap">${esc(PNAME[proj])}: stories per week. Blue dots are weeks with unusual volume; numbers are documented events.</p>` : awaitingNote('The weekly volume line'))
      + svg + list;
  }

  function panelCompare() {
    if (!HAS_H) {
      return awaitingNote('The side-by-side comparison')
        + `<div class="rows">${CORE.map(id => `<div class="row ph"><span class="k">${esc(PNAME[id])}</span><span class="track"></span><span class="val">n –</span></div>`).join('')}</div>
        <p class="note">Compared on the same rules: how much is said, who speaks, and the split between support, opposition and reporting. Each project at its own stage.</p>`;
    }
    const max = Math.max(...CORE.map(id => ((HIST.projects || []).find(p => p.id === id) || {}).stories || 0));
    return `<p class="cap">Unique stories per project in the city's data, and the split among labelled posts.</p><div class="rows">${CORE.map(id => {
      const p = (HIST.projects || []).find(x => x.id === id) || {}; const s = hStance(id);
      return `<div class="row"><span class="k">${esc(PNAME[id])}</span><span class="track"><span class="fill" style="width:${(p.stories || 0) / max * 100}%"></span></span><span class="val">${nf(p.stories)}</span></div>
        <div class="row" style="margin-top:-6px"><span></span><span style="font-size:12px;color:#5f6b7e">${s ? `${s.counts.support} support · ${s.counts.oppose} oppose · ${s.counts.neutral_informative} report only (n ${s.n}${s.low_sample ? ', small' : ''})` : 'no stance labels'}</span><span></span></div>`;
    }).join('')}</div>${provNote()}`;
  }

  function faqLine() {
    const f = FACTS, bits = [];
    if (f.length_km) bits.push(`${String(f.length_km.value).replace('.', ',')} km`);
    if (f.stations) bits.push(`${f.stations.value} stations`);
    if (f.travel_time_min) bits.push(`${f.travel_time_min.value} min to the AI park`);
    if (f.cost_invest) bits.push(`${f.cost_invest.value} Mio EUR estimate`);
    return bits.length ? `<p class="meta-line"><span>${bits.map(esc).join(' · ')}</span><span class="src">City FAQ</span></p>` : '';
  }
  const FINDING_CHART = [() => panelStance(HP), () => panelArgs(HP), () => panelTime(HP), () => panelVoice(HP), () => ''];
  function openFinding(i) {
    const f = FINDINGS[i], a = HAS_H ? f.answer() : null;
    if (!a) {
      openInfo(f.q, HAS_H ? `${CITY[HP]} · not measured for this project` : `Finding 0${i + 1} · awaiting the final run`,
        `<p class="cap">${HAS_H ? 'This test was not run for ' + esc(PNAME[HP]) + ' in the final analysis.' : 'It will show: ' + esc(f.measures) + '.'} Why it matters: ${esc(f.why)}</p>${FINDING_CHART[i]()}`);
      return;
    }
    const ev = f.evidence();
    const posts = HIST.posts.filter(ev.filter);
    openPosts(ev.title, f.q, posts, findingCard(f, a, posts) + `<div class="dbody0">${FINDING_CHART[i]()}</div>`);
  }
  function panelVoice(proj) {
    const voices = ['citizen', 'news_institutional', 'politician_official'];
    const rows = voices.map(v => {
      const s = hStance(proj, v);
      if (!s) return `<div class="row"><span class="k">${esc(VOICE[v])}</span><span class="track"></span><span class="val">n –</span></div>`;
      const side = (s.counts.support + s.counts.oppose) / Math.max(1, s.n);
      return `<div class="row"><span class="k">${esc(VOICE[v])}</span><span class="track"><span class="fill" style="width:${side * 100}%"></span></span><span class="val">${s.counts.support} for · ${s.counts.oppose} against · n ${s.n}</span></div>`;
    }).join('');
    return `<p class="cap">${esc(PNAME[proj])}: share of each speaker group that takes a side.</p><div class="rows">${rows}</div>${provNote()}`;
  }

  /* ---------- 03 today ---------- */
  const hhmm = iso => iso ? new Date(iso).toLocaleTimeString('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }) : '';
  function receiptSteps(m) {
    if (!m) return [];
    const runIso = runIdToIso(m.collect_run_id), u = m.usage || {}, probs = m.sources_problems || [];
    const dated = LITEMS.filter(i => i.date_known).length;
    const asked = (m.sources_clean || []).filter(x => x !== 'date_recovery').length;
    const reused = /no new scan/i.test(m.collect_note || '');
    return [
      { nm: 'Ask every source', ds: `${asked} answered${probs.length ? ', partly: ' + probs.join(', ') : ''}`, src: hhmm(runIso), st: probs.length ? 'warn' : 'done' },
      { nm: 'Search since 27 Oct', ds: `${nf(m.counts.strong)} strong matches${reused ? ', from the scan at ' + hhmm(runIso) : ''}`, src: hhmm(runIso), st: 'done' },
      { nm: 'Keep what is new, with its date', ds: `${nf(m.counts.new_this_update)} new since the last check · ${nf(dated)} dated`, src: hhmm(m.generated_at), st: 'done' },
      { nm: 'Read each new item', ds: `${nf(m.counts.labelled_this_update || 0)} read now · ${nf(m.counts.with_label)} read so far${u.usd ? ' · ' + u.usd.toFixed(2) + ' USD' : ''}`, src: hhmm(m.generated_at), st: 'done' },
      { nm: 'Run the analysis', ds: 'Checked in a test copy', src: hhmm(m.generated_at), st: 'done' },
      { nm: 'Write the dated report', ds: 'Saved, every item with its link', src: hhmm(m.generated_at), st: 'done' }
    ].concat((() => {   // step 7: the argument engine reads the new dated items (its own run record, not the receipt)
      const r = (typeof EN !== 'undefined' && EN && EN.has && EN.has()) ? EN.collectorRuns().find(x => /^done/.test(x.status)) : null;
      if (!r) return [];
      const c = r.counts || {};
      return [{ nm: 'Match the arguments', ds: `${plural(c.claims || 0, 'claim', 'claims')} · ${nf(c.familiar || 0)} known · ${nf(c.new || 0)} new · ${nf(c.ambiguous || 0)} to review`, src: hhmm(r.finished_at || r.created_at), st: 'done' }];
    })());
  }
  function stepHtml(s) {
    return `<li class="step ${s.st}"><span class="ck"></span><div><div class="nm">${esc(s.nm)}</div><div class="ds">${esc(s.ds)}</div></div><span class="tm">${esc(s.src)}</span></li>`;
  }

  /* ================= home + three focused reports ================= */
  const ANS = i => (HAS_H ? FINDINGS[i].answer() : null);
  function head(title, i) {
    const a = i == null ? null : ANS(i);
    const first = t => (t.match(/^.*?\.(\s|$)/) || [t])[0].trim();
    const ans = i == null ? '' : (a ? `<p class="ans">${esc(first(a.t))}</p>` : `<p class="ans wait">${HAS_H ? 'Not measured for ' + esc(CITY[HP]) : 'Awaiting final run'}</p>`);
    const more = i == null ? '' : `<button class="more" type="button" data-finding="${i}" aria-label="Evidence for ${esc(title)}">Evidence</button>`;
    return `<header class="ch"><h3>${esc(title)}</h3>${more}</header>${ans}`;
  }
  const SEG = { support: 'Support', oppose: 'Oppose', neutral_informative: 'Report only' };
  function stack(counts, n, big) {
    // one 100% bar: support (accent), oppose (ink), report only (light); the rest is mixed or unclear
    const w = k => (n ? (counts[k] || 0) / n * 100 : 0);
    return `<div class="stack${big ? ' big' : ''}"><i class="s1" style="width:${w('support')}%"></i><i class="s2" style="width:${w('oppose')}%"></i><i class="s3" style="width:${w('neutral_informative')}%"></i></div>`;
  }
  const skel = (w, h) => `<span class="sk" style="width:${w}${typeof w === 'number' ? 'px' : ''};height:${h || 10}px"></span>`;

  /* ---------- History: the city's data ---------- */
  function renderSoFar() {
    const s = hStance(HP);
    const stance = s ? `${stack(s.counts, s.n, true)}
        <div class="legend3">${Object.keys(SEG).map((k, j) => `<div><span class="dot d${j + 1}"></span><b>${nf(s.counts[k] || 0)}</b>${SEG[k]}</div>`).join('')}</div>
        <p class="foot">${nf(s.n)} labelled posts${s.low_sample ? ', small sample' : ''}</p>`
      : `${`<div class="stack big sk-stack"></div>`}<div class="legend3">${Object.keys(SEG).map((k, j) => `<div><span class="dot d${j + 1}"></span>${skel(26, 18)}${SEG[k]}</div>`).join('')}</div>`;

    const args = hArgs(HP).slice(0, 5);
    const amax = Math.max(0.01, ...args.map(a => a.share));
    const argRows = args.length ? args.map(a => `<li><span>${esc(ARG[a.code] || a.code)}</span><span class="bar"><i style="width:${a.share / amax * 100}%"></i></span><b>${nf(a.n)}</b></li>`).join('')
      : ['cost', 'traffic_mobility', 'climate_environment', 'tourism_image', 'cityscape_design'].map((k, j) => `<li><span>${ARG[k]}</span><span class="bar">${skel((90 - j * 14) + '%', 8)}</span><b>${skel(14, 10)}</b></li>`).join('');

    const voices = ['citizen', 'news_institutional', 'politician_official'];
    const voiceRows = voices.map(v => {
      const x = hStance(HP, v);
      return `<li><span>${esc(VOICE[v])}</span>${x ? stack(x.counts, x.n) : '<div class="stack sk-stack"></div>'}<b>${x ? plural(x.n, 'post', 'posts') : skel(22, 10)}</b></li>`;
    }).join('');

    const tone = hRel('vendor_vs_stance.match');
    const toneTile = tone ? `<div class="kpi tone"><b>${pct(tone.value)}</b><span class="bar"><i style="width:${Math.round(tone.value * 100)}%"></i></span><span>of ${nf(tone.n)} posts, all projects: tone matched the stance</span></div>`
      : '';

    // evidence: posts that take a side (pilot or final), or the documented events before the run is in
    let evid;
    if (HAS_H) {
      const ps = HIST.posts.filter(p => p.project === HP && (p.stance === 'support' || p.stance === 'oppose')).sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 4);
      evid = ps.map(p => `<li><span class="d">${esc(day(p.date))}</span><span class="tt">${esc(clean(p.title) || (p.media_type || 'Post') + ' on ' + (p.source || ''))}</span><span class="tag st-${esc(p.stance)}">${esc(STANCE[p.stance])}</span></li>`).join('');
    } else {
      const ev = (HIST && HIST.events || []).filter(e => e.project === HP && !e.after_dataset).slice(-4).reverse();
      evid = ev.map(e => `<li><span class="d">${esc(day(e.date))}</span><a class="tt" href="${esc(e.source_url)}" target="_blank" rel="noopener">${esc(e.title)}</a></li>`).join('');
    }
    const tag = MODE === 'pilot' ? '<span class="tag blue">Pilot, provisional</span>' : '';
    if (!HAS_H) { renderSoFarAwaiting(); return; }
    $('#history').innerHTML = `
      <div class="sh-head"><h2 id="history-h">Two years of debate.</h2>
        <nav class="cityswitch" aria-label="Project">${HCITIES.map(id => `<button type="button" data-city="${id}" class="${id === HP ? 'on' : ''}" aria-pressed="${id === HP}">${esc(CITY_TAB[id])}</button>`).join('')}</nav>
        <div class="sh-meta">${tag}<span>${nf(DATASET.records)} records</span><span>Oct 2024 – Oct 2026</span></div></div>
      <p class="promise" title="${esc(sentenceUp(AD.labelStatus()))}">${MODE === 'final' ? 'AI readings, not checked by people: one per post, a vote of four on the 240 pilot posts.' : esc(sentenceUp(AD.labelStatus()))}</p>
      <div class="grid g-sofar">
        <article class="card a1">${head('Who takes a side', 0)}${stance}</article>
        <article class="card a2">${head('What is raised', 1)}<ul class="bars">${argRows}</ul></article>
        <article class="card a3">${head('Who speaks', 3)}<ul class="vrows">${voiceRows}</ul><div class="key3"><span><i class="d1"></i>Support</span><span><i class="d2"></i>Oppose</span><span><i class="d3"></i>Report only</span></div></article>
        <article class="card a4">${head('When attention rises', 2)}<div class="tchart">${timeChart(HP)}</div></article>
        <article class="card a5">${tone ? `<header class="ch"><h3>Tone test</h3><button class="more" type="button" data-finding="4">Evidence</button></header><p class="ans">${tone.value < 0.5 ? 'Tone is not stance.' : 'Tone partly tracks stance.'}</p>` : head('Tone test', 4)}${toneTile}</article>
        <article class="card a6"><header class="ch"><h3>Evidence</h3><button class="more" type="button" data-finding="${HAS_H ? 0 : 2}">All</button></header><ul class="elist">${evid}</ul></article>
      </div>`;
    $('#history').onclick = e => {
      const c = e.target.closest('[data-city]');
      if (c) { if (c.dataset.city !== HP) { HP = c.dataset.city; renderSoFar(); const nb = $(`#history [data-city="${HP}"]`); if (nb) nb.focus(); } return; }
      const b = e.target.closest('[data-finding]'); if (b) openFinding(+b.dataset.finding);
    };
  }
  // Before the final run: the documented moments on a real time axis, their sources, and the four questions still open.
  const SHORT = {
    hn_2025_03_27_plans: 'Plans go public', hn_2025_04_03_council: 'Council: start planning', hn_2025_05_12_state: 'State: 4 M EUR to plan',
    hn_2025_07_17_critics: 'Critics: tram instead', hn_2026_07_22_cost: '157 M EUR estimate', hn_2026_07_27_council: 'Council: hire planners'
  };
  const shortOf = e => SHORT[e.event_id] || (e.project === 'paris_c1' ? (e.type === 'opening' ? 'C1 opens' : 'Opening date set') : (e.title.length > 26 ? e.title.slice(0, 24) + '…' : e.title));
  function momentsChart() {
    const W = 1200, H = 250, X0 = 96, X1 = W - 16;
    const t0 = Date.UTC(2024, 9, 1), t1 = Date.parse(DATASET.end_utc);
    const X = t => X0 + (t - t0) / (t1 - t0) * (X1 - X0);
    const ev = p => (HIST && HIST.events || []).filter(e => e.project === p && !e.after_dataset).sort((a, b) => a.date.localeCompare(b.date));
    const hn = ev('heilbronn_cablecar'), pa = ev('paris_c1');
    const yH = 168, yP = 206, yT = 240;
    // labels above the Heilbronn lane, each in the lowest row where it does not collide
    const rowY = [124, 80, 36];
    // Each label sits in one of three rows, right or left of its leader line. The layout with the lowest rows and
    // fewest left labels is chosen such that no label covers another label or another event's leader line.
    const L = hn.map(e => ({ e, x: X(Date.parse(e.date)), w: shortOf(e).length * 7.4 + 14 }));
    const opts = L.map(l => [0, 1, 2].flatMap(r => [false, true].map(left => ({ r, left, a: left ? l.x - l.w : l.x - 4, b: left ? l.x + 4 : l.x + l.w })))
      .filter(o => o.a >= 0 && o.b <= W));
    const clash = (i, o, j, q) => (o.r === q.r && !(o.b + 6 < q.a || q.b + 6 < o.a))
      || (q.r > o.r && L[j].x > o.a - 3 && L[j].x < o.b + 3) || (o.r > q.r && L[i].x > q.a - 3 && L[i].x < q.b + 3);
    let best = null, bestCost = Infinity;
    (function dfs(i, pick, cost) {
      if (cost >= bestCost) return;
      if (i === L.length) { best = pick.slice(); bestCost = cost; return; }
      opts[i].forEach(o => {
        if (pick.every((q, j) => !clash(i, o, j, q))) { pick.push(o); dfs(i + 1, pick, cost + o.r * 2 + (o.left ? 1 : 0)); pick.pop(); }
      });
    })(0, [], 0);
    const labels = L.map((l, i) => { const o = best ? best[i] : { r: i % 3, left: false }; return { e: l.e, x: l.x, y: rowY[o.r], left: o.left }; });
    const tick = [[2024, 9], [2025, 0], [2025, 3], [2025, 6], [2025, 9], [2026, 0], [2026, 3], [2026, 6], [2026, 9]].map(([y, m]) => {
      const x = X(Date.UTC(y, m, 1));
      return `<line x1="${x}" x2="${x}" y1="${yH + 6}" y2="${yT - 12}" stroke="#eef1f5"/><text x="${x}" y="${yT}" font-size="11" fill="#98a3b3" text-anchor="middle">${new Date(Date.UTC(y, m, 1)).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })}</text>`;
    }).join('');
    const dm = d => new Date(d + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    const hnMarks = labels.map(({ e, x, y, left }) => `<a href="${esc(e.source_url)}" target="_blank" rel="noopener"><title>${esc(day(e.date))}: ${esc(e.title)}</title>
        <line x1="${x}" x2="${x}" y1="${y + 8}" y2="${yH - 7}" stroke="#3b78f0" stroke-opacity=".35"/>
        <text x="${left ? x - 8 : x + 8}" y="${y - 6}" text-anchor="${left ? 'end' : 'start'}" font-size="10.5" fill="#98a3b3" font-family="JetBrains Mono, monospace">${esc(dm(e.date))}</text>
        <text x="${left ? x - 8 : x + 8}" y="${y + 9}" text-anchor="${left ? 'end' : 'start'}" font-size="13" font-weight="600" fill="#17202e">${esc(shortOf(e))}</text>
        <circle cx="${x}" cy="${y + 4}" r="2.5" fill="#3b78f0"/>
        <circle cx="${x}" cy="${yH}" r="6" fill="#3b78f0" stroke="#fff" stroke-width="2"/></a>`).join('');
    const paMarks = pa.map(e => { const x = X(Date.parse(e.date)); return `<a href="${esc(e.source_url)}" target="_blank" rel="noopener"><title>${esc(day(e.date))}: ${esc(e.title)}</title>
        <circle cx="${x}" cy="${yP}" r="5" fill="#fff" stroke="#5c6779" stroke-width="1.6"/><text x="${x + 10}" y="${yP + 4}" font-size="12" fill="#5c6779">${esc(e.type === 'opening' ? 'Opens' : 'Date set')}</text></a>`; }).join('');
    return `<svg viewBox="0 0 ${W} ${H}" class="chart moments" role="img" aria-label="Documented moments for Heilbronn's cable car, with Paris Câble C1 for comparison">
      ${tick}
      <text x="0" y="${yH + 4}" font-size="11" font-weight="600" letter-spacing="1" fill="#5c6779">HEILBRONN</text>
      <text x="0" y="${yP + 4}" font-size="11" font-weight="600" letter-spacing="1" fill="#98a3b3">PARIS C1</text>
      <line x1="${X0}" x2="${X1}" y1="${yH}" y2="${yH}" stroke="#d5dce6" stroke-width="1.5"/>
      <line x1="${X0}" x2="${X1}" y1="${yP}" y2="${yP}" stroke="#e6eaf0" stroke-dasharray="3 5"/>
      ${paMarks}${hnMarks}</svg>`;
  }
  function renderSoFarAwaiting() {
    const hn = (HIST && HIST.events || []).filter(e => e.project === 'heilbronn_cablecar' && !e.after_dataset).sort((a, b) => b.date.localeCompare(a.date));
    const src = hn.map(e => `<li><span class="d">${esc(day(e.date))}</span><a class="tt" href="${esc(e.source_url)}" target="_blank" rel="noopener">${esc(e.title)}</a><span class="tag">${esc(host(e.source_url))}</span></li>`).join('');
    const qs4 = [[0, 'Who takes a side'], [1, 'What is raised'], [3, 'Who speaks'], [4, 'Tone vs position']];
    $('#history').innerHTML = `
      <div class="sh-head"><h2 id="history-h">Two years of debate.</h2><div class="sh-meta"><span>${nf(DATASET.records)} records</span><span>Oct 2024 – Oct 2026</span></div></div>
      <div class="grid g-wait">
        <article class="card m1"><header class="ch"><h3>${hn.length ? `${hn.length} moments` : 'Moments'}</h3><span class="r">documented, with sources</span></header><div class="tchart">${momentsChart()}</div></article>
        <article class="card m2"><header class="ch"><h3>Sources</h3></header><ul class="elist">${src}</ul></article>
        <article class="card m3"><header class="ch"><h3>Final analysis</h3><span class="r pend"><i></i>Pending</span></header>
          <ul class="qlist">${qs4.map(([i, q]) => `<li><button type="button" data-finding="${i}"><span>${esc(q)}</span><span class="ghost"></span><span class="ar">→</span></button></li>`).join('')}</ul></article>
      </div>`;
    $('#history').onclick = e => { const b = e.target.closest('[data-finding]'); if (b) openFinding(+b.dataset.finding); };
  }
  // Places short labels in rows above their leader lines: no label covers another label or another leader line.
  // A small exhaustive search; there are at most a handful of documented moments per project.
  function placeLabels(L, W, nRows) {
    const opts = L.map(l => Array.from({ length: nRows }, (_, r) => r).flatMap(r => [false, true].map(left => ({ r, left, a: left ? l.x - l.w : l.x - 4, b: left ? l.x + 4 : l.x + l.w })))
      .filter(o => o.a >= 0 && o.b <= W));
    const clash = (i, o, j, q) => (o.r === q.r && !(o.b + 6 < q.a || q.b + 6 < o.a))
      || (q.r > o.r && L[j].x > o.a - 3 && L[j].x < o.b + 3) || (o.r > q.r && L[i].x > q.a - 3 && L[i].x < q.b + 3);
    let best = null, bestCost = Infinity;
    (function dfs(i, pick, cost) {
      if (cost >= bestCost) return;
      if (i === L.length) { best = pick.slice(); bestCost = cost; return; }
      opts[i].forEach(o => { if (pick.every((q, j) => !clash(i, o, j, q))) { pick.push(o); dfs(i + 1, pick, cost + o.r * 2 + (o.left ? 1 : 0)); pick.pop(); } });
    })(0, [], 0);
    return L.map((l, i) => best ? best[i] : { r: i % nRows, left: false });
  }
  function timeChart(proj) {
    const W = 760, H = 216, P = { l: 4, r: 4, t: 76, b: 22 };
    const t0 = Date.UTC(2024, 9, 1), t1 = Date.parse(DATASET.end_utc);
    const X = t => P.l + (t - t0) / (t1 - t0) * (W - P.l - P.r);
    const events = (HIST && HIST.events || []).filter(e => e.project === proj && !e.after_dataset).sort((a, b) => a.date.localeCompare(b.date));
    let series = '';
    if (HAS_H) {
      const wk = AD.weekly(proj, DATASET.end_utc), max = Math.max(1, ...wk.map(w => w.stories));
      const Y = v => H - P.b - v / max * (H - P.t - P.b);
      let d = `M${X(Date.parse(wk[0].week)).toFixed(1)} ${Y(0)}`;
      wk.forEach(w => { d += ` L${X(Date.parse(w.week)).toFixed(1)} ${Y(w.stories).toFixed(1)}`; });
      series = `<path d="${d} L${X(Date.parse(wk[wk.length - 1].week)).toFixed(1)} ${Y(0)} Z" fill="rgba(59,120,240,.10)"/><path d="${d}" fill="none" stroke="#3b78f0" stroke-width="1.6" stroke-linejoin="round"/>`;
    } else {
      series = `<path d="M${P.l} ${H - P.b - 30} L${W - P.r} ${H - P.b - 30}" stroke="#d9dfe7" stroke-dasharray="3 6"/>`;
    }
    const rowY = [62, 44, 26, 8];
    // moments less than ten days apart share one marker, so their leader lines never sit on top of each other
    const groups = [];
    events.forEach(e => { const g = groups[groups.length - 1]; if (g && Date.parse(e.date) - Date.parse(g[g.length - 1].date) < 10 * 864e5) g.push(e); else groups.push([e]); });
    const L = groups.map(g => { const txt = g.map(shortOf).join(' · '); return { e: g[0], g, txt, x: X(Date.parse(g[0].date)), w: txt.length * 6.4 + 12 }; });
    const pick = placeLabels(L, W, rowY.length);
    const marks = L.map((l, i) => { const o = pick[i], y = rowY[o.r], tx = o.left ? l.x - 6 : l.x + 6;
      return `<a href="${esc(l.e.source_url)}" target="_blank" rel="noopener"><title>${l.g.map(e => esc(day(e.date)) + ': ' + esc(e.title)).join('&#10;')}</title>
        <line x1="${l.x}" x2="${l.x}" y1="${y + 4}" y2="${H - P.b}" stroke="#17202e" stroke-opacity=".18"/>
        <circle cx="${l.x}" cy="${y}" r="2.5" fill="#17202e"/>
        <text x="${tx}" y="${y + 4}" text-anchor="${o.left ? 'end' : 'start'}" font-size="11" font-weight="600" fill="#2c3647">${esc(l.txt)}</text></a>`; }).join('');
    const ticks = [[2025, 0, 'Jan 2025'], [2025, 6, 'Jul 2025'], [2026, 0, 'Jan 2026'], [2026, 6, 'Jul 2026']].map(([y, m, l]) => `<text x="${X(Date.UTC(y, m, 1))}" y="${H - 6}" font-size="10.5" fill="#98a3b3" text-anchor="middle">${l}</text>`).join('');
    return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Weekly attention for ${esc(PNAME[proj])}, with documented moments"><line x1="${P.l}" x2="${W - P.r}" y1="${H - P.b}" y2="${H - P.b}" stroke="#e3e8f0"/>${series}${marks}${ticks}</svg>`;
  }

  /* ---------- So far: after the city's data ended ---------- */
  function renderNow() {
    if (!LM) { $('#since').innerHTML = `<div class="sh-head"><h2 id="since-h">Since the city's data ended.</h2></div><div class="grid"><article class="card"><p class="ans wait">No check has run yet.</p></article></div>`; return; }
    const coreItems = LITEMS.filter(i => CORE.includes(i.radar_project));
    const after = coreItems.filter(i => i.date_class === 'after');
    // daily trend: items published after the city's data ended, per day, Heilbronn cable car in accent
    const d0 = Date.UTC(2026, 9, 27), d1 = Date.parse(LM.generated_at);
    const days = []; for (let t = d0; t <= d1; t += 864e5) days.push(new Date(t).toISOString().slice(0, 10));
    const per = days.map(dd => ({ dd, all: after.filter(i => i.date === dd).length, hn: after.filter(i => i.date === dd && i.radar_project === 'heilbronn_cablecar').length }));
    const mx = Math.max(1, ...per.map(p => p.all));
    const W = 760, H = 170, bw = (W - 8) / days.length;
    const bars = per.map((p, k) => {
      const x = 4 + k * bw, h1 = p.all / mx * (H - 34), h2 = p.hn / mx * (H - 34);
      return `<rect x="${(x + 2).toFixed(1)}" y="${(H - 20 - h1).toFixed(1)}" width="${(bw - 4).toFixed(1)}" height="${h1.toFixed(1)}" rx="3" fill="#cfd7e2"><title>${p.dd}: ${p.all} items</title></rect>`
        + (p.hn ? `<rect x="${(x + 2).toFixed(1)}" y="${(H - 20 - h2).toFixed(1)}" width="${(bw - 4).toFixed(1)}" height="${h2.toFixed(1)}" rx="3" fill="#3b78f0"/>` : '');
    }).join('');
    const lab = per.filter((p, k) => k % 4 === 0).map(p => `<text x="${(4 + days.indexOf(p.dd) * bw + bw / 2).toFixed(1)}" y="${H - 4}" font-size="10.5" fill="#98a3b3" text-anchor="middle">${new Date(p.dd + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</text>`).join('');
    const trend = `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Items published per day since 27 October">${bars}${lab}</svg>`;

    // source mix of the core items
    const kinds = {}; coreItems.forEach(i => { const k = KIND[i.kind] || i.kind; kinds[k] = (kinds[k] || 0) + 1; });
    const kl = Object.entries(kinds).sort((a, b) => b[1] - a[1]).slice(0, 6), km = Math.max(1, ...kl.map(k => k[1]));
    const src = kl.map(([k, v]) => `<li><span>${esc(k)}</span><span class="bar"><i style="width:${v / km * 100}%"></i></span><b>${nf(v)}</b></li>`).join('');

    const proj = CORE.map(id => {
      const p = pp(id), tot = p.d_after + p.d_late + p.d_unknown || 1;
      return `<li><button type="button" data-proj="${id}"><span class="pn">${esc(PNAME[id])}</span><span class="pb"><i class="a" style="width:${p.d_after / tot * 100}%"></i><i class="b" style="width:${p.d_late / tot * 100}%"></i><i class="c" style="width:${p.d_unknown / tot * 100}%"></i></span><b>${nf(p.d_after)}</b></button></li>`;
    }).join('');
    const onTopic = after.filter(i => i.label_state !== 'labelled' || i.llm_project === i.radar_project);
    const latest = onTopic.slice().sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 5).map(i => `<li><span class="d">${esc(day(i.date))}</span><span class="tt">${esc(clean(i.title) || (KIND[i.kind] || 'Item') + ' on ' + (i.source || ''))}</span><span class="tag">${esc((PNAME[i.radar_project] || '').replace(' cable car', ''))}</span></li>`).join('');
    const hn = pp('heilbronn_cablecar');
    const others = {}; LITEMS.forEach(i => { if (!CORE.includes(i.radar_project) && i.date_class === 'after') others[i.radar_project] = (others[i.radar_project] || 0) + 1; });
    const otherRow = Object.entries(others).sort((a, b) => b[1] - a[1]).map(([id, n]) => `<button type="button" data-proj="${esc(id)}">${esc(PNAME[id] || id)}<b>${nf(n)}</b></button>`).join('');
    $('#since').innerHTML = `
      <div class="sh-head"><h2 id="since-h">Since the city's data ended.</h2><div class="sh-meta"><span>Since 27 Oct 2026</span><span>Sources checked ${esc(when(SCAN_ISO() || LM.generated_at, true))}</span></div></div>
      <div class="grid g-now">
        <article class="card k1"><div class="kpi"><b>${nf(sumCore('d_after'))}</b><span>new items</span></div></article>
        <article class="card k2"><div class="kpi"><b class="acc">${nf(hn.d_after)}</b><span>about Heilbronn's cable car</span></div></article>
        <article class="card k3"><div class="kpi"><b>${nf(sumCore('d_late'))}</b><span>older, found late</span></div></article>
        <article class="card k4"><div class="kpi"><b class="muted">${nf(sumCore('d_unknown'))}</b><span>undated, not counted</span></div></article>
        <article class="card b1"><header class="ch"><h3>New per day</h3><span class="key"><i class="kb"></i>Heilbronn<i class="kg"></i>all four projects</span></header>${trend}</article>
        <article class="card b2"><header class="ch"><h3>Where from</h3></header><ul class="bars">${src}</ul></article>
        <article class="card c1"><header class="ch"><h3>By project</h3><span class="key"><i class="ka"></i>new<i class="kl"></i>late<i class="ku"></i>undated</span></header><ul class="plist">${proj}</ul>${otherRow ? `<div class="others"><span>Other cities</span><div>${otherRow}</div></div>` : ''}</article>
        <article class="card c2"><header class="ch"><h3>Latest</h3><button class="more" type="button" data-proj="heilbronn_cablecar">All</button></header><ul class="elist">${latest}</ul></article>
      </div>`;
    $('#since').onclick = e => {
      const b = e.target.closest('[data-proj]');
      if (b) { const id = b.dataset.proj; openLive(PNAME[id] || id, `Found since ${day(LM.since)}`, LITEMS.filter(it => it.radar_project === id)); }
    };
  }

  /* ---------- Today: the live check ---------- */
  const ALL_SOURCES = ['rss', 'pagewatch', 'oparl', 'exa', 'tavily', 'youtube', 'bluesky', 'mastodon'];
  function renderToday() {
    const m = LM, steps = receiptSteps(m);
    const clean = m ? m.sources_clean || [] : [], probs = m ? (m.sources_problems || []).map(s => s.split(' ')[0]) : [];
    const srcRows = ALL_SOURCES.map(s => {
      const st = probs.includes(s) ? ['warn', 'partly'] : clean.includes(s) ? ['ok', 'answered'] : ['off', 'not run'];
      return `<li><span class="sd ${st[0]}"></span><span>${esc(SOURCE[s] || s)}</span><em>${st[1]}</em></li>`;
    }).join('');
    // out of reach for good (closed platforms, paywalls, no export); partial limits such as YouTube's search quota stay in the "Why" drawer
    const gaps = (m ? m.coverage_gaps || [] : []).filter(g => /^NOT COVERED BY DESIGN/.test(g)).map(g => g.replace(/^NOT COVERED BY DESIGN:\s*/, '')).map(g => { const i = g.indexOf(':'); return i > 0 ? g.slice(0, i) : g; })
      .filter(g => !/^(YouTube|GDELT|Google News)/.test(g));
    $('#today').innerHTML = `
      <div class="sh-head"><h2 id="today-h">What's new today.</h2><div class="sh-meta"><span>${m ? 'Sources checked ' + esc(when(SCAN_ISO() || m.generated_at, true)) : 'No check yet'}</span></div></div>
      <div class="grid g-today">
        <article class="card t1 runcard"><h3>Today's check</h3><button class="btn dark xl" id="btnUpdate" type="button">Run it now</button>
          <p class="hint" id="runHint"></p><button class="lnk" id="btnReplay" type="button">Replay the last check</button></article>
        <article class="card t2" id="run"><header class="ch"><h3 id="runTitle">Every step</h3><span class="r" id="runWhen"></span></header>
          <ol class="steps" id="steps">${steps.map(stepHtml).join('')}</ol><pre class="log" id="runLog"></pre></article>
        <article class="card t3"><header class="ch"><h3>Sources</h3></header><ul class="slist">${srcRows}</ul></article>
        <article class="card t4"><header class="ch"><h3>Out of reach</h3><button class="more" type="button" data-gaps>Why</button></header><ul class="glist">${gaps.slice(0, 5).map(g => `<li>${esc(g)}</li>`).join('')}</ul></article>
      </div>`;
    $('#today').onclick = e => { if (e.target.closest('[data-gaps]')) openGaps(); };
    setupRun(steps);
  }

  /* ---------- Human review: the argument engine (frozen into app/data/engine.js) ---------- */
  const EN = AD.engine;
  const CSTATE = { new_emerging: 'New, raised by several voices', new_single: 'New, one voice so far', ambiguous: 'Needs review',
    gaining: 'Known argument, raised more often', recurring: 'Known argument, came up again' };
  const POL = { pro: 'for', contra: 'against', neutral: 'no side', mixed: 'mixed' };
  const CHANNEL = { news: 'News', social: 'Social media', other_web: 'Web' };
  const RELATION = { unscored: 'First claim of the group', equivalent: 'Same argument', related: 'Related argument' };
  const REFNAME = { opus: 'Claude Opus' };
  const sentence = s => { s = String(s || '').trim(); return s ? s[0].toUpperCase() + s.slice(1) + (/[.!?]$/.test(s) ? '' : '.') : ''; };
  const f2 = x => Number(x).toFixed(2);
  const polLine = p => Object.entries(p || {}).filter(([, v]) => v).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${nf(v)} ${POL[k] || k}`).join(', ');
  const CMAP = new Map();      // every concern the page shows, by id, for the drawers
  function concernItem(c) {
    CMAP.set(c.id, c);
    const st = c.flagged ? `<span class="tag blue">Flagged ${esc(day(c.flagged_at))}</span>` : `<span class="tag">${esc(CSTATE[c.state] || c.state)}</span>`;
    return `<button class="citem" type="button" data-concern="${esc(c.id)}" aria-label="Open the posts behind: ${esc(c.label)}">
      <span class="cst">${st}<span class="pol" title="${esc(polLine(c.polarity))}">${esc(polLine(c.polarity).split(', ')[0])}</span><span class="cgo">Posts →</span></span>
      <b class="cl">${esc(c.label)}</b>
      <span class="cnum"><span><b>${nf(c.n_claims)}</b> claims</span><span><b>${nf(c.n_voices)}</b> independent voices</span><span>first seen ${esc(day(c.first_seen))}</span></span>
      ${c.flagged ? `<span class="cstate">${esc(CSTATE[c.state] || c.state)}</span>` : ''}</button>`;
  }
  let ELSE_IDS = [], LATE_IDS = [], SINCE_R = '';
  function renderArgs() {
    const el = $('#review');
    const headHtml = meta => `<div class="sh-head"><h2 id="review-h">Human review needed.</h2><div class="sh-meta">${meta}</div></div>
      <p class="promise">New or unclear arguments go to a person, with their posts.</p>`;
    if (!EN || !EN.has()) {
      el.innerHTML = headHtml('') + `<div class="grid"><article class="card"><p class="ans wait">The argument engine's results are not on this page yet.</p><p class="foot">They appear with the next engine snapshot.</p></article></div>`;
      return;
    }
    SINCE_R = '';
    const st = EN.status(), rp = EN.replay(), cs = EN.concerns(), fl = cs.filter(c => c.flagged), kb = EN.knownBefore(), mt = EN.matcher(), runs = EN.collectorRuns();
    const taken = EN.takenAt();
    const meta = `<span>Heilbronn</span>${taken ? `<span>Snapshot ${esc(when(taken, true))}</span>` : ''}`;
    const cut = rp && rp.cutoff ? day(rp.cutoff) : 'the cut-off';

    // b. the replay strip
    let replay;
    if (rp) {
      const k = rp.counts;
      const seg = [['f', k.familiar, 'matched a known argument'], ['j', k.joins_new, 'joined a new group'], ['o', k.opens_new, 'opened a new group'], ['a', k.ambiguous, 'need review']];
      replay = `<header class="ch"><h3>Replay</h3><span class="tag" title="${/cache/.test(rp.mode) ? 'Historical replay with cached model scores, not a live detection' : 'Historical replay, not a live detection'}">Replay, not live</span></header>
        <p class="ans">Frozen on ${esc(cut)}, then the next ${nf(k.n_claims)} Heilbronn claims arrived in their real order.</p>
        <div class="rstrip" role="img" aria-label="${seg.map(s => `${s[1]} ${s[2]}`).join(', ')}">${seg.map(s => s[1] ? `<i class="${s[0]}" style="flex:${s[1]}"></i>` : '').join('')}</div>
        <div class="rlegend">${seg.map(s => `<div><span class="sw ${s[0]}"></span><b>${nf(s[1])}</b><span>${s[2]}</span></div>`).join('')}
          <div class="rflag"><b>${nf(k.flagged)}</b><span>flagged by ${nf(EN.MIN_VOICES)}+ independent voices</span></div></div>`;
    } else replay = `<header class="ch"><h3>Replay</h3></header><p class="ans wait">The replay is not in this snapshot.</p>`;

    // c. concern cards, flagged first
    const shown = (fl.length ? fl : cs).slice(0, 3);
    const concernsHtml = `<header class="ch"><h3>${fl.length ? 'Flagged after the cut-off' : 'New groups after the cut-off'}</h3>${cs.length ? `<button class="more" type="button" data-allc>All ${nf(cs.length)} groups</button>` : ''}</header>
      ${shown.length ? `<div class="clist">${shown.map(concernItem).join('')}</div>` : '<p class="ans wait">No new groups in this replay.</p>'}
      ${!fl.length && cs.length ? '<p class="foot">None was flagged: no new group was raised by enough independent voices.</p>' : ''}`;
    cs.forEach(c => CMAP.set(c.id, c));

    // d. main arguments before the cut-off
    let famHtml = '<p class="ans wait">Not in this snapshot.</p>';
    if (kb) {
      const top = kb.top.slice(0, 4), mx = Math.max(1, ...top.map(f => f.n));
      famHtml = `<ul class="famlist">${top.map(f => `<li><span class="fn" title="${esc(f.name)}">${esc(f.name)}</span><b>${nf(f.n)}</b><span class="bar"><i style="width:${f.n / mx * 100}%"></i></span></li>`).join('')}</ul>
        <p class="foot">Claims per argument${kb.n_claims != null && kb.n_posts != null ? `, from ${nf(kb.n_claims)} claims in ${nf(kb.n_posts)} Heilbronn posts` : ''}. One post can make several claims.</p>`;
    }

    // e. since the collector: runs fed from the live collector into the engine
    let sinceHtml;
    const doneRuns = runs.filter(r => /^done/.test(r.status));
    if (!runs.length) {
      sinceHtml = `<p class="ans quiet">No collector run has reached the engine yet.</p>
        <p class="sub">New concerns after 27 Oct appear here when it does, each with its posts. Items found since then are in So far.</p>`;
    } else if (!doneRuns.length) {
      const r = runs[0];
      sinceHtml = `<p class="ans quiet">The latest collector run ${r.status === 'failed' ? 'failed' : 'is not finished'} (${esc(when(r.created_at, true))}).</p><p class="sub">Nothing from it is shown. The replay above is unchanged.</p>`;
    } else {
      // Date honesty (decision 15 Nov): only items PUBLISHED after the city's data ends count as new for this period.
      // Older items the collector found late are listed apart, never counted as new.
      const EDGE = '2026-10-27';
      // every finished collector run counts (each run only carries the items that were new to the engine that time)
      const seen = new Set(), allC = [];
      doneRuns.forEach(x => x.concerns.forEach(k => { if (!seen.has(k.id)) { seen.add(k.id); allC.push(k); } }));
      const c = {};
      doneRuns.forEach(x => ['claims', 'familiar', 'new', 'ambiguous'].forEach(k => { c[k] = (c[k] || 0) + (x.counts[k] || 0); }));
      const r = { finished_at: doneRuns[0].finished_at, created_at: doneRuns[0].created_at, concerns: allC };
      const fresh = allC.filter(x => x.state !== 'recurring' && (!x.project || x.project === 'heilbronn_cablecar'));
      fresh.forEach(x => CMAP.set(x.id, x));
      const after = fresh.filter(x => (x.first_seen || '') >= EDGE), late = fresh.filter(x => (x.first_seen || '') < EDGE);
      const row = x => `<li><span class="d">${esc(day(x.first_seen))}</span><button class="tt lnkrow" type="button" data-concern="${esc(x.id)}">${esc(x.label)}</button><span class="tag">${esc(CSTATE[x.state] || x.state)}</span></li>`;
      SINCE_R = `${nf(doneRuns.length)} ${doneRuns.length === 1 ? 'run' : 'runs'} · ${plural(c.claims || 0, 'claim', 'claims')}`;
      sinceHtml = (after.length
        ? `<p class="ans">${nf(after.length)} Heilbronn ${after.length === 1 ? 'point' : 'points'} published after 27 Oct</p><ul class="elist">${after.slice(0, 3).map(row).join('')}</ul>`
        : `<p class="ans quiet">Nothing new on Heilbronn published after 27 Oct, in the sources checked.</p>`)
        + (() => {   // other projects, published after 27 Oct (the comparison cities); shown, never mixed into Heilbronn's count
          const PN = { bonn_cablecar: 'Bonn', paris_c1: 'Paris C1', ipai: 'IPAI', other_urban_cablecar: 'Other cities' };
          const els = r.concerns.filter(x => x.project && x.project !== 'heilbronn_cablecar' && x.state !== 'recurring' && (x.first_seen || '') >= EDGE)
            .sort((a, b) => String(b.first_seen || '').localeCompare(String(a.first_seen || '')));
          els.forEach(x => CMAP.set(x.id, x));
          ELSE_IDS = els.map(x => x.id);
          return els.length ? `<button class="lnk morerow" type="button" data-else>Other cities after 27 Oct · ${nf(els.length)} →</button>` : '';
        })()
        + (late.length ? (LATE_IDS = late.map(x => x.id), `<button class="lnk morerow" type="button" data-late>Found late, not counted · ${nf(late.length)} →</button>`) : '');
    }

    // f. reliability, g. the analyst console
    let relHtml = '<p class="ans wait">The matcher test is not in this snapshot.</p>';
    if (mt) {
      const ref = REFNAME[mt.reference] || mt.reference || 'an AI model';
      relHtml = `<div class="relgrid"><div><p class="rel"><b>Matching: pair F1 ${f2(mt.f1)}</b> (likely range ${f2(mt.lo)} to ${f2(mt.hi)}) against ${f2(mt.base)} for plain embedding similarity, on ${nf(mt.n_pairs)} test pairs.</p>
        <p class="sub">Agreement with an AI reference (${esc(ref)}), not yet checked by people.${mt.wrongly_new != null ? ` Known arguments wrongly called new: ${nf(mt.wrongly_new)} of ${nf(mt.wrongly_new_of)} test claims.` : ''}</p></div>
        <div class="f1rows">
          <div><span>CityPulse matcher</span><span class="track"><span class="fill" style="width:${mt.f1 * 100}%"></span><span class="ci" style="left:${mt.lo * 100}%;width:${(mt.hi - mt.lo) * 100}%"></span></span><b>${f2(mt.f1)}</b></div>
          <div><span>Plain similarity</span><span class="track"><span class="fill base" style="width:${mt.base * 100}%"></span></span><b>${f2(mt.base)}</b></div></div></div>`;
    }
    const foot = `<p class="efoot"><span>Matcher ${esc(st.matcher)}${st.version ? ` (${esc(st.version)})` : ''} · embedder ${esc(st.embedder)}</span>
      ${LOCAL ? '<a class="lnk quiet" href="http://127.0.0.1:3000/emerging" target="_blank" rel="noopener">Open the analyst console ↗</a>' : ''}</p>`;

    el.innerHTML = headHtml(meta) + `
      <div class="grid g-args">
        <article class="card r1">${replay}</article>
        <article class="card r2">${concernsHtml}</article>
        <article class="card r3"><header class="ch"><h3>Main arguments before ${esc(cut)}</h3></header>${famHtml}</article>
        <article class="card r4"><header class="ch"><h3>Since 27 Oct</h3><span class="r" title="Collector runs read by the engine, all projects">${esc(SINCE_R)}</span></header>${sinceHtml}</article>
        <article class="card r5"><header class="ch"><h3>How reliable</h3>${mt ? '<button class="more" type="button" data-emethod>How it was tested</button>' : ''}</header>${relHtml}${foot}</article>
      </div>`;
    el.onclick = e => {
      const c = e.target.closest('[data-concern]'); if (c) return openConcern([CMAP.get(c.dataset.concern)]);
      if (e.target.closest('[data-allc]')) return openConcernList();
      if (e.target.closest('[data-else]')) return openConcernById(ELSE_IDS);
      if (e.target.closest('[data-late]')) return openConcernById(LATE_IDS);
      if (e.target.closest('[data-emethod]')) return openEngineMethod();
    };
  }

  function claimRow(x) {
    return `<li><div class="meta"><span class="d">${esc(day(x.date))}</span><span>${esc(CHANNEL[x.channel] || x.channel || 'Post')}</span><span>${esc(x.domain || host(x.url))}</span></div>
      ${x.url ? `<a class="ttl" href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.claim)} ↗</a>` : `<span class="ttl">${esc(x.claim)}</span>${x.link_withheld ? '<span class="tag">Link withheld: it names the account</span>' : ''}`}
      <div class="lab">${RELATION[x.relation] ? `<span class="tag">${esc(RELATION[x.relation])}</span>` : ''}${POL[x.polarity] ? `<span class="tag">${esc(sentence(POL[x.polarity]).replace(/\.$/, ''))}</span>` : ''}</div></li>`;
  }
  // The evidence behind one or more concerns: every claim with its date, channel, source and link. Never an author.
  function openConcern(list) {
    list = (list || []).filter(Boolean); if (!list.length) return;
    const one = list.length === 1, c0 = list[0], rp = EN && EN.replay();
    const basis = `Historical replay from ${rp && rp.cutoff ? day(rp.cutoff) : 'the cut-off'}${rp && /cache/.test(rp.mode) ? ' with cached model scores' : ''}, not a live detection. Provisional: agreement with an AI reference, not checked by people.`;
    openDrawer(drawerShell(one ? c0.label : `${list.length} concerns`,
      'Each claim is a one-line English summary of a post, written by the engine. The link opens the post itself.', null, 'evList'));
    if (one) {
      const co = c0.closest;
      drawer.querySelector('.dh').insertAdjacentHTML('afterend', `<div class="dcard"><dl class="fcard7">
        <div><dt>Status</dt><dd><b>${c0.flagged ? `Flagged on ${esc(day(c0.flagged_at))}. ` : ''}${esc(CSTATE[c0.state] || c0.state)}.</b>${c0.flagged ? ` Flagged because ${nf(EN.MIN_VOICES)} or more independent voices raised it.` : ''}</dd></div>
        <div><dt>Scale</dt><dd><b>${nf(c0.n_claims)} ${c0.n_claims === 1 ? 'claim' : 'claims'}</b> from ${nf(c0.n_voices)} independent ${c0.n_voices === 1 ? 'voice' : 'voices'}, first seen ${esc(day(c0.first_seen))}${polLine(c0.polarity) ? `; ${esc(polLine(c0.polarity))}` : ''}</dd></div>
        ${c0.note ? `<div><dt>Uncertainty</dt><dd>${esc(sentence(c0.note))}</dd></div>` : ''}
        ${co ? `<div><dt>Closest older claim</dt><dd>${co.url ? `<a href="${esc(co.url)}" target="_blank" rel="noopener">${esc(co.claim)} ↗</a>` : esc(co.claim)} · ${esc(co.domain)} · ${esc(day(co.date))}</dd></div>` : ''}
        <div><dt>Basis</dt><dd>${esc(basis)}</dd></div></dl></div>`);
      $('#evList').innerHTML = c0.claims.map(claimRow).join('') || '<li class="empty">No claims in this snapshot.</li>';
    } else {
      $('#evList').innerHTML = list.map(c => `<li class="egroup"><b>${esc(c.label)}</b><span>${c.flagged ? `Flagged ${esc(day(c.flagged_at))} · ` : ''}${nf(c.n_claims)} claims · ${nf(c.n_voices)} independent voices</span></li>${c.claims.map(claimRow).join('')}`).join('')
        + `<li class="empty">${esc(basis)}</li>`;
    }
  }
  function openConcernById(ids) { openConcern((ids || []).map(id => CMAP.get(id) || (EN && EN.concern(id)))); }
  function openConcernList() {
    const cs = EN ? EN.concerns() : [], rp = EN && EN.replay();
    const groups = [['Flagged', c => c.flagged], ['Needs review, not flagged', c => !c.flagged && c.state === 'ambiguous'], ['New, one voice so far', c => !c.flagged && /^new/.test(c.state)],
      ['Known argument, came up again', c => !c.flagged && ['recurring', 'gaining'].includes(c.state)]];
    openInfo('Every group after the cut-off', `Historical replay from ${rp && rp.cutoff ? day(rp.cutoff) : 'the cut-off'} · ${nf(cs.length)} groups`,
      groups.map(([name, f]) => { const g = cs.filter(f); return g.length ? `<p class="cap">${esc(name)} · ${nf(g.length)}</p><ul class="clines">${g.map(c =>
        `<li><button type="button" data-concern="${esc(c.id)}"><span>${esc(c.label)}</span><em>${nf(c.n_claims)} claims · ${nf(c.n_voices)} voices</em></button></li>`).join('')}</ul>` : ''; }).join('')
      + '<p class="note">A group with one voice is a candidate, and "needs review" means the engine could not tell new from known. Neither is an established finding.</p>');
  }
  function openEngineMethod() {
    const mt = EN && EN.matcher(), lk = (EN && EN.leakage()) || {}, ref = mt ? REFNAME[mt.reference] || mt.reference || 'an AI model' : 'an AI model';
    const d = x => (x ? day(x) : 'not reported');
    const clean = lk.candidates_older_than_query_all_pairs === true && lk.query_sets_disjoint === true && lk.time_order_train_cal_test === true && lk.test_queries_whose_text_occurs_in_training === 0;
    openInfo('How the matching was tested', 'Argument engine · the matcher', `<div class="rules">
      <p><b>Trained</b> on claims published up to ${esc(d(lk.train_newest_query))}.</p>
      <p><b>Tuned</b> (weights and cut-offs) on claims from ${esc(d(lk.cal_oldest_query))} to ${esc(d(lk.cal_newest_query))}.</p>
      <p><b>Tested</b> on claims from ${esc(d(lk.test_oldest_query))}${mt ? `: ${nf(mt.n_pairs)} pairs, used for scoring only` : ''}.</p>
      ${clean ? '<p><b>No look-ahead.</b> Each claim is compared only with older claims, and no test claim appears in training.</p>' : ''}
      <p><b>The reference is an AI.</b> ${esc(ref)} labelled which pairs make the same argument. The score is agreement with it, not accuracy: no person has checked these labels yet.</p>
      ${mt ? `<p><b>Result.</b> Pair F1 ${f2(mt.f1)} (likely range ${f2(mt.lo)} to ${f2(mt.hi)}), against ${f2(mt.base)} for plain embedding similarity.</p>` : ''}
      </div>${(lk.known_soft_spots || []).length ? `<p class="cap">Known soft spots, as the engine states them</p><div class="rules">${lk.known_soft_spots.map(s => `<p>${esc(s)}</p>`).join('')}</div>` : ''}`);
  }

  /* ---------- home ---------- */
  function renderHome() {
    $('#home').innerHTML = `
      <div class="hook"><h1 id="home-h">Let's see how close Heilbronn is<br><span class="lt">to its cable car.</span></h1>
        <nav class="enter" aria-label="Open a report">
          <a href="#history"><span class="n">01</span>History<span class="fx">${nf(DATASET.records)} records</span><span class="ar">→</span></a>
          <a href="#since"><span class="n">02</span>So far${LM ? `<span class="fx">${nf(sumCore('d_after'))} new</span>` : ''}<span class="ar">→</span></a>
          <a href="#today"><span class="n">03</span>Today${LM ? `<span class="fx">${esc(hhmm(SCAN_ISO() || LM.generated_at))}</span>` : ''}<span class="ar">→</span></a>
          <a href="#review"><span class="n">04</span>Human review${EN && EN.replay() ? `<span class="fx">${nf(EN.replay().counts.flagged)} flagged</span>` : ''}<span class="ar">→</span></a>
        </nav></div>`;
  }

  function openGaps() {
    const m = LM;
    const gaps = (m ? m.coverage_gaps || [] : []).filter(g => /^NOT COVERED BY DESIGN/.test(g)).map(g => g.replace(/^NOT COVERED BY DESIGN:\s*/, ''));
    const probs = (m ? m.coverage_gaps || [] : []).filter(g => !/^NOT COVERED BY DESIGN/.test(g));
    const p = g => { const i = g.indexOf(':'); return `<p><b>${esc(i > 0 ? g.slice(0, i) : g)}</b> ${esc(i > 0 ? g.slice(i + 1).trim() : '')}</p>`; };
    openInfo('What the collector cannot see', 'Gaps, said out loud',
      `<div class="gaps">${gaps.map(p).join('')}${probs.length ? '<p class="cap">In this check</p>' + probs.map(p).join('') : ''}</div>`);
  }
  function openMethod() {
    openInfo('How it works', 'Four steps, each one checkable', `
      <div class="chain">
        <div><span class="n">1 · Find</span><b>Collect legally</b><p>News feeds, city pages, council papers, video and search services. Social platforms only as links and search snippets.</p></div>
        <div><span class="n">2 · Keep the proof</span><b>Link, date, version</b><p>Every item keeps its link, when it was published, when we found it, and older versions if it changed.</p></div>
        <div><span class="n">3 · Read</span><b>About it? Which side?</b><p>The analysis decides whether an item is about the project, whether it takes a side, and which arguments it raises. A small model we trained spots the same argument in other words; new or unclear ones go to Human review, for a person to check.</p></div>
        <div><span class="n">4 · Check</span><b>An independent referee</b><p>Fixed tests the labellers never train on: a public human-labelled stance benchmark (Swiss political comments, not Heilbronn posts), edited posts and known hard cases. No Heilbronn post has been checked by a person yet.</p></div>
      </div>
      <div class="rules">
        <p><b>Position, not tone.</b> "Heilbronn says yes to the cable car idea" is news that takes no side, even if it sounds positive.</p>
        <p><b>Items, not people.</b> Counts are things published. They are not a poll of residents.</p>
        <p><b>No names.</b> Authors, handles and e-mails are never shown; links that name an account are withheld.</p>
        <p><b>A quiet check says so.</b> "Nothing new found in the sources checked", never "nobody talked".</p>
        <p><b>Small samples are marked.</b> Under 30 posts a share is a direction, not a number.</p>
        <p><b>The city's FAQ is not the judge.</b> It names the topics; it never decides who is for or against.</p>
      </div>
      ${faqLine()}
      <p class="note">City data to ${DATASET.end} · collector receipt ${LM ? esc(LM.update_id) : 'none'} · analysis: ${MODE === 'final' ? 'final run' : MODE === 'pilot' ? 'pilot run (provisional)' : 'awaiting final run'} · photo: Peter Schmelzle, CC BY-SA 4.0</p>`);
  }

  function setupRun(steps) {
    const btnU = $('#btnUpdate'), btnR = $('#btnReplay'), hint = $('#runHint'), log = $('#runLog'), list = $('#steps'), run = $('#run');
    let server = false, busy = false;
    fetch('/api/status', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(j => {
      server = !!(j && j.ok);
      hint.textContent = server ? 'About 4 minutes' : OFFLINE_HINT;
      btnU.disabled = !server;
      if (!server) hostedButton();
    }).catch(() => { hint.textContent = OFFLINE_HINT; btnU.disabled = true; hostedButton(); });
    function hostedButton() {
      if (LOCAL) return;                      // on the laptop a missing server is a real problem and says so
      const scan = SCAN_ISO() || (LM && LM.generated_at);
      btnU.textContent = 'Replay today\'s check'; btnU.disabled = false; btnR.style.display = 'none';
      hint.textContent = scan ? `Checked ${when(scan, true)}, every step with its source` : 'Every step with its source';
      btnU.addEventListener('click', () => btnR.click());
    }

    let live = false, cur = -1;
    const setStates = (activeIdx, note) => {
      [...list.children].forEach((li, i) => {
        li.className = 'step ' + (i < activeIdx ? (live ? 'done' : (steps[i] ? steps[i].st : 'done')) : i === activeIdx ? 'active' : 'wait');
        if (live) {   // during a real check show only what this check reports, never the old receipt
          const ds = li.querySelector('.ds'), src = li.querySelector('.src');
          if (i === activeIdx && note) { ds.textContent = note; src.textContent = when(new Date().toISOString(), true); }
          if (i > activeIdx) { ds.textContent = 'waiting'; src.textContent = ''; }
          if (i < activeIdx && ds.textContent === 'waiting') ds.textContent = 'done';
        }
      });
      cur = activeIdx;
    };
    btnR.addEventListener('click', () => {
      if (busy) return; busy = true; run.classList.add('running');
      $('#runTitle').textContent = 'Replay of the last check';
      let i = 0; setStates(0);
      const tick = () => { i++; setStates(i); if (i < steps.length) setTimeout(tick, 900); else { busy = false; run.classList.remove('running'); $('#runTitle').textContent = 'Every step, visible'; } };
      setTimeout(tick, 900);
    });
    btnU.addEventListener('click', async () => {
      if (busy || !server) return; busy = true; run.classList.add('running');
      btnU.disabled = true; btnR.disabled = true;
      $('#runTitle').textContent = 'Checking now'; $('#runWhen').textContent = 'started ' + when(new Date().toISOString(), true);
      live = true; log.textContent = ''; log.classList.add('on'); setStates(0, 'starting');
      const phase = { '[1/4]': 0, '[2/4]': 3, '[3/4]': 4, '[4/4]': 5, '[5/5]': 6 };
      try {
        const r = await fetch('/api/update?mode=quick', { method: 'POST' });
        if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || ('server answered ' + r.status)); }
        const rd = r.body.getReader(); const dec = new TextDecoder(); let buf = '';
        for (;;) {
          const { value, done } = await rd.read(); if (done) break;
          buf += dec.decode(value, { stream: true });
          let k; while ((k = buf.indexOf('\n')) >= 0) {
            const line = buf.slice(0, k); buf = buf.slice(k + 1);
            log.textContent += line + '\n'; log.scrollTop = log.scrollHeight;
            const tag = line.slice(0, 5);
            if (tag in phase) setStates(phase[tag], line.slice(6).trim());
            else if (line.trim() && !line.startsWith('CITYPULSE_DONE') && cur >= 0) { const li = list.children[cur]; if (li) li.querySelector('.ds').textContent = line.trim().slice(0, 140); }
            if (line.startsWith('[1/4]')) setTimeout(() => busy && cur === 0 && setStates(1, 'searching'), 2500);
            if (line.startsWith('CITYPULSE_DONE')) {
              const ok = / 0$/.test(line.trim());
              if (ok) setStates(list.children.length); else if (list.children[cur]) list.children[cur].className = 'step warn';
              $('#runTitle').textContent = ok ? 'Check finished' : 'Check stopped';
              hint.textContent = ok ? 'Done. Reloading with the new receipt.' : `The check stopped at step ${cur + 1}. Nothing was published: the briefing on this page is still the last successful one (${LM ? when(LM.generated_at, true) : 'none'}).`;
              if (ok) setTimeout(() => location.reload(), 1500);
            }
          }
        }
      } catch (e) {
        hint.textContent = 'The check could not run: ' + e.message;
        if (list.children[cur]) list.children[cur].className = 'step warn';
      }
      busy = false; run.classList.remove('running'); btnU.disabled = false; btnR.disabled = false;
    });
  }

  /* ---------- evidence drawer ---------- */
  const wrap = $('#drawerWrap'), drawer = $('#drawer');
  let lastFocus = null;
  function openDrawer(html) {
    lastFocus = document.activeElement;
    drawer.innerHTML = html; wrap.hidden = false; document.body.style.overflow = 'hidden';
    drawer.focus();
  }
  function closeDrawer() { wrap.hidden = true; document.body.style.overflow = ''; if (lastFocus) lastFocus.focus(); }
  wrap.addEventListener('click', e => { if (e.target.closest('[data-close]')) closeDrawer(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !wrap.hidden) closeDrawer(); });

  function drawerShell(title, meta, filters, listId) {
    return `<div class="dh"><button class="x" data-close aria-label="Close">×</button><span class="tag">Evidence</span>
      <h3 id="drawer-h">${esc(title)}</h3><p class="dm">${esc(meta)}</p>
      ${filters ? `<div class="filters">${filters}</div>` : ''}</div><ul class="ev" id="${listId}"></ul>`;
  }

  function openLive(title, meta, items) {
    const order = { after: 0, late: 1, unknown: 2 };
    items = items.slice().sort((a, b) => (order[a.date_class] - order[b.date_class]) || String(b.date || '').localeCompare(String(a.date || '')));
    const counts = { all: items.length, after: 0, late: 0, unknown: 0 };
    items.forEach(i => { counts[i.date_class] = (counts[i.date_class] || 0) + 1; });
    const f = ['all', 'after', 'late', 'unknown'].map((k, i) => `<button class="${i ? '' : 'on'}" data-f="${k}">${k === 'all' ? 'All' : DATECLASS[k]} · ${counts[k] || 0}</button>`).join('');
    openDrawer(drawerShell(title, `${meta}. ${items.length} items. Readings are provisional.`, f, 'evList'));
    const draw = k => {
      const rows = items.filter(i => k === 'all' || i.date_class === k).map(i => {
        const label = i.label_state === 'labelled'
          ? (i.counted_project === i.radar_project || i.llm_project === i.radar_project
            ? `<span class="tag">${esc(STANCE[i.stance] || 'No reading')}</span>${i.voice ? `<span class="tag">${esc(VOICE[i.voice] || i.voice)}</span>` : ''}<span class="tag">${esc(i.confidence || '')} agreement</span>`
            : `<span class="tag">The model says: not about this project</span>`)
          : `<span class="tag">Not read yet</span>`;
        return `<li><div class="meta"><span class="d">${i.date ? esc(day(i.date)) : 'date unknown'}</span><span>${esc(KIND[i.kind] || i.kind)}</span><span>${esc(i.source || host(i.url))}</span><span class="tag ${i.date_class === 'after' ? 'blue' : ''}">${esc(DATECLASS[i.date_class] || '')}</span></div>
          ${i.url ? `<a class="ttl" href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title || (KIND[i.kind] || 'Post') + ' on ' + (i.source || host(i.url)))} ↗</a>` : `<span class="ttl">${esc(i.title || (KIND[i.kind] || 'Post') + ' on ' + (i.source || 'a platform'))}</span><span class="tag">Link withheld: it names the account</span>`}
          <div class="lab">${label}</div></li>`;
      }).join('');
      $('#evList').innerHTML = rows || '<li class="empty">Nothing in this group.</li>';
    };
    drawer.querySelector('.filters').addEventListener('click', e => {
      const b = e.target.closest('[data-f]'); if (!b) return;
      [...b.parentNode.children].forEach(x => x.classList.toggle('on', x === b)); draw(b.dataset.f);
    });
    draw('all');
  }

  function openPosts(title, question, posts, card) {
    posts = posts.slice().sort((a, b) => String(b.date).localeCompare(String(a.date)));
    const st = {}; posts.forEach(p => { st[p.stance] = (st[p.stance] || 0) + 1; });
    const f = ['all'].concat(STANCE_ORDER.filter(k => st[k])).map((k, i) => `<button class="${i ? '' : 'on'}" data-f="${k}">${k === 'all' ? 'All' : STANCE[k]} · ${k === 'all' ? posts.length : st[k]}</button>`).join('');
    openDrawer(drawerShell(title, `${question} ${posts.length} posts from the city's data.${MODE === 'pilot' ? ' Pilot labels, provisional.' : ''}`, f, 'evList'));
    if (card) drawer.querySelector('.dh').insertAdjacentHTML('afterend', `<div class="dcard">${card}</div>`);
    const draw = k => {
      $('#evList').innerHTML = posts.filter(p => k === 'all' || p.stance === k).slice(0, 200).map(p => `<li>
        <div class="meta"><span class="d">${esc(day(p.date))}</span><span>${esc(p.media_type || '')}</span><span>${esc(p.source || host(p.url))}</span></div>
        ${p.url ? `<a class="ttl" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title || (p.media_type || 'Post') + ' on ' + (p.source || host(p.url)))} ↗</a>` : `<span class="ttl">${esc(p.title || (p.media_type || 'Post') + ' on ' + (p.source || 'a platform'))}</span><span class="tag">Link withheld: it names the account</span>`}
        <div class="lab">${p.stance ? `<span class="tag">${esc(STANCE[p.stance])}</span>` : ''}${p.voice ? `<span class="tag">${esc(VOICE[p.voice] || p.voice)}</span>` : ''}${(p.arguments || []).map(a => `<span class="tag">${esc(ARG[a] || a)}</span>`).join('')}<span class="tag">${esc(p.confidence || '')} confidence</span></div></li>`).join('') || '<li class="empty">Nothing in this group.</li>';
    };
    drawer.querySelector('.filters').addEventListener('click', e => {
      const b = e.target.closest('[data-f]'); if (!b) return;
      [...b.parentNode.children].forEach(x => x.classList.toggle('on', x === b)); draw(b.dataset.f);
    });
    draw('all');
  }

  // A drawer with free content (comparison, gaps, method, a finding that waits for the final run)
  function openInfo(title, kicker, html) {
    openDrawer(`<div class="dh"><button class="x" data-close aria-label="Close">×</button><span class="k">${esc(kicker)}</span>
      <h3 id="drawer-h">${esc(title)}</h3></div><div class="dbody">${html}</div>`);
  }
  // Every share inside a drawer chart opens the posts behind it
  drawer.addEventListener('click', e => {
    const cc = e.target.closest('[data-concern]'); if (cc) { openConcern([CMAP.get(cc.dataset.concern)]); return; }
    const r = e.target.closest('[data-inspect]'); if (!r || !HAS_H) return;
    const [kind, key, project] = r.dataset.inspect.split('|');
    if (kind === 'stance') {
      const s = hStance(project); const posts = HIST.posts.filter(p => p.project === project && p.stance === key);
      openPosts(`${PNAME[project]}: ${STANCE[key]}`, 'How this share is counted.', posts,
        scaleCard(`${STANCE[key]}`, s.counts[key] || 0, s.n, 'labelled posts of this project', posts, s.low_sample));
    } else if (kind === 'arg') {
      const a = hArgs(project).find(x => x.code === key); const posts = HIST.posts.filter(p => p.project === project && (p.arguments || []).includes(key));
      openPosts(`${PNAME[project]}: ${ARG[key] || key}`, 'How this share is counted.', posts,
        scaleCard(ARG[key] || key, a.n, null, `posts of this project raise it. ${ARGS_BASE}`, posts, true));
    }
  });


  /* ---------- home and three reports ---------- */
  const VIEWS = ['home', 'history', 'since', 'today', 'review'];
  const ALIAS = { arguments: 'review' };          // old links to the tab's former name keep working
  function route() {
    let v = (location.hash || '#home').slice(1);
    if (ALIAS[v]) { v = ALIAS[v]; history.replaceState(null, '', '#' + v); }
    if (!VIEWS.includes(v)) v = 'home';
    document.querySelectorAll('.view').forEach(e => e.classList.toggle('on', e.dataset.view === v));
    document.querySelectorAll('.tabs3 a').forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + v));
    document.documentElement.dataset.view = v;
    // the browser also jumps to the section the hash names (on phones it then hides the title under the bar): undo it after that jump
    window.scrollTo(0, 0); requestAnimationFrame(() => window.scrollTo(0, 0)); setTimeout(() => window.scrollTo(0, 0), 60); setTimeout(() => window.scrollTo(0, 0), 200);
  }
  window.addEventListener('hashchange', route);
  window.addEventListener('popstate', route);
  // links to the screens change the view without the browser's jump to the section (which hides the title on phones)
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href^="#"]'); if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey) return;
    const v = a.getAttribute('href').slice(1); if (!VIEWS.includes(v)) return;
    e.preventDefault();
    if (location.hash !== '#' + v) history.pushState(null, '', '#' + v);
    route();
  });
  // a link like ...#since must not jump the page down to that section
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  window.addEventListener('load', () => setTimeout(() => window.scrollTo(0, 0), 0));
  $('#howLink').addEventListener('click', openMethod);

  // read-only hooks for app/ask.js (Ask CityPulse) and app/demo.js: open the same evidence drawers the reports use
  window.CP_APP = { mode: MODE, hasH: HAS_H, openLive, openPosts, openGaps, openInfo, openFinding, openConcernById, openEngineMethod };

  renderHome();
  renderSoFar();
  renderNow();
  renderToday();
  renderArgs();
  route();
  if (window.CityScene) window.CityScene.mount(document.getElementById('scene'), document.getElementById('scenePhoto'));
})();
