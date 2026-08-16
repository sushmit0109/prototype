/* Bangladesh Overseas Employment dashboard.
 *
 * No external libraries: geometry, projections, scales and the brush are all
 * hand-rolled so the page is one stylesheet plus one script and works offline.
 *
 * The core of the interaction is linked filtering. Selecting a district must
 * not blank out the district map, and selecting a country must not blank out
 * the world map - so each view is aggregated against *the other* view's filter:
 *   district totals  <- month range + country filter
 *   country totals   <- month range + district filter
 *   monthly series   <- both filters, across all months
 * That is what lets you read "where do Comilla's workers go" and "which
 * districts feed Saudi Arabia" from the same two maps.
 */
'use strict';

const $ = (s) => document.querySelector(s);
const fmt = (n) => n.toLocaleString('en-US');
const fmtCompact = (n) =>
  n >= 1e6 ? (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + 'M'
  : n >= 1e3 ? (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + 'k'
  : String(n);
const MONTH_LABEL = (ym) => {
  const [y, m] = ym.split('-');
  return ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+m - 1] + ' ' + y;
};

let DATA, BDGEO, WORLDGEO;
const state = { m0: 0, m1: 0, dSel: null, cSel: null, tlMode: 'months', measure: 'total' };

/* Per-100,000-residents view.
 *
 * Absolute counts mostly rank districts by how big they are. Dividing by the
 * 2022 census population turns the map into a propensity measure: out of every
 * 100,000 residents, how many took a clearance in the selected period. Only the
 * origin side is normalised - a rate per Bangladeshi head is meaningless on a
 * destination country. */
const PER = 100000;
const isRate = () => state.measure === 'rate';
const districtValue = (i) =>
  isRate() ? (agg.dTot[i] / DATA.districts[i].p) * PER : agg.dTot[i];
const fmtRate = (v) => (v >= 100 ? Math.round(v).toLocaleString('en-US')
  : v >= 10 ? v.toFixed(1) : v.toFixed(2));
const fmtDistrict = (v) => (isRate() ? fmtRate(v) + ' / 100k' : fmt(Math.round(v)));
let agg = null;

/* ---------------------------------------------------------------- utils */

function svgEl(tag, attrs) {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
  return e;
}

/** Quantile breaks over the non-zero values: the distribution is extremely
 *  skewed (one destination is ~58% of all records), so equal-width bins would
 *  paint almost everything the lightest step. */
function quantileBreaks(values, nBins) {
  const v = values.filter((x) => x > 0).sort((a, b) => a - b);
  if (!v.length) return [];
  const breaks = [];
  for (let i = 1; i < nBins; i++) {
    const p = (i / nBins) * (v.length - 1);
    const lo = Math.floor(p), hi = Math.ceil(p);
    breaks.push(v[lo] + (v[hi] - v[lo]) * (p - lo));
  }
  return breaks;
}
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

const binOf = (val, breaks) => {
  if (val <= 0) return -1;
  let i = 0;
  while (i < breaks.length && val > breaks[i]) i++;
  return i;
};

/* ------------------------------------------------------------ projections */

/** Equirectangular with a cos(lat) correction, fitted to a bounding box.
 *  Adequate for a country-scale map and for a world reference map, and it
 *  keeps the whole file dependency-free. */
function makeProjection(bbox, width, height, pad) {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const midLat = ((minLat + maxLat) / 2) * Math.PI / 180;
  const kx = Math.cos(midLat);
  const w = (maxLon - minLon) * kx, h = maxLat - minLat;
  const s = Math.min((width - 2 * pad) / w, (height - 2 * pad) / h);
  const ox = (width - w * s) / 2, oy = (height - h * s) / 2;
  return (lon, lat) => [
    ox + (lon - minLon) * kx * s,
    oy + (maxLat - lat) * s,
  ];
}

/** Height that fits a bbox exactly at the given width, so a wide world map and
 *  a tall country map each use their frame instead of padding it with blanks. */
function fitHeight(bbox, width, pad, maxH) {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const kx = Math.cos(((minLat + maxLat) / 2) * Math.PI / 180);
  const aspect = ((maxLon - minLon) * kx) / (maxLat - minLat);
  return Math.min(maxH, Math.round((width - 2 * pad) / aspect) + 2 * pad);
}

function pathFor(geometry, proj) {
  const parts = [];
  const ring = (coords) => {
    // Break the path where a ring crosses the antimeridian. Russia and Fiji
    // wrap past +/-180, and joining those points straight across draws a band
    // through the whole map.
    let d = '', prevLon = null, pending = true;
    for (let i = 0; i < coords.length; i++) {
      const lon = coords[i][0];
      if (prevLon !== null && Math.abs(lon - prevLon) > 180) pending = true;
      const p = proj(lon, coords[i][1]);
      d += (pending ? 'M' : 'L') + p[0].toFixed(1) + ' ' + p[1].toFixed(1);
      pending = false;
      prevLon = lon;
    }
    return d + 'Z';
  };
  if (geometry.type === 'Polygon') geometry.coordinates.forEach((r) => parts.push(ring(r)));
  else if (geometry.type === 'MultiPolygon')
    geometry.coordinates.forEach((poly) => poly.forEach((r) => parts.push(ring(r))));
  return parts.join('');
}

/* -------------------------------------------------------------- tooltip */

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

/* ------------------------------------------------------------ aggregate */

function aggregate() {
  const { m, d, c, v } = DATA.cube;
  const nD = DATA.districts.length, nC = DATA.countries.length, nM = DATA.months.length;
  const dTot = new Float64Array(nD), cTot = new Float64Array(nC), mSer = new Float64Array(nM);
  // Per-entity monthly series, so every row of a ranking can carry its own
  // sparkline. Flat arrays indexed [entity * nM + month]: 64x39 and 157x39 are
  // small enough to rebuild on every filter change.
  const dSer = new Float64Array(nD * nM), cSer = new Float64Array(nC * nM);
  const { m0, m1, dSel, cSel } = state;
  let total = 0;

  for (let i = 0; i < m.length; i++) {
    const mi = m[i], di = d[i], ci = c[i], vi = v[i];
    const dOk = dSel === null || dSel === di;
    const cOk = cSel === null || cSel === ci;
    if (dOk && cOk) mSer[mi] += vi;            // timeline spans all months
    if (cOk) dSer[di * nM + mi] += vi;         // sparklines span all months too
    if (dOk) cSer[ci * nM + mi] += vi;
    if (mi < m0 || mi > m1) continue;          // maps and bars respect the brush
    if (cOk) dTot[di] += vi;
    if (dOk) cTot[ci] += vi;
    if (dOk && cOk) total += vi;
  }
  agg = { dTot, cTot, mSer, dSer, cSer, nM, total };
}

/** Slice one entity's monthly series over the selected window. */
function seriesOf(flat, idx, nM) {
  return Array.from(flat.subarray(idx * nM + state.m0, idx * nM + state.m1 + 1));
}

/** Change from the first half of the visible window to the second.
 *  Null when there is too little history, or too little volume, to mean
 *  anything - a jump from 1 to 4 is not a 300% trend. */
function trendOf(series) {
  if (series.length < 4) return null;
  const half = Math.floor(series.length / 2);
  const a = series.slice(0, half).reduce((x, y) => x + y, 0);
  const b = series.slice(series.length - half).reduce((x, y) => x + y, 0);
  if (a < 30) return null;
  return (b - a) / a;
}

/* ------------------------------------------------------------- rendering */

function render() {
  aggregate();
  renderKpis();
  renderCorridor();
  renderTimeline();
  renderBdMap();
  renderWorldMap();
  renderBars();
  if (!$('#table-body').hidden) renderTable();
}

function renderKpis() {
  const { dTot, cTot, mSer, total } = agg;
  $('#kpi-total').textContent = fmtCompact(total);
  $('#kpi-total-sub').textContent =
    total === DATA.meta.total ? 'all records' : fmt(total) + ' in view';

  const dVals = DATA.districts.map((_, i) => districtValue(i));
  const dMax = maxIdx(dVals), cMax = maxIdx(cTot);
  $('#kpi-district').textContent = dMax < 0 ? '—' : DATA.districts[dMax].n;
  $('#kpi-district-sub').textContent = dMax < 0 ? ''
    : isRate() ? fmtRate(dVals[dMax]) + ' per 100k residents'
    : fmt(dTot[dMax]) + ' (' + pct(dTot[dMax], sum(dTot)) + ')';
  $('#kpi-district-label').textContent = isRate() ? 'Highest rate' : 'Top origin';
  $('#kpi-country').textContent = cMax < 0 ? '—' : DATA.countries[cMax].n;
  $('#kpi-country-sub').textContent =
    cMax < 0 ? '' : fmt(cTot[cMax]) + ' (' + pct(cTot[cMax], sum(cTot)) + ')';

  let pk = -1, pkv = -1;
  for (let i = state.m0; i <= state.m1; i++) if (mSer[i] > pkv) { pkv = mSer[i]; pk = i; }
  $('#kpi-peak').textContent = pk < 0 ? '—' : MONTH_LABEL(DATA.months[pk]);
  $('#kpi-peak-sub').textContent = pk < 0 ? '' : fmt(pkv) + ' clearances';
}
const sum = (a) => a.reduce((x, y) => x + y, 0);
const pct = (a, b) => (b ? ((100 * a) / b).toFixed(1) : '0.0') + '%';
function maxIdx(a) { let bi = -1, bv = 0; for (let i = 0; i < a.length; i++) if (a[i] > bv) { bv = a[i]; bi = i; } return bi; }

function chip(label, kind, onClear) {
  const s = document.createElement('span');
  s.className = 'chip';
  s.innerHTML = `<span class="dot ${kind}"></span>${label}`;
  if (onClear) {
    const b = document.createElement('button');
    b.type = 'button';
    b.innerHTML = '&times;';
    b.setAttribute('aria-label', 'Clear ' + label);
    b.onclick = onClear;
    s.appendChild(b);
  }
  return s;
}

function renderCorridor() {
  const from = $('#corridor-from'), to = $('#corridor-to');
  from.replaceChildren(
    state.dSel === null
      ? chip('All 64 districts', 'origin')
      : chip(DATA.districts[state.dSel].n, 'origin', () => { state.dSel = null; render(); })
  );
  to.replaceChildren(
    state.cSel === null
      ? chip('All ' + DATA.countries.length + ' destinations', 'dest')
      : chip(DATA.countries[state.cSel].n, 'dest', () => { state.cSel = null; render(); })
  );
  const a = MONTH_LABEL(DATA.months[state.m0]), b = MONTH_LABEL(DATA.months[state.m1]);
  $('#corridor-period').textContent = a === b ? a : a + ' – ' + b;
}

/* ---------------------------------------------------------- timeline */

let brushDrag = null;

/* ---- time-window presets -------------------------------------------
 * A shortcut for the brush, not a second source of truth: a preset just sets
 * [m0, m1], and dragging the brush deselects whichever preset no longer
 * matches. That keeps one window, however it was chosen.
 */

function presetList() {
  const months = DATA.months;
  const last = months.length - 1;
  const years = [...new Set(months.map((m) => m.slice(0, 4)))];
  const out = [{ id: 'all', label: 'All time', m0: 0, m1: last }];
  if (months.length > 12)
    out.push({ id: 'last12', label: 'Last 12 months', m0: last - 11, m1: last });
  years.forEach((y) => {
    const idx = months.map((m, i) => (m.startsWith(y) ? i : -1)).filter((i) => i >= 0);
    out.push({ id: y, label: y, m0: idx[0], m1: idx[idx.length - 1] });
  });
  return out;
}

function renderPresets() {
  const host = $('#tl-presets');
  host.replaceChildren();
  presetList().forEach((p) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = p.label;
    const active = state.m0 === p.m0 && state.m1 === p.m1;
    b.setAttribute('aria-pressed', String(active));
    b.onclick = () => { state.m0 = p.m0; state.m1 = p.m1; render(); };
    host.appendChild(b);
  });
}

/* ---- year comparison ------------------------------------------------
 * Months of the year on one axis, one line per year. This is the view that
 * answers "is this year running above or below last year", which a continuous
 * timeline cannot show at a glance. Years are ordered, so the lines take an
 * ordinal ramp of the origin hue - older lighter, current darkest - rather
 * than categorical hues, and each line is labelled at its end.
 */

// Years are ordered, so they take an ordinal ramp of the origin hue rather
// than categorical hues. Spread wide, because the two most recent years are
// the pair a reader actually compares and must not look alike; the current
// year also carries extra stroke weight.
const YEAR_RAMP = ['--year-1', '--year-2', '--year-3', '--year-4'];
const MON_ABBR = ['J','F','M','A','M','J','J','A','S','O','N','D'];

function renderYearChart(host) {
  const W = host.clientWidth || 900, H = 210, padL = 46, padR = 52, padT = 12, padB = 26;
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.setAttribute('aria-label', 'Clearances by month of year, one line per year');

  const years = [...new Set(DATA.months.map((m) => m.slice(0, 4)))];
  // value per (year, month-of-year), from the corridor-filtered series
  const byYear = years.map((y) => {
    const pts = [];
    DATA.months.forEach((ym, i) => {
      if (ym.slice(0, 4) === y) pts.push({ mo: +ym.slice(5, 7) - 1, v: agg.mSer[i], i });
    });
    return { y, pts, total: pts.reduce((a, b) => a + b.v, 0) };
  });

  const max = Math.max(1, ...byYear.flatMap((s) => s.pts.map((p) => p.v)));
  const x = (mo) => padL + (mo / 11) * (W - padL - padR);
  const yy = (v) => H - padB - (v / max) * (H - padT - padB);

  for (let t = 0; t <= 2; t++) {
    const gv = (max / 2) * t;
    svg.appendChild(svgEl('line', { class: 'gridline', x1: padL, x2: W - padR, y1: yy(gv), y2: yy(gv) }));
    const lb = svgEl('text', { x: padL - 7, y: yy(gv) + 4, 'text-anchor': 'end' });
    lb.setAttribute('fill', 'var(--text-muted)');
    lb.style.fontSize = '10.5px';
    lb.textContent = fmtCompact(Math.round(gv));
    svg.appendChild(lb);
  }
  for (let mo = 0; mo < 12; mo++) {
    const t = svgEl('text', { x: x(mo), y: H - 8, 'text-anchor': 'middle' });
    t.setAttribute('fill', 'var(--text-muted)');
    t.style.fontSize = '10.5px';
    t.textContent = MON_ABBR[mo];
    svg.appendChild(t);
  }

  // If the window is exactly one year, emphasise that year's line instead of
  // the newest, so the chart and the period buttons agree with each other.
  const selYear = DATA.months[state.m0].slice(0, 4) === DATA.months[state.m1].slice(0, 4)
    ? DATA.months[state.m0].slice(0, 4) : null;
  const emphYear = selYear || years[years.length - 1];

  const labels = [];
  byYear.forEach((s, k) => {
    if (!s.pts.length) return;
    const stroke = `var(${YEAR_RAMP[Math.min(k, YEAR_RAMP.length - 1)]})`;
    const isLatest = s.y === emphYear;
    let d = '';
    s.pts.forEach((p, j) => { d += (j ? 'L' : 'M') + x(p.mo).toFixed(1) + ' ' + yy(p.v).toFixed(1); });
    svg.appendChild(svgEl('path', {
      class: 'year-line', d, stroke,
      'stroke-width': isLatest ? 2.8 : 1.7,
      opacity: isLatest ? 1 : 0.85,
    }));
    const lastPt = s.pts[s.pts.length - 1];
    svg.appendChild(svgEl('circle', {
      cx: x(lastPt.mo).toFixed(1), cy: yy(lastPt.v).toFixed(1), r: isLatest ? 3.6 : 2.8, fill: stroke,
    }));
    labels.push({ y: s.y, stroke, isLatest, px: Math.min(x(lastPt.mo) + 8, W - 42), py: yy(lastPt.v) });
  });

  // Two years ending December at similar volumes put their labels on top of
  // each other. Push them apart before drawing, keeping the order intact.
  labels.sort((a, b) => a.py - b.py);
  const GAP = 14;
  for (let i = 1; i < labels.length; i++)
    if (labels[i].py - labels[i - 1].py < GAP) labels[i].py = labels[i - 1].py + GAP;
  const overflow = labels.length && labels[labels.length - 1].py - (H - padB);
  if (overflow > 0) labels.forEach((l) => { l.py -= overflow; });

  labels.forEach((l) => {
    // Direct label: identity never rests on colour alone.
    const lb = svgEl('text', { x: l.px, y: l.py + 4, class: 'year-label' });
    lb.setAttribute('fill', l.stroke);
    if (!l.isLatest) lb.setAttribute('opacity', '0.9');
    lb.textContent = l.y;
    svg.appendChild(lb);
  });

  // One hover target per month: a crosshair that reports every year at once.
  const bandW = (W - padL - padR) / 11;
  for (let mo = 0; mo < 12; mo++) {
    const hit = svgEl('rect', {
      x: x(mo) - bandW / 2, y: padT, width: bandW, height: H - padT - padB,
      fill: 'transparent',
    });
    hit.addEventListener('pointermove', (e) => {
      const rows = byYear
        .map((s) => ({ y: s.y, p: s.pts.find((p) => p.mo === mo) }))
        .filter((r) => r.p)
        .map((r) => `<div class="t-val">${r.y}: ${fmt(Math.round(r.p.v))}</div>`)
        .join('');
      showTip(e, `<div class="t-name">${['January','February','March','April','May','June','July','August','September','October','November','December'][mo]}</div>${rows}<div class="t-sub">${corridorText()}</div>`);
    });
    hit.addEventListener('pointerleave', hideTip);
    svg.appendChild(hit);
  }

  host.replaceChildren(svg);
}

function renderTimeline() {
  const host = $('#timeline');
  renderPresets();
  if (state.tlMode === 'years') {
    $('#tl-hint').textContent =
      'Each year on the same twelve months, so this year reads directly against the last. ' +
      'Use the buttons below to change the period the maps and rankings cover.';
    renderYearChart(host);
    return;
  }
  $('#tl-hint').textContent =
    'Monthly clearances for the current corridor. Drag across the chart to select a period; click once to clear.';
  const W = host.clientWidth || 900, H = 132, padL = 46, padR = 12, padT = 10, padB = 22;
  const n = DATA.months.length;
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.setAttribute('aria-label', 'Monthly clearances; drag to select a period');

  const max = Math.max(1, ...agg.mSer);
  const x = (i) => padL + (i / Math.max(1, n - 1)) * (W - padL - padR);
  const y = (v) => H - padB - (v / max) * (H - padT - padB);
  const bandW = (W - padL - padR) / Math.max(1, n - 1);

  for (let t = 0; t <= 2; t++) {
    const gv = (max / 2) * t;
    svg.appendChild(svgEl('line', { class: 'gridline', x1: padL, x2: W - padR, y1: y(gv), y2: y(gv) }));
    const lb = svgEl('text', { x: padL - 7, y: y(gv) + 4, 'text-anchor': 'end', class: 'axis' });
    lb.setAttribute('fill', 'var(--text-muted)');
    lb.style.fontSize = '10.5px';
    lb.textContent = fmtCompact(Math.round(gv));
    svg.appendChild(lb);
  }

  let dArea = `M${x(0)} ${y(0)}`, dLine = '';
  for (let i = 0; i < n; i++) {
    dArea += `L${x(i)} ${y(agg.mSer[i])}`;
    dLine += (i ? 'L' : 'M') + x(i) + ' ' + y(agg.mSer[i]);
  }
  dArea += `L${x(n - 1)} ${y(0)}Z`;
  svg.appendChild(svgEl('path', { class: 'timeline-area', d: dArea }));
  svg.appendChild(svgEl('path', { class: 'timeline-line', d: dLine }));

  // shade months outside the selected range
  if (state.m0 > 0)
    svg.appendChild(svgEl('rect', { class: 'brush-out', x: padL, y: padT, width: Math.max(0, x(state.m0) - padL), height: H - padT - padB }));
  if (state.m1 < n - 1)
    svg.appendChild(svgEl('rect', { class: 'brush-out', x: x(state.m1), y: padT, width: Math.max(0, W - padR - x(state.m1)), height: H - padT - padB }));

  // Tick density follows the available width, or the labels collide on phones.
  const nTicks = Math.max(3, Math.min(8, Math.round(W / 130)));
  for (let i = 0; i < n; i += Math.ceil(n / nTicks)) {
    const t = svgEl('text', { x: x(i), y: H - 6, 'text-anchor': 'middle', class: 'axis' });
    t.setAttribute('fill', 'var(--text-muted)');
    t.style.fontSize = '10.5px';
    t.textContent = MONTH_LABEL(DATA.months[i]);
    svg.appendChild(t);
  }

  const hit = svgEl('rect', { class: 'brush-bg', x: padL, y: padT, width: W - padL - padR, height: H - padT - padB });
  svg.appendChild(hit);

  const idxAt = (evt) => {
    const r = svg.getBoundingClientRect();
    const px = ((evt.clientX - r.left) / r.width) * W;
    return Math.max(0, Math.min(n - 1, Math.round((px - padL) / bandW)));
  };

  hit.addEventListener('pointerdown', (e) => {
    brushDrag = { start: idxAt(e), moved: false };
    hit.setPointerCapture(e.pointerId);
  });
  hit.addEventListener('pointermove', (e) => {
    const i = idxAt(e);
    if (brushDrag) {
      brushDrag.moved = true;
      state.m0 = Math.min(brushDrag.start, i);
      state.m1 = Math.max(brushDrag.start, i);
      render();
      return;
    }
    showTip(e, `<div class="t-name">${MONTH_LABEL(DATA.months[i])}</div>
      <div class="t-val">${fmt(Math.round(agg.mSer[i]))} clearances</div>
      <div class="t-sub">${corridorText()}</div>`);
  });
  hit.addEventListener('pointerleave', hideTip);
  hit.addEventListener('pointerup', () => {
    if (brushDrag && !brushDrag.moved) { state.m0 = 0; state.m1 = n - 1; render(); }
    brushDrag = null;
  });

  host.replaceChildren(svg);
}

const corridorText = () =>
  (state.dSel === null ? 'All districts' : DATA.districts[state.dSel].n) + ' → ' +
  (state.cSel === null ? 'all destinations' : DATA.countries[state.cSel].n);

/* ----------------------------------------------------------- BD map */

// Sequential ramp for the choropleth. In dark mode these tokens are
// re-stepped so near-zero recedes toward the dark surface instead of glowing.
const RAMP_O = ['--o-100','--o-200','--o-300','--o-400','--o-500','--o-700'];
const RAMP_D = ['--d-100','--d-200','--d-300','--d-400','--d-500','--d-700'];
// Order-of-magnitude breaks for the destination scale. Deliberately spaced so
// the top band isolates the single dominant destination and the low bands stay
// pale: a choropleth of counts inflates whatever is physically large, and
// Russia, Canada and Brazil are big on screen but small in the data.
const MAG_BREAKS = [100, 1000, 10000, 100000, 1000000];

function renderBdMap() {
  const host = $('#bd-map');
  const W = host.clientWidth || 460;
  const bbox = bboxOf(BDGEO);
  const H = fitHeight(bbox, W, 8, 560);
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.setAttribute('aria-label', 'Choropleth of Bangladesh districts by clearances');
  const proj = makeProjection(bbox, W, H, 8);
  const dVals = DATA.districts.map((_, i) => districtValue(i));
  const breaks = quantileBreaks(dVals, 6);

  BDGEO.features.forEach((f) => {
    const i = DISTRICT_INDEX[f.properties.name];
    const val = dVals[i] || 0;
    const b = binOf(val, breaks);
    const p = svgEl('path', {
      class: 'geo' + (state.dSel === i ? ' sel' : ''),
      d: pathFor(f.geometry, proj),
      fill: b < 0 ? 'var(--empty)' : `var(${RAMP_O[b]})`,
      tabindex: '0', role: 'button',
    });
    p.setAttribute('aria-label',
      `${f.properties.name}: ${fmtDistrict(val)}${isRate() ? ' per 100,000 residents' : ' clearances'}`);
    const activate = () => { state.dSel = state.dSel === i ? null : i; render(); };
    p.addEventListener('click', activate);
    p.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); } });
    p.addEventListener('pointermove', (e) =>
      showTip(e, `<div class="t-name">${f.properties.name}</div>
        <div class="t-val">${isRate()
          ? fmtRate(val) + ' per 100,000 residents'
          : fmt(Math.round(val)) + ' clearances'}</div>
        <div class="t-sub">${isRate()
          ? fmt(agg.dTot[i]) + ' clearances · population ' + fmt(DATA.districts[i].p)
          : fmtRate((agg.dTot[i] / DATA.districts[i].p) * PER) + ' per 100k · population ' + fmt(DATA.districts[i].p)}</div>
        <div class="t-sub">${f.properties.division} division${state.cSel !== null ? ' → ' + DATA.countries[state.cSel].n : ''}</div>`));
    p.addEventListener('pointerleave', hideTip);
    svg.appendChild(p);
  });

  host.replaceChildren(svg);
  renderLegend($('#bd-legend'), breaks, RAMP_O,
    isRate() ? 'Per 100,000 residents' : 'Clearances', Math.max(...dVals));
  $('#bd-hint').textContent = state.cSel === null
    ? 'Where workers come from. Click a district to see its destinations.'
    : `Districts sending workers to ${DATA.countries[state.cSel].n}.`;
}

/* -------------------------------------------------------- world map */

/* The destination distribution is far too skewed for a choropleth: one country
 * is ~58% of all records and the next 150 share the rest, so any binning either
 * flattens the leader or paints mid-volume countries as dark as it. Proportional
 * circles encode magnitude by area honestly, and they also give Singapore,
 * Maldives, Malta, Hong Kong and Bahrain a presence - none of which have a
 * polygon at 110m resolution. The land underneath stays a neutral base. */
function renderWorldMap() {
  const host = $('#world-map');
  const W = host.clientWidth || 460;
  const WORLD_BBOX = [-180, -56, 180, 84];
  const H = fitHeight(WORLD_BBOX, W, 4, 420);
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.setAttribute('aria-label', 'World map of destination countries, circle area proportional to clearances');
  const proj = makeProjection(WORLD_BBOX, W, H, 4);

  const byGeo = new Map();
  DATA.countries.forEach((c, i) => { if (c.g) byGeo.set(c.g, i); });

  // Magnitude bins, not quantiles. Destinations span six orders of magnitude
  // (1.9M down to 1), so equal-count bins would colour Russia at 8.5k as darkly
  // as Saudi Arabia at 1.9M. Powers of ten are honest here and read directly
  // off the legend: "tens", "hundreds", "thousands".
  const breaks = MAG_BREAKS.filter((b) => b <= Math.max(...agg.cTot));

  WORLDGEO.features.forEach((f) => {
    if (f.properties.name === 'Antarctica') return;   // never a destination
    const i = byGeo.get(f.properties.name);
    const val = i == null ? 0 : agg.cTot[i] || 0;
    const b = binOf(val, breaks);
    const p = svgEl('path', {
      d: pathFor(f.geometry, proj),
      // An inline style, not a fill attribute: a presentation attribute loses
      // to any CSS rule, and .world-base sets a fill.
      style: b < 0 ? null : `fill:var(${RAMP_D[Math.min(b, RAMP_D.length - 1)]})`,
      class: 'world-base' + (i != null && val > 0 ? ' has-data' : '') +
             (state.cSel === i ? ' sel' : ''),
    });
    if (i != null && val > 0) {
      p.setAttribute('tabindex', '0');
      p.setAttribute('role', 'button');
      p.setAttribute('aria-label', `${DATA.countries[i].n}: ${fmt(val)} clearances`);
      const activate = () => { state.cSel = state.cSel === i ? null : i; render(); };
      p.addEventListener('click', activate);
      p.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); } });
      p.addEventListener('pointermove', (e) => showTip(e, countryTip(i, val)));
      p.addEventListener('pointerleave', hideTip);
    }
    svg.appendChild(p);
  });

  const maxV = Math.max(1, ...agg.cTot);
  // Only countries with no polygon at this resolution get a marker - Singapore,
  // Maldives, Malta, Hong Kong, Bahrain and the island states. They are filled
  // from the same ramp as the land, so the map carries one encoding, not two.
  const order = DATA.countries.map((c, i) => i)
    .filter((i) => agg.cTot[i] > 0 && !DATA.countries[i].g)
    .sort((a, b) => agg.cTot[b] - agg.cTot[a]);

  // Connection arcs, origin -> destination. Capped at the busiest corridors:
  // 64 districts x 157 countries would be an unreadable hairball, and the tail
  // adds no information at hairline weight. Drawn before the circles so they
  // sit underneath, and left non-interactive so they never steal a click.
  const origin = state.dSel === null
    ? [90.35, 23.70]                       // national centroid
    : DATA.districts[state.dSel].c;
  const arcs = order.slice(0, 30);
  if (arcs.length) {
    const g = svgEl('g', { class: 'arcs', 'aria-hidden': 'true' });
    const [ox, oy] = proj(origin[0], origin[1]);
    arcs.forEach((i) => {
      const c = DATA.countries[i];
      if (!c.c || (c.c[0] === 0 && c.c[1] === 0)) return;
      const [dx, dy] = proj(c.c[0], c.c[1]);
      const len = Math.hypot(dx - ox, dy - oy);
      if (len < 4) return;
      // Bow the curve perpendicular to the chord, so arcs to nearby countries
      // stay shallow and long hauls sweep - the usual flight-path read.
      const mx = (ox + dx) / 2, my = (oy + dy) / 2;
      const nx = -(dy - oy) / len, ny = (dx - ox) / len;
      const bow = Math.min(len * 0.2, 70);
      const share = agg.cTot[i] / maxV;
      const p = svgEl('path', {
        class: 'arc' + (state.cSel === i ? ' sel' : ''),
        d: `M${ox.toFixed(1)} ${oy.toFixed(1)}Q${clamp(mx + nx * bow, 2, W - 2).toFixed(1)} ${clamp(my + ny * bow, 2, H - 2).toFixed(1)} ${dx.toFixed(1)} ${dy.toFixed(1)}`,
        'stroke-width': (0.5 + Math.sqrt(share) * 1.9).toFixed(2),
        opacity: (0.3 + Math.sqrt(share) * 0.45).toFixed(2),
      });
      g.appendChild(p);
    });
    // Anchor the fan so it reads as leaving somewhere, in the origin hue.
    g.appendChild(svgEl('circle', {
      class: 'origin-dot', cx: ox.toFixed(1), cy: oy.toFixed(1), r: 2.6,
    }));
    svg.appendChild(g);
  }

  order.forEach((i) => {
    const c = DATA.countries[i];
    if (!c.c || (c.c[0] === 0 && c.c[1] === 0)) return;
    const val = agg.cTot[i];
    const [cx, cy] = proj(c.c[0], c.c[1]);
    const b = binOf(val, breaks);
    const circ = svgEl('circle', {
      class: 'micro' + (state.cSel === i ? ' sel' : ''),
      style: `fill:var(${RAMP_D[Math.min(Math.max(b, 0), RAMP_D.length - 1)]})`,
      cx: cx.toFixed(1), cy: cy.toFixed(1), r: 3.2,
      tabindex: '0', role: 'button',
    });
    circ.setAttribute('aria-label', `${c.n}: ${fmt(val)} clearances`);
    const activate = () => { state.cSel = state.cSel === i ? null : i; render(); };
    circ.addEventListener('click', activate);
    circ.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); } });
    circ.addEventListener('pointermove', (e) => showTip(e, countryTip(i, val)));
    circ.addEventListener('pointerleave', hideTip);
    svg.appendChild(circ);
  });

  host.replaceChildren(svg);
  renderLegend($('#world-legend'), breaks, RAMP_D, 'Clearances', Math.max(...agg.cTot), true);
  $('#world-hint').textContent = state.dSel === null
    ? 'Where they go, shaded by volume. Small states appear as dots. Click a country to see which districts feed it.'
    : `Destinations of workers from ${DATA.districts[state.dSel].n}.`;
}

function countryTip(i, val) {
  const share = pct(val, sum(agg.cTot));
  return `<div class="t-name">${DATA.countries[i].n}</div>
    <div class="t-val">${fmt(val)} clearances · ${share}</div>
    <div class="t-sub">${state.dSel === null ? 'from all districts' : 'from ' + DATA.districts[state.dSel].n}</div>`;
}

function bboxOf(fc) {
  let a = 1e9, b = 1e9, c = -1e9, d = -1e9;
  const scan = (co) => {
    if (typeof co[0] === 'number') {
      a = Math.min(a, co[0]); c = Math.max(c, co[0]);
      b = Math.min(b, co[1]); d = Math.max(d, co[1]);
    } else co.forEach(scan);
  };
  fc.features.forEach((f) => scan(f.geometry.coordinates));
  return [a, b, c, d];
}

/** Binned ramp with the bin boundaries printed under the joins, so a reader can
 *  tell what a shade is worth instead of only that it is "darker". */
function renderLegend(host, breaks, ramp, caption, maxVal, microNote) {
  const SW = 40, H = 30;
  const nSw = Math.min(ramp.length, breaks.length + 1);
  const w = nSw * SW + 52;
  const parts = [
    `<span class="cap">${caption}</span>`,
    `<svg viewBox="0 0 ${w} ${H}" style="width:${w}px;height:${H}px;flex:none">`,
  ];
  for (let i = 0; i < nSw; i++) {
    parts.push(`<rect x="${i * SW + 2}" y="0" width="${SW - 2}" height="11" rx="2" fill="var(${ramp[i]})"/>`);
  }
  // Label every boundary. With magnitude bins these are round numbers, so the
  // reader can tell what a shade is worth rather than only that it is darker.
  breaks.slice(0, nSw - 1).forEach((b, i) => {
    parts.push(`<text x="${(i + 1) * SW + 1}" y="23" text-anchor="middle" fill="var(--text-muted)" style="font-size:10px">${fmtCompact(Math.round(b))}</text>`);
  });
  parts.push(`<text x="0" y="23" fill="var(--text-muted)" style="font-size:10px">0</text>`);
  if (maxVal)
    parts.push(`<text x="${nSw * SW + 2}" y="23" fill="var(--text-muted)" style="font-size:10px">${fmtCompact(Math.round(maxVal))}</text>`);
  parts.push('</svg>');
  if (microNote)
    parts.push(`<span class="tick" style="margin-left:10px">● small states shown as dots</span>`);
  host.innerHTML = parts.join('');
}

/* ------------------------------------------------------------- bars */

function barChart(host, items, colorClass, onPick, selIdx, valFmt) {
  const W = host.clientWidth || 460;
  // The sparkline column is the first thing to go when space is tight; the
  // ranking still works without it.
  const sparkW = W >= 400 ? 62 : 0;
  const rowH = 28, padT = 4, labelW = Math.min(132, W * 0.3), valW = 60;
  const trendW = sparkW ? 46 : 0;
  const H = padT + items.length * rowH;
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}` });
  const max = Math.max(1, ...items.map((it) => it.v));
  const barMax = W - labelW - valW - sparkW - trendW - 14;

  items.forEach((it, r) => {
    const y = padT + r * rowH;
    const g = svgEl('g', { class: 'bar-row' + (selIdx === it.i ? ' sel' : ''), tabindex: '0', role: 'button' });
    const trendTxt = it.trend == null ? ''
      : `, ${it.trend >= 0 ? 'up' : 'down'} ${Math.abs(Math.round(it.trend * 100))}% across the period`;
    g.setAttribute('aria-label',
      `${it.n}: ${valFmt ? valFmt(it.v) + ' per 100,000 residents' : fmt(it.v) + ' clearances'}${trendTxt}`);

    const lb = svgEl('text', { x: labelW - 8, y: y + 15, 'text-anchor': 'end', class: 'bar-label' });
    // Fit the label to the gutter actually available rather than a fixed count.
    const maxChars = Math.max(8, Math.floor((labelW - 10) / 6.4));
    lb.textContent = it.n.length > maxChars ? it.n.slice(0, maxChars - 1) + '…' : it.n;
    g.appendChild(lb);

    const w = Math.max(2, (it.v / max) * barMax);
    g.appendChild(svgEl('rect', {
      class: 'bar ' + colorClass + (selIdx !== null && selIdx !== it.i ? ' dim' : ''),
      x: labelW, y: y + 4, width: w, height: 14, rx: 4,
    }));

    const vl = svgEl('text', { x: labelW + w + 8, y: y + 15, class: 'bar-value' });
    vl.textContent = valFmt ? valFmt(it.v) : fmt(it.v);
    g.appendChild(vl);

    // Sparkline: this row's own trajectory over the selected period. Twelve of
    // them side by side is what turns a ranking into a comparison of trends.
    if (sparkW && it.series && it.series.length > 1) {
      const sx = W - sparkW - trendW, sy = y + 5, sh = 15;
      const smax = Math.max(...it.series, 1);
      const step = sparkW / (it.series.length - 1);
      let dLine = '', dArea = `M${sx} ${sy + sh}`;
      it.series.forEach((val, k) => {
        const px = sx + k * step, py = sy + sh - (val / smax) * sh;
        dLine += (k ? 'L' : 'M') + px.toFixed(1) + ' ' + py.toFixed(1);
        dArea += `L${px.toFixed(1)} ${py.toFixed(1)}`;
      });
      dArea += `L${(sx + sparkW).toFixed(1)} ${sy + sh}Z`;
      g.appendChild(svgEl('path', { class: 'spark-area ' + colorClass, d: dArea }));
      g.appendChild(svgEl('path', { class: 'spark-line ' + colorClass, d: dLine }));
      // Emphasise the endpoint — where the series ended is what a reader wants.
      const last = it.series[it.series.length - 1];
      g.appendChild(svgEl('circle', {
        class: 'spark-end ' + colorClass, r: 1.9,
        cx: (sx + sparkW).toFixed(1),
        cy: (sy + sh - (last / smax) * sh).toFixed(1),
      }));

      if (it.trend != null) {
        const up = it.trend >= 0;
        const t = svgEl('text', {
          x: W, y: y + 19, 'text-anchor': 'end',
          class: 'trend ' + (Math.abs(it.trend) < 0.05 ? 'flat' : up ? 'up' : 'down'),
        });
        t.textContent = (Math.abs(it.trend) < 0.05 ? '±' : up ? '▲' : '▼') +
          Math.abs(Math.round(it.trend * 100)) + '%';
        g.appendChild(t);
      }
    }

    const activate = () => onPick(it.i);
    g.addEventListener('click', activate);
    g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); } });
    g.addEventListener('pointermove', (e) =>
      showTip(e, `<div class="t-name">${it.n}</div><div class="t-val">${
        valFmt ? valFmt(it.v) + ' per 100,000 residents' : fmt(it.v) + ' clearances'}</div>
        <div class="t-sub">${it.sub || ''}</div>`));
    g.addEventListener('pointerleave', hideTip);
    svg.appendChild(g);
  });
  host.replaceChildren(svg);
}

function topItems(arr, names, n, flatSeries, valueFn) {
  const total = sum(arr);
  return Array.from(arr)
    .map((v, i) => ({ i, v: valueFn ? valueFn(i) : v, raw: v, n: names[i] }))
    .filter((x) => x.v > 0)
    .sort((a, b) => b.v - a.v)
    .slice(0, n)
    .map((x) => {
      const series = flatSeries ? seriesOf(flatSeries, x.i, agg.nM) : null;
      const trend = series ? trendOf(series) : null;
      return {
        ...x, series, trend,
        sub: (valueFn
          ? fmt(Math.round(x.raw)) + ' clearances · ' + pct(x.raw, total) + ' of the current view'
          : pct(x.v, total) + ' of the current view') +
          (trend == null ? '' :
            `<br>${trend >= 0 ? 'Up' : 'Down'} ${Math.abs(Math.round(trend * 100))}% — ` +
            'second half of the period vs the first'),
      };
    });
}

function renderBars() {
  const dNames = DATA.districts.map((d) => d.n);
  const cNames = DATA.countries.map((c) => c.n);
  barChart($('#bars-districts'),
    topItems(agg.dTot, dNames, 12, agg.dSer, isRate() ? districtValue : null), '',
    (i) => { state.dSel = state.dSel === i ? null : i; render(); }, state.dSel,
    isRate() ? fmtRate : null);
  barChart($('#bars-countries'), topItems(agg.cTot, cNames, 12, agg.cSer), 'dest',
    (i) => { state.cSel = state.cSel === i ? null : i; render(); }, state.cSel);
  const trendNote = ' Each row carries its own trend for the selected period.';
  $('#bars-d-hint').textContent = (isRate()
    ? 'Ranked by clearances per 100,000 residents — propensity, not volume.'
    : state.cSel === null
      ? 'Ranked by clearances in the current view.'
      : `Districts sending to ${DATA.countries[state.cSel].n}.`) + trendNote;
  $('#bars-c-hint').textContent = (state.dSel === null
    ? 'Ranked by clearances in the current view.'
    : `Destinations for ${DATA.districts[state.dSel].n} — how its mix has shifted.`) + trendNote;
}

/* ------------------------------------------------------------ table */

function renderTable() {
  const dNames = DATA.districts.map((d) => d.n);
  const cNames = DATA.countries.map((c) => c.n);
  const rows = [];
  topItems(agg.dTot, dNames, 64).forEach((x) =>
    rows.push(['District', x.n, DATA.districts[x.i].v, x.v,
               fmtRate((x.v / DATA.districts[x.i].p) * PER), fmt(DATA.districts[x.i].p)]));
  topItems(agg.cTot, cNames, 200).forEach((x) =>
    rows.push(['Destination', x.n, '', x.v, '', '']));

  const html = `<div class="tablewrap"><table>
    <caption class="sr-only">Clearances for ${corridorText()}, ${MONTH_LABEL(DATA.months[state.m0])} to ${MONTH_LABEL(DATA.months[state.m1])}</caption>
    <thead><tr><th>Type</th><th>Name</th><th>Division</th><th class="num">Clearances</th>
      <th class="num">Per 100k</th><th class="num">Population</th></tr></thead>
    <tbody>${rows.map((r) =>
      `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td class="num">${fmt(r[3])}</td>` +
      `<td class="num">${r[4]}</td><td class="num">${r[5]}</td></tr>`
    ).join('')}</tbody></table></div>`;
  $('#table-body').innerHTML = html;
}

/* ------------------------------------------------------------- boot */

let DISTRICT_INDEX = {};

async function boot() {
  const [d, bd, w] = await Promise.all([
    fetch('data/dashboard.json').then((r) => r.json()),
    fetch('data/bd-districts.geo.json').then((r) => r.json()),
    fetch('data/world.geo.json').then((r) => r.json()),
  ]);
  DATA = d; BDGEO = bd; WORLDGEO = w;
  DATA.districts.forEach((x, i) => (DISTRICT_INDEX[x.n] = i));
  state.m0 = 0;
  state.m1 = DATA.months.length - 1;

  $('#foot-meta').textContent =
    `Data through ${DATA.meta.dateEnd}; rebuilt ${DATA.meta.generated}. ` +
    `${fmt(DATA.meta.total)} clearances mapped.`;

  document.querySelectorAll('.seg button[data-measure]').forEach((b) => {
    b.onclick = () => {
      state.measure = b.dataset.measure;
      document.querySelectorAll('.seg button[data-measure]').forEach((o) =>
        o.setAttribute('aria-pressed', String(o.dataset.measure === state.measure)));
      render();
    };
  });

  document.querySelectorAll('.seg button[data-mode]').forEach((b) => {
    b.onclick = () => {
      state.tlMode = b.dataset.mode;
      document.querySelectorAll('.seg button[data-mode]').forEach((o) =>
        o.setAttribute('aria-pressed', String(o.dataset.mode === state.tlMode)));
      render();
    };
  });

  $('#reset-btn').onclick = () => {
    state.dSel = state.cSel = null;
    state.m0 = 0; state.m1 = DATA.months.length - 1;
    render();
  };
  const tb = $('#table-btn');
  tb.onclick = () => {
    const body = $('#table-body');
    body.hidden = !body.hidden;
    tb.setAttribute('aria-expanded', String(!body.hidden));
    tb.textContent = body.hidden ? 'Show table' : 'Hide table';
    if (!body.hidden) renderTable();
  };
  $('#theme-btn').onclick = () => {
    const cur = document.documentElement.getAttribute('data-theme');
    const next = cur === 'dark' ? 'light' : cur === 'light' ? 'dark'
      : (matchMedia('(prefers-color-scheme: dark)').matches ? 'light' : 'dark');
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('bmet-theme', next); } catch (e) { /* private mode */ }
    render();
  };
  try {
    const saved = localStorage.getItem('bmet-theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
  } catch (e) { /* ignore */ }

  let rt;
  addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(render, 160); });

  render();
}

boot().catch((e) => {
  document.querySelector('.wrap').insertAdjacentHTML('afterbegin',
    `<div class="caveat"><strong>Could not load the data.</strong> ${e}</div>`);
});
