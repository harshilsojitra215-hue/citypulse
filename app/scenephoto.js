/* CityPulse: the living background.
   A real photo of Heilbronn (view from the tower of the Kilianskirche to the Wartberg; Peter Schmelzle,
   CC BY-SA 4.0, Wikimedia Commons) with the planned cable car drawn into it in the photo's own perspective:
   one foreground mast, two ropes, cabins passing each other. The cable car is an illustration of the plan,
   not its real position. Masts up to 55 m and a cabin every 20 to 30 s follow the city FAQ.

   How it is drawn: every part is a small 3D model in metres (cabin body, windows, hanger, grip, mast head,
   sheave trains), projected through the photo's own camera and lit by the photo's own sun (behind the
   camera, to the right, high: read off the shadows of the dormers and chimneys). So each cabin shows the
   faces the camera really sees, at the right size for its distance, and the glass catches the sun as it
   passes. Everything is in photo pixels (2048 x 1536); the SVG uses the same cover framing as the <img>.
   Respects prefers-reduced-motion (the cable car stands still). */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const PW = 2048, PH = 1536;
  // Camera of the photo: horizon at y 672, focal length about 1607 px (a 28 mm compact), eye 62 m above ground.
  const F = 1607, CX = 1024, HY = 672, EYE = 62;
  const P = (x, y, z) => [CX + F * x / z, HY + F * (EYE - y) / z, F / z];
  const CAM = [0, EYE, 0];

  /* ---------- small vector maths ---------- */
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const norm = a => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
  const SUN = norm([0.45, 0.65, -0.6]);          // x right, y up, z away from the camera

  /* ---------- light and colour, graded to the photo (soft blacks, a little warmth) ---------- */
  const grade = c => c.map((v, i) => Math.max(0, Math.min(255, Math.round(v * 0.88 + [16, 14, 11][i]))));
  const rgb = c => `rgb(${c[0]},${c[1]},${c[2]})`;
  function lit(alb, N) {
    const l = Math.max(0, dot(N, SUN)), sky = 0.55 + 0.45 * N[1];
    const k = 0.55 * sky + 0.85 * l;
    return rgb(grade(alb.map(v => v * k)));
  }
  function glass(N, p) {
    const V = norm(sub(CAM, p)), nv = dot(N, V);
    const fres = 0.10 + 0.55 * Math.pow(1 - Math.abs(nv), 2);
    const base = [34, 42, 54], skyc = [150, 168, 190];
    const R = [2 * nv * N[0] - V[0], 2 * nv * N[1] - V[1], 2 * nv * N[2] - V[2]];
    const spec = Math.pow(Math.max(0, dot(R, SUN)), 36) * 230;
    return rgb(grade(base.map((v, i) => v + (skyc[i] - v) * fres + spec)));
  }

  /* ---------- the line ---------- */
  // Crosses in front of the tower about 60 m away, receding a little to the right.
  const zAt = (x, side) => 62 + 0.12 * x + side * 3;          // side -1 near rope, +1 far rope
  const MAST = { x: -8.5, h: 54 };
  const SPAN = 256;                                            // to the next supports, both outside the photo
  function ropeY(x) {
    const d = Math.abs(x - MAST.x), t = Math.min(1, d / SPAN);
    return MAST.h - 0.6 - 4 * (0.02 * SPAN) * t * (1 - t);     // highest at the mast, sagging toward the next span
  }
  const DIR = norm([1, 0, 0.12]), ACROSS = norm([-0.12, 0, 1]);   // along the rope, and across it (away from camera)

  function el(name, attrs, parent) {
    const n = document.createElementNS(NS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  const pts = arr => arr.map(q => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' ');

  /* ---------- a box in any frame: returns the faces the camera sees, lit ---------- */
  // frame(u, w, s) -> world point; axes(nu, nw, ns) -> world normal
  function boxFaces(frame, axes, c, h, alb) {
    const out = [];
    const faces = [[0, 1], [0, -1], [1, 1], [1, -1], [2, 1], [2, -1]];
    faces.forEach(([ax, sg]) => {
      const n = [0, 0, 0]; n[ax] = sg;
      const N = axes(n[0], n[1], n[2]);
      const o = [1, 2, 0][ax], q = [2, 0, 1][ax];
      const corner = (a, b) => { const p = c.slice(); p[ax] += sg * h[ax]; p[o] += a * h[o]; p[q] += b * h[q]; return frame(p[0], p[1], p[2]); };
      const quad = [corner(-1, -1), corner(1, -1), corner(1, 1), corner(-1, 1)];
      const mid = [0, 1, 2].map(i => (quad[0][i] + quad[2][i]) / 2);
      if (dot(N, sub(CAM, mid)) > 0) out.push({ p: quad.map(w => P(w[0], w[1], w[2])), fill: lit(alb, N) });
    });
    return out;
  }
  const WORLD = (x, y, z) => [x, y, z], WAXES = (a, b, c) => [a, b, c];

  /* ---------- the cabin: a modern 10-seat cabin, about 2.5 m long, 2.2 m high, 1.95 m wide ---------- */
  const CAB = { L: 2.5, Lb: 2.24, H: 2.15, W: 1.95, rt: 0.5, rb: 0.42, DROP: 2.55 };   // DROP: grip to roof
  const PROFILE = (function () {
    const p = [], seg = 6, { L, Lb, H, rt, rb } = CAB;
    const arc = (cu, cv, r, a0, a1) => { for (let i = 0; i <= seg; i++) { const a = a0 + (a1 - a0) * i / seg; p.push([cu + r * Math.cos(a), cv + r * Math.sin(a)]); } };
    arc(L / 2 - rt, -rt, rt, 0, Math.PI / 2);
    arc(-L / 2 + rt, -rt, rt, Math.PI / 2, Math.PI);
    arc(-Lb / 2 + rb, -H + rb, rb, Math.PI, 1.5 * Math.PI);
    arc(Lb / 2 - rb, -H + rb, rb, 1.5 * Math.PI, 2 * Math.PI);
    return p;                                                    // counter-clockwise, v = 0 at the roof
  })();
  const NP = PROFILE.length, SEG1 = 7;
  const EDGES = PROFILE.map((a, i) => {
    const b = PROFILE[(i + 1) % NP], du = b[0] - a[0], dv = b[1] - a[1], l = Math.hypot(du, dv) || 1;
    const mv = (a[1] + b[1]) / 2;
    return { a, b, n: [dv / l, -du / l], mat: mv > -0.18 ? 'roof' : mv < -CAB.H + 0.3 ? 'skirt' : 'body' };
  });
  const RIGHT_END = NP - 1, LEFT_END = 2 * SEG1 - 1;              // the two end walls
  const ALB = { body: [236, 236, 232], roof: [176, 178, 181], skirt: [86, 89, 94], dark: [70, 73, 78], frame: [58, 61, 66] };
  const WIN = { u: 0.98, v0: -1.44, v1: -0.42, r: 0.16 };
  function rrect(u0, u1, v0, v1, r) {
    const p = [], seg = 4;
    const arc = (cu, cv, a0) => { for (let i = 0; i <= seg; i++) { const a = a0 + (Math.PI / 2) * i / seg; p.push([cu + r * Math.cos(a), cv + r * Math.sin(a)]); } };
    arc(u1 - r, v1 - r, 0); arc(u0 + r, v1 - r, Math.PI / 2); arc(u0 + r, v0 + r, Math.PI); arc(u1 - r, v0 + r, 1.5 * Math.PI);
    return p;
  }
  const WINDOW = rrect(-WIN.u, WIN.u, WIN.v0, WIN.v1, WIN.r);
  const REFLECT = rrect(-WIN.u + 0.02, WIN.u - 0.02, -0.86, WIN.v1 - 0.02, WIN.r - 0.02);

  // the lower band of the long side: the profile below a cut line
  const CUT = -CAB.H + 0.3;
  const BAND = (function () {
    const out = [];
    PROFILE.forEach((a, i) => {
      const b = PROFILE[(i + 1) % NP];
      if (a[1] <= CUT) out.push(a);
      if ((a[1] - CUT) * (b[1] - CUT) < 0) { const t = (CUT - a[1]) / (b[1] - a[1]); out.push([a[0] + (b[0] - a[0]) * t, CUT]); }
    });
    return out;
  })();
  let cabinCount = 0;
  function makeCabin(layer, side) {
    const id = 'cabFace' + (cabinCount++);
    const defs = document.getElementById('sceneDefs');
    const gr = el('linearGradient', { id, x1: 0, y1: 0, x2: 0.25, y2: 1 }, defs);
    const stops = [el('stop', { offset: 0 }, gr), el('stop', { offset: 0.55 }, gr), el('stop', { offset: 1 }, gr)];
    const g = el('g', { filter: 'url(#lens)' }, layer);
    const behind = el('g', {}, g), body = el('g', {}, g), front = el('g', {}, g);
    const quads = EDGES.map(() => el('polygon', {}, body));
    const face = el('polygon', { fill: `url(#${id})` }, body);
    const band = el('polygon', {}, body);
    const win = el('polygon', {}, body), refl = el('polygon', { fill: '#dfe7f0', opacity: 0.16 }, body);
    const ends = [el('polygon', {}, body), el('polygon', {}, body)];
    const doors = [el('line', { stroke: rgb(grade(ALB.frame)), 'stroke-linecap': 'round' }, body), el('line', { stroke: rgb(grade(ALB.frame)), 'stroke-linecap': 'round' }, body)];
    const sill = el('line', { stroke: '#f4f3ef', opacity: 0.5 }, body);
    const hanger = el('path', { fill: 'none', stroke: rgb(grade([72, 75, 80])), 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, side < 0 ? front : behind);
    const hangerHi = el('path', { fill: 'none', stroke: '#e9e8e4', opacity: 0.35, 'stroke-linecap': 'round' }, side < 0 ? front : behind);
    const parts = el('g', {}, front);
    return { g, quads, face, band, stops, win, refl, ends, doors, sill, hanger, hangerHi, parts, side, theta: 0, omega: 0, last: null };
  }

  function drawCabin(c, x, th) {
    const G = [x, ropeY(x), zAt(x, c.side)];
    const cs = Math.cos(th), sn = Math.sin(th);
    const frame = (u, w, s) => { const cu = u * cs - w * sn, cw = u * sn + w * cs; return [G[0] + DIR[0] * cu + ACROSS[0] * s, G[1] + cw, G[2] + DIR[2] * cu + ACROSS[2] * s]; };
    const axes = (nu, nw, ns) => { const cu = nu * cs - nw * sn, cw = nu * sn + nw * cs; return [DIR[0] * cu + ACROSS[0] * ns, cw, DIR[2] * cu + ACROSS[2] * ns]; };
    const D = CAB.DROP, hw = CAB.W / 2;
    const at = (u, v, s) => { const w = frame(u, v - D, s); return P(w[0], w[1], w[2]); };
    const k = P(G[0], G[1], G[2])[2];

    // side walls, roof and floor: each strip of the profile, seen only if it faces the camera
    EDGES.forEach((e, i) => {
      const q = c.quads[i];
      const N = axes(e.n[0], e.n[1], 0);
      const mid = frame((e.a[0] + e.b[0]) / 2, (e.a[1] + e.b[1]) / 2 - D, 0);
      if (dot(N, sub(CAM, mid)) <= 0) { q.setAttribute('visibility', 'hidden'); return; }
      q.setAttribute('visibility', 'visible');
      q.setAttribute('points', pts([at(e.a[0], e.a[1], -hw), at(e.b[0], e.b[1], -hw), at(e.b[0], e.b[1], hw), at(e.a[0], e.a[1], hw)]));
      q.setAttribute('fill', lit(ALB[e.mat], N));
    });
    // the long side facing the camera, its glazing, the sliding doors
    const NF = axes(0, 0, -1);
    c.face.setAttribute('points', pts(PROFILE.map(p => at(p[0], p[1], -hw))));
    const fc = lit(ALB.body, NF), fcv = fc.match(/\d+/g).map(Number);
    const tone = m => rgb(fcv.map(v => Math.max(0, Math.min(255, Math.round(v * m)))));
    c.stops[0].setAttribute('stop-color', tone(1.05)); c.stops[1].setAttribute('stop-color', fc); c.stops[2].setAttribute('stop-color', tone(0.84));
    c.band.setAttribute('points', pts(BAND.map(p => at(p[0], p[1], -hw - 0.002))));
    c.band.setAttribute('fill', lit(ALB.skirt, NF));
    const sf = -hw - 0.004;
    c.win.setAttribute('points', pts(WINDOW.map(p => at(p[0], p[1], sf))));
    c.win.setAttribute('fill', glass(NF, frame(0, (WIN.v0 + WIN.v1) / 2 - D, sf)));
    c.refl.setAttribute('points', pts(REFLECT.map(p => at(p[0], p[1], sf - 0.002))));
    [-0.36, 0.36].forEach((u, j) => {
      const a = at(u, WIN.v1, sf - 0.003), b = at(u * 0.96, -CAB.H + 0.3, sf - 0.003);
      const ln = c.doors[j];
      ln.setAttribute('x1', a[0].toFixed(1)); ln.setAttribute('y1', a[1].toFixed(1)); ln.setAttribute('x2', b[0].toFixed(1)); ln.setAttribute('y2', b[1].toFixed(1));
      ln.setAttribute('stroke-width', Math.max(0.8, 0.05 * k).toFixed(2));
    });
    const s0 = at(-WIN.u + 0.05, WIN.v0 - 0.05, sf), s1 = at(WIN.u - 0.05, WIN.v0 - 0.05, sf);
    c.sill.setAttribute('x1', s0[0].toFixed(1)); c.sill.setAttribute('y1', s0[1].toFixed(1)); c.sill.setAttribute('x2', s1[0].toFixed(1)); c.sill.setAttribute('y2', s1[1].toFixed(1));
    c.sill.setAttribute('stroke-width', Math.max(0.6, 0.035 * k).toFixed(2));
    // the end wall the camera sees gets its window too
    [[RIGHT_END, 0], [LEFT_END, 1]].forEach(([ei, j]) => {
      const e = EDGES[ei], q = c.ends[j], N = axes(e.n[0], e.n[1], 0);
      const mid = frame((e.a[0] + e.b[0]) / 2, (e.a[1] + e.b[1]) / 2 - D, 0);
      if (dot(N, sub(CAM, mid)) <= 0) { q.setAttribute('visibility', 'hidden'); return; }
      const uAt = v => e.a[0] + (e.b[0] - e.a[0]) * (v - e.a[1]) / ((e.b[1] - e.a[1]) || 1);
      const lift = 0.004, ue = v => uAt(v) + Math.sign(e.n[0]) * lift;
      const s0w = -hw + 0.24, s1w = hw - 0.24;
      q.setAttribute('visibility', 'visible');
      q.setAttribute('points', pts([at(ue(WIN.v0), WIN.v0, s0w), at(ue(WIN.v1), WIN.v1, s0w), at(ue(WIN.v1), WIN.v1, s1w), at(ue(WIN.v0), WIN.v0, s1w)]));
      q.setAttribute('fill', glass(N, mid));
    });
    // hanger: down from the grip, out to the side away from the mast, back in to the middle of the roof
    const o = c.side * 0.5;
    const H = [[0, 0, 0], [0, -0.45, 0], [0, -0.95, o], [0, -1.3, o], [0, -1.85, o], [0, -2.35, o], [0, -D + 0.05, 0]].map(([u, w, s]) => { const p = frame(u, w, s); return P(p[0], p[1], p[2]); });
    const f = q => q[0].toFixed(1) + ' ' + q[1].toFixed(1);
    const d = `M${f(H[0])} L${f(H[1])} Q${f(H[2])} ${f(H[3])} L${f(H[4])} Q${f(H[5])} ${f(H[6])}`;
    c.hanger.setAttribute('d', d); c.hanger.setAttribute('stroke-width', Math.max(1.4, 0.13 * k).toFixed(2));
    c.hangerHi.setAttribute('d', d); c.hangerHi.setAttribute('stroke-width', Math.max(0.5, 0.04 * k).toFixed(2));
    c.hangerHi.setAttribute('transform', `translate(${(0.03 * k).toFixed(2)} 0)`);
    // grip on the rope, and the coupling block on the roof
    const faces = boxFaces(frame, axes, [0, 0.08, 0], [0.42, 0.16, 0.14], ALB.dark)
      .concat(boxFaces(frame, axes, [0, -D + 0.09, 0], [0.34, 0.09, 0.3], ALB.roof));
    let html = '';
    faces.forEach(fc => { html += `<polygon points="${pts(fc.p)}" fill="${fc.fill}"/>`; });
    c.parts.innerHTML = html;
  }

  /* ---------- the foreground mast: tubular steel column, crossarm, a sheave train under each rope ---------- */
  function drawMast(g) {
    const zc = zAt(MAST.x, 0);
    const topY = MAST.h - 1.9;
    const top = P(MAST.x, topY, zc), base = P(MAST.x, 0, zc);
    const k = top[2];
    const w1 = 1.25 * k, w0 = 2.6 * k;
    el('path', { d: `M${base[0] - w0 / 2} ${base[1]} L${top[0] - w1 / 2} ${top[1]} L${top[0] + w1 / 2} ${top[1]} L${base[0] + w0 / 2} ${base[1]} Z`, fill: 'url(#mastShade)' }, g);
    // the street canyon darkens the lower shaft
    el('path', { d: `M${base[0] - w0 / 2} ${base[1]} L${top[0] - w1 / 2} ${top[1]} L${top[0] + w1 / 2} ${top[1]} L${base[0] + w0 / 2} ${base[1]} Z`, fill: 'url(#mastFoot)' }, g);
    // a climbing ladder up the shaded side, very faint
    el('line', { x1: base[0] - w0 * 0.3, y1: base[1], x2: top[0] - w1 * 0.3, y2: top[1], stroke: '#5d6064', 'stroke-width': Math.max(0.8, 0.06 * k), opacity: 0.45 }, g);
    // crossarm running across the line (toward the camera), on a short neck
    const parts = [];
    const add = list => list.forEach(fc => parts.push(fc));
    const zN = zAt(MAST.x, -1), zF = zAt(MAST.x, 1);
    add(boxFaces(WORLD, WAXES, [MAST.x, topY + 0.35, zc], [0.4, 0.35, 0.4], [150, 151, 150]));
    add(boxFaces(WORLD, WAXES, [MAST.x, topY + 0.85, (zN + zF) / 2], [0.28, 0.22, (zF - zN) / 2 + 0.55], [168, 168, 165]));
    // under each rope: a hanger plate and a rocker beam carrying six sheaves
    [1, -1].forEach(side => {
      const zz = zAt(MAST.x, side), ry = ropeY(MAST.x);
      add(boxFaces(WORLD, WAXES, [MAST.x, (topY + 1.07 + ry - 0.55) / 2, zz], [0.12, Math.max(0.05, (ry - 0.55 - topY - 1.07) / 2), 0.08], [110, 112, 114]));
      add(boxFaces(WORLD, WAXES, [MAST.x, ry - 0.5, zz], [2.9, 0.13, 0.11], [96, 99, 103]));
    });
    parts.forEach(fc => el('polygon', { points: pts(fc.p), fill: fc.fill }, g));
    [1, -1].forEach(side => {
      const zz = zAt(MAST.x, side), ry = ropeY(MAST.x);
      for (let j = -2.5; j <= 2.5; j += 1) {
        const q = P(MAST.x + j, ry - 0.22, zz);
        el('circle', { cx: q[0].toFixed(1), cy: q[1].toFixed(1), r: (0.21 * q[2]).toFixed(1), fill: '#45484c' }, g);
        el('circle', { cx: q[0].toFixed(1), cy: q[1].toFixed(1), r: (0.07 * q[2]).toFixed(1), fill: '#a8a9a7' }, g);
      }
    });
  }

  function ropePath(side) {
    let d = '';
    for (let x = -150; x <= 170; x += 0.5) {
      const q = P(x, ropeY(x), zAt(x, side));
      d += (d ? 'L' : 'M') + q[0].toFixed(1) + ' ' + q[1].toFixed(1);
    }
    return d;
  }

  /* ---------- build ---------- */
  // Each rope carries cabins 120 m apart at 5 m/s: one every 24 s per direction (the FAQ says every 20 to 30 s).
  const XA = -120, XB = 120, LOOP = XB - XA, SPEED = 5;
  function build(svg) {
    const defs = el('defs', { id: 'sceneDefs' }, svg);
    const ms = el('linearGradient', { id: 'mastShade', x1: 0, y1: 0, x2: 1, y2: 0 }, defs);
    [['0', '#55585a'], ['.18', '#7d7e7b'], ['.55', '#b9b7b0'], ['.72', '#d3d1c9'], ['.8', '#c4c2bb'], ['1', '#7f7e7a']].forEach(([o, c]) => el('stop', { offset: o, 'stop-color': c }, ms));
    const mf = el('linearGradient', { id: 'mastFoot', x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    [['0', 0], ['.35', 0], ['.75', 0.22], ['1', 0.35]].forEach(([o, a]) => el('stop', { offset: o, 'stop-color': '#1d2228', 'stop-opacity': a }, mf));
    const soft = el('filter', { id: 'lens', x: '-10%', y: '-10%', width: '120%', height: '120%' }, defs);
    el('feGaussianBlur', { stdDeviation: 0.5 }, soft);
    // passing cloud shadows on the town (never on the sky)
    const cg = el('radialGradient', { id: 'cloudShade' }, defs);
    [['0', 0.5], ['.55', 0.28], ['1', 0]].forEach(([o, a]) => el('stop', { offset: o, 'stop-color': '#0d1520', 'stop-opacity': a }, cg));
    const clip = el('clipPath', { id: 'town' }, defs);
    el('rect', { x: 0, y: HY + 40, width: PW, height: PH }, clip);
    const clouds = el('g', { 'clip-path': 'url(#town)', opacity: 0.3 }, svg);
    const cloud = [[0.0, 1050, 820, 300, 150], [0.55, 1330, 620, 230, 200]].map(([ph, y, rx, ry, period]) => ({ e: el('ellipse', { cy: y, rx, ry, fill: 'url(#cloudShade)' }, clouds), ph, period, rx }));

    const L = {
      birds: el('g', { fill: 'none', stroke: '#3a3f46', 'stroke-width': 1.3, 'stroke-linecap': 'round', opacity: 0.6 }, svg),
      farRope: el('g', {}, svg), farCab: el('g', {}, svg), mast: el('g', {}, svg), nearRope: el('g', {}, svg), nearCab: el('g', {}, svg)
    };
    [[1, L.farRope, '#43464a', 2.2], [-1, L.nearRope, '#383b3f', 2.7]].forEach(([side, layer, col, w]) => {
      const d = ropePath(side);
      el('path', { d, stroke: col, 'stroke-width': w, fill: 'none', 'stroke-linecap': 'round', opacity: 0.92 }, layer);
      el('path', { d, stroke: '#f2f1ec', 'stroke-width': w * 0.3, fill: 'none', opacity: 0.32, transform: 'translate(0 -0.7)' }, layer);
    });
    drawMast(L.mast);
    const cabins = [];
    // near rope runs left to right, far rope right to left; two cabins on each, half a loop apart
    [[-1, L.nearCab, 1, 0.30], [-1, L.nearCab, 1, 0.80], [1, L.farCab, -1, 0.42], [1, L.farCab, -1, 0.92]].forEach(([side, layer, dir, phase]) => {
      const c = makeCabin(layer, side); c.dir = dir; c.phase = phase; cabins.push(c);
    });
    const birds = [[0.0, 520, 1.0, 46], [0.06, 545, 0.8, 50], [0.6, 470, 0.9, 58]].map(([ph, y, s, speed]) => {
      const gg = el('g', {}, L.birds), w = el('path', { d: '' }, gg);
      return { g: gg, w, ph, y, s, speed };
    });
    return { cabins, birds, cloud };
  }

  function frame(S, t, dt) {
    S.cabins.forEach(c => {
      const k = ((t * SPEED / LOOP + c.phase) % 1 + 1) % 1;
      const x = c.dir > 0 ? XA + k * LOOP : XB - k * LOOP;
      if (x < -75 || x > 90) { c.g.setAttribute('visibility', 'hidden'); c.last = null; return; }
      c.g.setAttribute('visibility', 'visible');
      // passing over the mast's sheaves changes the rope's slope: the cabin starts to swing, then settles
      const slope = (ropeY(x + 0.5) - ropeY(x - 0.5)) * c.dir;
      if (c.last !== null) c.omega += (slope - c.last) * 2.2;
      c.last = slope;
      c.omega += (-1.9 * c.theta - 0.45 * c.omega) * dt;
      c.theta += c.omega * dt;
      const wind = Math.sin(t * 0.45 + c.phase * 9) * 0.006;
      drawCabin(c, x, Math.max(-0.09, Math.min(0.09, c.theta + wind)) * c.dir);
    });
    S.cloud.forEach(cl => {
      const span = PW + 2 * cl.rx, k = ((t / cl.period + cl.ph) % 1 + 1) % 1;
      cl.e.setAttribute('cx', (-cl.rx + k * span).toFixed(1));
    });
    S.birds.forEach(b => {
      const span = PW + 200, k = ((t / b.speed + b.ph) % 1 + 1) % 1;
      const x = -100 + k * span, y = b.y + Math.sin(t * 0.6 + b.ph * 20) * 8;
      const beat = Math.sin(t * 0.9 + b.ph * 13) > 0.2 ? Math.sin(t * 11 + b.ph * 30) * 2.6 : 0.6;   // glide, then a few beats
      const w = 6.5 * b.s, f = beat * b.s;
      b.w.setAttribute('d', `M${-w} ${-f} Q${-w / 2} ${-f - 2 * b.s} 0 0 Q${w / 2} ${-f - 2 * b.s} ${w} ${-f}`);
      b.g.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)})`);
    });
  }

  window.CityScene = {
    mount(svg, img) {
      svg.setAttribute('viewBox', `0 0 ${PW} ${PH}`);
      svg.setAttribute('preserveAspectRatio', 'xMidYMid slice');
      if (img) img.style.objectPosition = '50% 50%';
      const S = build(svg);
      let t = 3, last = performance.now(), visible = true;
      frame(S, t, 0.016);
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return S;
      document.addEventListener('visibilitychange', () => { visible = !document.hidden; last = performance.now(); });
      (function loop(now) {
        const dt = Math.min(0.05, (now - last) / 1000); last = now;
        if (visible) { t += dt; frame(S, t, dt); }
        requestAnimationFrame(loop);
      })(performance.now());
      return S;
    }
  };
})();
