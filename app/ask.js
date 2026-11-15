/* Ask CityPulse: questions answered from the verified data, never from a language model.
   Briefs: debate/chatgpt/2026-11-15_0500_ui_and_ask_citypulse_handoff.md (section C) and
           debate/chatgpt/2026-11-15_0530_ai_assistant_deck_and_demo_direction.md (section 2, "safe answer process").

   How one question is answered (the same order as the brief's safe answer process):
   1. interpret()  reads the question: intent, project(s), period, speaker group, and whether it follows on from the last answer.
                   Defaults are stated back to the user in the "Read as" line.
   2. a fixed, read-only answer function computes counts from the analysis pipeline's export or the collector receipt.
                   No free SQL, no web, no model. Record text is only ever displayed (escaped), never interpreted.
   3. every number that enters the answer goes through F(), which records it as a fact.
   4. validate()   checks the answer before it is shown: every number in the sentences is a recorded fact, every evidence id
                   exists in the data, no withheld link or name is shown. A failed check shows "could not be verified" instead.
   5. the answer:  1 to 3 sentences, one proof, one way to the evidence, the basis (source and version), one next question.
   The core (makeCore) has no DOM, so app/tests/ask_suite.js runs the frozen question suite against the real data in Node. */
(function () {
  'use strict';
  const G = typeof window !== 'undefined' ? window : globalThis;

  /* =====================================================================
     CORE: pure functions over the data. env = { live, hist, facts, factsUrl }
     ===================================================================== */
  function makeCore(env) {
    const LIVE = env.live || null, HIST = env.hist || null;
    const FACTS = (env.facts && env.facts.figures) || {};
    const FACTS_URL = (env.facts && env.facts.source_url) || 'https://www.heilbronn.de/umwelt-mobilitaet/mobilitaet/seilbahn.html';
    const LM = LIVE ? LIVE.meta : null;
    const ITEMS = LIVE ? LIVE.items || [] : [];
    const POSTS = HIST ? HIST.posts || [] : [];
    const LIVE_BY_ID = new Map(ITEMS.map(i => [i.id, i]));
    const POST_BY_ID = new Map(POSTS.map(p => [p.id, p]));
    const DATASET_END = (HIST && HIST.meta && HIST.meta.dataset_end) || '2026-10-27T12:29:00Z';

    const CORE = ['heilbronn_cablecar', 'ipai', 'bonn_cablecar', 'paris_c1'];
    const OTHERS = ['berlin_cablecar', 'hamburg_cablecar', 'koblenz_cablecar', 'koeln_cablecar', 'muenchen_cablecar', 'stuttgart_cablecar', 'wuppertal_cablecar'];
    const PNAME = { heilbronn_cablecar: 'Heilbronn cable car', ipai: 'IPAI Heilbronn', bonn_cablecar: 'Bonn cable car', paris_c1: 'Paris Câble C1',
      berlin_cablecar: 'Berlin', hamburg_cablecar: 'Hamburg', koblenz_cablecar: 'Koblenz', koeln_cablecar: 'Köln', muenchen_cablecar: 'München',
      stuttgart_cablecar: 'Stuttgart', wuppertal_cablecar: 'Wuppertal' };
    const SHORT = id => (PNAME[id] || id).replace(' cable car', '');
    const PROJECT_RE = [
      ['ipai', /\b(ipai|ki-park|ai park|innovation park|innovationspark)\b/],
      ['paris_c1', /\b(paris|c1|câble|cable c1)\b|île-de-france|ile-de-france/],
      ['bonn_cablecar', /\bbonn\b/],
      ['berlin_cablecar', /\bberlin\b/], ['hamburg_cablecar', /\bhamburg\b/], ['koblenz_cablecar', /\bkoblenz\b/],
      ['koeln_cablecar', /\b(köln|koeln|cologne)\b/], ['muenchen_cablecar', /\b(münchen|muenchen|munich)\b/],
      ['stuttgart_cablecar', /\bstuttgart\b/], ['wuppertal_cablecar', /\bwuppertal\b/],
      ['heilbronn_cablecar', /\b(heilbronn|heilbronner|neckar)\b/]
    ];
    const STANCE_KEYS = ['support', 'oppose', 'neutral_informative', 'mixed', 'unclear'];
    const STANCE_WORD = { support: 'Support', oppose: 'Oppose', neutral_informative: 'Report only', mixed: 'Mixed', unclear: 'Unclear' };
    const VOICE = { citizen: 'citizens', news_institutional: 'news and institutions', politician_official: 'politicians and officials' };
    const ARG = { cost: 'Cost', traffic_mobility: 'Traffic and mobility', tourism_image: 'Tourism and image', climate_environment: 'Climate and environment',
      ipai_who_benefits: 'Who benefits', noise_privacy_overflight: 'Noise and flying over homes', cityscape_design: 'Cityscape and design',
      process_participation: 'Process and participation', safety_technology: 'Safety and technology', other: 'Other' };
    const KIND = { news: 'News', official: 'Official page', council_paper: 'Council paper', web: 'Web page', social_link: 'Social media link',
      social_post: 'Social post', video: 'Video', video_comment: 'Video comment', forum: 'Forum' };
    const SOURCE = { rss: 'news feeds', pagewatch: 'city pages', bluesky: 'Bluesky', mastodon: 'Mastodon', youtube: 'YouTube', exa: 'Exa search',
      tavily: 'Tavily search', oparl: 'council papers', date_recovery: 'date recovery' };
    const MONTHS = [/\b(january|januar|jan)\b/, /\b(february|februar|feb)\b/, /\b(march|märz|maerz|mar)\b/, /\b(april|apr)\b/, /\b(may|mai)\b/,
      /\b(june|juni|jun)\b/, /\b(july|juli|jul)\b/, /\b(august|aug)\b/, /\b(september|sept|sep)\b/, /\b(october|oktober|oct|okt)\b/,
      /\b(november|nov)\b/, /\b(december|dezember|dec|dez)\b/];
    const MIN_DIRECTION = 10;   // under this many posts no direction is claimed
    const SMALL = 30;           // under this many posts a share is marked "small sample"

    /* ---------- formatting ---------- */
    const TZ = 'Europe/Berlin';
    const nf = n => Number(n).toLocaleString('en-GB');
    const day = iso => iso ? new Date(iso.length <= 10 ? iso + 'T12:00:00Z' : iso).toLocaleDateString('en-GB', { timeZone: TZ, day: 'numeric', month: 'short', year: 'numeric' }) : 'date unknown';
    const monthLabel = (y, m) => new Date(Date.UTC(y, m, 15)).toLocaleDateString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' });
    const when = iso => iso ? new Date(iso).toLocaleString('en-GB', { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }).replace(',', '') : 'not known';
    const runIso = id => { const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(id || ''); return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z` : null; };
    const host = u => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (e) { return ''; } };
    const norm = q => ' ' + String(q || '').toLowerCase().normalize('NFC').replace(/[’‘`]/g, "'").replace(/\s+/g, ' ').trim() + ' ';

    /* ---------- data access (read-only) ---------- */
    const stanceRow = (p, v) => HIST ? (HIST.stance || []).find(s => s.project === p && s.voice === (v || 'all')) || null : null;
    const argRows = p => HIST ? (HIST.arguments || []).filter(a => a.project === p).sort((a, b) => b.n - a.n) : [];
    const placebo = p => HIST ? (HIST.placebo || []).find(x => x.project === p) || null : null;
    const projRow = p => HIST ? (HIST.projects || []).find(x => x.id === p) || null : null;
    const events = p => (HIST && HIST.events || []).filter(e => e.project === p && !e.after_dataset).sort((a, b) => a.date.localeCompare(b.date));
    const peaks = p => (HIST && HIST.peaks || []).filter(k => k.project === p && !k.weak);
    const lp = id => { const p = (LM && LM.per_project && LM.per_project[id]) || {}; return Object.assign({ found: 0, d_after: 0, d_late: 0, d_unknown: 0, about: 0, not_this: 0, pending: 0 }, p); };
    const liveOf = id => ITEMS.filter(i => i.radar_project === id);
    const onTopic = i => i.label_state !== 'labelled' || i.llm_project === i.radar_project;
    function weekly(p) {
      if (!HIST) return [];
      const have = new Map((HIST.weekly || []).filter(w => w.project === p).map(w => [w.week, w.stories]));
      const out = [], t1 = Date.parse(DATASET_END);
      for (let t = Date.UTC(2024, 9, 14); t <= t1; t += 7 * 864e5) { const k = new Date(t).toISOString().slice(0, 10); out.push({ week: k, stories: have.get(k) || 0 }); }
      return out;
    }
    function versionHist(mode) {
      const m = HIST && HIST.meta || {};
      return `City data Oct 2024 to 27 Oct 2026 · ${mode === 'final' ? 'final run' : 'pilot run, provisional'} · codebook ${m.codebook_version || '?'} (${(m.codebook_sha || '').slice(0, 7)})`;
    }
    const versionLive = () => LM ? `Collector receipt ${LM.update_id} · scan of ${when(runIso(LM.collect_run_id) || LM.generated_at)}` : 'No collector receipt';

    /* ---------- an answer under construction: every number goes through F() ---------- */
    function draft(intent, params) {
      const facts = [], ids = [];
      const F = (x, d) => { const s = d == null ? nf(x) : Number(x).toFixed(d); facts.push(parseFloat(s.replace(/,/g, ''))); return s; };
      const P = x => { const v = Math.round(x * 100); facts.push(v); return v + '%'; };
      const V = (x, dp) => parseFloat(F(x, dp).replace(/,/g, ''));   // a proof value: recorded as a fact, returned as a number
      return { intent, params, facts, ids, F, P, V };
    }
    function done(d, a) { return Object.assign({ intent: d.intent, params: d.params, facts: d.facts, ids: d.ids }, a); }
    const rec = (d, i) => { d.ids.push(i.id); return { id: i.id, date: i.date, title: i.title || `${KIND[i.kind] || 'Item'} on ${i.source || host(i.url)}`, source: i.source || host(i.url), url: i.url_withheld ? null : i.url, tag: i.date_class === 'late' ? 'older, found late' : '' }; };
    const recPost = (d, p) => { d.ids.push(p.id); return { id: p.id, date: p.date, title: (!p.title_withheld && p.title) || `${p.media_type || 'Post'} on ${p.source || host(p.url)}`, source: p.source || host(p.url), url: p.url || null, tag: STANCE_WORD[p.stance] || '' }; };

    /* ---------- the argument engine snapshot (app/data/engine.js), read through the adapter's engine model ---------- */
    const ENG = (() => { const m = G.CPEngineModel ? G.CPEngineModel(env.engine || null) : null; return m && m.has() ? m : null; })();
    const CLAIM_BY_ID = new Map(ENG ? ENG.allClaims().filter(c => c.cid).map(c => [c.cid, c]) : []);
    const ENGINE_INTENTS = ['arg_new', 'arg_concern', 'arg_main', 'arg_rel', 'arg_since'];
    const recClaim = (d, c) => { d.ids.push(c.cid); return { id: c.cid, date: c.date, title: c.claim, source: c.domain, url: c.url || null, tag: c.domain }; };
    const qt = s => '"' + String(s || '').replace(/"/g, "'").replace(/[&<>]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch])) + '"';   // record text in an answer: quoted and escaped, never a CityPulse number
    const versionEng = (noReplay) => {
      const r = !noReplay && ENG && ENG.replay(), st = ENG ? ENG.status() : {};
      return `Argument engine snapshot of ${when(ENG && ENG.takenAt())}${r ? ` · historical replay from ${day(r.cutoff)}${/cache/.test(r.mode) ? ', cached model scores' : ''}` : ''}${st.version ? ` · matcher ${st.version}` : ''} · provisional`;
    };
    const replayNote = r => (/cache/.test((r && r.mode) || '') ? 'This is a historical replay with cached model scores, not a live detection.' : 'This is a historical replay, not a live detection.');
    const engOnlyHn = (d, other) => done(d, { status: 'insufficient', read: `${PNAME[other] || other} · argument engine`,
      text: `<b>Heilbronn only.</b> The argument engine's results on this site cover Heilbronn, not ${SHORT(other)}.`, basis: versionEng(), next: 'arg_main' });

    /* ---------- 1. interpret ---------- */
    const INTENT_KEYS = {
      since: /\b(27|after|since|changed?|changes|new|latest|recent|update|updated|neu|neue|neues|seit|aktuell|export|cutoff)\b/g,
      latest: /\b(tender|ausschreibung|vergabe|official|offiziell|developments?|what happened|was ist passiert|news about)\b/g,
      stance: /\b(oppose[sd]?|opposing|opposition|against|support|supports|supporting|supporters|for or against|side|sides|stance|position|positions|opinion|opinions|attitude|sentiment|mood|tone|dagegen|dafür|meinung|ablehnung|zustimmung|kritik|critical|criticism|critics|protest|resistance|widerstand|like it|hate|love)\b/g,
      concerns: /\b(concern|concerns|worry|worries|worried|argument|arguments|raise|raised|issue|issues|topic|topics|theme|themes|complain|complaints|gripe|gripes|grumble|grumbling|objections?|reasons|sorge|sorgen|argumente|themen|bedenken|noise|lärm)\b/g,
      attention: /\b(when|attention|peak|peaks|spike|spiked|rise|rose|surge|jump|busiest|loudest|timeline|over time|volume|discussion (rise|rose|increase)|aufmerksamkeit|anstieg)\b/g,
      compare: /\b(compare|comparison|compared|vs|versus|other cities|difference|different|vergleich|andere städte|than)\b/g,
      facts: /\b(cost|costs|kosten|kostet|teuer|expensive|euro|eur|million|money|price|budget|fund|funding|förder|km|length|long is|route|strecke|station|stations|stationen|minutes|travel time|fahrzeit|how long does it take|how fast|capacity|kapazität|cabin|cabins|gondel|mast|masts|height|start of operation|eröffnung|faq|officially say|city say|city's own)\b/g,
      gaps: /\b(unavailable|cannot|can't|not see|not covered|blind spots?|gaps?|miss|missing|fail|failed|failing|partial|coverage|instagram|facebook|tiktok|reddit|linkedin|youtube|stimme|paywall|which sources|what sources|quellen|fehlen|scan|last check)\b/g,
      reliability: /\b(reliable|reliability|trust|accurate|accuracy|correct|wrong|confidence|confident|verify|verified|kappa|agree|agreement|review|reviewed|human|zuverlässig|genau|vertrauen|sure)\b/g,
      addressed: /\b(addressed|address|answered|answers|already (answer|explain|cover)|responded|respond to|covered by the faq|faq cover|beantwortet|eingegangen)\b/g
    };
    const FOLLOW_EVIDENCE = /\b(what (sources|evidence|items|posts) (support|back|show)|show (me )?(the )?(sources|evidence|items|posts|records|proof)|which (items|posts|articles)|belege|zeig)\b/;
    const FOLLOW_METHOD = /\b(how (is|was|are|were) (this|that|it|these) counted|where (did|does|do) (this|that|the|these) (number|numbers|figure|figures) come from|what does (this|that) number mean|denominator|what is the base|woher)\b/;
    const REFERS_BACK = /\b(that|this|it|these|those|same|then|and)\b/;

    const GUARDS = [
      { id: 'population', re: /\d+ ?% of (the )?(residents|people|citizens|population|heilbronn)|\b(percent of (the )?(residents|people|citizens|population|heilbronn)|majority|mehrheit|prozent der|how many (residents|people|citizens|heilbronners)|what does heilbronn think|was denkt heilbronn|do heilbronners|poll|umfrage|representative|repräsentativ|population|bevölkerung)\b/ },
      { id: 'names', re: /\b(who wrote|who posted|author|authors|autor|name of|names of|their names|handle|username|e-?mail|email address|account name|wer hat)\b/ },
      { id: 'predict', re: /\b(predict|prediction|forecast|prognose|will (it|the line|the cable car|they) (be built|happen|pass|succeed|fail)|referendum|bürgerentscheid|chances?|likely to (pass|win|be built))\b/ },
      { id: 'cause', re: /\b(prove|proof that|caused by|did .* cause|because of the council)\b/ }
    ];
    const ENGINE_ROUTES = [
      // "what are people saying since 27 Oct / since the export": the engine's collector runs (before arg_new, which is the July replay)
      ['arg_since', /\b(arguments?|points?|claims?|concerns?|said|saying|say|talking)\b.*\b(since|after) (27|the (city's )?(data|export)|october|oktober|the cut)|\b(since|after) (27|the (city's )?(data|export)|october|oktober)\b.*\b(arguments?|points?|claims?|concerns?|said|saying)\b/],
      ['arg_rel', /\b(argument )?(match|matching|matcher|matches)\b.*\b(reliab\w*|trust\w*|accura\w*|good|f1|tested|sure)\b|\b(reliab\w*|trust\w*|accura\w*|how good|tested|f1|zuverlässig|verlässlich)\b.*\b(match|matching|matcher)\b/],
      ['arg_concern', /\b(hospital|hospitals|clinic|klinik|klinikum|krankenhaus|löwenstein|loewenstein)\b/],
      ['arg_new', /\b(new|emerging|emerged|neue?n?|fresh)\b.*\b(concerns?|arguments?|worries|sorgen|bedenken|argumente)\b|\b(concerns?|arguments?)\b.*\b(appear|appeared|emerge|emerged|emerging|flagged)\b|\bflagged\b/],
      ['arg_main', /\b(main|top|most common|biggest|key|frequent|leading)\b.*\barguments?\b|\barguments?\b.*\b(people make|made in|in heilbronn)\b|\bargument (families|groups|map)\b/]
    ];

    function detectProjects(t) {
      const found = [];
      PROJECT_RE.forEach(([id, re]) => { const m = t.match(re); if (m) found.push([t.indexOf(m[0]), id]); });
      // "IPAI Heilbronn" names one project, not two
      let ids = found.sort((a, b) => a[0] - b[0]).map(x => x[1]);
      if (ids.includes('ipai') && ids.includes('heilbronn_cablecar') && !/\b(cable car|seilbahn|line|linie)\b/.test(t)) ids = ids.filter(i => i !== 'heilbronn_cablecar');
      if (/\b(all four|four projects|all projects|alle vier)\b/.test(t)) ids = CORE.slice();
      return [...new Set(ids)];
    }
    function detectVoice(t) {
      const v = [];
      if (/\b(citizens?|residents?|bürger|einwohner|people)\b/.test(t)) v.push('citizen');
      if (/\b(news|media|press|presse|zeitung|journalists?|newspapers?)\b/.test(t)) v.push('news_institutional');
      if (/\b(politicians?|officials?|mayor|oberbürgermeister|parties|party)\b/.test(t)) v.push('politician_official');
      return v;
    }
    function detectPeriod(t, project) {
      if (/\b(since (27|the (city's )?(data|export|dataset))|after (27|the (city's )?(data|export|dataset))|after october 27|since october|seit dem 27|cutoff|since the cut)\b/.test(t)) return { kind: 'since', label: 'after 27 Oct 2026' };
      const rel = /\b(after|since|seit|nach|following)\b/.test(t) ? 'after' : /\b(before|vor|prior to)\b/.test(t) ? 'before' : null;
      if (/\b(opening|opened|eröffnung|eröffnet|inauguration)\b/.test(t)) {
        const ev = events(project || 'paris_c1').filter(e => e.type === 'opening');
        if (ev.length) { const e = ev[ev.length - 1]; return { kind: 'event', rel: rel || 'around', date: e.date, label: `the opening on ${day(e.date)}`, event: e }; }
      }
      if (/\b(council|gemeinderat|beschluss|decision|decided|vote)\b/.test(t) && !/\b(will|next)\b/.test(t)) {
        const ev = events(project || 'heilbronn_cablecar').filter(e => e.type === 'decision');
        if (ev.length) { const e = ev[ev.length - 1]; return { kind: 'event', rel: rel || 'after', date: e.date, label: `the council decision of ${day(e.date)}`, event: e }; }
      }
      let mi = MONTHS.findIndex(re => re.test(t.replace(/\bmay i\b/, '')));
      const ym = t.match(/\b(2024|2025|2026)\b/);
      // a season stands for its first month; "after the summer" starts the month after it ends. The "Read as" line names the month used.
      const SEASON = [[/\b(spring|frühling|frühjahr)\b/, 2, 5], [/\b(summer|sommer)\b/, 5, 8], [/\b(autumn|fall|herbst)\b/, 8, 11], [/\b(winter)\b/, 11, 2]];
      let span = 1;
      if (mi < 0) { const s = SEASON.find(([re]) => re.test(t)); if (s) { mi = rel === 'after' ? s[2] : s[1]; span = rel === 'after' ? 1 : 3; } }
      if (mi >= 0) {
        let y = ym ? +ym[1] : null;
        const endY = new Date(DATASET_END).getUTCFullYear(), endM = new Date(DATASET_END).getUTCMonth();
        if (!y) y = mi <= endM ? endY : endY - 1;     // the most recent such month inside the city's data
        if (span > 1) {   // a season: three months, e.g. "June to August 2026"
          const end = new Date(Date.UTC(y, mi + span - 1, 15));
          const start = new Date(Date.UTC(y, mi, 15)), sameYear = start.getUTCFullYear() === end.getUTCFullYear();
          return { kind: 'month', rel, y, m: mi, n: span, label: `${start.toLocaleDateString('en-GB', sameYear ? { month: 'long', timeZone: 'UTC' } : { month: 'long', year: 'numeric', timeZone: 'UTC' })} to ${end.toLocaleDateString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' })}` };
        }
        return { kind: 'month', rel, y, m: mi, label: monthLabel(y, mi) };
      }
      if (ym) return { kind: 'year', rel, y: +ym[1], label: ym[1] };
      if (/\b(so far|history|historical|two years|in the (city's )?data|over the years|bisher)\b/.test(t)) return { kind: 'history', label: 'Oct 2024 to 27 Oct 2026' };
      return null;
    }

    function interpret(q, ctx) {
      ctx = ctx || {};
      const t = norm(q);
      for (const g of GUARDS) if (g.re.test(t)) return { guard: g.id, t };
      const projects = detectProjects(t);
      const voice = detectVoice(t);
      // questions about the argument engine's results (the Human review tab): matched before the keyword scores
      for (const [id, re] of ENGINE_ROUTES) if (re.test(t)) return { t, intent: id, params: { projects, voice, period: null, t } };
      const scores = {};
      Object.entries(INTENT_KEYS).forEach(([id, re]) => { scores[id] = (t.match(re) || []).length; });
      // "new" with a named project asks for that project's items, not the four-project total
      if (scores.since && projects.length === 1 && /\b(new|latest|recent|neu|neue|neues|aktuell|happened)\b/.test(t) && !/\b(changed?|change)\b/.test(t)) scores.latest += 2;
      if (/\bwhy\b/.test(t)) scores.attention += 0.5;
      if (/\b(can i trust|trust|reliable|reliability|accurate|accuracy|how sure|zuverlässig)\b/.test(t)) scores.reliability += 2;   // "can I trust the stance labels" asks about trust, not stance
      if (projects.length >= 2) scores.compare += 1.5;
      if (scores.addressed) scores.addressed += 1;   // "has the city addressed these concerns" is about the answers, not the concerns
      if (scores.stance && /\b(increase|increased|grow|grew|rise|rose|more|less|fewer|change|changed|louder|quieter|stronger|weaker)\b/.test(t)) scores.stance += 1;   // "did opposition increase" is about positions
      // "what happened around the opening / in December 2025" asks about a moment in time, not about the newest items
      const per0 = detectPeriod(t, projects[0]);
      if (per0 && ['month', 'event', 'year'].includes(per0.kind) && /\b(what happened|happened|around|was ist passiert|passierte)\b/.test(t)) { scores.attention += 2; scores.latest = 0; scores.since = 0; }
      // "what changed since the council decision" is a before/after question about that date
      if (per0 && ['event', 'month', 'year'].includes(per0.kind) && per0.rel && scores.since && /\b(changed?|change)\b/.test(t)) scores.stance += 2;
      const ctxList = (SUGGEST[ctx.view] || SUGGEST.home);
      let intent = null, best = 0;
      Object.entries(scores).forEach(([id, s]) => { if (s && ctxList.includes(id)) s += 0.25; if (s > best) { best = s; intent = id; } });
      let follow = null;
      const last = ctx.last && ctx.last.intent && !ctx.last.guard ? ctx.last : null;
      if (last && FOLLOW_EVIDENCE.test(t) && (REFERS_BACK.test(t) || best === 0 || intent === 'gaps')) { intent = 'evidence'; follow = last; }
      else if (FOLLOW_METHOD.test(t)) { intent = 'method'; follow = last; }
      else if (!intent && last && (projects.length || /\b(and|what about|how about|und|same for)\b/.test(t))) { intent = last.intent; follow = last; }
      if (!intent) return { t, intent: null };
      const base = follow && follow.params ? follow.params : {};
      const period = detectPeriod(t, projects[0]) || (follow && intent === follow.intent ? base.period : null);
      return { t, intent, follow: follow ? follow.question : null, params: {
        projects: projects.length ? projects : (follow && intent === follow.intent && base.projects ? base.projects : []),
        voice: voice.length ? voice : (follow && intent === follow.intent ? base.voice || [] : []),
        period: period || null, t } };
    }

    /* ---------- 2. the answers ---------- */
    const P1 = p => (p.projects && p.projects[0]) || 'heilbronn_cablecar';
    const isCore = id => CORE.includes(id);
    const notYet = (d, text, extra) => done(d, Object.assign({ status: 'insufficient', text: `<b>Not yet.</b> ${text}` }, extra || {}));

    const ANSWER = {
      since(d, p, ctx) {
        if (!LM) return notYet(d, 'No collector check has run since the city\'s data ended.', { basis: 'No collector receipt', next: 'gaps' });
        // "since the council decision" or "since July" is not "since 27 Oct": never answer it with collector counts
        if (p.period && ['event', 'month', 'year'].includes(p.period.kind)) {
          if (ctx.hasH) return stanceSplit(d, p, ctx, P1(p), Object.assign({ rel: 'after' }, p.period));
          return notYet(d, `Changes since ${p.period.label} need the final analysis run; the collector only covers what was published after 27 Oct.`, { basis: versionLive(), next: 'since' });
        }
        const one = p.projects.length === 1 ? p.projects[0] : null;
        const scan = runIso(LM.collect_run_id) || LM.generated_at;
        const reuse = /no new scan/.test(LM.collect_note || '') ? ` The last update reused the scan of ${when(scan)}.` : '';
        if (one) {
          const x = lp(one);
          return done(d, {
            status: 'answered', read: `${PNAME[one]} · after 27 Oct 2026 · items found by the collector`,
            text: `For ${SHORT(one)}, the collector found <b>${d.F(x.d_after)} item${x.d_after === 1 ? '' : 's'} published after 27 Oct</b>. ${d.F(x.d_late)} older item${x.d_late === 1 ? ' was' : 's were'} found late and ${d.F(x.d_unknown)} ${x.d_unknown === 1 ? 'has' : 'have'} no date; neither group counts as new.`,
            more: (isCore(one) ? (x.not_this ? `The AI set ${d.F(x.not_this)} of all ${d.F(x.found)} found items aside as being about something else.` : '') : `These items have not been read by the AI yet: ${SHORT(one)} is a comparison city, not one of the four analysed projects.`) + reuse,
            proof: { kind: 'rows', rows: [['Published after 27 Oct', d.V(x.d_after), true], ['Older, found late', d.V(x.d_late)], ['Date unknown', d.V(x.d_unknown)]], unit: `${SHORT(one)}: items by date` },
            evidence: { label: `See the ${SHORT(one)} items`, kind: 'live', project: one }, report: { label: 'Open So far', hash: 'since' },
            basis: versionLive(), next: isCore(one) ? 'latest' : 'compare'
          });
        }
        const a = CORE.reduce((s, id) => s + lp(id).d_after, 0), late = CORE.reduce((s, id) => s + lp(id).d_late, 0), unk = CORE.reduce((s, id) => s + lp(id).d_unknown, 0);
        return done(d, {
          status: 'answered', read: 'The four projects · after 27 Oct 2026 · items found by the collector',
          text: `Since the city's data ended on 27 Oct, the collector found <b>${d.F(a)} items published after that date</b> about the four projects. ${lp('heilbronn_cablecar').d_after ? `${d.F(lp('heilbronn_cablecar').d_after)} of them concern Heilbronn's line.` : "None of them concerns Heilbronn's line."}`,
          more: `${d.F(late)} older item${late === 1 ? ' was' : 's were'} found late and ${d.F(unk)} ${unk === 1 ? 'has' : 'have'} no date; neither group counts as new.${reuse}`,
          proof: { kind: 'rows', rows: CORE.map(id => [PNAME[id], d.V(lp(id).d_after), id === 'heilbronn_cablecar']).sort((x, y) => y[1] - x[1]), unit: 'Items published after 27 Oct, per project' },
          evidence: { label: 'See the Heilbronn items', kind: 'live', project: 'heilbronn_cablecar' }, report: { label: 'Open So far', hash: 'since' },
          basis: versionLive(), next: 'latest'
        });
      },

      latest(d, p) {
        const id = P1(p);
        if (!LM) return notYet(d, 'No collector check has run yet.', { basis: 'No collector receipt', next: 'gaps' });
        const all = liveOf(id), after = all.filter(i => i.date_class === 'after'), about = after.filter(onTopic);
        const late = all.filter(i => i.date_class === 'late' && onTopic(i)).sort((a, b) => String(b.date).localeCompare(String(a.date)));
        const official = /\b(official|offiziell|tender|ausschreibung|vergabe|council|developments?)\b/.test(p.t || '');
        const isOfficial = i => i.kind !== 'social_link' && (['official', 'council_paper'].includes(i.kind) || /tender|vergabe|ratsinfo|rathaus|^(www\.)?(heilbronn|bonn)\.de$/.test(i.source || ''));
        const pool = official ? about.concat(late).filter(isOfficial) : about;
        const read = `${PNAME[id]} · after 27 Oct 2026${official ? ', plus older items found late' : ''} · ${official ? 'official pages and council papers' : 'items the AI reads as about this project'}`;
        if (!about.length && !(official && pool.length)) {
          return done(d, { status: 'answered', read, text: `<b>Nothing new about ${SHORT(id)} was found</b> in the sources checked since 27 Oct.`, more: 'A quiet check means nothing new in these sources, not that nobody talked.',
            evidence: { label: 'See what was checked', kind: 'gaps' }, basis: versionLive(), next: 'gaps' });
        }
        const shown = (official ? pool : about).slice().sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 4);
        const recs = shown.map(i => rec(d, i));
        if (!official && late[0] && recs.length < 4) recs.push(rec(d, late[0]));
        const newest = about.slice().sort((a, b) => String(b.date).localeCompare(String(a.date)))[0];
        return done(d, {
          status: isCore(id) ? 'answered' : 'partial', read,
          text: official
            ? `<b>${d.F(pool.length)} official item${pool.length === 1 ? '' : 's'}</b> about ${SHORT(id)} ${pool.length === 1 ? 'was' : 'were'} found by the collector${pool.some(i => i.date_class === 'late') ? ', including older ones found late' : ''}.`
            : `<b>${d.F(about.length)} item${about.length === 1 ? '' : 's'} published after 27 Oct</b> ${about.length === 1 ? 'is' : 'are'} about ${SHORT(id)}${newest ? `; the newest is from ${day(newest.date)}` : ''}.`,
          more: official
            ? 'Each item keeps its real publication date; older ones found late are not counted as new.'
            : (after.length > about.length ? `The AI set ${d.F(after.length - about.length)} more aside as off topic. ` : '')
              + (late.length ? `${d.F(late.length)} older item${late.length === 1 ? ' was' : 's were'} found late; ${late.length === 1 ? 'it keeps its' : 'they keep their'} real date and ${late.length === 1 ? 'is' : 'are'} not counted as new.` : ''),
          proof: { kind: 'recs', recs },
          evidence: { label: `See all ${SHORT(id)} items`, kind: 'live', project: id }, report: { label: 'Open So far', hash: 'since' },
          basis: versionLive() + ' · readings by AI, provisional', next: 'stance'
        });
      },

      stance(d, p, ctx) {
        const id = P1(p);
        const voices = p.voice || [];
        const per = p.period;
        if (ctx.hasH && isCore(id) && per && ['month', 'event', 'year'].includes(per.kind) && per.rel) return stanceSplit(d, p, ctx, id, per);
        const s = ctx.hasH ? stanceRow(id) : null;
        if (s) {
          const c = s.counts, rep = c.neutral_informative || 0, sup = c.support || 0, opp = c.oppose || 0, side = sup + opp;
          const head = rep / Math.max(1, s.n) > 0.5 ? 'Mostly reporting, not opinion.' : side / Math.max(1, s.n) > 0.5 ? 'Most labelled posts take a side.' : 'Reporting and taking a side are close.';
          // a lean is claimed only when chance alone would rarely give such a split (exact test against 50:50, p < 0.05)
          const lean = side < MIN_DIRECTION ? `Too few posts take a side (${d.F(side)}) to say which way they lean.`
            : binom2(opp, side) >= 0.05 ? 'Those that take a side are split.' : opp > sup ? 'Those that take a side lean against.' : 'Those that take a side lean in favour.';
          // speaker groups may exist for only part of the labelled posts (the pilot sample): say so
          const nVoice = POSTS.filter(x => x.project === id && x.stance && x.voice).length;
          const vcover = nVoice < 0.9 * s.n ? `Speaker groups are known for only ${d.F(nVoice)} of the ${d.F(s.n)} labelled posts. ` : '';
          // the speaker group the question asks about, or citizens vs news when it names both
          const vlist = voices.length ? voices : ['citizen'];
          const vtxt = vlist.map(v => {
            const r = stanceRow(id, v); if (!r) return '';
            const rc = r.counts;
            if (r.n < MIN_DIRECTION) return `Only ${d.F(r.n)} labelled posts come from ${VOICE[v]}, too few to say how they lean.`;
            return `Of ${d.F(r.n)} labelled posts from ${VOICE[v]}, ${d.F(rc.oppose || 0)} oppose, ${d.F(rc.support || 0)} support and ${d.F(rc.neutral_informative || 0)} only report${r.n < SMALL ? ' (small sample)' : ''}.`;
          }).filter(Boolean).join(' ');
          return done(d, {
            status: 'answered', read: `${PNAME[id]} · Oct 2024 to 27 Oct 2026 · labelled posts${voices.length ? ', by speaker group' : ''}`,
            text: `<b>${head}</b> Of ${d.F(s.n)} labelled ${SHORT(id)} posts, ${d.F(rep)} take no side, ${d.F(sup)} support and ${d.F(opp)} oppose. ${lean}`,
            more: `${vtxt ? vcover + vtxt : ''} Posts are not a poll of residents.`.trim(),
            proof: { kind: 'rows', rows: STANCE_KEYS.filter(k => c[k]).map(k => [STANCE_WORD[k], d.V(c[k]), k === 'support' ? 'acc' : k === 'oppose' ? 'ink' : '']), unit: `Labelled ${SHORT(id)} posts by position${s.n < SMALL ? ' · small sample' : ''}` },
            evidence: { label: 'See the labelled posts', kind: 'posts', project: id, stance: true, voice: voices.length === 1 ? voices[0] : null },
            report: { label: 'Open History', hash: 'history' }, basis: versionHist(ctx.mode), next: 'concerns'
          });
        }
        const h = LM && LM.per_project && LM.per_project[id];
        if (!h || !h.about) return notYet(d, `Positions for ${SHORT(id)} appear when the final analysis run is in.`, { basis: versionLive(), next: 'latest' });
        const sup = h.support || 0, opp = h.oppose || 0, rep = h.neutral_informative || 0;
        const few = h.about < MIN_DIRECTION;
        return done(d, {
          status: few ? 'insufficient' : 'partial', read: `${PNAME[id]} · found since 27 Oct 2026 · items the AI read (provisional)`,
          text: `<b>${few ? 'Too early to say.' : 'Only a first reading.'}</b> The analysis of the city's data is not in yet. Of the ${d.F(h.about)} ${SHORT(id)} items found since 27 Oct, the AI reads ${d.F(rep)} as reporting only, ${d.F(sup)} as support and ${d.F(opp)} as opposed.`,
          more: `${few ? `${d.F(h.about)} items are far too few to measure opinion, and items` : 'Items'} are not a poll of residents.`,
          proof: { kind: 'rows', rows: [['Report only', d.V(rep)], ['Support', d.V(sup), 'acc'], ['Oppose', d.V(opp), 'ink']].concat(h.unclear ? [['Unclear', d.V(h.unclear)]] : []), unit: `${SHORT(id)} items since 27 Oct, read by AI` },
          evidence: { label: 'See the items', kind: 'live', project: id }, basis: versionLive() + ' · readings by AI, provisional', next: 'latest'
        });
      },

      concerns(d, p, ctx) {
        const id = P1(p);
        const a = ctx.hasH && isCore(id) ? argRows(id).filter(r => r.n > 0).slice(0, 4) : [];
        if (!a.length) return notYet(d, `The arguments people raise about ${SHORT(id)} appear when the final analysis run is in.`, { basis: ctx.hasH ? versionHist(ctx.mode) : 'Awaiting the final analysis run', next: 'facts' });
        const top = a[0];
        return done(d, {
          status: 'answered', read: `${PNAME[id]} · Oct 2024 to 27 Oct 2026 · labelled posts that raise an argument`,
          text: `<b>${ARG[top.code] || top.code} comes up most</b>: ${d.F(top.n)} ${SHORT(id)} posts raise it.${a[1] ? ` Next is ${(ARG[a[1].code] || a[1].code).toLowerCase()} (${d.F(a[1].n)}).` : ''}`,
          more: 'Argument codes exist only for the pilot sample, so these are counts, not shares of all posts. ' + `Of the posts raising ${(ARG[top.code] || top.code).toLowerCase()}, ${d.F(top.oppose || 0)} oppose and ${d.F(top.support || 0)} support the project; the rest only report. One post can raise several arguments.`,
          proof: { kind: 'rows', rows: a.map((r, k) => [ARG[r.code] || r.code, d.V(r.n), k === 0]), unit: `${SHORT(id)} posts that raise it (pilot sample)` },
          evidence: { label: 'See the posts', kind: 'posts', project: id, arg: top.code }, report: { label: 'Open History', hash: 'history' },
          basis: versionHist(ctx.mode), next: id === 'heilbronn_cablecar' && ENG ? 'arg_main' : 'facts'   // the engine's argument map covers all posts, not only the pilot sample
        });
      },

      attention(d, p, ctx) {
        const id = P1(p), ev = events(id);
        let per = p.period;
        if (per && per.kind === 'event') { const x = new Date(per.date + 'T12:00:00Z'); per = { kind: 'month', y: x.getUTCFullYear(), m: x.getUTCMonth(), label: monthLabel(x.getUTCFullYear(), x.getUTCMonth()) }; }
        // a period covers one month, or a span of months (a season): per.n months from per.y / per.m
        const inMonth = (iso, y, m) => { const t = Date.parse(iso + 'T12:00:00Z'), a = Date.UTC(y, m, 1), b = Date.UTC(y, m + ((per && per.n) || 1), 1); return t >= a && t < b; };
        const evRecs = list => list.slice(-4).reverse().map(e => ({ id: e.event_id, date: e.date, title: e.title, source: host(e.source_url), url: e.source_url, tag: 'documented event' }));
        if (per && per.kind === 'month') {
          const evm = ev.filter(e => inMonth(e.date, per.y, per.m));
          if (!ctx.hasH) {
            return done(d, { status: evm.length ? 'partial' : 'insufficient', read: `${PNAME[id]} · ${per.label} · documented events`,
              text: `<b>The weekly volume appears when the final analysis run is in.</b> ${evm.length ? `What is documented in ${per.label}: ${d.F(evm.length)} public moment${evm.length === 1 ? '' : 's'} for ${SHORT(id)}.` : `No documented public moment for ${SHORT(id)} falls in ${per.label}.`}`,
              more: 'A date match alone never proves a cause.', proof: evm.length ? { kind: 'recs', recs: evRecs(evm) } : null,
              evidence: { label: 'Open the timeline', kind: 'view', hash: 'history' }, basis: 'Documented events with their sources (reference list)', next: 'facts' });
          }
          const wk = weekly(id).filter(w => inMonth(w.week, per.y, per.m)), all = weekly(id);
          if (!wk.length) return notYet(d, `${per.label} is outside the city's data (Oct 2024 to 27 Oct 2026). For what came after, ask what changed after 27 October.`, { basis: versionHist(ctx.mode), next: 'since' });
          const sum = wk.reduce((s, w) => s + w.stories, 0), avg = all.reduce((s, w) => s + w.stories, 0) / Math.max(1, all.length);
          const pk = peaks(id).filter(k => inMonth(k.week, per.y, per.m));
          const weak = (HIST.peaks || []).filter(k => k.project === id && k.weak && inMonth(k.week, per.y, per.m));
          const evById = new Map(ev.map(e => [e.event_id, e]));
          const why = pk.concat(weak).map(k => k.linked_event_id && evById.get(k.linked_event_id)).filter(Boolean)[0] || evm[0];
          return done(d, {
            status: 'answered', read: `${PNAME[id]} · ${per.label} · unique stories per week`,
            text: `In ${per.label}, ${SHORT(id)} had <b>${d.F(sum)} unique stories</b>, against about ${d.F(avg * wk.length, 0)} in an average stretch of ${d.F(wk.length)} weeks. ${pk.length ? `${d.F(pk.length)} week${pk.length === 1 ? '' : 's'} stand${pk.length === 1 ? 's' : ''} out as unusual.` : weak.length ? 'One week is higher than usual, but not clearly unusual.' : 'No week stands out as unusual.'}`,
            more: why ? `It coincides with a documented event on ${day(why.date)}: "${why.title}". A date match is not proof of cause.` : `No documented event falls in this ${per.n > 1 ? 'period' : 'month'}.`,
            proof: { kind: 'rows', rows: wk.map(w => [`Week of ${day(w.week)}`, d.V(w.stories), pk.some(k => k.week === w.week)]), unit: 'Unique stories per week (near-duplicates merged)' },
            evidence: { label: 'See the posts of that month', kind: 'posts', project: id, from: `${per.y}-${String(per.m + 1).padStart(2, '0')}-01`, to: `${per.y}-${String(per.m + 1).padStart(2, '0')}-31` },
            report: { label: 'Open History', hash: 'history' }, basis: versionHist(ctx.mode), next: 'stance'
          });
        }
        const pl = ctx.hasH ? placebo(id) : null;
        if (pl) {
          const pk = peaks(id), evById = new Map(ev.map(e => [e.event_id, e]));
          return done(d, {
            status: 'answered', read: `${PNAME[id]} · Oct 2024 to 27 Oct 2026 · weeks with unusual volume`,
            text: `<b>${d.F(pl.peaks_linked)} of ${d.F(pl.n_peaks)} weeks with unusual attention</b> fall on a documented city event. Random dates would match about ${d.F(pl.placebo_mean_linked, 1)} on average.`,
            more: 'This is a match in time, not proof of a cause. The list of events was partly built by reading the posts around these weeks, so the comparison with random dates flatters the result.',
            proof: { kind: 'recs', recs: pk.map(k => { const e = k.linked_event_id && evById.get(k.linked_event_id); return { id: 'peak:' + k.week, date: k.week, title: `${d.F(k.stories)} stories that week${e ? ' · ' + e.title : ''}`, source: e ? host(e.source_url) : '', url: e ? e.source_url : null, tag: e ? 'documented event' : 'no event found' }; }) },
            evidence: { label: 'See the posts in the peak weeks', kind: 'finding', i: 2 }, report: { label: 'Open History', hash: 'history' },
            basis: versionHist(ctx.mode), next: 'stance'
          });
        }
        if (!ev.length) return notYet(d, `Neither the weekly peaks nor documented events for ${SHORT(id)} are in yet.`, { basis: 'Reference list', next: 'since' });
        return done(d, {
          status: 'partial', read: `${PNAME[id]} · Oct 2024 to 27 Oct 2026 · documented events`,
          text: `<b>The weekly peaks appear when the final analysis run is in.</b> What is documented now: ${d.F(ev.length)} public moments for ${SHORT(id)}, from ${day(ev[0].date)} to ${day(ev[ev.length - 1].date)}.`,
          more: 'When the peaks are in, each one is checked against these dates. A date match alone does not prove a cause.',
          proof: { kind: 'recs', recs: evRecs(ev) }, evidence: { label: 'Open the timeline', kind: 'view', hash: 'history' },
          basis: 'Documented events with their sources (reference list)', next: 'facts'
        });
      },

      compare(d, p, ctx) {
        let ids = p.projects.length ? p.projects.slice() : ['bonn_cablecar'];
        if (ids.length === 1 && ids[0] !== 'heilbronn_cablecar') ids.unshift('heilbronn_cablecar');
        if (ids.length === 1) ids.push('bonn_cablecar');
        ids = ids.slice(0, 4);
        const label = ids.map(SHORT).join(' and ');
        const allCore = ids.every(isCore);
        if (ctx.hasH && allCore) {
          const rows = ids.map(id => ({ id, st: (projRow(id) || {}).stories || 0, s: stanceRow(id), cit: ((projRow(id) || {}).by_voice || {}).citizen || 0 }));
          return done(d, {
            status: 'answered', read: `${label} · Oct 2024 to 27 Oct 2026 · unique stories in the city's data`,
            text: rows.map((r, k) => `${k ? '' : '<b>'}${SHORT(r.id)} has ${d.F(r.st)} unique stories${k ? '' : '</b>'}`).join(', ') + '. Each project is at its own stage, so this compares attention, not opinion.',
            more: rows.map(r => r.s ? `${SHORT(r.id)}: ${d.F(r.s.counts.support || 0)} support and ${d.F(r.s.counts.oppose || 0)} oppose among ${d.F(r.s.n)} labelled posts${r.s.n < SMALL ? ' (small sample)' : ''}.` : '').filter(Boolean).join(' '),
            proof: { kind: 'rows', rows: rows.map(r => [PNAME[r.id], d.V(r.st), r.id === 'heilbronn_cablecar']), unit: "Unique stories in the city's data" },
            evidence: { label: 'Open History', kind: 'view', hash: 'history' }, basis: versionHist(ctx.mode), next: 'since'
          });
        }
        if (!LM) return notYet(d, 'The comparison needs the final analysis run or a collector check. Neither is in yet.', { basis: 'Nothing loaded', next: 'facts' });
        return done(d, {
          status: 'partial', read: `${label} · after 27 Oct 2026 · items found by the collector`,
          text: ids.map((id, k) => `${k ? '' : '<b>'}${SHORT(id)} has ${d.F(lp(id).d_after)} new items${k ? '' : '</b>'}`).join(', ') + ' since 27 Oct.' + (allCore ? " The longer comparison over the city's data appears when the final analysis run is in." : ''),
          more: (allCore ? '' : 'Comparison cities are found but not read by the AI. ') + 'Counts compare attention, not opinion; each city is at its own stage.',
          proof: { kind: 'rows', rows: ids.map(id => [PNAME[id], d.V(lp(id).d_after), id === 'heilbronn_cablecar']), unit: 'Items published after 27 Oct' },
          evidence: { label: `See the ${SHORT(ids[1] || ids[0])} items`, kind: 'live', project: ids[1] || ids[0] }, basis: versionLive(), next: 'attention'
        });
      },

      facts(d, p, ctx) {
        // "from the centre to the IPAI" is a figure of Heilbronn's line, not a question about the IPAI project
        const id = p.projects.includes('heilbronn_cablecar') || /\b(to|zum|zur|from) (the )?ipai\b/.test(p.t || '') ? 'heilbronn_cablecar' : P1(p);
        if (id !== 'heilbronn_cablecar') return notYet(d, `CityPulse holds official figures only for Heilbronn's line (the city's FAQ), not for ${SHORT(id)}.`, { status: 'insufficient', basis: 'heilbronn.de cable car FAQ', next: 'compare' });
        if (!FACTS.cost_invest) return notYet(d, 'The city\'s FAQ figures are not loaded.', { basis: 'Nothing loaded', next: 'since' });
        const f = k => FACTS[k] || {};
        const FIG = [['cost_invest', /\b(cost|costs|kosten|kostet|teuer|expensive|euro|eur|million|price|budget)\b/, x => `a first cost estimate of ${d.F(x.value)} million EUR`],
          ['funding_share', /\b(fund|funding|förder|subsid|who pays|pay for)\b/, x => `up to ${d.F(x.value)}% public funding from the state and federal government`],
          ['length_km', /\b(length|long is|km|strecke|route)\b/, x => `a route of ${d.F(x.value, 1)} km`],
          ['stations', /\b(station|stations|stationen|stops)\b/, x => `at least ${d.F(x.value)} stations`],
          ['travel_time_min', /\b(minutes|travel time|fahrzeit|how fast|how long does)\b/, x => `${d.F(x.value)} minutes from the city centre to the IPAI`],
          ['capacity_pphpd', /\b(capacity|passengers|kapazität)\b/, x => `${d.F(x.value)} passengers per hour and direction`],
          ['cabin_size', /\b(cabin|cabins|gondel|persons per)\b/, x => `${d.F(x.value)} persons per cabin`],
          ['mast_height_m', /\b(mast|masts|height|tall)\b/, x => `masts up to ${d.F(x.value)} m high`],
          ['start_operation', /\b(when (will|could|can|does|do|is)|ride it|start of operation|eröffnung|in betrieb|open|opens|ready|wann)\b/, x => `a realistic start of operation in the ${String(x.value).replace(/^early /, 'early ')}`]];
        const asked = FIG.filter(([k, re]) => re.test(p.t || '') && FACTS[k]);
        const differs = ctx.hasH ? (HIST.faq_figure_differs || []).filter(x => asked.some(([k]) => k === x.figure_id)) : [];
        const lead = asked.length ? asked.slice(0, 2) : [FIG[0], FIG[1]];
        const more = [];
        lead.forEach(([k]) => { if (f(k).note && k === 'length_km') more.push('The same page also says "about 5" km.'); if (k === 'stations' && f(k).note) more.push('The page says "at least six", possibly more.'); });
        if (differs.length) more.push(`${d.F(differs.length)} post${differs.length === 1 ? '' : 's'} in the data cite${differs.length === 1 ? 's' : ''} a different figure (for example "${differs[0].post_value}").`);
        more.push('These are the city\'s own statements; CityPulse never uses them to decide who is for or against.');
        const dl = [['Investment, first estimate', `${f('cost_invest').value} million EUR`], ['Public funding', `up to ${f('funding_share').value}%`],
          ['Length', `${f('length_km').value} km`], ['Stations', `at least ${f('stations').value}`], ['Centre to IPAI', `${f('travel_time_min').value} minutes`], ['Start of operation', f('start_operation').value]];
        return done(d, {
          status: 'answered', read: `Heilbronn cable car · the city's FAQ · ${asked.length ? asked.map(([k]) => f(k).label[0].toLowerCase() + f(k).label.slice(1)).slice(0, 2).join(', ') : 'main figures'}`,
          text: `The city's FAQ gives <b>${lead.map(([k, , fn]) => fn(f(k))).join('</b> and <b>')}</b>.`,
          more: more.join(' '),
          proof: { kind: 'dl', items: dl },
          evidence: { label: 'Open the city\'s FAQ', kind: 'url', url: FACTS_URL },
          basis: `heilbronn.de cable car FAQ · figures valid from ${day(lead.map(([k]) => f(k).valid_from).sort().pop())}`, next: 'concerns'
        });
      },

      // "has the city already answered these concerns?": the pipeline export links each FAQ answer to the posts that raise
      // the concern it answers (pipeline/CONTRACT.md faq_matches, match_type concern_answered)
      addressed(d, p, ctx) {
        const faq = ctx.hasH ? (HIST.faq || []).filter(f => f.project === 'heilbronn_cablecar') : [];
        if (!faq.length) return notYet(d, 'Matching the concerns in the posts to the city\'s FAQ answers appears when the final analysis run is in.', { basis: 'heilbronn.de cable car FAQ', next: 'facts' });
        const top = faq.filter(f => f.n_concern_posts > 0).sort((a, b) => b.n_concern_posts - a.n_concern_posts);
        const none = faq.filter(f => !f.n_concern_posts);
        const codes = new Set(faq.map(f => f.argument_code));
        const missing = argRows('heilbronn_cablecar').filter(a => a.n > 0 && !codes.has(a.code)).map(a => (ARG[a.code] || a.code).toLowerCase());
        const differs = (HIST.faq_figure_differs || []).length;
        const q = f => `"${f.question_en}"`;
        return done(d, {
          status: 'answered', read: "Heilbronn cable car · Oct 2024 to 27 Oct 2026 · the city's FAQ answers and the posts raising the same concern",
          text: `<b>Mostly yes.</b> The city's FAQ has ${d.F(faq.length)} answers, and the concerns raised most already have one: ${top.slice(0, 3).map(f => `${q(f)} (${d.F(f.n_concern_posts)} posts)`).join(', ')}.`,
          more: `${missing.length ? `Concerns with no FAQ answer: ${missing.join(', ')}. ` : 'Every kind of argument in the posts has at least one FAQ answer. '}`
            + `${d.F(none.length)} FAQ answers match no concern in the posts.${differs ? ` ${d.F(differs)} post${differs === 1 ? '' : 's'} state${differs === 1 ? 's' : ''} a figure that differs from the FAQ.` : ''} Whether people find the answers convincing is not measured; the matching is done by the pipeline's rules.`,
          proof: { kind: 'rows', rows: top.slice(0, 5).map((f, k) => [f.question_en.length > 42 ? f.question_en.slice(0, 40) + '…' : f.question_en, d.V(f.n_concern_posts), k === 0]), unit: 'Posts raising a concern that this FAQ answer already covers' },
          evidence: { label: 'Open the city\'s FAQ', kind: 'url', url: FACTS_URL }, report: { label: 'Open History', hash: 'history' },
          basis: versionHist(ctx.mode) + ' · heilbronn.de cable car FAQ', next: 'concerns'
        });
      },

      gaps(d) {
        if (!LM) return notYet(d, 'No collector check has run yet.', { basis: 'No collector receipt', next: 'since' });
        const clean = (LM.sources_clean || []).filter(s => s !== 'date_recovery'), probs = LM.sources_problems || [];
        const gaps = (LM.coverage_gaps || []).filter(g => /^NOT COVERED BY DESIGN/.test(g)).map(g => g.replace(/^NOT COVERED BY DESIGN:\s*/, '')).map(g => { const k = g.indexOf(':'); return k > 0 ? g.slice(0, k) : g; });
        const st = LM.collect_status;
        return done(d, {
          status: 'answered', read: 'All projects · the last collector check · sources asked and known gaps',
          text: `The last check asked ${d.F(clean.length)} kinds of sources${probs.length ? ` and ${d.F(probs.length)} did not answer fully` : ', and all of them answered'}. <b>By design it cannot see ${gaps.slice(0, 2).join(' or ')}</b>, among ${d.F(gaps.length)} known gaps.`,
          more: st === 'failed' ? 'That check failed, so the reports still show the last successful one.' : st === 'partial' ? 'Some sources answered only partly; the reports say so.' : 'Missing sources mean fewer items, never invented ones.',
          proof: { kind: 'two', left: { title: 'Asked', items: clean.map(s => SOURCE[s] || s).concat(probs.map(s => s + ' (partly)')) }, right: { title: 'Cannot see', items: gaps } },
          evidence: { label: 'Why each gap exists', kind: 'gaps' }, report: { label: 'Open Today', hash: 'today' },
          basis: versionLive(), next: 'since'
        });
      },

      reliability(d, p, ctx) {
        if (ctx.hasH) {
          // in the final run, the labels shown come from one labeller: report its agreement with the earlier independent runs,
          // not the earlier runs' agreement with each other
          const runs = (HIST.meta && HIST.meta.label_runs) || [];
          const fin = ctx.mode === 'final' ? runs.find(r => !/^(pilot_|rules_|student_)/.test(r)) : null;
          const rel = (HIST.reliability || []).filter(r => /^agreement\./.test(r.metric_id));
          const fr = fin ? rel.filter(r => r.metric_id.includes(fin)) : [];
          if (fr.length) {
            const fs = fr.filter(r => /^agreement\.stance_relevant/.test(r.metric_id)), fp = fr.filter(r => /^agreement\.project\./.test(r.metric_id));
            const others = rel.filter(r => /^agreement\.stance_relevant/.test(r.metric_id) && !r.metric_id.includes(fin));
            const rng = list => [Math.min(...list.map(r => r.value)), Math.max(...list.map(r => r.value))];
            if (fs.length && fp.length) {
              const [slo, shi] = rng(fs), [plo, phi] = rng(fp);
              const tone = (HIST.reliability || []).find(r => r.metric_id === 'vendor_vs_stance.match');
              return done(d, {
                status: 'answered', read: 'All four projects · the final analysis run · agreement of its labeller with three earlier independent AI runs',
                text: `The final labels agree with three earlier, independent AI runs on <b>which project a post is about</b> with kappa ${d.F(plo, 2)} to ${d.F(phi, 2)}, and on <b>its position</b> with kappa ${d.F(slo, 2)} to ${d.F(shi, 2)} on relevant posts (about ${d.F(Math.min(...fs.map(r => r.n)))} posts).`,
                more: `Agreement shows the readings are consistent, not that they are right; none is checked against people yet.${others.length ? ` The earlier runs agreed with each other at kappa ${d.F(rng(others)[0], 2)} to ${d.F(rng(others)[1], 2)}.` : ''}${tone ? ` The monitoring tool's tone score matched the position in only ${d.P(tone.value)} of ${d.F(tone.n)} posts, which is why CityPulse reads position, not tone.` : ''}`,
                proof: { kind: 'rows', rows: fs.map(r => [`vs ${r.metric_id.split('~').find(x => !x.includes(fin)).replace(/^agreement\.stance_relevant\./, '').replace(/_cb1$/, '').replace('pilot_', 'pilot ')} (n ${d.F(r.n)})`, d.V(r.value, 2), true]), unit: 'Kappa for position, final labels against each earlier run (1 = always agree)' },
                evidence: { label: 'How it works', kind: 'method' }, basis: versionHist(ctx.mode), next: 'stance'
              });
            }
          }
          const rs = rel.filter(r => /^agreement\.stance_relevant/.test(r.metric_id));
          const ps = rel.filter(r => /^agreement\.project\./.test(r.metric_id));
          if (rs.length) {
            const lo = Math.min(...rs.map(r => r.value)), hi = Math.max(...rs.map(r => r.value));
            const plo = Math.min(...ps.map(r => r.value)), phi = Math.max(...ps.map(r => r.value));
            const tone = (HIST.reliability || []).find(r => r.metric_id === 'vendor_vs_stance.match');
            return done(d, {
              status: 'answered', read: 'All four projects · the analysis run · agreement between independent AI runs',
              text: `Independent AI runs agree on <b>which project a post is about</b> with kappa ${d.F(plo, 2)} to ${d.F(phi, 2)}, and on <b>its position</b> with kappa ${d.F(lo, 2)} to ${d.F(hi, 2)} on relevant posts.`,
              more: `Agreement shows the readings are consistent, not that they are right; they are not yet checked against people.${tone ? ` The monitoring tool's tone score matched the position in only ${d.P(tone.value)} of ${d.F(tone.n)} posts, which is why CityPulse reads position, not tone.` : ''} "Unclear" means a post shows no position; "runs disagreed" means the readings did not agree and the post is held out.`,
              proof: { kind: 'rows', rows: rs.map((r, k) => [`Run pair ${k + 1} (n ${d.F(r.n)})`, d.V(r.value, 2), true]), unit: 'Kappa for position between two AI runs (1 = always agree)' },
              evidence: { label: 'How it works', kind: 'method' }, basis: versionHist(ctx.mode), next: 'stance'
            });
          }
        }
        const lab = ITEMS.filter(i => i.label_state === 'labelled');
        if (!lab.length) return notYet(d, 'No readings are in yet.', { basis: versionLive(), next: 'since' });
        const unanimous = lab.filter(i => i.agreement_stance === 1).length, uncertain = lab.filter(i => i.stance === 'uncertain').length;
        return done(d, {
          status: 'partial', read: 'New items since 27 Oct · the collector\'s provisional readings · agreement between three AI runs',
          text: `Each new item is read three times by the AI. <b>${d.F(unanimous)} of ${d.F(lab.length)} readings were unanimous</b>${uncertain ? `, and ${d.F(uncertain)} where the runs disagreed are held out` : ''}.`,
          more: 'Agreement shows consistency, not correctness: these readings are not checked against people, and the full analysis of the city\'s data is not in yet. "Unclear" means an item shows no position; it is not the same as the runs disagreeing.',
          proof: { kind: 'rows', rows: [['All three runs agree', d.V(unanimous), true], ['Two of three agree', d.V(lab.length - unanimous - uncertain)]].concat(uncertain ? [['Runs disagreed', d.V(uncertain)]] : []), unit: 'Readings of items found since 27 Oct' },
          evidence: { label: 'How it works', kind: 'method' }, basis: versionLive(), next: 'stance'
        });
      },

      /* ---------- the argument engine (Human review tab). Heilbronn only; every number recorded through F() ---------- */
      arg_new(d, p) {
        const r = ENG && ENG.replay();
        if (!r) return notYet(d, 'The argument engine\'s results are not on this page yet.', { basis: 'No argument engine snapshot', next: 'concerns' });
        const other = (p.projects || []).find(x => x !== 'heilbronn_cablecar');
        if (other) return engOnlyHn(d, other);
        const k = r.counts, fl = ENG.concerns().filter(c => c.flagged), cut = day(r.cutoff);
        const read = `Heilbronn cable car · claims after ${cut} · new groups in the argument engine's replay`;
        if (!fl.length) {
          return done(d, { status: 'answered', read,
            text: `<b>No concern was flagged</b> in the ${d.F(k.n_claims)} Heilbronn claims after ${cut}. ${d.F(k.opens_new)} opened a new group and ${d.F(k.ambiguous)} need review, but none was raised by ${d.F(ENG.MIN_VOICES)} or more independent voices.`,
            more: replayNote(r), evidence: { label: 'Open Human review', kind: 'view', hash: 'review' }, basis: versionEng(), next: 'arg_main' });
        }
        return done(d, {
          status: 'answered', read,
          text: `<b>${d.F(fl.length)} new concern${fl.length === 1 ? ' was' : 's were'} flagged</b> after ${cut}, each raised by ${d.F(ENG.MIN_VOICES)} or more independent voices. Of the next ${d.F(k.n_claims)} Heilbronn claims, ${d.F(k.opens_new)} opened a new group and ${d.F(k.ambiguous)} need review.`,
          more: `Flagged: ${fl.slice(0, 4).map(c => qt(c.label)).join(', ')}. ${replayNote(r)} Flagged means a person should look at it, not that it is established.`,
          proof: { kind: 'rows', rows: fl.slice(0, 4).map((c, i) => [c.label, d.V(c.n_voices), i === 0]), unit: 'Independent voices per flagged concern' },
          evidence: { label: 'See their posts', kind: 'concern', ids: fl.map(c => c.id) }, report: { label: 'Open Human review', hash: 'review' },
          basis: versionEng(), next: 'arg_concern'
        });
      },

      arg_concern(d, p) {
        const r = ENG && ENG.replay();
        if (!r) return notYet(d, 'The argument engine\'s results are not on this page yet.', { basis: 'No argument engine snapshot', next: 'concerns' });
        const other = (p.projects || []).find(x => x !== 'heilbronn_cablecar');
        if (other) return engOnlyHn(d, other);
        const cut = day(r.cutoff), c = ENG.findConcern(/hospital|clinic|klinik|krankenhaus|löwenstein/i);
        const read = `Heilbronn cable car · claims after ${cut} · one group in the argument engine's replay`;
        if (!c) return done(d, { status: 'insufficient', read, text: `<b>No hospital concern is in the engine's results</b> for Heilbronn after ${cut}.`, more: 'CityPulse does not guess. Ask what new concerns appeared to see what is there.', basis: versionEng(), next: 'arg_new' });
        const verdict = { new_emerging: 'Yes, as far as the engine can tell.', new_single: 'Possibly, but only one voice so far.', ambiguous: 'Not clearly.', gaining: 'No, it is a known argument.', recurring: 'No, it is a known argument.' }[c.state] || 'The engine cannot say.';
        const how = { new_emerging: 'found no equivalent among older claims', new_single: 'found no equivalent among older claims', ambiguous: 'scores it between its two cut-offs, so it may be a variant of a known argument',
          gaining: 'matched it to an argument made before the cut-off', recurring: 'matched it to an argument made before the cut-off' }[c.state] || 'gives no clear reading';
        const co = c.closest;
        return done(d, {
          status: 'answered', read,
          text: `<b>${verdict}</b> ${qt(c.label)} was ${c.flagged && c.flagged_at === c.first_seen ? `first seen and flagged on ${day(c.first_seen)}` : `first seen on ${day(c.first_seen)}${c.flagged ? ` and flagged on ${day(c.flagged_at)}` : ''}`}; ${d.F(c.n_voices)} independent voice${c.n_voices === 1 ? ' has' : 's have'} raised it. The engine ${how}.`,
          more: `${co ? `The closest older claim is ${qt(co.claim)} (${co.domain && !/\d/.test(co.domain) ? co.domain + ', ' : ''}${day(co.date)}). ` : ''}A person should decide. ${replayNote(r)}`,
          proof: { kind: 'recs', recs: c.claims.slice(0, 4).map(x => recClaim(d, x)) },
          evidence: { label: 'See its posts', kind: 'concern', ids: [c.id] }, report: { label: 'Open Human review', hash: 'review' },
          basis: versionEng(), next: 'arg_new'
        });
      },

      // the arguments in items published after 27 Oct: the engine's collector runs, with the same rule as the Human review
      // tab's "Since 27 Oct" card (finished runs, each point once, Heilbronn only, known arguments left out, found-late apart)
      arg_since(d, p) {
        const runs = ENG ? ENG.collectorRuns().filter(r => r.status === 'done') : [];
        if (!runs.length) return notYet(d, 'No collector run has reached the argument engine yet.', { basis: ENG ? versionEng(true) : 'No argument engine snapshot', next: 'since' });
        const other = (p.projects || []).find(x => x !== 'heilbronn_cablecar');
        if (other) return engOnlyHn(d, other);
        const EDGE = '2026-10-27', seen = new Set(), all = [];
        runs.forEach(r => r.concerns.forEach(k => { if (!seen.has(k.id)) { seen.add(k.id); all.push(k); } }));
        const c = {}; runs.forEach(r => ['claims', 'familiar', 'new', 'ambiguous'].forEach(k => { c[k] = (c[k] || 0) + (r.counts[k] || 0); }));
        const fresh = all.filter(x => x.state !== 'recurring' && (!x.project || x.project === 'heilbronn_cablecar'));
        const after = fresh.filter(x => (x.first_seen || '') >= EDGE).sort((a, b) => String(b.first_seen).localeCompare(String(a.first_seen)));
        const late = fresh.filter(x => (x.first_seen || '') < EDGE);
        const elsewhere = all.filter(x => x.project && x.project !== 'heilbronn_cablecar' && x.state !== 'recurring' && (x.first_seen || '') >= EDGE);
        const STATE = { ambiguous: 'to review', new_single: 'new, one voice', new_emerging: 'new, several voices', gaining: 'gaining', recurring: 'known' };
        const latest = runs[0].finished_at || runs[0].created_at;
        const basis = `Argument engine · ${runs.length} collector run${runs.length === 1 ? '' : 's'}, latest ${when(latest)}${ENG.status().version ? ` · matcher ${ENG.status().version}` : ''} · provisional`;
        const read = 'Heilbronn cable car · published after 27 Oct 2026 · points the argument engine found in collector items';
        const tail = `${late.length ? `${d.F(late.length)} more ${late.length === 1 ? 'was' : 'were'} found late but published earlier, so not counted. ` : ''}`
          + `${elsewhere.length ? `Elsewhere (other cities), ${d.F(elsewhere.length)} point${elsewhere.length === 1 ? '' : 's'} published after 27 Oct, kept apart. ` : ''}`
          + `"To review" means the engine could not tell whether it is a known argument; a person should decide.`;
        if (!after.length) {
          return done(d, { status: 'answered', read, text: '<b>Nothing new on Heilbronn published after 27 Oct</b> reached the argument engine, in the sources checked.',
            more: `Across all projects the runs held ${d.F(c.claims || 0)} claims; ${d.F(c.familiar || 0)} matched a known argument. ${tail.replace(/\s*"To review" means[^]*$/, '')}`.trim(),
            evidence: { label: 'Open Human review', kind: 'view', hash: 'review' }, basis, next: 'since' });
        }
        const known = (c.familiar || 0);
        return done(d, {
          status: 'answered', read,
          text: `<b>${d.F(after.length)} new point${after.length === 1 ? '' : 's'} about Heilbronn</b> in items published after 27 Oct: ${after.slice(0, 2).map(x => `${qt(x.label)} (${STATE[x.state] || x.state})`).join(' and ')}.`,
          more: `Across all projects the collector runs held ${d.F(c.claims || 0)} claims; ${d.F(known)} matched an argument the engine already knew. ${tail}`,
          proof: { kind: 'recs', recs: after.slice(0, 5).map(x => { const cl = x.claims[0] || {}; return { id: 'concern:' + x.id, date: x.first_seen, title: x.label, source: cl.domain || '', url: cl.url || null, tag: STATE[x.state] || x.state }; }) },
          evidence: { label: 'Open Human review', kind: 'view', hash: 'review' }, basis, next: 'since'
        });
      },

      arg_main(d, p) {
        const kb = ENG && ENG.knownBefore(), r = ENG && ENG.replay();
        const other = (p.projects || []).find(x => x !== 'heilbronn_cablecar');
        if (other && ENG) return engOnlyHn(d, other);
        // whole period first: the engine's argument families over all its Heilbronn posts (overview_hn.top_arguments)
        const ov = env.engine && env.engine.overview_hn, em = (env.engine && env.engine.meta) || {};
        const fam = (ov && Array.isArray(ov.top_arguments) ? ov.top_arguments : [])
          .filter(f => f && typeof f.name === 'string' && Number.isFinite(f.n) && f.n > 0)
          .map(f => ({ name: f.name.replace(/(^|\s)@[A-Za-z0-9_.]{2,}/g, '$1@[USER]'), n: f.n, voices: Number.isFinite(f.n_voices) ? f.n_voices : null,
            pro: Number.isFinite(f.pro) ? f.pro : null, contra: Number.isFinite(f.contra) ? f.contra : null }))
          .sort((a, b) => b.n - a.n);
        if (fam.length) {
          const t = fam[0], span = em.date_min && em.date_max ? `${day(em.date_min)} to ${day(em.date_max)}` : 'the whole engine data';
          // "most often against" looks at every family, not only the ten largest
          const allFam = (env.engine.families_hn && Array.isArray(env.engine.families_hn.items) ? env.engine.families_hn.items : [])
            .filter(f => f && typeof f.name === 'string' && Number.isFinite(f.contra))
            .map(f => ({ name: f.name.replace(/(^|\s)@[A-Za-z0-9_.]{2,}/g, '$1@[USER]'), contra: f.contra }));
          const against = (allFam.length ? allFam : fam.filter(f => f.contra != null)).sort((a, b) => b.contra - a.contra)[0];
          return done(d, {
            status: 'answered', read: `Heilbronn cable car · ${span} · claims per argument family in the argument engine`,
            text: `<b>${qt(t.name)} is the argument made most often</b>: ${d.F(t.n)} claims${t.voices != null ? ` from ${d.F(t.voices)} independent voices` : ''}.${fam[1] ? ` Next is ${qt(fam[1].name)} (${d.F(fam[1].n)}).` : ''}`,
            more: `${against && against.contra ? `The argument raised most often against the line: ${qt(against.name)} (${d.F(against.contra)} claims against). ` : ''}`
              + `The engine groups differently worded versions of the same argument${Number.isFinite(ov.n_claims) ? ` (${d.F(ov.n_claims)} Heilbronn claims in all)` : ''}. Claims are counted, not people, and the grouping is an AI result, not yet checked by people.`,
            proof: { kind: 'rows', rows: fam.slice(0, 5).map((f, i) => [f.name, d.V(f.n), i === 0]), unit: 'Claims per argument family, Heilbronn' },
            evidence: { label: 'Open Human review', kind: 'view', hash: 'review' },
            basis: versionEng(true), next: 'arg_new'
          });
        }
        if (!kb || !r) return notYet(d, 'The argument engine\'s results are not on this page yet.', { basis: 'No argument engine snapshot', next: 'concerns' });
        const cut = day(r.cutoff), top = kb.top.slice(0, 5);
        return done(d, {
          status: 'answered', read: `Heilbronn cable car · before ${cut} · claims per argument in the argument engine`,
          text: `<b>${qt(top[0].name)} comes up most</b>: ${d.F(top[0].n)}${kb.n_claims != null ? ` of ${d.F(kb.n_claims)}` : ''} Heilbronn claims before ${cut}.${top[1] ? ` Next is ${qt(top[1].name)} (${d.F(top[1].n)}).` : ''}`,
          more: `The engine counts differently worded versions of the same argument together${kb.n_posts != null ? `; these claims come from ${d.F(kb.n_posts)} posts` : ''}. Counts are claims, not people, and one post can make several.`,
          proof: { kind: 'rows', rows: top.map((f, i) => [f.name, d.V(f.n), i === 0]), unit: `Claims per argument, Heilbronn, before ${cut}` },
          evidence: { label: 'Open Human review', kind: 'view', hash: 'review' },
          basis: versionEng(), next: 'arg_new'
        });
      },

      arg_rel(d) {
        const m = ENG && ENG.matcher();
        if (!m) return notYet(d, 'The argument matcher\'s test results are not on this page yet.', { basis: ENG ? versionEng() : 'No argument engine snapshot', next: 'reliability' });
        const ref = { opus: 'Claude Opus' }[m.reference] || m.reference || 'an AI model', lk = ENG.leakage() || {};
        return done(d, {
          status: 'answered', read: `The argument matcher · held-out test pairs · agreement with ${ref}`,
          text: `<b>The matcher scores pair F1 ${d.F(m.f1, 2)}</b> (likely range ${d.F(m.lo, 2)} to ${d.F(m.hi, 2)}), against ${d.F(m.base, 2)} for plain embedding similarity, on ${d.F(m.n_pairs)} test pairs. This is agreement with an AI reference (${ref}), not yet checked by people.`,
          more: `${m.wrongly_new != null ? `Known arguments wrongly called new: ${d.F(m.wrongly_new)} of ${d.F(m.wrongly_new_of)} test claims. ` : ''}${lk.time_order_train_cal_test === true && lk.test_oldest_query ? `The test claims were published from ${day(lk.test_oldest_query)}, after everything the matcher was trained or tuned on. ` : ''}The score measures agreement on which pairs make the same argument; it is not accuracy.`,
          proof: { kind: 'rows', rows: [['CityPulse matcher', d.V(m.f1, 2), true], ['Plain embedding similarity', d.V(m.base, 2)]], unit: 'Pair F1 on held-out test pairs' },
          evidence: { label: 'How it was tested', kind: 'engine_method' }, report: { label: 'Open Human review', hash: 'review' },
          basis: versionEng(), next: 'arg_new'
        });
      },

      evidence(d, p, ctx) {
        const last = ctx.last;
        if (!last) return done(d, { status: 'unsupported', text: '<b>Which answer?</b> Ask a question first; then "show the sources" opens the items behind it.', next: 'since' });
        const recs = (last.ids || []).map(i => LIVE_BY_ID.get(i) ? rec(d, LIVE_BY_ID.get(i)) : POST_BY_ID.get(i) ? recPost(d, POST_BY_ID.get(i)) : CLAIM_BY_ID.get(i) ? recClaim(d, CLAIM_BY_ID.get(i)) : null).filter(Boolean).slice(0, 6);
        return done(d, {
          status: 'answered', read: `Follow-up to "${last.question}" · the records behind that answer`,
          text: recs.length ? `<b>${d.F(recs.length)} record${recs.length === 1 ? '' : 's'}</b> stand behind that answer; each opens at its source. The button below opens the full list.` : last.evidence && last.evidence.kind === 'gaps'
              ? '<b>No records stand behind that answer</b>: nothing new was found. The button below shows which sources were checked.'
              : '<b>That answer is a count.</b> The button below opens every item behind it.',
          proof: recs.length ? { kind: 'recs', recs } : null, evidence: last.evidence, basis: last.basis, next: last.next
        });
      },

      method(d, p, ctx) {
        const last = ctx.last;
        if (!last || !last.read) {
          return done(d, { status: 'answered', read: 'How CityPulse answers', text: '<b>Every answer is counted, not written by an AI.</b> The numbers come from the analysis export or the collector receipt, each answer names its source under "From", and the evidence button opens the items behind it.',
            more: 'Before an answer is shown, every number in it is checked against the data; if one does not match, the answer is not shown.', basis: 'How CityPulse answers', next: 'since' });
        }
        return done(d, {
          status: 'answered', read: `Follow-up to "${last.question}"`,
          text: `<b>That answer counts ${(last.read.split(' · ')[2] || 'items')}</b> for ${last.read.split(' · ')[0].replace(/^(The|All|New) /, m => m.toLowerCase())}, over ${last.read.split(' · ')[1] || 'the period shown'}.`,
          more: 'Its numbers were computed from the source named under "From" and checked against it before they were shown; none was written by an AI.',
          evidence: last.evidence, basis: last.basis, next: last.next
        });
      }
    };

    /* exact tests, so a "lean" or a "change" is claimed only when chance alone would rarely produce it */
    const LF = [0];
    const lf = n => { for (let i = LF.length; i <= n; i++) LF[i] = LF[i - 1] + Math.log(i); return LF[n]; };
    function binom2(k, n) {      // two-sided exact binomial test against 50:50
      const pk = j => Math.exp(lf(n) - lf(j) - lf(n - j) - n * Math.LN2), p0 = pk(k);
      let s = 0; for (let j = 0; j <= n; j++) { const q = pk(j); if (q <= p0 * (1 + 1e-7)) s += q; }
      return Math.min(1, s);
    }
    function fisher2(a, b, c, d) { // two-sided Fisher's exact test for [[a, b], [c, d]]
      const n = a + b + c + d, r1 = a + b, c1 = a + c;
      const pk = k => Math.exp(lf(r1) + lf(n - r1) + lf(c1) + lf(n - c1) - lf(n) - lf(k) - lf(r1 - k) - lf(c1 - k) - lf(n - r1 - c1 + k));
      const p0 = pk(a); let s = 0;
      for (let k = Math.max(0, c1 - (n - r1)); k <= Math.min(r1, c1); k++) { const q = pk(k); if (q <= p0 * (1 + 1e-7)) s += q; }
      return Math.min(1, s);
    }

    function stanceSplit(d, p, ctx, id, per) {
      let from, to;
      if (per.kind === 'event') from = per.date;
      else if (per.kind === 'month') from = `${per.y}-${String(per.m + 1).padStart(2, '0')}-01`;
      else from = `${per.y}-01-01`;
      const posts = POSTS.filter(x => x.project === id && x.stance && STANCE_KEYS.includes(x.stance));
      const cnt = list => { const c = { n: list.length }; STANCE_KEYS.forEach(k => { c[k] = list.filter(x => x.stance === k).length; }); return c; };
      const A = cnt(posts.filter(x => x.date >= from)), B = cnt(posts.filter(x => x.date < from));
      const fewA = A.n < MIN_DIRECTION, fewB = B.n < MIN_DIRECTION;
      const wk = weekly(id), avg = list => list.length ? list.reduce((s, w) => s + w.stories, 0) / list.length : 0;
      const wA = avg(wk.filter(w => w.week >= from)), wB = avg(wk.filter(w => w.week < from));
      // a change is claimed only if chance alone would rarely produce it (Fisher's exact test, p < 0.05)
      const pA = A.n ? A.oppose / A.n : 0, pB = B.n ? B.oppose / B.n : 0;
      const pv = fewA || fewB ? 1 : fisher2(A.oppose, A.n - A.oppose, B.oppose, B.n - B.oppose);
      const head = fewA || fewB ? 'Too few labelled posts on one side of the date to say whether it changed.'
        : pv < 0.05 ? `Opposition makes up a ${pA > pB ? 'larger' : 'smaller'} share after it (${d.P(pA)} against ${d.P(pB)}).`
        : Math.abs(pA - pB) >= 0.05 ? `Opposition is a little ${pA > pB ? 'higher' : 'lower'} after it (${d.P(pA)} against ${d.P(pB)}), but with this few posts the gap could be chance.`
        : 'The share of opposition is about the same before and after.';
      return done(d, {
        status: fewA || fewB ? 'insufficient' : 'answered', read: `${PNAME[id]} · before vs from ${per.kind === 'event' ? day(from) : per.label} · labelled posts`,
        text: `<b>${head}</b> From ${per.kind === 'event' ? per.label : per.label}: ${d.F(A.oppose)} of ${d.F(A.n)} labelled posts oppose and ${d.F(A.support)} support. Before: ${d.F(B.oppose)} of ${d.F(B.n)} oppose and ${d.F(B.support)} support.`,
        more: `Attention: about ${d.F(wA, 1)} unique stories a week from then on, ${d.F(wB, 1)} before. ${A.n < SMALL || B.n < SMALL ? 'Small samples: read the positions as a direction, not a number. ' : ''}Labelled posts are a sample, not a poll of residents, and a change after a date does not prove the date caused it.`,
        proof: { kind: 'rows', rows: [['Before: oppose', d.V(B.oppose)], ['Before: support', d.V(B.support)], ['After: oppose', d.V(A.oppose), 'ink'], ['After: support', d.V(A.support), 'acc']], unit: `Labelled ${SHORT(id)} posts, split at ${day(from)}` },
        evidence: { label: 'See the posts after it', kind: 'posts', project: id, stance: true, from },
        report: { label: 'Open History', hash: 'history' }, basis: versionHist(ctx.mode), next: 'attention'
      });
    }

    const REFUSE = {
      population: d => done(d, { status: 'refused', text: '<b>CityPulse cannot tell you that.</b> It counts published items, not people, so it cannot say what share of residents support or oppose the line.', more: 'Only a survey of residents could. What the data can show is who takes a side in what is published.', basis: 'A rule of CityPulse', next: 'stance' }),
      names: d => done(d, { status: 'refused', text: '<b>Names are never shown.</b> Authors, handles and e-mail addresses stay out of CityPulse, and links that name an account are withheld.', more: 'Every item that does not name a person can still be opened.', basis: 'A rule of CityPulse', next: 'latest' }),
      predict: d => done(d, { status: 'refused', text: '<b>CityPulse does not predict.</b> It shows what was published and when, with sources. Trends from Paris or Bonn do not tell what Heilbronn will decide.', basis: 'A rule of CityPulse', next: 'compare' }),
      cause: d => done(d, { status: 'refused', text: '<b>CityPulse cannot prove a cause.</b> It can show that attention or positions changed around a date, and which documented event fell on it.', more: 'Timing is a lead to check, not proof.', basis: 'A rule of CityPulse', next: 'attention' })
    };

    const QUESTION = {
      since: 'What changed after 27 October?', latest: "What is new about Heilbronn's line?", stance: 'Do people oppose it, or is it mostly news?',
      concerns: 'What concerns come up most?', attention: 'When did attention rise, and why?', compare: 'How does Bonn compare with Heilbronn?',
      facts: 'What does the city say about cost and route?', gaps: 'What could the last check not see?', reliability: 'How reliable are these readings?',
      addressed: 'Has the city already answered these concerns?',
      arg_new: 'What new concerns appeared?', arg_concern: 'Is the hospital concern new?', arg_main: 'What are the main arguments in Heilbronn?',
      arg_rel: 'How reliable is the argument matching?', arg_since: 'What new arguments came up since 27 October?'
    };
    const SUGGEST = {
      home: ['since', 'stance', 'attention', 'facts', 'latest', 'gaps'],
      history: ['attention', 'stance', 'concerns', 'addressed', 'reliability', 'facts', 'compare'],
      since: ['since', 'arg_since', 'latest', 'compare', 'stance', 'gaps'],
      today: ['gaps', 'since', 'latest', 'reliability', 'compare'],
      review: ['arg_new', 'arg_since', 'arg_concern', 'arg_main', 'arg_rel'],
      arguments: ['arg_new', 'arg_since', 'arg_concern', 'arg_main', 'arg_rel']   // old name of the review tab, kept as an alias
    };

    /* ---------- 3. validate before anything is shown ---------- */
    const DATE_RE = /\b\d{1,2} (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*( \d{4})?\b/gi;
    function numbersIn(html) {
      const s = String(html || '').replace(/<[^>]+>/g, ' ').replace(DATE_RE, ' ').replace(/\b(january|february|march|april|may|june|july|august|september|october|november|december) \d{4}\b/gi, ' ')
        .replace(/"[^"]*"/g, ' ')   // quoted text is the source's own words (a title, a post), shown as a quote, not a CityPulse number
        .replace(/\b(19|20)\d{2}s?\b/g, ' ').replace(/\bC1\b/g, ' ').replace(/\bpair F1\b/g, ' ')   // "pair F1" is the name of a metric, not a number
        .replace(/\b\d{1,2}:\d{2}\b/g, ' ');
      return (s.match(/\d[\d,]*(\.\d+)?/g) || []).map(x => parseFloat(x.replace(/,/g, '')));
    }
    function validate(a) {
      const problems = [];
      if (!a || !a.text) return ['empty answer'];
      const facts = (a.facts || []).map(Number);
      const known = x => facts.some(f => Math.abs(f - x) < 1e-9);
      numbersIn(a.text + ' ' + (a.more || '')).forEach(x => { if (!known(x)) problems.push(`number ${x} is not a computed fact`); });
      if (a.proof && a.proof.kind === 'rows') a.proof.rows.forEach(r => { if (!known(r[1])) problems.push(`proof value ${r[1]} is not a computed fact`); });
      (a.ids || []).forEach(id => { if (!LIVE_BY_ID.has(id) && !POST_BY_ID.has(id) && !CLAIM_BY_ID.has(id)) problems.push(`evidence id ${id} not in the data`); });
      if (a.proof && a.proof.kind === 'recs') a.proof.recs.forEach(r => {
        const li = LIVE_BY_ID.get(r.id);
        if (li && li.url_withheld && r.url) problems.push(`withheld link shown for ${r.id}`);
        if (/(^|\s)@[a-z0-9_.]{2,}|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i.test(r.title || '') || /\/@[a-z0-9_.]/i.test(r.url || '')) problems.push(`handle or e-mail in record ${r.id}`);
      });
      if (/\b\d+(\.\d+)? ?% of (residents|people|citizens|heilbronn)\b/i.test(a.text)) problems.push('population share claimed');
      return problems;
    }

    /* ---------- 4. run one question ---------- */
    function run(q, ctx) {
      ctx = ctx || {};
      const it = typeof q === 'object' ? q : interpret(q, ctx);
      const question = typeof q === 'object' ? q.question : q;
      let a;
      if (it.guard) a = REFUSE[it.guard](draft('refuse:' + it.guard, {}));
      else if (!it.intent) a = { status: 'unsupported', intent: null, facts: [], ids: [], text: "<b>I can't answer that from the checked data.</b> CityPulse answers only questions its data can back, so it does not guess." };
      else a = ANSWER[it.intent](draft(it.intent, it.params || {}), it.params || { projects: [], voice: [], t: '' }, ctx);
      a.question = question; a.follow = it.follow || null; a.guard = it.guard || null;
      a.problems = validate(a);
      if (a.problems.length && a.status !== 'unsupported') {
        a = { status: 'unverified', intent: a.intent, question, facts: [], ids: [], problems: a.problems,
          text: '<b>This answer could not be verified against the data, so it is not shown.</b> Please open the report instead.', report: a.report };
      }
      return a;
    }
    // a suggestion button runs its own intent, whatever the words would match
    function ask(intent, ctx) {
      const it = interpret(QUESTION[intent], ctx || {});
      if (it.guard || it.intent !== intent) { it.guard = null; it.intent = intent; it.params = it.params || { projects: [], voice: [], period: null, t: norm(QUESTION[intent]) }; }
      it.question = QUESTION[intent];
      return run(it, ctx);
    }
    function suggestions(view, ctx) {
      return (SUGGEST[view] || SUGGEST.home).filter(id => ['answered', 'partial'].includes(ask(id, Object.assign({}, ctx, { last: null })).status)).slice(0, 4).map(id => ({ id, q: QUESTION[id] }));
    }

    /* ---------- 5. the model's reading of a question (app/ask_model.py) ----------
       The model only says which answer to run, for which project, period and speaker group. Its query is checked
       again here (same rules as the server), the fixed refusal rules run first, and the answer itself is computed
       and validated exactly as for a typed keyword question. A low-confidence or "none" reading defers to the keywords. */
    const SPEC = {
      intents: ['since', 'latest', 'stance', 'concerns', 'attention', 'compare', 'facts', 'addressed', 'gaps', 'reliability', 'evidence', 'method', 'arg_new', 'arg_concern', 'arg_main', 'arg_rel', 'arg_since', 'none'],
      projects: CORE.concat(OTHERS), voices: ['citizen', 'news_institutional', 'politician_official'], refuse: ['population', 'names', 'predict', 'cause'],
      kinds: ['since', 'history', 'month', 'year', 'event'], events: { council_decision: 'decision', opening: 'opening', cost_estimate: 'money' }, rels: ['after', 'before', 'around']
    };
    function specOk(s) {
      if (!s || typeof s !== 'object' || !SPEC.intents.includes(s.intent)) return false;
      if (!Array.isArray(s.projects || []) || (s.projects || []).some(p => !SPEC.projects.includes(p)) || (s.projects || []).length > 4) return false;
      if (!Array.isArray(s.voice || []) || (s.voice || []).some(v => !SPEC.voices.includes(v))) return false;
      if (s.refuse != null && !SPEC.refuse.includes(s.refuse)) return false;
      const p = s.period;
      if (p != null) {
        if (typeof p !== 'object' || !SPEC.kinds.includes(p.kind) || (p.rel != null && !SPEC.rels.includes(p.rel))) return false;
        if (['month', 'year'].includes(p.kind) && !(Number.isInteger(p.y) && p.y >= 2024 && p.y <= 2026)) return false;
        if (p.kind === 'month' && !(Number.isInteger(p.m) && p.m >= 1 && p.m <= 12)) return false;
        if (p.kind === 'event' && !SPEC.events[p.event]) return false;
      }
      return true;
    }
    function periodFromSpec(sp, project) {
      if (!sp) return null;
      const rel = sp.rel === 'around' ? null : sp.rel || null;
      if (sp.kind === 'since') return { kind: 'since', label: 'after 27 Oct 2026' };
      if (sp.kind === 'history') return { kind: 'history', label: 'Oct 2024 to 27 Oct 2026' };
      if (sp.kind === 'month') return { kind: 'month', rel, y: sp.y, m: sp.m - 1, label: monthLabel(sp.y, sp.m - 1) };
      if (sp.kind === 'year') return { kind: 'year', rel, y: sp.y, label: String(sp.y) };
      const type = SPEC.events[sp.event];
      const ev = events(project || (type === 'opening' ? 'paris_c1' : 'heilbronn_cablecar')).filter(e => e.type === type);
      if (!ev.length) return null;
      const e = ev[ev.length - 1];
      const what = { decision: 'the council decision of', opening: 'the opening on', money: 'the cost estimate of' }[type];
      return { kind: 'event', rel: sp.rel || 'after', date: e.date, label: `${what} ${day(e.date)}`, event: e };
    }
    function fromSpec(spec, q, ctx) {
      ctx = ctx || {};
      if (!specOk(spec)) return null;
      const t = norm(q);
      for (const g of GUARDS) if (g.re.test(t)) return { guard: g.id, t, by: 'rules' };   // fixed refusals never depend on the model
      if (spec.refuse) return { guard: spec.refuse, t, by: 'model' };
      const kw = interpret(q, ctx);
      // a question that names the argument engine's results (matching, the hospital concern, new or main arguments) keeps its engine answer
      if (ENGINE_INTENTS.includes(kw.intent) && ['concerns', 'reliability', 'since', 'latest', 'none'].includes(spec.intent)) return Object.assign(kw, { by: 'keywords' });
      // "new arguments" with the period "after 27 Oct" can only be the collector runs: the arg_new answer is the July replay
      if (spec.intent === 'arg_new' && spec.period && spec.period.kind === 'since') spec = Object.assign({}, spec, { intent: 'arg_since' });
      if (spec.intent === 'none' || spec.confidence === 'low') {
        if (kw.intent) return Object.assign(kw, { by: 'keywords' });
        if (spec.intent === 'none') return { t, intent: null, by: 'model' };
      }
      const last = ctx.last && ctx.last.intent && !ctx.last.guard ? ctx.last : null;
      const follow = ['evidence', 'method'].includes(spec.intent) ? last
        : (last && spec.intent === last.intent && !(spec.projects || []).length ? last : null);
      const base = follow && follow.params ? follow.params : {};
      const projects = (spec.projects || []).length ? spec.projects.slice() : (follow && base.projects ? base.projects : []);
      const period = periodFromSpec(spec.period, projects[0]) || (follow && spec.intent === follow.intent ? base.period || null : null);
      return { t, intent: spec.intent, by: 'model', follow: follow ? follow.question : null,
        params: { projects, voice: (spec.voice || []).slice(), period, t } };
    }
    function runSpec(spec, q, ctx) {
      const it = fromSpec(spec, q, ctx);
      if (!it) return null;
      it.question = q;
      const a = run(it, ctx);
      a.by = it.by;
      return a;
    }
    return { interpret, run, ask, validate, suggestions, runSpec, fromSpec, specOk, QUESTION, PNAME, KIND, SOURCE, day, host, numbersIn };
  }
  G.CityAskCore = { makeCore };

  /* =====================================================================
     PANEL: the browser UI. Skipped in Node (the test suite uses the core only).
     ===================================================================== */
  if (typeof document === 'undefined' || !document.body) return;
  const core = makeCore({ live: G.CP_LIVE, hist: G.CP_HISTORY, facts: G.CP_FACTS, engine: G.CP_ENGINE });
  const APP = () => G.CP_APP || {};
  const ctxNow = () => ({ mode: APP().mode || 'awaiting', hasH: !!(APP().hasH && G.CP_HISTORY), view: document.documentElement.dataset.view || 'home', last });
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const nf = n => Number(n).toLocaleString('en-GB');

  const wrap = document.createElement('div');
  wrap.className = 'ask-wrap'; wrap.hidden = true;
  wrap.innerHTML = `<div class="ask-veil" data-askclose></div>
    <section class="ask" role="dialog" aria-modal="true" aria-label="Ask CityPulse">
      <form class="ask-in" autocomplete="off"><span class="ask-ic" aria-hidden="true"></span>
        <input id="askInput" type="text" placeholder="Ask about the cable car debate" aria-label="Your question" maxlength="200">
        <button class="ask-x" type="button" data-askclose aria-label="Close">Esc</button></form>
      <div class="ask-body" id="askBody" aria-live="polite"></div>
    </section>`;
  document.body.appendChild(wrap);
  const input = wrap.querySelector('#askInput'), body = wrap.querySelector('#askBody');
  let last = null, lastFocus = null;

  function proofHtml(p) {
    if (!p) return '';
    if (p.kind === 'rows') {
      const mx = Math.max(1, ...p.rows.map(r => r[1]));
      return `<ul class="ask-rows">${p.rows.map(r => `<li><span>${esc(r[0])}</span><span class="ab"><i class="${r[2] === true ? 'acc' : (r[2] || '')}" style="width:${r[1] / mx * 100}%"></i></span><b>${r[1] % 1 ? r[1].toFixed(2) : nf(r[1])}</b></li>`).join('')}</ul>${p.unit ? `<p class="ask-unit">${esc(p.unit)}</p>` : ''}`;
    }
    if (p.kind === 'recs') {
      return `<ul class="ask-recs">${p.recs.map(r => `<li><span class="d">${esc(core.day(r.date))}</span>${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)} ↗</a>` : `<span>${esc(r.title)}</span>`}<em>${esc(r.tag || r.source || '')}</em></li>`).join('')}</ul>`;
    }
    if (p.kind === 'dl') return `<dl class="ask-dl">${p.items.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`;
    if (p.kind === 'two') return `<div class="ask-two">${[p.left, p.right].map(s => `<div><p class="ask-k">${esc(s.title)}</p><ul>${s.items.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`).join('')}</div>`;
    return '';
  }
  // the evidence button: opens the same drawers the reports use, filtered to exactly what the answer counted
  function openEvidence(ev) {
    const A = APP(); if (!ev) return;
    const L = G.CP_LIVE, H = G.CP_HISTORY;
    if (ev.kind === 'live' && A.openLive && L) A.openLive(core.PNAME[ev.project], `Found since ${core.day(L.meta.since)}`, L.items.filter(i => i.radar_project === ev.project));
    else if (ev.kind === 'posts' && A.openPosts && H) {
      const posts = (H.posts || []).filter(x => x.project === ev.project && (!ev.stance || x.stance) && (!ev.voice || x.voice === ev.voice)
        && (!ev.arg || (x.arguments || []).includes(ev.arg)) && (!ev.from || x.date >= ev.from) && (!ev.to || x.date <= ev.to));
      A.openPosts(core.PNAME[ev.project], 'The posts this answer counted.', posts);
    }
    else if (ev.kind === 'finding' && A.openFinding) A.openFinding(ev.i);
    else if (ev.kind === 'gaps' && A.openGaps) A.openGaps();
    else if (ev.kind === 'method') { const b = document.getElementById('howLink'); if (b) b.click(); }
    else if (ev.kind === 'url') G.open(ev.url, '_blank', 'noopener');
    else if (ev.kind === 'view') location.hash = ev.hash;
    else if (ev.kind === 'concern' && A.openConcernById) A.openConcernById(ev.ids);
    else if (ev.kind === 'engine_method' && A.openEngineMethod) A.openEngineMethod();
  }

  function suggestionsHtml(title) {
    const s = core.suggestions(ctxNow().view, ctxNow());
    return `<p class="ask-k">${esc(title)}</p><ul class="ask-sug">${s.map(x => `<li><button type="button" data-q="${x.id}">${esc(x.q)}<span>→</span></button></li>`).join('')}</ul>`;
  }
  function showSuggestions() {
    body.innerHTML = suggestionsHtml('Try') + '<p class="ask-foot">Answers are counted from the checked data and checked before they are shown. If the data cannot answer, it says so.</p>';
  }
  function render(a) {
    if (a.problems && a.problems.length) console.warn('Ask CityPulse: answer held back', a.problems);
    if (a.status === 'unsupported' && !a.next) {
      body.innerHTML = `<div class="ask-a weak"><p class="ask-t">${a.text}</p></div>${suggestionsHtml('It can answer')}`;
      return;
    }
    if (!['unsupported', 'unverified'].includes(a.status) && !a.guard) last = a;
    const strong = a.status === 'answered' || a.status === 'partial';
    const next = a.next && core.QUESTION[a.next] && a.next !== a.intent ? a.next : null;
    body.innerHTML = `${a.read ? `<p class="ask-read"><span>${a.by === 'model' ? 'Understood as' : 'Read as'}</span>${esc(a.read)}</p>` : ''}
      <div class="ask-a${strong ? '' : ' weak'}"><p class="ask-t">${a.text}</p>${a.more ? `<p class="ask-m">${a.more}</p>` : ''}</div>
      ${proofHtml(a.proof) ? `<div class="ask-proof">${proofHtml(a.proof)}</div>` : ''}
      ${a.evidence || a.report ? `<div class="ask-act">${a.evidence ? `<button class="btn dark" type="button" data-act="ev">${esc(a.evidence.label)} →</button>` : ''}${a.report ? `<button class="btn" type="button" data-act="rep">${esc(a.report.label)}</button>` : ''}</div>` : ''}
      ${a.basis ? `<p class="ask-basis">From: ${esc(a.basis)}</p>` : ''}
      ${next ? `<button class="ask-next" type="button" data-q="${next}"><span>Next</span>${esc(core.QUESTION[next])}</button>` : ''}`;
    shown = a;
  }
  let shown = null, turn = 0;
  // the model reads the question when app/serve.py has a key and budget left; otherwise the keyword reader does
  let modelOn = false;
  fetch('/api/status', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(j => { modelOn = !!(j && j.ask_model && j.ask_model.available); }).catch(() => { modelOn = false; });
  async function readWithModel(q, last) {
    const ctl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timer = setTimeout(() => ctl && ctl.abort(), 9000);
    try {
      const r = await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: ctl ? ctl.signal : undefined,
        body: JSON.stringify({ q, last: last ? { question: last.question, read: last.read } : null }) });
      return r.ok ? await r.json() : null;
    } catch (e) { return null; } finally { clearTimeout(timer); }
  }
  async function ask(q, intent) {
    const my = ++turn;
    const ctx = ctxNow();
    let a = null;
    if (!intent && modelOn && !core.interpret(q, ctx).guard) {   // fixed refusals answer at once, without the model
      input.value = q;
      body.innerHTML = '<p class="ask-wait">Reading your question</p>';
      const r = await readWithModel(q, ctx.last);
      if (my !== turn) return null;                                 // a newer question was asked meanwhile
      if (r && r.ok) a = core.runSpec(r.spec, q, ctx);
      else if (r && r.error) console.info('Ask CityPulse: model reader unavailable, using keywords:', r.error);
    }
    if (!a) a = intent ? core.ask(intent, ctx) : core.run(q, ctx);
    input.value = a.question || q;
    render(a);
    return a;
  }
  function open(q) {
    lastFocus = document.activeElement;
    wrap.hidden = false; document.documentElement.classList.add('ask-on');
    input.value = q || '';
    if (q) ask(q); else showSuggestions();
    setTimeout(() => input.focus(), 30);
  }
  function close() { wrap.hidden = true; document.documentElement.classList.remove('ask-on'); if (lastFocus && lastFocus.focus) lastFocus.focus(); }

  wrap.querySelector('form').addEventListener('submit', e => { e.preventDefault(); const q = input.value.trim(); if (q) ask(q); else showSuggestions(); });
  input.addEventListener('input', () => { if (!input.value.trim()) showSuggestions(); });
  wrap.addEventListener('click', e => {
    if (e.target.closest('[data-askclose]')) return close();
    const s = e.target.closest('[data-q]');
    if (s) return ask(null, s.dataset.q);
    const b = e.target.closest('[data-act]');
    if (b && shown) { close(); if (b.dataset.act === 'ev') openEvidence(shown.evidence); else if (shown.report) location.hash = shown.report.hash; }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !wrap.hidden) { e.stopImmediatePropagation(); close(); return; }   // Esc closes the panel only, not the guided demo
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || '') || (e.target && e.target.isContentEditable);
    const dw = document.getElementById('drawerWrap');
    if (e.key === '/' && wrap.hidden && !typing && !(dw && !dw.hidden)) { e.preventDefault(); open(); }
  }, true);

  const pill = document.getElementById('askOpen');
  if (pill) pill.addEventListener('click', () => open());
  function homeField() {
    const hook = document.querySelector('#home .hook');
    if (!hook || hook.querySelector('.ask-home')) return;
    hook.insertAdjacentHTML('beforeend', `<button class="ask-home" type="button"><span class="ask-ic" aria-hidden="true"></span>Ask CityPulse a question<kbd>/</kbd></button>`);
    hook.querySelector('.ask-home').addEventListener('click', () => open());
  }
  homeField();

  // for the guided demo and for testing: CityAsk.open('What changed after 27 October?')
  G.CityAsk = { open, close, ask: q => open(q), run: q => core.run(q, ctxNow()), core };
})();
