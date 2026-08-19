/* ------------------------------------------------------------------
   Bangladesh crime statistics — dashboard logic.

   One page, cross-filtered: picking a jurisdiction or an offence
   re-scopes every panel at once, and the timeline brush re-scopes the
   period. No tabs, because the whole point is to hold the map, the
   ranking and the trend in view together.

   Dependency-free on purpose. The projection is equirectangular with a
   cos(lat) correction, which is fine at country scale and keeps the
   page to three static files.
   ------------------------------------------------------------------ */
'use strict';

const $ = (s) => document.querySelector(s);
const NS = 'http://www.w3.org/2000/svg';
const fmt = (n) => (n == null || !isFinite(n) ? '—' : Math.round(n).toLocaleString('en-US'));
const fmt1 = (n) => (n == null || !isFinite(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
const fmtCompact = (n) =>
  n >= 1e6 ? (n / 1e6).toFixed(1) + 'm' : n >= 1e4 ? Math.round(n / 1e3) + 'k' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'k' : String(Math.round(n));
const pctStr = (v) => {
  const r = Math.abs(v) < 0.05 ? 0 : v;   // -0.0% reads as a fall that is not there
  return (r > 0 ? '+' : '') + r.toFixed(1) + '%';
};
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const mLabel = (ym) => MONTHS[+ym.slice(5, 7) - 1] + " '" + ym.slice(2, 4);
const mLong = (ym) => MONTHS[+ym.slice(5, 7) - 1] + ' ' + ym.slice(0, 4);

/* Governments over the covered period. The dashboard is built around these
   because the interesting question in this data is what changed at each
   handover — and because the three run 55, 18 and 6 months, every comparison
   between them has to be per month rather than a total. */
const TENURES = [
  { id: 't1', name: 'Awami League',       short: 'AL',      from: '2020-01', to: '2024-07', ink: 'var(--t1-ink)', wash: 'var(--t1-wash)' },
  { id: 't2', name: 'Interim government', short: 'Interim', from: '2024-08', to: '2026-01', ink: 'var(--t2-ink)', wash: 'var(--t2-wash)' },
  { id: 't3', name: 'Elected government', short: 'Elected', from: '2026-02', to: '2026-07', ink: 'var(--t3-ink)', wash: 'var(--t3-wash)' },
];

let DATA = null, GEO = null;
let NM = 0, NU = 0, NC = 0, YEARS = [];
const state = { offence: -1, measure: 'count', m0: 0, m1: 0, unit: null, season: 'grid' };
let brush = null;

/* ------------------------------------------------------------------ helpers */

function el(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
  return e;
}
function txt(e, s) { e.textContent = s; return e; }

const tip = $('#tip');
function showTip(evt, html) {
  tip.innerHTML = html;
  tip.classList.add('on');
  const r = tip.getBoundingClientRect();
  let x = evt.clientX + 14, y = evt.clientY + 14;
  if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - 14;
  if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - 14;
  tip.style.left = x + 'px';
  tip.style.top = y + 'px';
}
const hideTip = () => tip.classList.remove('on');
function hoverable(node, html) {
  node.addEventListener('pointerenter', (e) => showTip(e, typeof html === 'function' ? html() : html));
  node.addEventListener('pointermove', (e) => showTip(e, typeof html === 'function' ? html() : html));
  node.addEventListener('pointerleave', hideTip);
}

function niceTicks(max, count) {
  if (max <= 0) return [0];
  const raw = max / count, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
  const out = [];
  for (let v = 0; v <= max + step * 0.001; v += step) out.push(v);
  return out;
}

/** Quantile breaks over the non-zero values. Recorded crime is heavily skewed —
 *  Dhaka Range alone is a fifth of the country — so equal-width bins would paint
 *  every other division the same palest step. */
function quantileBreaks(values, nBins) {
  const v = values.filter((x) => x > 0).sort((a, b) => a - b);
  if (!v.length) return [];
  const out = [];
  for (let i = 1; i < nBins; i++) {
    const p = (i / nBins) * (v.length - 1);
    const lo = Math.floor(p), hi = Math.ceil(p);
    out.push(v[lo] + (v[hi] - v[lo]) * (p - lo));
  }
  return out;
}
const binOf = (val, breaks) => {
  if (!(val > 0)) return -1;
  let i = 0;
  while (i < breaks.length && val > breaks[i]) i++;
  return i;
};

function makeProjection(bbox, width, height, pad) {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const kx = Math.cos(((minLat + maxLat) / 2) * Math.PI / 180);
  const w = (maxLon - minLon) * kx, h = maxLat - minLat;
  const s = Math.min((width - 2 * pad) / w, (height - 2 * pad) / h);
  const ox = (width - w * s) / 2, oy = (height - h * s) / 2;
  return (lon, lat) => [ox + (lon - minLon) * kx * s, oy + (maxLat - lat) * s];
}
function fitHeight(bbox, width, pad, maxH) {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const kx = Math.cos(((minLat + maxLat) / 2) * Math.PI / 180);
  const aspect = ((maxLon - minLon) * kx) / (maxLat - minLat);
  return Math.min(maxH, Math.round((width - 2 * pad) / aspect) + 2 * pad);
}
function pathFor(geometry, proj) {
  const parts = [];
  const ring = (coords) => {
    let d = '';
    for (let i = 0; i < coords.length; i++) {
      const p = proj(coords[i][0], coords[i][1]);
      d += (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1);
    }
    return d + 'Z';
  };
  if (geometry.type === 'Polygon') geometry.coordinates.forEach((r) => parts.push(ring(r)));
  else geometry.coordinates.forEach((poly) => poly.forEach((r) => parts.push(ring(r))));
  return parts.join('');
}
function bboxOf(fc) {
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  fc.features.forEach((f) => {
    const g = f.geometry;
    (g.type === 'Polygon' ? [g.coordinates] : g.coordinates).forEach((poly) =>
      poly.forEach((ring) => ring.forEach((p) => {
        if (p[0] < x0) x0 = p[0];
        if (p[0] > x1) x1 = p[0];
        if (p[1] < y0) y0 = p[1];
        if (p[1] > y1) y1 = p[1];
      })));
  });
  return [x0, y0, x1, y1];
}

/* -------------------------------------------------------------- aggregation */

const monthIdx = (ym) => DATA.months.indexOf(ym);
const tenureRange = (t) => [monthIdx(t.from), monthIdx(t.to)];
const isRate = () => state.measure === 'rate';

/** One (month, unit) cell for the selected offence. */
function cell(m, u) {
  const row = DATA.values[m][u];
  if (state.offence < 0) { let s = 0; for (let c = 0; c < NC; c++) s += row[c]; return s; }
  return row[state.offence];
}
/** Monthly national (or selected-unit) series across the whole record. Never
 *  sliced to the window, because a rolling mean needs the months either side. */
function series(offence = state.offence, unit = state.unit) {
  const out = new Array(NM).fill(0);
  for (let m = 0; m < NM; m++) {
    if (unit != null) {
      const row = DATA.values[m][unit];
      out[m] = offence < 0 ? row.reduce((a, b) => a + b, 0) : row[offence];
    } else {
      let s = 0;
      for (let u = 0; u < NU; u++) {
        const row = DATA.values[m][u];
        s += offence < 0 ? row.reduce((a, b) => a + b, 0) : row[offence];
      }
      out[m] = s;
    }
  }
  return out;
}
function unitTotals(m0 = state.m0, m1 = state.m1) {
  const out = new Array(NU).fill(0);
  for (let m = m0; m <= m1; m++) for (let u = 0; u < NU; u++) out[u] += cell(m, u);
  return out;
}
function offenceTotals(m0 = state.m0, m1 = state.m1) {
  const out = new Array(NC).fill(0);
  for (let m = m0; m <= m1; m++) {
    if (state.unit != null) { for (let c = 0; c < NC; c++) out[c] += DATA.values[m][state.unit][c]; }
    else for (let u = 0; u < NU; u++) for (let c = 0; c < NC; c++) out[c] += DATA.values[m][u][c];
  }
  return out;
}
/** Cases per 100,000 residents per year. Null where there is no population —
 *  Railway Range polices a network, not a place. */
function rateOf(total, unit, m0 = state.m0, m1 = state.m1) {
  const pop = DATA.units[unit].population;
  if (!pop) return null;
  return total / ((m1 - m0 + 1) / 12) / pop * 1e5;
}
function displayUnit(total, u) { return isRate() ? rateOf(total, u) : total; }

const offenceName = () => (state.offence < 0 ? 'All offences' : DATA.crimes[state.offence]);
const unitName = (u) => DATA.units[u].short || DATA.units[u].label;
const scopeLabel = () => (state.unit == null ? 'Bangladesh' : DATA.units[state.unit].label);

/* ------------------------------------------------------------------- KPIs */

function renderKpis() {
  const s = series();
  const win = s.slice(state.m0, state.m1 + 1);
  const n = win.length;
  const total = win.reduce((a, b) => a + b, 0);

  // Compare with the equally long stretch immediately before, when there is one.
  const pStart = state.m0 - n;
  const prev = pStart >= 0 ? s.slice(pStart, state.m0).reduce((a, b) => a + b, 0) : null;
  const delta = prev ? ((total - prev) / prev) * 100 : null;

  const natPop = DATA.units.reduce((a, u) => a + (u.population || 0), 0);
  const unitPop = state.unit != null ? DATA.units[state.unit].population : natPop;
  const asRate = (v) => (unitPop ? v / (n / 12) / unitPop * 1e5 : null);

  $('#k1-label').textContent = offenceName();
  $('#k1').textContent = isRate() ? fmt1(asRate(total)) : fmt(total);
  $('#k1-sub').innerHTML =
    (isRate() ? 'per 100k residents / yr' : `${n} months`) +
    (delta == null ? '' : ` <span class="delta ${Math.abs(delta) < 1 ? 'flat' : delta > 0 ? 'up' : 'down'}">${pctStr(delta)}</span> vs previous ${n}`);

  $('#k2').textContent = fmt(total / n);
  $('#k2-sub').textContent = 'cases per month' + (state.unit != null ? ' in ' + unitName(state.unit) : '');

  const totals = unitTotals();
  const ranked = DATA.units.map((u, i) => ({ u, i, v: displayUnit(totals[i], i) }))
    .filter((o) => o.v != null && isFinite(o.v) && o.v > 0)
    .sort((a, b) => b.v - a.v);
  $('#k3-label').textContent = isRate() ? 'Highest rate' : 'Most cases';
  if (ranked.length) {
    $('#k3').textContent = unitName(ranked[0].i);
    $('#k3-sub').textContent = isRate() ? fmt1(ranked[0].v) + ' per 100k / yr' : fmt(ranked[0].v) + ' cases';
  } else { $('#k3').textContent = '—'; $('#k3-sub').textContent = ''; }

  let bi = state.m0;
  for (let m = state.m0; m <= state.m1; m++) if (s[m] > s[bi]) bi = m;
  $('#k4').textContent = mLong(DATA.months[bi]);
  $('#k4-sub').textContent = fmt(s[bi]) + ' cases';

  $('#period-readout').textContent =
    `${mLong(DATA.months[state.m0])} – ${mLong(DATA.months[state.m1])}`;
}

/* ------------------------------------------------------- selection chips */

function chip(label, onClear) {
  const c = document.createElement('span');
  c.className = 'chip';
  c.appendChild(document.createTextNode(label));
  if (onClear) {
    const b = document.createElement('button');
    b.type = 'button';
    b.setAttribute('aria-label', 'Clear ' + label);
    b.textContent = '×';
    b.addEventListener('click', onClear);
    c.appendChild(b);
  }
  return c;
}
function renderSelbar() {
  const host = $('#sel-chips');
  host.replaceChildren();
  host.appendChild(chip(offenceName(), state.offence < 0 ? null : () => { state.offence = -1; $('#offence').value = '-1'; render(); }));
  host.appendChild(chip(scopeLabel(), state.unit == null ? null : () => { state.unit = null; render(); }));
  const full = state.m0 === 0 && state.m1 === NM - 1;
  host.appendChild(chip(`${mLabel(DATA.months[state.m0])} – ${mLabel(DATA.months[state.m1])}`,
    full ? null : () => { state.m0 = 0; state.m1 = NM - 1; render(); }));
}

/* ----------------------------------------------------------- period presets */

function presetList() {
  const out = [{ id: 'all', label: 'All years', m0: 0, m1: NM - 1 }];
  TENURES.forEach((t) => {
    const [a, b] = tenureRange(t);
    out.push({ id: t.id, label: t.short, m0: a, m1: b, ink: t.ink });
  });
  out.push({ id: 'l12', label: 'Last 12 months', m0: Math.max(0, NM - 12), m1: NM - 1 });
  return out;
}
function renderPresets() {
  const host = $('#presets');
  host.replaceChildren();
  presetList().forEach((p) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = p.label;
    const on = state.m0 === p.m0 && state.m1 === p.m1;
    b.setAttribute('aria-pressed', String(on));
    b.addEventListener('click', () => { state.m0 = p.m0; state.m1 = p.m1; render(); });
    host.appendChild(b);
  });
}

/* ------------------------------------------------------------- timeline */

function renderTimeline() {
  const host = $('#timeline');
  const W = host.clientWidth || 900, H = 168;
  const padL = 52, padR = 14, padT = 26, padB = 26;
  const s = series();
  const max = Math.max(1, ...s);
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.setAttribute('aria-label', `Monthly ${offenceName()} for ${scopeLabel()}; drag to select a period`);

  const x = (i) => padL + (i / Math.max(1, NM - 1)) * (W - padL - padR);
  const y = (v) => H - padB - (v / max) * (H - padT - padB);
  const band = (W - padL - padR) / Math.max(1, NM - 1);

  // Tenure bands sit behind everything, as washes rather than blocks: they are
  // context for the line, not a series of their own.
  TENURES.forEach((t) => {
    const [a, b] = tenureRange(t);
    svg.appendChild(el('rect', { x: x(a), y: padT, width: Math.max(0, x(b) - x(a) + band / 2), height: H - padT - padB, fill: t.wash }));
    // Name the band only where there is room for it; the legend below carries
    // the full names and dates, so a cramped label here is pure clutter.
    const w = x(b) - x(a);
    if (w > 70) {
      const lab = el('text', { x: x(a) + w / 2, y: padT - 9, 'text-anchor': 'middle', class: 'axis' });
      lab.setAttribute('fill', t.ink);
      lab.setAttribute('font-weight', '650');
      svg.appendChild(txt(lab, t.short));
    }
  });

  niceTicks(max, 4).forEach((v) => {
    svg.appendChild(el('line', { class: 'gridline', x1: padL, x2: W - padR, y1: y(v), y2: y(v) }));
    const t = el('text', { x: padL - 7, y: y(v) + 4, 'text-anchor': 'end', class: 'axis' });
    svg.appendChild(txt(t, fmtCompact(v)));
  });

  let area = `M${x(0)} ${y(0)}`, line = '';
  for (let i = 0; i < NM; i++) {
    area += `L${x(i).toFixed(1)} ${y(s[i]).toFixed(1)}`;
    line += (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(s[i]).toFixed(1);
  }
  area += `L${x(NM - 1)} ${y(0)}Z`;
  svg.appendChild(el('path', { d: area, fill: 'var(--range)', 'fill-opacity': .13 }));
  svg.appendChild(el('path', { d: line, fill: 'none', stroke: 'var(--range)', 'stroke-width': 2, 'stroke-linejoin': 'round' }));

  // Transition rules: the moment of handover, drawn once and labelled.
  TENURES.slice(1).forEach((t) => {
    const i = monthIdx(t.from);
    svg.appendChild(el('line', { x1: x(i), x2: x(i), y1: padT, y2: H - padB, stroke: t.ink, 'stroke-width': 1.5, 'stroke-opacity': .9 }));
    const lb = el('text', { x: x(i), y: padT + 11, 'text-anchor': x(i) > W - 90 ? 'end' : 'start', class: 'axis' });
    lb.setAttribute('fill', t.ink);
    lb.setAttribute('font-weight', '650');
    lb.setAttribute('dx', x(i) > W - 90 ? -4 : 4);
    svg.appendChild(txt(lb, mLabel(t.from)));
  });

  if (state.m0 > 0)
    svg.appendChild(el('rect', { class: 'brush-out', x: padL, y: padT, width: Math.max(0, x(state.m0) - padL), height: H - padT - padB }));
  if (state.m1 < NM - 1)
    svg.appendChild(el('rect', { class: 'brush-out', x: x(state.m1), y: padT, width: Math.max(0, W - padR - x(state.m1)), height: H - padT - padB }));

  const nTicks = Math.max(3, Math.min(8, Math.round(W / 130)));
  for (let i = 0; i < NM; i += Math.ceil(NM / nTicks)) {
    const t = el('text', { x: x(i), y: H - 7, 'text-anchor': 'middle', class: 'axis' });
    svg.appendChild(txt(t, mLabel(DATA.months[i])));
  }

  const hit = el('rect', { class: 'brush-bg', x: padL, y: padT, width: W - padL - padR, height: H - padT - padB });
  svg.appendChild(hit);
  const idxAt = (e) => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    return Math.max(0, Math.min(NM - 1, Math.round((px - padL) / band)));
  };
  hit.addEventListener('pointerdown', (e) => { brush = { start: idxAt(e), moved: false }; hit.setPointerCapture(e.pointerId); });
  hit.addEventListener('pointermove', (e) => {
    const i = idxAt(e);
    if (brush) {
      brush.moved = true;
      state.m0 = Math.min(brush.start, i);
      state.m1 = Math.max(brush.start, i);
      render();
      return;
    }
    const ten = TENURES.find((t) => { const [a, b] = tenureRange(t); return i >= a && i <= b; });
    showTip(e, `<div class="t-name">${mLong(DATA.months[i])}</div>
      <div class="t-row"><span>${offenceName()}</span><b>${fmt(s[i])}</b></div>
      <div class="t-sub">${scopeLabel()}${ten ? ' · ' + ten.name : ''}</div>`);
  });
  hit.addEventListener('pointerleave', hideTip);
  hit.addEventListener('pointerup', () => {
    if (brush && !brush.moved) { state.m0 = 0; state.m1 = NM - 1; render(); }
    brush = null;
  });

  host.replaceChildren(svg);
  $('#timeline-legend').innerHTML =
    TENURES.map((t) => `<span class="key"><i class="sw" style="background:${t.ink};opacity:.55"></i>${t.name} · ${mLabel(t.from)}–${mLabel(t.to)}</span>`).join('') +
    '<span class="key" style="color:var(--text-muted)">Drag the chart to choose a period</span>';
}

/* ------------------------------------------------------------------- maps */

const RAMP_R = ['--r-200','--r-300','--r-400','--r-500','--r-600','--r-800'];
const RAMP_C = ['--c-200','--c-300','--c-400','--c-500','--c-600','--c-800'];

/** Division choropleth: the Range jurisdictions, one polygon each. */
function renderRangeMap() {
  const host = $('#range-map');
  const totals = unitTotals();
  const byDiv = {};
  DATA.units.forEach((u, i) => { if (u.kind === 'range') byDiv[u.division] = { i, v: displayUnit(totals[i], i) }; });

  const W = host.clientWidth || 480;
  const bbox = bboxOf(GEO);
  const H = fitHeight(bbox, W, 8, 460);
  const proj = makeProjection(bbox, W, H, 8);
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.setAttribute('aria-label', `${offenceName()} by Range jurisdiction`);

  const vals = Object.values(byDiv).map((d) => d.v).filter((v) => v != null && isFinite(v));
  const breaks = quantileBreaks(vals, RAMP_R.length);

  GEO.features.forEach((f) => {
    const name = f.properties.name;
    const d = byDiv[name];
    const b = d ? binOf(d.v, breaks) : -1;
    const p = el('path', {
      d: pathFor(f.geometry, proj),
      fill: b < 0 ? 'var(--empty)' : `var(${RAMP_R[b]})`,
      stroke: d && state.unit === d.i ? 'var(--text-primary)' : 'var(--surface-1)',
      'stroke-width': d && state.unit === d.i ? 2.2 : 1.1,
      style: 'cursor:pointer',
    });
    p.setAttribute('tabindex', '0');
    if (d) {
      const pick = () => { state.unit = state.unit === d.i ? null : d.i; render(); };
      p.addEventListener('click', pick);
      p.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
      hoverable(p, () => `<div class="t-name">${DATA.units[d.i].label}</div>
        <div class="t-row"><span>${offenceName()}</span><b>${isRate() ? fmt1(d.v) : fmt(totals[d.i])}</b></div>
        <div class="t-sub">${name} division, outside its metropolitan cities · click to filter</div>`);
    }
    svg.appendChild(p);
  });
  host.replaceChildren(svg);
  legendRamp($('#range-legend'), breaks, RAMP_R, vals);
}

/** Metropolitan forces.
 *
 *  These are drawn as fixed-size markers at each city, not as areas and not as
 *  value-scaled circles. Two reasons, both about not claiming more than the
 *  data supports. Metropolitan police boundaries are not published as open
 *  data, and a metropolitan area is a subset of its district — so shading the
 *  host district would draw a jurisdiction several times its real size. And
 *  Dhaka and Gazipur are about 21km apart, so circles scaled by caseload
 *  overlap into one blob and imply a shared territory that does not exist.
 *
 *  So position is the honest part and carries location; colour carries the
 *  value; and magnitude comparison is left to the ranked bars below, where it
 *  reads properly anyway.
 */
function renderCityMap() {
  const host = $('#city-map');
  const totals = unitTotals();
  const metros = DATA.units.map((u, i) => ({ u, i })).filter((o) => o.u.kind === 'metro');

  const W = host.clientWidth || 480;
  const bbox = bboxOf(GEO);
  const H = fitHeight(bbox, W, 8, 460);
  const proj = makeProjection(bbox, W, H, 8);
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.setAttribute('aria-label', `${offenceName()} by metropolitan force`);

  GEO.features.forEach((f) =>
    svg.appendChild(el('path', { d: pathFor(f.geometry, proj), fill: 'var(--empty)', stroke: 'var(--surface-1)', 'stroke-width': 1.1 })));

  const vals = metros.map((o) => displayUnit(totals[o.i], o.i)).filter((v) => v != null && isFinite(v));
  const breaks = quantileBreaks(vals, RAMP_C.length);
  // Small enough that neighbouring cities never touch: Dhaka and Gazipur sit
  // about 15px apart at this scale.
  const R = Math.max(5, Math.min(7.5, Math.min(W, H) * 0.017));
  const placed = [];

  const nodes = metros.map((o) => ({
    ...o, v: displayUnit(totals[o.i], o.i), p: proj(o.u.lon, o.u.lat),
  }));

  nodes.forEach(({ u, i, v, p }) => {
    const bi = binOf(v, breaks);
    const c = el('circle', {
      cx: p[0], cy: p[1], r: R,
      fill: bi < 0 ? 'var(--empty)' : `var(${RAMP_C[bi]})`,
      stroke: state.unit === i ? 'var(--text-primary)' : 'var(--surface-1)',
      'stroke-width': state.unit === i ? 2.4 : 1.6,
      style: 'cursor:pointer',
    });
    c.setAttribute('tabindex', '0');
    const pick = () => { state.unit = state.unit === i ? null : i; render(); };
    c.addEventListener('click', pick);
    c.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
    hoverable(c, () => `<div class="t-name">${u.label}</div>
      <div class="t-row"><span>${offenceName()}</span><b>${isRate() ? fmt1(v) : fmt(totals[i])}</b></div>
      <div class="t-row"><span>Population</span><b>${fmt(u.population)}</b></div>
      <div class="t-sub">Marker shows the city, not the jurisdiction's extent · click to filter</div>`);
    svg.appendChild(c);
  });

  nodes.forEach(({ u, p }) => {
    const clashes = (px, py) =>
      placed.some((q) => Math.abs(q.x - px) < 36 && Math.abs(q.y - py) < 14) ||
      nodes.some((q) => q.p !== p && Math.hypot(q.p[0] - px, q.p[1] - py) < R + 7);
    const candidates = [
      [p[0], p[1] - R - 6], [p[0], p[1] + R + 13],
      [p[0] - R - 20, p[1] + 4], [p[0] + R + 20, p[1] + 4],
      [p[0], p[1] - R - 20], [p[0], p[1] + R + 26],
    ];
    const spot = candidates.find(([px, py]) => !clashes(px, py)) || candidates[0];
    placed.push({ x: spot[0], y: spot[1] });
    const t = el('text', {
      x: spot[0], y: spot[1], 'text-anchor': 'middle', class: 'axis',
      stroke: 'var(--surface-1)', 'stroke-width': 3, 'paint-order': 'stroke', 'stroke-linejoin': 'round',
    });
    t.setAttribute('fill', 'var(--text-primary)');
    t.setAttribute('font-weight', '650');
    svg.appendChild(txt(t, u.code));
  });

  host.replaceChildren(svg);
  legendRamp($('#city-legend'), breaks, RAMP_C, vals);
}

function legendRamp(host, breaks, ramp, vals, dots) {
  if (!vals.length) { host.replaceChildren(); return; }
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const f = isRate() ? fmt1 : fmtCompact;
  host.innerHTML =
    `<span>${f(lo)}</span>` +
    `<span class="ramp">${ramp.map((r) => `<i style="background:var(${r})"></i>`).join('')}</span>` +
    `<span>${f(hi)}</span>` +
    `<span style="color:var(--text-muted)">${isRate() ? 'per 100k / yr' : 'cases'} · equal-count bins</span>`;
}

/* -------------------------------------------------------------- rankings */

function barPanel(host, items, ramp, onPick, selected, valueFmt) {
  host.replaceChildren();
  const max = Math.max(1, ...items.map((i) => i.v || 0));
  items.forEach((it) => {
    const row = document.createElement('div');
    row.className = 'bar-row';
    row.setAttribute('role', 'button');
    row.tabIndex = 0;
    row.setAttribute('aria-pressed', String(it.key === selected));
    row.innerHTML =
      `<span class="nm">${it.name}</span>` +
      `<span class="track"><i style="width:${((it.v || 0) / max * 100).toFixed(1)}%;background:${it.color}"></i></span>` +
      `<span class="val">${valueFmt(it.v)}</span>`;
    const go = () => onPick(it.key);
    row.addEventListener('click', go);
    row.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    if (it.tip) hoverable(row, it.tip);
    host.appendChild(row);
  });
}

function renderRanks() {
  const totals = unitTotals();
  const items = DATA.units.map((u, i) => ({
    key: i, name: unitName(i), v: displayUnit(totals[i], i),
    color: u.kind === 'metro' ? 'var(--city)' : u.kind === 'range' ? 'var(--range)' : 'var(--text-muted)',
    tip: () => `<div class="t-name">${u.label}</div>
      <div class="t-row"><span>${offenceName()}</span><b>${fmt(totals[i])} cases</b></div>
      ${u.population ? `<div class="t-row"><span>Per 100k / yr</span><b>${fmt1(rateOf(totals[i], i))}</b></div>` : ''}
      <div class="t-sub">${u.kind === 'railway' ? 'Rail network — no territory or population' : (u.division || '') + (u.kind === 'metro' ? ' division · city force' : ' division · Range')}</div>`,
  })).filter((o) => o.v != null && isFinite(o.v));
  items.sort((a, b) => b.v - a.v);
  barPanel($('#rank-bars'), items, RAMP_R,
    (k) => { state.unit = state.unit === k ? null : k; render(); },
    state.unit, (v) => (isRate() ? fmt1(v) : fmtCompact(v)));
  $('#rank-hint').textContent = isRate()
    ? 'Cases per 100,000 residents a year. Railway Range has no population and is omitted.'
    : 'All seventeen reporting units for the current offence and period. Click one to filter.';

  const oTot = offenceTotals();
  const grand = oTot.reduce((a, b) => a + b, 0) || 1;
  const oItems = DATA.crimes.map((c, i) => ({
    key: i, name: c, v: oTot[i], color: 'var(--range)',
    tip: () => `<div class="t-name">${c}</div>
      <div class="t-row"><span>Cases</span><b>${fmt(oTot[i])}</b></div>
      <div class="t-row"><span>Share</span><b>${(oTot[i] / grand * 100).toFixed(1)}%</b></div>
      <div class="t-sub">${scopeLabel()} · click to filter to this offence</div>`,
  })).sort((a, b) => b.v - a.v);
  barPanel($('#offence-bars'), oItems, RAMP_R,
    (k) => { state.offence = state.offence === k ? -1 : k; $('#offence').value = String(state.offence); render(); },
    state.offence, fmtCompact);
  $('#offence-hint').textContent = `What ${scopeLabel()}'s caseload is made of over the selected period. Click one to filter.`;
}

/* -------------------------------------------------- year against year */

const YEAR_RAMP = ['--y1','--y2','--y3','--y4','--y5','--y6','--y7'];
const yearColor = (yi, nYears) =>
  `var(${YEAR_RAMP[Math.round((yi / Math.max(1, nYears - 1)) * (YEAR_RAMP.length - 1))]})`;

/** Values by [year][month]. Null where a month has not been published, so a
 *  part-year never draws a line down to zero. */
function yearMatrix() {
  const s = series();
  const m = {};
  YEARS.forEach((y) => (m[y] = new Array(12).fill(null)));
  DATA.months.forEach((ym, i) => { m[ym.slice(0, 4)][+ym.slice(5, 7) - 1] = s[i]; });
  return m;
}

function renderSeason() {
  const host = $('#season');
  return state.season === 'grid' ? seasonGrid(host) : seasonLines(host);
}

function seasonLines(host) {
  const M = yearMatrix();
  const W = host.clientWidth || 900, H = 320, padL = 54, padR = 62, padT = 16, padB = 30;
  const all = Object.values(M).flat().filter((v) => v != null);
  const max = Math.max(1, ...all);
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.setAttribute('aria-label', `${offenceName()} by month of year, one line per year`);
  const x = (i) => padL + (i / 11) * (W - padL - padR);
  const y = (v) => H - padB - (v / max) * (H - padT - padB);

  niceTicks(max, 4).forEach((v) => {
    svg.appendChild(el('line', { class: 'gridline', x1: padL, x2: W - padR, y1: y(v), y2: y(v) }));
    svg.appendChild(txt(el('text', { x: padL - 7, y: y(v) + 4, 'text-anchor': 'end', class: 'axis' }), fmtCompact(v)));
  });
  MONTHS.forEach((m, i) =>
    svg.appendChild(txt(el('text', { x: x(i), y: H - 9, 'text-anchor': 'middle', class: 'axis' }), m)));

  const ends = [];
  YEARS.forEach((yr, yi) => {
    const vals = M[yr];
    let d = '';
    vals.forEach((v, i) => { if (v != null) d += (d ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); });
    if (!d) return;
    svg.appendChild(el('path', { d, fill: 'none', stroke: yearColor(yi, YEARS.length), 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    let li = -1;
    vals.forEach((v, i) => { if (v != null) li = i; });
    if (li >= 0) ends.push({ yr, yi, x: x(li), y: y(vals[li]) });
  });

  // Direct-label every line so identity never rests on colour alone. Five years
  // can finish within a few pixels of one another, so nudge the labels apart
  // rather than let them overprint into an unreadable smudge.
  const MIN_GAP = 12;
  ends.sort((a, b) => a.y - b.y).forEach((e, i, arr) => {
    e.ly = i === 0 ? e.y : Math.max(e.y, arr[i - 1].ly + MIN_GAP);
  });
  ends.forEach((e) => {
    svg.appendChild(el('circle', { cx: e.x, cy: e.y, r: 3.4, fill: yearColor(e.yi, YEARS.length), stroke: 'var(--surface-1)', 'stroke-width': 1.6 }));
    if (Math.abs(e.ly - e.y) > 2)
      svg.appendChild(el('line', { x1: e.x + 3, y1: e.y, x2: e.x + 7, y2: e.ly - 4, stroke: 'var(--border-strong)', 'stroke-width': 1 }));
    const t = el('text', { x: e.x + 9, y: e.ly, class: 'axis' });
    t.setAttribute('fill', 'var(--text-secondary)');
    t.setAttribute('font-weight', '650');
    svg.appendChild(txt(t, e.yr));
  });

  // one hit column per month, covering the full height
  for (let i = 0; i < 12; i++) {
    const r = el('rect', { x: x(i) - (W - padL - padR) / 24, y: padT, width: (W - padL - padR) / 12, height: H - padT - padB, fill: 'transparent', style: 'cursor:crosshair' });
    hoverable(r, () => `<div class="t-name">${MONTHS[i]} · ${offenceName()}</div>` +
      YEARS.filter((y) => M[y][i] != null)
        .map((y) => `<div class="t-row"><span>${y}</span><b>${fmt(M[y][i])}</b></div>`).join('') +
      `<div class="t-sub">${scopeLabel()}</div>`);
    svg.appendChild(r);
  }
  host.replaceChildren(svg);
  $('#season-legend').innerHTML =
    YEARS.map((y, i) => `<span class="key"><i class="sw" style="background:${yearColor(i, YEARS.length)}"></i>${y}</span>`).join('') +
    `<span class="key" style="color:var(--text-muted)">2026 runs to ${mLabel(DATA.months[NM - 1])}</span>`;
  $('#season-hint').textContent =
    'Every year on the same twelve months, so a seasonal shape separates from a rising or falling level. Oldest year is palest.';
}

/** Month-by-year grid. With seven years the lines can tangle; the grid trades
 *  exact values for an immediate read of which months run hot in which years. */
function seasonGrid(host) {
  const M = yearMatrix();
  const W = host.clientWidth || 900;
  const padL = 52, padT = 22, padR = 10;
  const cw = (W - padL - padR) / 12, ch = 30, gap = 2;
  const H = padT + YEARS.length * ch + 8;
  const all = Object.values(M).flat().filter((v) => v != null);
  const breaks = quantileBreaks(all, RAMP_R.length);
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.setAttribute('aria-label', `${offenceName()} by month and year`);

  MONTHS.forEach((m, i) =>
    svg.appendChild(txt(el('text', { x: padL + i * cw + cw / 2, y: padT - 8, 'text-anchor': 'middle', class: 'axis' }), m)));
  YEARS.forEach((yr, yi) => {
    svg.appendChild(txt(el('text', { x: padL - 8, y: padT + yi * ch + ch / 2 + 4, 'text-anchor': 'end', class: 'axis' }), yr));
    for (let i = 0; i < 12; i++) {
      const v = M[yr][i];
      const b = v == null ? -1 : binOf(v, breaks);
      const r = el('rect', {
        x: padL + i * cw + gap / 2, y: padT + yi * ch + gap / 2,
        width: cw - gap, height: ch - gap, rx: 3,
        fill: v == null ? 'var(--empty)' : `var(${RAMP_R[b]})`,
      });
      if (v != null) hoverable(r, `<div class="t-name">${MONTHS[i]} ${yr}</div>
        <div class="t-row"><span>${offenceName()}</span><b>${fmt(v)}</b></div>
        <div class="t-sub">${scopeLabel()}</div>`);
      svg.appendChild(r);
    }
  });
  host.replaceChildren(svg);
  const lo = Math.min(...all), hi = Math.max(...all);
  $('#season-legend').innerHTML =
    `<span>${fmtCompact(lo)}</span><span class="ramp">${RAMP_R.map((r) => `<i style="background:var(${r})"></i>`).join('')}</span><span>${fmtCompact(hi)}</span>` +
    `<span style="color:var(--text-muted)">cases per month · equal-count bins · grey = not yet published</span>`;
  $('#season-hint').textContent =
    'One cell per month. Reading down a column shows how a given month changed year on year; reading across a row shows that year’s season.';
}

/* ------------------------------------------------- across the transitions */

/** Cases per month for one offence in one tenure, over the current scope. */
function tenureRate(offence, t) {
  const [a, b] = tenureRange(t);
  let s = 0;
  for (let m = a; m <= b; m++) {
    if (state.unit != null) {
      const row = DATA.values[m][state.unit];
      s += offence < 0 ? row.reduce((x, y) => x + y, 0) : row[offence];
    } else {
      for (let u = 0; u < NU; u++) {
        const row = DATA.values[m][u];
        s += offence < 0 ? row.reduce((x, y) => x + y, 0) : row[offence];
      }
    }
  }
  return s / (b - a + 1);
}

function renderTenure() {
  const host = $('#tenure');
  host.replaceChildren();

  // headline: the three periods side by side, per month
  const overall = TENURES.map((t) => ({ t, v: tenureRate(state.offence, t) }));
  const head = document.createElement('div');
  head.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:6px 0 18px';
  overall.forEach((o, i) => {
    const prev = i ? overall[i - 1].v : null;
    const d = prev ? ((o.v - prev) / prev) * 100 : null;
    const [a, b] = tenureRange(o.t);
    const box = document.createElement('div');
    box.style.cssText = `border:1px solid var(--border);border-left:3px solid ${o.t.ink};border-radius:9px;padding:11px 13px;background:var(--surface-2)`;
    box.innerHTML =
      `<div style="font-size:.71rem;font-weight:650;letter-spacing:.05em;text-transform:uppercase;color:${o.t.ink}">${o.t.name}</div>
       <div style="font-size:1.45rem;font-weight:650;letter-spacing:-.02em;margin:2px 0 1px">${fmt(o.v)}</div>
       <div style="font-size:.76rem;color:var(--text-muted)">cases per month · ${b - a + 1} months
         ${d == null ? '' : `<span class="delta ${Math.abs(d) < 1 ? 'flat' : d > 0 ? 'up' : 'down'}">${pctStr(d)}</span>`}</div>`;
    head.appendChild(box);
  });
  host.appendChild(head);

  // per-offence change at each handover, as a diverging bar
  const grid = document.createElement('div');
  grid.className = 'grid2';
  [[0, 1], [1, 2]].forEach(([ai, bi]) => {
    const A = TENURES[ai], B = TENURES[bi];
    const rows = DATA.crimes.map((c, i) => {
      const a = tenureRate(i, A), b = tenureRate(i, B);
      return { c, a, b, d: a > 0.5 ? ((b - a) / a) * 100 : null };
    }).filter((r) => r.d != null).sort((x, y) => y.d - x.d);

    const cap = Math.max(20, ...rows.map((r) => Math.abs(r.d)));
    const W = 470, rowH = 20, padL = 148, padR = 46;
    const H = rows.length * rowH + 34;
    const mid = padL + (W - padL - padR) / 2, half = (W - padL - padR) / 2;
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
    svg.setAttribute('aria-label', `Change in cases per month from ${A.name} to ${B.name}, by offence`);

    svg.appendChild(el('line', { x1: mid, x2: mid, y1: 4, y2: H - 26, stroke: 'var(--border-strong)', 'stroke-width': 1 }));
    rows.forEach((r, i) => {
      const y = 4 + i * rowH;
      const w = Math.min(1, Math.abs(r.d) / cap) * half * 0.94;
      const rect = el('rect', {
        x: r.d >= 0 ? mid : mid - w, y: y + 3, width: Math.max(w, 1.5), height: rowH - 7, rx: 2.5,
        fill: r.d >= 0 ? 'var(--up)' : 'var(--down)', 'fill-opacity': .85,
      });
      hoverable(rect, `<div class="t-name">${r.c}</div>
        <div class="t-row"><span>${A.short}</span><b>${fmt1(r.a)} / month</b></div>
        <div class="t-row"><span>${B.short}</span><b>${fmt1(r.b)} / month</b></div>
        <div class="t-sub">${pctStr(r.d)} · ${scopeLabel()}</div>`);
      svg.appendChild(rect);
      svg.appendChild(txt(el('text', { x: padL - 8, y: y + rowH / 2 + 3, 'text-anchor': 'end', class: 'axis' }),
        r.c.replace('Woman & Child Repression', 'Woman & child').replace('RC ', '')));
      const outside = r.d >= 0 ? mid + w + 5 : mid - w - 5;
      const fitsOutside = r.d >= 0 ? outside < W - 4 : outside > padL + 42;
      const v = el('text', {
        x: fitsOutside ? outside : (r.d >= 0 ? mid + w - 5 : mid - w + 5),
        y: y + rowH / 2 + 3,
        'text-anchor': fitsOutside === (r.d >= 0) ? 'start' : 'end',
        class: 'axis',
      });
      v.setAttribute('fill', fitsOutside ? 'var(--text-secondary)' : 'var(--surface-1)');
      v.setAttribute('font-weight', fitsOutside ? '400' : '650');
      svg.appendChild(txt(v, pctStr(r.d)));
    });
    svg.appendChild(txt(el('text', { x: mid, y: H - 8, 'text-anchor': 'middle', class: 'axis' }), 'no change'));
    svg.appendChild(txt(el('text', { x: mid - half * 0.94, y: H - 8, 'text-anchor': 'start', class: 'axis' }), '\u2212' + Math.round(cap) + '%'));
    svg.appendChild(txt(el('text', { x: mid + half * 0.94, y: H - 8, 'text-anchor': 'end', class: 'axis' }), '+' + Math.round(cap) + '%'));

    const sec = document.createElement('section');
    sec.innerHTML = `<h3 style="font-size:.9rem;font-weight:650;margin:0 0 2px">${A.short} → ${B.short}</h3>
      <p class="hint" style="margin:0 0 8px">Change in cases per month at the ${mLong(B.from)} handover.</p>`;
    sec.appendChild(svg);
    grid.appendChild(sec);
  });
  host.appendChild(grid);
}

/* ------------------------------------------------------------------ render */

function render() {
  renderSelbar();
  renderKpis();
  renderPresets();
  renderTimeline();
  renderRangeMap();
  renderCityMap();
  renderRanks();
  renderSeason();
  renderTenure();
}

/* -------------------------------------------------------------------- init */

function wire() {
  const sel = $('#offence');
  sel.innerHTML = '<option value="-1">All offences</option>' +
    DATA.crimes.map((c, i) => `<option value="${i}">${c}</option>`).join('');
  sel.value = String(state.offence);
  sel.addEventListener('change', (e) => { state.offence = +e.target.value; render(); });

  document.querySelectorAll('[data-measure]').forEach((b) =>
    b.addEventListener('click', () => {
      state.measure = b.dataset.measure;
      document.querySelectorAll('[data-measure]').forEach((o) => o.setAttribute('aria-pressed', String(o === b)));
      render();
    }));
  document.querySelectorAll('[data-season]').forEach((b) =>
    b.addEventListener('click', () => {
      state.season = b.dataset.season;
      document.querySelectorAll('[data-season]').forEach((o) => o.setAttribute('aria-pressed', String(o === b)));
      renderSeason();
    }));

  $('#reset-btn').addEventListener('click', () => {
    state.offence = -1; state.unit = null; state.m0 = 0; state.m1 = NM - 1;
    sel.value = '-1';
    render();
  });

  const themeBtn = $('#theme-btn');
  const saved = localStorage.getItem('crimebd-theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
  themeBtn.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme');
    const dark = cur ? cur === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    const next = dark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('crimebd-theme', next);
    render();                       // SVG fills resolve at draw time
  });

  let rt;
  addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(render, 180); });
}

Promise.all([
  fetch('data/crime.json').then((r) => r.json()),
  fetch('data/bd_divisions.geojson').then((r) => r.json()),
]).then(([d, g]) => {
  DATA = d; GEO = g;
  NM = DATA.months.length; NU = DATA.units.length; NC = DATA.crimes.length;
  YEARS = [...new Set(DATA.months.map((m) => m.slice(0, 4)))];
  state.m0 = 0; state.m1 = NM - 1;
  $('#foot-meta').textContent =
    `${DATA.meta.months} monthly sheets, ${mLong(DATA.meta.first_month)} to ${mLong(DATA.meta.last_month)}, across ${NU} jurisdictions and ${NC} offence categories.`;
  wire();
  render();
}).catch((err) => {
  $('#timeline').innerHTML =
    `<p style="color:var(--up)">Could not load the data files (${err}). If you opened this page from disk, serve the folder over HTTP instead — browsers block fetch on file:// URLs.</p>`;
});
