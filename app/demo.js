/* CityPulse guided demo mode. Open the site with ?demo=long (preselection) or ?demo=short (final).
   Add &scene=3 to start at step 3. Right arrow, Page Down, Space or a presenter clicker: next. Left arrow or Page Up: back.
   Esc: leave the demo (a drawer or the Ask panel closes first).
   One click = one main screen. The demo only switches the real tabs (and, on the long route, asks one question in the
   real Ask panel), so the site stays fully clickable and picks up new data by itself. No copied UI, no fake data.
   The difference from clicking the tabs yourself: in demo mode each screen makes an entrance. The sheet rises in, its
   panels follow one after another, the big numbers count up from 0 to the value already on the page, bars and charts
   grow from zero, the caption fades in. Only transform and opacity are animated (the count-up only rewrites text),
   about 1.1 s per screen, and nothing at all moves when the system asks for reduced motion. */
(function () {
  'use strict';
  const route = new URLSearchParams(location.search).get('demo');
  if (!route) return;
  const ROUTE = route === 'short' ? 'short' : 'long';
  const $ = s => document.querySelector(s);
  const HAS_H = () => !!(window.CP_APP && window.CP_APP.hasH);                      // analysis answers on screen (pilot or final)
  const REDUCED = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
  const EASE = 'cubic-bezier(0.23, 1, 0.32, 1)';                                     // the site's --ease: fast out, no bounce
  document.documentElement.classList.add('demo-on');

  // One step list, two routes. Five main screens, then home again; the long route adds one Ask step.
  const STEPS = [
    { id: 'home', view: 'home', caption: () => 'Heilbronn, live' },
    { id: 'history', view: 'history', caption: () => 'Two years of debate' },
    { id: 'since', view: 'since', caption: () => 'Since the city’s data ended' },
    { id: 'review', view: 'review', caption: () => 'Human review needed' },
    { id: 'ask', view: 'review', long: true, caption: () => 'Ask, get the proof',
      question: () => HAS_H() ? 'Are citizens actually opposing the cable car, or is this mostly news?' : 'What changed after 27 October?' },
    { id: 'today', view: 'today', caption: () => 'Today’s check, step by step' },
    { id: 'close', view: 'home', caption: () => 'Keep listening' }
  ];
  const list = STEPS.filter(s => !s.long || ROUTE === 'long');
  let i = -1;

  const bar = document.createElement('div');
  bar.className = 'demo-bar';
  bar.setAttribute('role', 'status');
  bar.innerHTML = `<button class="demo-btn" data-d="-1" aria-label="Previous screen">‹</button>
    <span class="demo-count"></span><span class="demo-cap"></span>
    <button class="demo-btn" data-d="1" aria-label="Next screen">›</button>`;
  document.body.appendChild(bar);
  bar.addEventListener('click', e => { const b = e.target.closest('[data-d]'); if (b) go(i + +b.dataset.d); });
  const cap = bar.querySelector('.demo-cap');

  /* ---------- the entrance ---------- */
  let running = [];          // WAAPI animations of the current entrance
  let counting = [];         // { el, text } of numbers being counted, restored exactly when the entrance stops
  let rafId = 0, settleId = 0;
  function stopEntrance() {
    running.forEach(a => a.cancel()); running = [];
    cancelAnimationFrame(rafId); rafId = 0; clearTimeout(settleId);
    counting.forEach(c => { c.el.textContent = c.text; }); counting = [];
  }
  const play = (el, keyframes, opts) => { const a = el.animate(keyframes, Object.assign({ easing: EASE, fill: 'backwards' }, opts)); running.push(a); return a; };
  const RISE = [{ opacity: 0, transform: 'translateY(18px)' }, { opacity: 1, transform: 'none' }];
  const GROW_X = [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }];
  const GROW_Y = [{ transform: 'scaleY(0)' }, { transform: 'scaleY(1)' }];
  const FADE = [{ opacity: 0 }, { opacity: 1 }];
  const END = 1150;          // every part of an entrance is done by then (ms)

  // A number shown on its own ("39,361", "39%", "0.65", "n 12", "46 new"): prefix and suffix hold no digits.
  const NUM = /^(\D*?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(\D*)$/;
  function countable(el) {
    if (el.childElementCount) return null;
    const text = el.textContent, m = text.trim() && text.match(NUM);
    if (!m) return null;
    const whole = m[2], dec = m[3] || '';
    if (!dec && !whole.includes(',') && /^(19|20)\d\d$/.test(whole)) return null;    // a year, not a count
    const value = parseFloat(whole.replace(/,/g, '') + dec);
    if (!(value > 0)) return null;
    return { el, text, pre: m[1], post: m[4], value, places: dec ? dec.length - 1 : 0, comma: whole.includes(',') || value >= 10000 };
  }
  const fmt = (c, v) => c.pre + (c.places ? v.toFixed(c.places) : Math.round(v).toLocaleString('en-GB', { useGrouping: c.comma })) + c.post;

  // Plays the entrance of one screen. All layout reads happen first, then only writes and compositor animations.
  function enter(viewEl, withScreen) {
    stopEntrance();
    if (!viewEl || REDUCED.matches || !viewEl.animate) return;
    const home = viewEl.dataset.view === 'home';
    const panels = home
      ? [...viewEl.querySelectorAll('.hook h1, .enter a, .ask-home')]
      : [...viewEl.querySelectorAll(':scope > .sh-head, :scope > .promise, :scope > .grid > .card')];
    const step = Math.max(60, Math.min(90, 520 / Math.max(1, panels.length)));
    const delayOf = new Map(panels.map((p, k) => [p, 90 + k * step]));
    const panelOf = el => { for (const p of panels) if (p.contains(el)) return p; return null; };
    const startOf = (el, extra) => Math.min(END - 420, (delayOf.get(panelOf(el)) || 90) + extra);

    // reads
    const nums = [...viewEl.querySelectorAll('b, .fx, .ds')].map(countable).filter(Boolean).filter(c => c.el.getClientRects().length).slice(0, 40);
    const barsX = [...viewEl.querySelectorAll('.bar > i, .stack, .rstrip, .pb, .track .fill')];
    const charts = [...viewEl.querySelectorAll('svg.chart')].map(svg => {
      const shapes = [...svg.querySelectorAll('rect, path')];
      let base = 0;
      shapes.forEach(s => { try { const b = s.getBBox(); base = Math.max(base, b.y + b.height); } catch (e) { /* not rendered */ } });
      return { svg, shapes, base, marks: [...svg.querySelectorAll('circle, text, a')] };
    });
    const rows = [...viewEl.querySelectorAll('.steps > li, .slist > li, .glist > li')];

    // writes
    if (withScreen) play(viewEl, [{ opacity: 0, transform: 'translateY(26px) scale(.985)' }, { opacity: 1, transform: 'none' }], { duration: 620 });
    panels.forEach(p => play(p, RISE, { duration: 520, delay: delayOf.get(p) }));
    rows.forEach(r => { const k = [...r.parentNode.children].indexOf(r); play(r, [{ opacity: 0, transform: 'translateX(-10px)' }, { opacity: 1, transform: 'none' }], { duration: 420, delay: startOf(r, 140 + k * 60) }); });
    barsX.forEach(b => { const d = startOf(b, 120); play(b, GROW_X, { duration: Math.max(500, END - d), delay: d }); });
    charts.forEach(c => {
      const d = startOf(c.svg, 120), dur = Math.max(500, END - d);
      c.shapes.forEach(s => { s.style.transformBox = 'view-box'; s.style.transformOrigin = `0 ${c.base}px`; play(s, GROW_Y, { duration: dur, delay: d }); });
      c.marks.forEach(m => play(m, FADE, { duration: 360, delay: Math.min(END - 360, d + dur * .6) }));
    });
    if (nums.length) {
      const t0 = performance.now();
      nums.forEach(c => { c.start = startOf(c.el, 120); c.dur = Math.max(450, END - c.start); c.el.textContent = fmt(c, 0); });
      counting = nums;
      const tick = now => {
        let live = 0;
        nums.forEach(c => {
          const t = Math.min(1, Math.max(0, (now - t0 - c.start) / c.dur));
          if (t >= 1) { if (c.el.textContent !== c.text) c.el.textContent = c.text; return; }   // ends on the exact text the page had
          live++;
          c.el.textContent = fmt(c, c.value * (1 - Math.pow(1 - t, 3)));
        });
        if (live) rafId = requestAnimationFrame(tick); else { rafId = 0; counting = []; }
      };
      rafId = requestAnimationFrame(tick);
      // if frames pause (a hidden tab), the numbers still end on the page's exact text
      settleId = setTimeout(() => { cancelAnimationFrame(rafId); rafId = 0; nums.forEach(c => { c.el.textContent = c.text; }); counting = []; }, END + 250);
    }
  }
  function captionIn(text) {
    cap.textContent = text;
    if (REDUCED.matches || !cap.animate) return;
    cap.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 480, delay: 220, easing: EASE, fill: 'backwards' });
  }

  // switch to a view; resolves after app.js has shown it (its hashchange listener runs before this one)
  function show(v) {
    if (document.documentElement.dataset.view === v && location.hash === '#' + v) return Promise.resolve(false);
    return new Promise(ok => { window.addEventListener('hashchange', () => ok(true), { once: true }); location.hash = '#' + v; });
  }
  const closeOverlays = () => {
    const x = document.querySelector('#drawerWrap:not([hidden]) [data-close]'); if (x) x.click();
    if (window.CityAsk) window.CityAsk.close();
  };
  const blur = () => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); };   // the clicker keeps moving the demo

  // The Ask step: the panel opens, the question types itself in, the real answer appears (no drawer is opened).
  async function askStep(s, wait) {
    if (!window.CityAsk) return;
    window.CityAsk.open();
    await wait(60); blur();
    const input = $('#askInput'), body = $('#askBody'), q = s.question();
    if (!input || !input.form) return;
    if (REDUCED.matches) input.value = q;
    else { input.value = ''; for (const ch of q) { input.value += ch; await wait(22); } }
    await wait(180);
    input.form.requestSubmit ? input.form.requestSubmit() : input.form.dispatchEvent(new Event('submit', { cancelable: true }));
    blur();
    for (let t = 0; t < 120 && !body.querySelector('.ask-a'); t++) await wait(80);      // the model reader may take a few seconds
    if (!body.querySelector('.ask-a') || REDUCED.matches) return;
    stopEntrance();
    const parts = [...body.children];
    parts.forEach((p, k) => play(p, RISE, { duration: 480, delay: k * 70 }));
    body.querySelectorAll('.ask-rows .ab i').forEach(b => play(b, GROW_X, { duration: 700, delay: 160 }));
  }

  let token = 0;
  async function go(n) {
    if (n < 0 || n >= list.length) return;
    const prev = list[i];
    i = n;
    const mine = ++token;
    // a step's delayed parts stop as soon as the presenter moves on
    const wait = ms => new Promise((ok, stop) => setTimeout(() => (mine === token ? ok() : stop('moved on')), ms));
    const s = list[i];
    stopEntrance();
    closeOverlays();
    bar.querySelector('.demo-count').textContent = `${i + 1} / ${list.length}`;
    captionIn(s.caption());
    const changed = await show(s.view);
    if (mine !== token) return;
    // a new screen enters in full; the same screen again (going back from Ask) replays its panels only; Ask keeps the screen still
    if (s.id !== 'ask') enter(document.getElementById(s.view), changed);
    else if (changed) enter(document.getElementById(s.view), true);
    if (s.id === 'ask') { try { await askStep(s, wait); } catch (e) { /* moved on */ } }
  }
  function leave() {
    stopEntrance(); bar.remove();
    document.documentElement.classList.remove('demo-on');
    document.removeEventListener('keydown', onKey, true);
  }
  function onKey(e) {
    if (e.target.closest && e.target.closest('input, textarea, select')) return;
    if (['ArrowRight', 'PageDown'].includes(e.key) || (e.key === ' ' && !e.target.closest('button'))) { e.preventDefault(); go(i + 1); }
    else if (['ArrowLeft', 'PageUp'].includes(e.key)) { e.preventDefault(); go(i - 1); }
    else if (e.key === 'Escape') {
      if (!document.getElementById('drawerWrap').hidden) return;    // the drawer closes first
      leave();
    }
  }
  document.addEventListener('keydown', onKey, true);
  window.CPDemo = { go: n => go(n), next: () => go(i + 1), prev: () => go(i - 1), steps: list.map(s => s.id), get index() { return i; } };
  const start = Math.max(1, Math.min(list.length, +new URLSearchParams(location.search).get('scene') || 1));
  setTimeout(() => go(start - 1), 300);
})();
