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

/* If a stale cache hands us this file without its string table, say so plainly
   rather than throwing and leaving a blank page behind. */
if (typeof I18N === 'undefined') {
  addEventListener('DOMContentLoaded', () => {
    const b = document.querySelector('.wrap') || document.body;
    b.insertAdjacentHTML('afterbegin',
      '<p style="padding:14px;margin:14px 0;border:1px solid #c5392f;border-radius:10px;color:#c5392f">' +
      'A cached copy of this page is out of step with its scripts. ' +
      'Reload with Ctrl/Cmd + Shift + R.</p>');
  });
  throw new Error('i18n.js did not load');
}

let LANG = 'en';
let T = I18N.en;
/** Bangla prose with Western digits reads like a machine wrote it. The locale
 *  also brings the lakh-crore grouping — ১০,৪৪,৩৬০, not ১,০৪৪,৩৬০ — which is
 *  what makes a large number scan correctly to a Bangla reader. */
const LOC = () => (LANG === 'bn' ? 'bn-BD' : 'en-US');
const num = (x) => (LANG === 'bn' ? toBnDigits(x) : String(x));

const fmt = (n) => (n == null || !isFinite(n) ? '—' : Math.round(n).toLocaleString(LOC()));
const fmt1 = (n) => (n == null || !isFinite(n) ? '—' : n.toLocaleString(LOC(), { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
/** Compact axis labels. Bangla gets লক্ষ rather than a Latin k, and below a
 *  lakh it simply spells the number out — ১৫,০০০ is short enough to read and a
 *  half-Latin label like ১৫k looks like a bug. */
const fmtCompact = (n) => {
  if (LANG === 'bn') {
    return n >= 1e5
      ? (n / 1e5).toLocaleString('bn-BD', { maximumFractionDigits: 1 }) + ' লক্ষ'
      : Math.round(n).toLocaleString('bn-BD');
  }
  return n >= 1e6 ? (n / 1e6).toFixed(1) + 'm'
       : n >= 1e4 ? Math.round(n / 1e3) + 'k'
       : n >= 1e3 ? (n / 1e3).toFixed(1) + 'k'
       : String(Math.round(n));
};
const pctStr = (v) => {
  const r = Math.abs(v) < 0.05 ? 0 : v;   // -0.0% reads as a fall that is not there
  return num((r > 0 ? '+' : r < 0 ? '−' : '') + Math.abs(r).toFixed(1) + '%');
};
const MONTHS_EN = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const mShort = (i) => T.months[i];
const mLabel = (ym) => T.months[+ym.slice(5, 7) - 1] + (LANG === 'bn' ? " '" + num(ym.slice(2, 4)) : " '" + ym.slice(2, 4));
const mLong = (ym) => T.monthsLong[+ym.slice(5, 7) - 1] + ' ' + num(ym.slice(0, 4));
const yearLabel = (y) => num(y);

/* Names that come off the data file rather than the string table. */
const crimeLabel = (i) => T.crimes[i];
const crimeShort = (i) => T.crimesShort[i];
function unitLabel(u, short) {
  if (LANG !== 'bn') return short ? (u.short || u.label) : u.label;
  const pair = NAMES_BN.units[u.code] || NAMES_BN.units[u.label];
  return pair ? pair[short ? 1 : 0] : u.label;
}
const divisionLabel = (d) => (LANG === 'bn' ? (NAMES_BN.divisions[d] || d) : d);
const tenureName = (t) => T.tenures[t.id];
const tenureShort = (t) => T.tenuresShort[t.id];

/* Governments over the covered period. The dashboard is built around these
   because the interesting question in this data is what changed at each
   handover — and because the three run 55, 18 and 6 months, every comparison
   between them has to be per month rather than a total. */
const TENURES = [
  { id: 't1', from: '2021-01', to: '2024-07', ink: 'var(--t1-ink)', wash: 'var(--t1-wash)' },
  { id: 't2', from: '2024-08', to: '2026-01', ink: 'var(--t2-ink)', wash: 'var(--t2-wash)' },
  { id: 't3', from: '2026-02', to: '2026-07', ink: 'var(--t3-ink)', wash: 'var(--t3-wash)' },
];

/* 2020 is in the data file but out of the analysis. The Covid general holiday
   halved recorded crime for months, and leaving it in drags every trend and
   every year-on-year comparison toward a recovery that is really a return to
   normal reporting. The file keeps it; the dashboard starts in 2021. */
const ANALYSIS_START = '2021-01';

/* The two handover months themselves are excluded from every statistic while
   still being drawn. Policing was interrupted in both — August 2024 is the
   lowest month in the whole record — so averaging them in understates the
   period they belong to and invents a fall that is an administrative gap. */
const EXCLUDED_MONTHS = ['2024-08', '2026-02'];

let DATA = null, GEO = null, RAW = null;
let NM = 0, NU = 0, NC = 0, YEARS = [];
let EX = new Set();                      // indices excluded from statistics
const inStats = (m) => !EX.has(m);
/** Months inside [a,b] that count toward a statistic. */
function statMonths(a, b) {
  const out = [];
  for (let m = a; m <= b; m++) if (inStats(m)) out.push(m);
  return out;
}
const state = { offence: -1, measure: 'count', m0: 0, m1: 0, unit: null, season: 'grid', sm: 'year' };
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
const tenureRange = (t) => [Math.max(0, monthIdx(t.from)), Math.min(NM - 1, monthIdx(t.to))];
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
  for (const m of statMonths(m0, m1)) for (let u = 0; u < NU; u++) out[u] += cell(m, u);
  return out;
}
function offenceTotals(m0 = state.m0, m1 = state.m1) {
  const out = new Array(NC).fill(0);
  for (const m of statMonths(m0, m1)) {
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
  const n = statMonths(m0, m1).length || 1;   // annualise over counted months
  return total / (n / 12) / pop * 1e5;
}
function displayUnit(total, u) { return isRate() ? rateOf(total, u) : total; }

const offenceName = () => (state.offence < 0 ? T.allOffences : crimeLabel(state.offence));
const unitName = (u) => unitLabel(DATA.units[u], true);
const scopeLabel = () => (state.unit == null ? T.bangladesh : unitLabel(DATA.units[state.unit]));

/* ------------------------------------------------------------------- KPIs */

function renderKpis() {
  const s = series();
  const months = statMonths(state.m0, state.m1);
  const n = months.length;
  const total = months.reduce((a, m) => a + s[m], 0);

  // Compare against the same number of *counted* months immediately before.
  // Stepping back a fixed number of calendar months and then filtering is what
  // produced "5 months counted … vs previous 6": the current window loses a
  // handover month, the earlier one does not, and the totals stop being
  // comparable. Walk backwards collecting counted months instead, so both
  // sides always hold the same number of them.
  const prevMonths = [];
  for (let m = state.m0 - 1; m >= 0 && prevMonths.length < n; m--)
    if (inStats(m)) prevMonths.push(m);
  prevMonths.reverse();

  // Where the record runs out before we have n of them, fall back to the
  // monthly average so a short tail still compares fairly.
  const prevN = prevMonths.length;
  const prevTotal = prevN ? prevMonths.reduce((a, m) => a + s[m], 0) : null;
  const delta = prevTotal
    ? (((total / n) - (prevTotal / prevN)) / (prevTotal / prevN)) * 100
    : null;

  const natPop = DATA.units.reduce((a, u) => a + (u.population || 0), 0);
  const unitPop = state.unit != null ? DATA.units[state.unit].population : natPop;
  const asRate = (v) => (unitPop ? v / (n / 12) / unitPop * 1e5 : null);

  $('#k1-label').textContent = offenceName();
  $('#k1').textContent = isRate() ? fmt1(asRate(total)) : fmt(total);
  $('#k1-sub').innerHTML =
    (isRate() ? T.perHundredK : T.monthsCounted(num(n))) +
    (delta == null ? '' : ` <span class="delta ${Math.abs(delta) < 1 ? 'flat' : delta > 0 ? 'up' : 'down'}">${pctStr(delta)}</span> ${T.vsPrevious(num(prevN))}`);

  $('#k2').textContent = fmt(total / n);
  $('#k2-sub').textContent = T.casesPerMonth + (state.unit != null ? ' · ' + unitName(state.unit) : '');

  const totals = unitTotals();
  const ranked = DATA.units.map((u, i) => ({ u, i, v: displayUnit(totals[i], i) }))
    .filter((o) => o.v != null && isFinite(o.v) && o.v > 0)
    .sort((a, b) => b.v - a.v);
  $('#k3-label').textContent = isRate() ? T.kHighestRate : T.kMostCases;
  if (ranked.length) {
    $('#k3').textContent = unitName(ranked[0].i);
    $('#k3-sub').textContent = isRate() ? fmt1(ranked[0].v) + ' ' + T.per100kYr : fmt(ranked[0].v) + ' ' + T.casesWord;
  } else { $('#k3').textContent = '—'; $('#k3-sub').textContent = ''; }

  let bi = months.length ? months[0] : state.m0;
  for (const m of months) if (s[m] > s[bi]) bi = m;
  $('#k4').textContent = mLong(DATA.months[bi]);
  $('#k4-sub').textContent = fmt(s[bi]) + ' ' + T.casesWord;

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
  const out = [{ id: 'all', label: T.allYears, m0: 0, m1: NM - 1 }];
  TENURES.forEach((t) => {
    const [a, b] = tenureRange(t);
    out.push({ id: t.id, label: tenureShort(t), m0: a, m1: b, ink: t.ink });
  });
  out.push({ id: 'l12', label: T.last12, m0: Math.max(0, NM - 12), m1: NM - 1 });
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
      svg.appendChild(txt(lab, tenureShort(t)));
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

  // The two handover months are plotted but not counted; hatch them so the dip
  // is visible and its exclusion is visible too.
  EX.forEach((i) => {
    svg.appendChild(el('rect', {
      x: x(i) - band / 2, y: padT, width: band, height: H - padT - padB,
      fill: 'var(--text-muted)', 'fill-opacity': .16,
    }));
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
      <div class="t-sub">${scopeLabel()}${ten ? ' · ' + tenureName(ten) : ''}${
        inStats(i) ? '' : ' · ' + T.handoverNote}</div>`);
  });
  hit.addEventListener('pointerleave', hideTip);
  hit.addEventListener('pointerup', () => {
    if (brush && !brush.moved) { state.m0 = 0; state.m1 = NM - 1; render(); }
    brush = null;
  });

  host.replaceChildren(svg);
  $('#timeline-legend').innerHTML =
    TENURES.map((t) => `<span class="key"><i class="sw" style="background:${t.ink};opacity:.55"></i>${tenureName(t)} · ${mLabel(t.from)}–${mLabel(t.to)}</span>`).join('') +
    `<span class="key"><i class="sw" style="background:var(--text-muted);opacity:.4"></i>${T.handoverKey}</span>` +
    `<span class="key" style="color:var(--text-muted)">${T.dragHint}</span>`;
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
      hoverable(p, () => `<div class="t-name">${unitLabel(DATA.units[d.i])}</div>
        <div class="t-row"><span>${offenceName()}</span><b>${isRate() ? fmt1(d.v) : fmt(totals[d.i])}</b></div>
        <div class="t-sub">${divisionLabel(name)} ${T.divisionWord} · ${T.clickToFilter}</div>`);
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
    hoverable(c, () => `<div class="t-name">${unitLabel(u)}</div>
      <div class="t-row"><span>${offenceName()}</span><b>${isRate() ? fmt1(v) : fmt(totals[i])}</b></div>
      <div class="t-row"><span>${T.population}</span><b>${fmt(u.population)}</b></div>
      <div class="t-sub">${T.markerNote}</div>`);
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
    `<span style="color:var(--text-muted)">${isRate() ? T.per100kYr : T.casesWord} · ${T.equalBins}</span>`;
}

/* -------------------------------------------------------------- rankings */

/** Half-on-half change across the counted months of the window. Comparing the
 *  ends of a noisy monthly series would report whatever the last month happened
 *  to do; comparing the two halves reports the direction of the period. */
function halfChange(ser, m0, m1) {
  const ms = statMonths(m0, m1);
  if (ms.length < 6) return null;
  const mid = Math.floor(ms.length / 2);
  const a = ms.slice(0, mid), b = ms.slice(ms.length - mid);
  const av = a.reduce((x, m) => x + ser[m], 0) / a.length;
  const bv = b.reduce((x, m) => x + ser[m], 0) / b.length;
  return av > 0 ? ((bv - av) / av) * 100 : null;
}

function sparkPath(ser, m0, m1, w, h) {
  const vals = [];
  for (let m = m0; m <= m1; m++) vals.push(ser[m]);
  const mx = Math.max(...vals), mn = Math.min(...vals);
  const X = (i) => (i / Math.max(1, vals.length - 1)) * w;
  const Y = (v) => h - 2 - (mx > mn ? (v - mn) / (mx - mn) : 0.5) * (h - 4);
  return vals.map((v, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1)).join('');
}

function barPanel(host, items, ramp, onPick, selected, valueFmt) {
  host.replaceChildren();
  const max = Math.max(1, ...items.map((i) => i.v || 0));
  items.forEach((it) => {
    const row = document.createElement('div');
    row.className = 'bar-row';
    row.setAttribute('role', 'button');
    row.tabIndex = 0;
    row.setAttribute('aria-pressed', String(it.key === selected));
    const d = it.trend;
    const cls = d == null ? 'flat' : Math.abs(d) < 3 ? 'flat' : d > 0 ? 'up' : 'down';
    const mark = d == null ? '' : Math.abs(d) < 3 ? '±' : d > 0 ? '▲' : '▼';
    row.innerHTML =
      `<span class="nm">${it.name}</span>` +
      `<span class="track"><i style="width:${((it.v || 0) / max * 100).toFixed(1)}%;background:${it.color}"></i></span>` +
      `<span class="val">${valueFmt(it.v)}</span>` +
      (it.spark
        ? `<svg class="spark" viewBox="0 0 60 20" preserveAspectRatio="none" aria-hidden="true">
             <path d="${it.spark}" fill="none" stroke="${it.color}" stroke-width="1.4"
                   stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
           </svg>`
        : '<span></span>') +
      `<span class="trend delta ${cls}">${mark}${d == null ? '—' : Math.abs(d).toFixed(0) + '%'}</span>`;
    const go = () => onPick(it.key);
    row.addEventListener('click', go);
    row.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    if (it.tip) hoverable(row, it.tip);
    host.appendChild(row);
  });
}

function renderRanks() {
  const totals = unitTotals();
  const items = DATA.units.map((u, i) => {
    const ser = series(state.offence, i);
    return {
    key: i, name: unitName(i), v: displayUnit(totals[i], i),
    spark: sparkPath(ser, state.m0, state.m1, 60, 20),
    trend: halfChange(ser, state.m0, state.m1),
    color: u.kind === 'metro' ? 'var(--city)' : u.kind === 'range' ? 'var(--range)' : 'var(--text-muted)',
    tip: () => `<div class="t-name">${unitLabel(u)}</div>
      <div class="t-row"><span>${offenceName()}</span><b>${fmt(totals[i])} ${T.casesWord}</b></div>
      ${u.population ? `<div class="t-row"><span>${T.per100kYr}</span><b>${fmt1(rateOf(totals[i], i))}</b></div>` : ''}
      <div class="t-sub">${u.kind === 'railway' ? T.railNote : divisionLabel(u.division || '') + ' ' + (u.kind === 'metro' ? T.cityForce : T.rangeForce)}
        · ${T.trendNote}</div>`,
  }; }).filter((o) => o.v != null && isFinite(o.v));
  items.sort((a, b) => b.v - a.v);
  barPanel($('#rank-bars'), items, RAMP_R,
    (k) => { state.unit = state.unit === k ? null : k; render(); },
    state.unit, (v) => (isRate() ? fmt1(v) : fmtCompact(v)));
  $('#rank-hint').textContent = isRate() ? T.ranksHintRate : T.ranksHint;

  const oTot = offenceTotals();
  const grand = oTot.reduce((a, b) => a + b, 0) || 1;
  const oItems = DATA.crimes.map((c, i) => {
    const ser = series(i, state.unit);
    return {
      key: i, name: crimeLabel(i), v: oTot[i], color: 'var(--range)',
      spark: sparkPath(ser, state.m0, state.m1, 60, 20),
      trend: halfChange(ser, state.m0, state.m1),
      tip: () => `<div class="t-name">${crimeLabel(i)}</div>
        <div class="t-row"><span>${T.cases}</span><b>${fmt(oTot[i])}</b></div>
        <div class="t-row"><span>${T.share}</span><b>${num((oTot[i] / grand * 100).toFixed(1))}%</b></div>
        <div class="t-sub">${scopeLabel()} · ${T.trendNote} · ${T.clickToFilter}</div>`,
    };
  }).sort((a, b) => b.v - a.v);
  barPanel($('#offence-bars'), oItems, RAMP_R,
    (k) => { state.offence = state.offence === k ? -1 : k; $('#offence').value = String(state.offence); render(); },
    state.offence, fmtCompact);
  $('#offence-hint').textContent = T.offencesHint(scopeLabel());
}

/* -------------------------------------------------- year against year */

/* Years get distinct hues rather than shades of one, because telling seven
   blues apart in a tangle of lines is guesswork. Assigned in fixed order and
   never cycled: once the record passes seven years the oldest fall back to a
   context grey rather than repeating a hue already in use. */
const YEAR_RAMP = ['--y1','--y2','--y3','--y4','--y5','--y6','--y7'];
function yearColor(yi, nYears) {
  const slot = yi - Math.max(0, nYears - YEAR_RAMP.length);
  return slot < 0 ? 'var(--ctx)' : `var(${YEAR_RAMP[slot]})`;
}

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
  T.months.forEach((m, i) =>
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
    svg.appendChild(txt(t, yearLabel(e.yr)));
  });

  // one hit column per month, covering the full height
  for (let i = 0; i < 12; i++) {
    const r = el('rect', { x: x(i) - (W - padL - padR) / 24, y: padT, width: (W - padL - padR) / 12, height: H - padT - padB, fill: 'transparent', style: 'cursor:crosshair' });
    hoverable(r, () => `<div class="t-name">${T.monthsLong[i]} · ${offenceName()}</div>` +
      YEARS.filter((y) => M[y][i] != null)
        .map((y) => `<div class="t-row"><span>${yearLabel(y)}</span><b>${fmt(M[y][i])}</b></div>`).join('') +
      `<div class="t-sub">${scopeLabel()}</div>`);
    svg.appendChild(r);
  }
  host.replaceChildren(svg);
  $('#season-legend').innerHTML =
    YEARS.map((y, i) => `<span class="key"><i class="sw" style="background:${yearColor(i, YEARS.length)}"></i>${yearLabel(y)}</span>`).join('') +
    `<span class="key" style="color:var(--text-muted)">${T.runsTo(mLabel(DATA.months[NM - 1]))}</span>`;
  $('#season-hint').textContent = T.seasonHintLines;
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

  T.months.forEach((m, i) =>
    svg.appendChild(txt(el('text', { x: padL + i * cw + cw / 2, y: padT - 8, 'text-anchor': 'middle', class: 'axis' }), m)));
  YEARS.forEach((yr, yi) => {
    svg.appendChild(txt(el('text', { x: padL - 8, y: padT + yi * ch + ch / 2 + 4, 'text-anchor': 'end', class: 'axis' }), yearLabel(yr)));
    for (let i = 0; i < 12; i++) {
      const v = M[yr][i];
      const b = v == null ? -1 : binOf(v, breaks);
      const r = el('rect', {
        x: padL + i * cw + gap / 2, y: padT + yi * ch + gap / 2,
        width: cw - gap, height: ch - gap, rx: 3,
        fill: v == null ? 'var(--empty)' : `var(${RAMP_R[b]})`,
      });
      if (v != null) hoverable(r, `<div class="t-name">${T.monthsLong[i]} ${yearLabel(yr)}</div>
        <div class="t-row"><span>${offenceName()}</span><b>${fmt(v)}</b></div>
        <div class="t-sub">${scopeLabel()}</div>`);
      svg.appendChild(r);
    }
  });
  host.replaceChildren(svg);
  const lo = Math.min(...all), hi = Math.max(...all);
  $('#season-legend').innerHTML =
    `<span>${fmtCompact(lo)}</span><span class="ramp">${RAMP_R.map((r) => `<i style="background:var(${r})"></i>`).join('')}</span><span>${fmtCompact(hi)}</span>` +
    `<span style="color:var(--text-muted)">${T.casesPerMonth} · ${T.equalBins} · ${T.notPublished}</span>`;
  $('#season-hint').textContent = T.seasonHintGrid;
}

/* ------------------------------------------------- across the transitions */

/** Cases per month for one offence in one tenure, over the current scope. */
function tenureRate(offence, t) {
  const [a, b] = tenureRange(t);
  const months = statMonths(a, b);
  let s = 0;
  for (const m of months) {
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
  return months.length ? s / months.length : null;
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
      `<div style="font-size:.71rem;font-weight:650;letter-spacing:.05em;text-transform:uppercase;color:${o.t.ink}">${tenureName(o.t)}</div>
       <div style="font-size:1.45rem;font-weight:650;letter-spacing:-.02em;margin:2px 0 1px">${fmt(o.v)}</div>
       <div style="font-size:.76rem;color:var(--text-muted)">${T.casesPerMonth} · ${num(statMonths(a, b).length)} ${T.monthsWord}
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
      return { c: crimeShort(i), full: crimeLabel(i), a, b, d: a > 0.5 ? ((b - a) / a) * 100 : null };
    }).filter((r) => r.d != null).sort((x, y) => y.d - x.d);

    const cap = Math.max(20, ...rows.map((r) => Math.abs(r.d)));
    const W = 470, rowH = 20, padL = 148, padR = 46;
    const H = rows.length * rowH + 34;
    const mid = padL + (W - padL - padR) / 2, half = (W - padL - padR) / 2;
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
    svg.setAttribute('aria-label', `${tenureName(A)} → ${tenureName(B)}`);

    svg.appendChild(el('line', { x1: mid, x2: mid, y1: 4, y2: H - 26, stroke: 'var(--border-strong)', 'stroke-width': 1 }));
    rows.forEach((r, i) => {
      const y = 4 + i * rowH;
      const w = Math.min(1, Math.abs(r.d) / cap) * half * 0.94;
      const rect = el('rect', {
        x: r.d >= 0 ? mid : mid - w, y: y + 3, width: Math.max(w, 1.5), height: rowH - 7, rx: 2.5,
        fill: r.d >= 0 ? 'var(--up)' : 'var(--down)', 'fill-opacity': .85,
      });
      hoverable(rect, `<div class="t-name">${r.full}</div>
        <div class="t-row"><span>${tenureShort(A)}</span><b>${fmt1(r.a)}</b></div>
        <div class="t-row"><span>${tenureShort(B)}</span><b>${fmt1(r.b)}</b></div>
        <div class="t-sub">${pctStr(r.d)} · ${T.casesPerMonth} · ${scopeLabel()}</div>`);
      svg.appendChild(rect);
      svg.appendChild(txt(el('text', { x: padL - 8, y: y + rowH / 2 + 3, 'text-anchor': 'end', class: 'axis' }), r.c));
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
    svg.appendChild(txt(el('text', { x: mid, y: H - 8, 'text-anchor': 'middle', class: 'axis' }), T.noChange));
    svg.appendChild(txt(el('text', { x: mid - half * 0.94, y: H - 8, 'text-anchor': 'start', class: 'axis' }), num('\u2212' + Math.round(cap) + '%')));
    svg.appendChild(txt(el('text', { x: mid + half * 0.94, y: H - 8, 'text-anchor': 'end', class: 'axis' }), num('+' + Math.round(cap) + '%')));

    const sec = document.createElement('section');
    sec.innerHTML = `<h3 style="font-size:.9rem;font-weight:650;margin:0 0 2px">${tenureShort(A)} → ${tenureShort(B)}</h3>
      <p class="hint" style="margin:0 0 8px">${T.handoverAt(mLong(B.from))}</p>`;
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
  renderSmallMultiples();
  renderTenure();
}

/* -------------------------------------------------------------------- init */

/** Push the current language into everything that is not redrawn by render():
 *  the static markup, the offence list, the footer and the document itself. */
function applyLanguage() {
  T = I18N[LANG];
  document.documentElement.lang = LANG === 'bn' ? 'bn' : 'en';
  document.title = T.title;
  document.querySelectorAll('[data-i18n]').forEach((n) => {
    const v = T[n.dataset.i18n];
    if (typeof v === 'string') n.textContent = v;
  });
  $('#lang-btn').textContent = T.langName;
  $('#k1-label').textContent = offenceName();

  const sel = $('#offence');
  sel.innerHTML = `<option value="-1">${T.allOffences}</option>` +
    DATA.crimes.map((c, i) => `<option value="${i}">${crimeLabel(i)}</option>`).join('');
  sel.value = String(state.offence);

  $('#foot-source').innerHTML =
    `<strong>${T.sourceLead}</strong> ${T.sourceBody} ` +
    `<a href="https://www.police.gov.bd/en/crime_statistic_home" rel="noopener" target="_blank">police.gov.bd</a>. ` +
    `${T.sourceTail} <span id="foot-meta"></span>`;
  $('#foot-caveat').innerHTML = `<strong>${T.caveatLead}</strong> ${T.caveatBody}`;
  $('#foot-meta').textContent = T.footMeta(
    mLong(DATA.months[0]), mLong(DATA.months[NM - 1]), num(NM), num(NU), num(NC),
    num(RAW.meta.months), mLong(RAW.meta.first_month));
}

function wire() {
  const sel = $('#offence');
  sel.addEventListener('change', (e) => { state.offence = +e.target.value; render(); });

  $('#lang-btn').addEventListener('click', () => {
    LANG = LANG === 'en' ? 'bn' : 'en';
    localStorage.setItem('crimebd-lang', LANG);
    applyLanguage();
    render();
  });

  document.querySelectorAll('[data-measure]').forEach((b) =>
    b.addEventListener('click', () => {
      state.measure = b.dataset.measure;
      document.querySelectorAll('[data-measure]').forEach((o) => o.setAttribute('aria-pressed', String(o === b)));
      render();
    }));
  document.querySelectorAll('[data-sm]').forEach((b) =>
    b.addEventListener('click', () => {
      state.sm = b.dataset.sm;
      document.querySelectorAll('[data-sm]').forEach((o) => o.setAttribute('aria-pressed', String(o === b)));
      renderSmallMultiples();
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
  RAW = d; GEO = g;
  // Keep the whole file, analyse from 2021. Slicing here rather than filtering
  // at every call site means no chart can accidentally reach back into 2020.
  const cut = Math.max(0, d.months.indexOf(ANALYSIS_START));
  DATA = { ...d, months: d.months.slice(cut), values: d.values.slice(cut) };
  NM = DATA.months.length; NU = DATA.units.length; NC = DATA.crimes.length;
  YEARS = [...new Set(DATA.months.map((m) => m.slice(0, 4)))];
  EX = new Set(EXCLUDED_MONTHS.map((m) => DATA.months.indexOf(m)).filter((i) => i >= 0));
  state.m0 = 0; state.m1 = NM - 1;
  LANG = localStorage.getItem('crimebd-lang') === 'bn' ? 'bn' : 'en';
  wire();
  applyLanguage();
  render();
}).catch((err) => {
  $('#timeline').innerHTML =
    `<p style="color:var(--up)">Could not load the data files (${err}). If you opened this page from disk, serve the folder over HTTP instead — browsers block fetch on file:// URLs.</p>`;
});

/* ------------------------------------------- every offence, month by month */

/** Fifteen panels, one per offence, on a shared x-axis but independent y —
 *  a small-multiple. Two readings of the same data: "By year" puts each year
 *  on the same twelve months so seasonality separates from level, "By
 *  government" runs the whole record with the tenure bands behind it so the
 *  handovers line up across every category at once. */
function renderSmallMultiples() {
  const host = $('#smallmults');
  host.replaceChildren();
  const grid = document.createElement('div');
  grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:14px';

  DATA.crimes.forEach((name, ci) => {
    const cardEl = document.createElement('button');
    cardEl.type = 'button';
    const on = state.offence === ci;
    cardEl.style.cssText = `text-align:left;font:inherit;color:inherit;cursor:pointer;padding:9px 10px;
      border-radius:9px;background:${on ? 'var(--surface-2)' : 'transparent'};
      border:1px solid ${on ? 'var(--border-strong)' : 'var(--border)'};width:100%`;
    cardEl.setAttribute('aria-pressed', String(on));
    const head = document.createElement('div');
    head.style.cssText = 'font-size:.78rem;font-weight:650;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
    head.textContent = crimeLabel(ci);
    cardEl.appendChild(head);
    cardEl.appendChild(state.sm === 'gov' ? smGov(ci) : smYear(ci));
    cardEl.addEventListener('click', () => {
      state.offence = state.offence === ci ? -1 : ci;
      $('#offence').value = String(state.offence);
      render();
    });
    grid.appendChild(cardEl);
  });
  host.appendChild(grid);

  $('#sm-legend').innerHTML = state.sm === 'gov'
    ? TENURES.map((t) => `<span class="key"><i class="sw" style="background:${t.ink};opacity:.55"></i>${tenureName(t)}</span>`).join('') +
      `<span class="key" style="color:var(--text-muted)">${T.rulesAreHandovers}</span>`
    : YEARS.map((y, i) => `<span class="key"><i class="sw" style="background:${yearColor(i, YEARS.length)}"></i>${yearLabel(y)}</span>`).join('');
  $('#sm-hint').textContent = state.sm === 'gov' ? T.smallHintGov(scopeLabel()) : T.smallHintYear(scopeLabel());
}

/** One offence, twelve months, a line per year. */
function smYear(ci) {
  const s = series(ci);
  const M = {};
  YEARS.forEach((y) => (M[y] = new Array(12).fill(null)));
  DATA.months.forEach((ym, i) => { M[ym.slice(0, 4)][+ym.slice(5, 7) - 1] = s[i]; });
  const all = Object.values(M).flat().filter((v) => v != null);
  const max = Math.max(1, ...all);
  const W = 232, H = 96, padL = 4, padR = 4, padT = 6, padB = 13;
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img' });
  svg.setAttribute('aria-label', `${crimeLabel(ci)}`);
  const x = (i) => padL + (i / 11) * (W - padL - padR);
  const y = (v) => H - padB - (v / max) * (H - padT - padB);
  svg.appendChild(el('line', { class: 'gridline', x1: padL, x2: W - padR, y1: y(0), y2: y(0) }));
  YEARS.forEach((yr, yi) => {
    let d = '';
    M[yr].forEach((v, i) => { if (v != null) d += (d ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); });
    if (d) svg.appendChild(el('path', { d, fill: 'none', stroke: yearColor(yi, YEARS.length), 'stroke-width': 1.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
  });
  [0, 3, 6, 9].forEach((i) => {
    // anchor the end labels inward so neither is clipped by the viewBox
    const anchor = i === 0 ? 'start' : 'middle';
    svg.appendChild(txt(el('text', { x: x(i), y: H - 3, 'text-anchor': anchor, class: 'axis', 'font-size': 8.5 }), T.months[i]));
  });
  svg.appendChild(txt(el('text', { x: W - padR, y: padT + 7, 'text-anchor': 'end', class: 'axis', 'font-size': 8.5 }), T.maxWord + ' ' + fmtCompact(max)));
  for (let i = 0; i < 12; i++) {
    const r = el('rect', { x: x(i) - (W - padL - padR) / 24, y: padT, width: (W - padL - padR) / 12, height: H - padT - padB, fill: 'transparent' });
    hoverable(r, () => `<div class="t-name">${crimeLabel(ci)} · ${T.monthsLong[i]}</div>` +
      YEARS.filter((yy) => M[yy][i] != null).map((yy) => `<div class="t-row"><span>${yearLabel(yy)}</span><b>${fmt(M[yy][i])}</b></div>`).join('') +
      `<div class="t-sub">${scopeLabel()}</div>`);
    svg.appendChild(r);
  }
  return svg;
}

/** One offence across the whole record, with the governments shaded behind. */
function smGov(ci) {
  const s = series(ci);
  const max = Math.max(1, ...s);
  const W = 232, H = 96, padL = 4, padR = 4, padT = 6, padB = 13;
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img' });
  svg.setAttribute('aria-label', `${crimeLabel(ci)}`);
  const x = (i) => padL + (i / Math.max(1, NM - 1)) * (W - padL - padR);
  const y = (v) => H - padB - (v / max) * (H - padT - padB);
  TENURES.forEach((t) => {
    const [a, b] = tenureRange(t);
    svg.appendChild(el('rect', { x: x(a), y: padT, width: Math.max(0, x(b) - x(a)), height: H - padT - padB, fill: t.wash }));
  });
  let d = '';
  s.forEach((v, i) => { d += (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); });
  svg.appendChild(el('path', { d, fill: 'none', stroke: 'var(--range)', 'stroke-width': 1.4, 'stroke-linejoin': 'round' }));
  TENURES.slice(1).forEach((t) => {
    const i = monthIdx(t.from);
    svg.appendChild(el('line', { x1: x(i), x2: x(i), y1: padT, y2: H - padB, stroke: t.ink, 'stroke-width': 1.2 }));
  });
  svg.appendChild(txt(el('text', { x: padL, y: H - 3, 'text-anchor': 'start', class: 'axis', 'font-size': 8.5 }), yearLabel(YEARS[0])));
  svg.appendChild(txt(el('text', { x: W - padR, y: H - 3, 'text-anchor': 'end', class: 'axis', 'font-size': 8.5 }), yearLabel(YEARS[YEARS.length - 1])));
  svg.appendChild(txt(el('text', { x: W - padR, y: padT + 7, 'text-anchor': 'end', class: 'axis', 'font-size': 8.5 }), T.maxWord + ' ' + fmtCompact(max)));
  const band = (W - padL - padR) / Math.max(1, NM - 1);
  const hit = el('rect', { x: padL, y: padT, width: W - padL - padR, height: H - padT - padB, fill: 'transparent' });
  hit.addEventListener('pointermove', (e) => {
    const r = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(NM - 1, Math.round((((e.clientX - r.left) / r.width) * W - padL) / band)));
    const ten = TENURES.find((t) => { const [a, b] = tenureRange(t); return i >= a && i <= b; });
    showTip(e, `<div class="t-name">${crimeLabel(ci)}</div>
      <div class="t-row"><span>${mLong(DATA.months[i])}</span><b>${fmt(s[i])}</b></div>
      <div class="t-sub">${scopeLabel()}${ten ? ' · ' + tenureName(ten) : ''}</div>`);
  });
  hit.addEventListener('pointerleave', hideTip);
  svg.appendChild(hit);
  return svg;
}
