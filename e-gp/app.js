/* Bangladesh e-GP — findings dashboard.
   Charts are hand-built inline SVG: no library, no build step, and the marks
   stay legible because every one of them is chosen for the claim it supports. */

const CR = 1e7;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const int = n => n == null ? "—" : Math.round(n).toLocaleString("en-US");
const pct = (n, d = 0) => `${(n * 100).toFixed(d)}%`;

/** Taka, abbreviated the way Bangladeshi readers actually read it. */
function taka(n) {
  if (n == null) return "—";
  if (n >= 1e11) return `৳${(n / 1e11).toFixed(1)}k Cr`;
  if (n >= CR) return `৳${(n / CR).toLocaleString("en-US", { maximumFractionDigits: 0 })} Cr`;
  if (n >= 1e5) return `৳${(n / 1e5).toFixed(1)} L`;
  return `৳${int(n)}`;
}

async function loadJSON(p) {
  const r = await fetch(p);
  if (!r.ok) throw new Error(`${p}: HTTP ${r.status}`);
  return r.json();
}
const svg = (w, h, body) =>
  `<svg viewBox="0 0 ${w} ${h}" role="img" xmlns="http://www.w3.org/2000/svg">${body}</svg>`;
const legend = items => items.map(([c, l]) =>
  `<span><i class="swatch" style="background:${c}"></i>${esc(l)}</span>`).join("");

/* ── 01 · Monthly seasonality ─────────────────────────────────────── */

function chartMonths(a) {
  const by = a.seasonality.by_month;
  const keys = Object.keys(by).sort();
  const vals = keys.map(k => by[k].share);
  const max = Math.max(...vals);
  const W = 800, H = 250, padL = 34, padR = 10, padT = 26, padB = 34;
  const pw = W - padL - padR, ph = H - padT - padB;
  const bw = pw / 12 * 0.62, step = pw / 12;
  const uniform = 1 / 12;

  let body = "";
  // reference line: what a flat year would look like
  const uy = padT + ph - (uniform / max) * ph;
  body += `<line class="grid" x1="${padL}" y1="${uy}" x2="${W - padR}" y2="${uy}"
            stroke-dasharray="3 3"/>
           <text class="ax" x="${W - padR}" y="${uy - 5}" text-anchor="end">even spread · 8.3%</text>`;

  keys.forEach((k, i) => {
    const v = by[k].share;
    const isJune = k === "06";
    const h = (v / max) * ph;
    const x = padL + i * step + (step - bw) / 2;
    const y = padT + ph - h;
    body += `<rect x="${x}" y="${y}" width="${bw}" height="${h}" rx="3"
               fill="${isJune ? "var(--s2)" : "var(--s1)"}" ${isJune ? "" : 'opacity="0.55"'}>
               <title>${MONTHS[i]}: ${int(by[k].count)} contracts (${pct(v, 1)})</title></rect>
             <text class="val-label${isJune ? " hi" : ""}" x="${x + bw / 2}" y="${y - 7}"
               text-anchor="middle">${pct(v, 1)}</text>
             <text class="${isJune ? "ax-strong" : "ax"}" x="${x + bw / 2}" y="${H - 12}"
               text-anchor="middle">${MONTHS[i]}</text>`;
  });
  // fiscal-year boundary
  const fx = padL + 6 * step;
  body += `<line x1="${fx}" y1="${padT - 12}" x2="${fx}" y2="${padT + ph}"
            stroke="var(--s2)" stroke-width="1" stroke-dasharray="2 3" opacity="0.7"/>
           <text class="val-label hi" x="${fx + 5}" y="${padT - 15}">fiscal year ends 30 Jun</text>`;

  document.getElementById("chartMonths").innerHTML = svg(W, H, body);
  document.getElementById("capMonths").textContent =
    `Share of all ${int(a.meta.contracts)} contracts by calendar month of signing, 2011–2026. `
    + `June carries ${pct(by["06"].share, 1)} against the ${pct(1 / 12, 1)} an even spread would give.`;
}

/* ── 02 · Procurement-method mix ──────────────────────────────────── */

function chartMethods(a) {
  const byYear = a.method_mix.value_share_by_year;
  const years = Object.keys(byYear).filter(y => y >= "2015").sort();
  const series = [
    { k: "OTM", label: "Open tendering (OTM)", c: "var(--s1)" },
    { k: "LTM", label: "Limited / invitation-only (LTM)", c: "var(--s2)" },
    { k: "OSTETM", label: "Two-envelope (OSTETM)", c: "var(--s3)" },
  ];
  const W = 800, H = 270, padL = 40, padR = 96, padT = 16, padB = 32;
  const pw = W - padL - padR, ph = H - padT - padB;
  const x = i => padL + (i / (years.length - 1)) * pw;
  const y = v => padT + ph - v * ph;

  let body = "";
  for (let g = 0; g <= 100; g += 25) {
    const gy = y(g / 100);
    body += `<line class="grid" x1="${padL}" y1="${gy}" x2="${W - padR}" y2="${gy}"/>
             <text class="ax" x="${padL - 7}" y="${gy + 3}" text-anchor="end">${g}%</text>`;
  }
  years.forEach((yr, i) => {
    if (i % 2 === 0 || i === years.length - 1)
      body += `<text class="ax" x="${x(i)}" y="${H - 12}" text-anchor="middle">${yr}</text>`;
  });
  for (const s of series) {
    const pts = years.map((yr, i) => [x(i), y(byYear[yr][s.k] || 0)]);
    body += `<polyline fill="none" stroke="${s.c}" stroke-width="2" stroke-linejoin="round"
               points="${pts.map(p => p.join(",")).join(" ")}"/>`;
    pts.forEach(([px, py], i) => {
      body += `<circle cx="${px}" cy="${py}" r="2.5" fill="${s.c}">
                 <title>${years[i]} · ${s.label}: ${pct(byYear[years[i]][s.k] || 0, 1)}</title></circle>`;
    });
    const [lx, ly] = pts[pts.length - 1];
    body += `<text class="val-label" x="${lx + 8}" y="${ly + 3}" fill="${s.c}">${s.k} ${pct(byYear[years[years.length - 1]][s.k] || 0)}</text>`;
  }
  document.getElementById("legendMethods").innerHTML =
    legend(series.map(s => [s.c, s.label]));
  document.getElementById("chartMethods").innerHTML = svg(W, H, body);
  document.getElementById("capMethods").textContent =
    "Share of contract value by procurement method, per year of signing. Lines are labelled at their latest value.";
}

/* ── 03 · Plan vs outcome ─────────────────────────────────────────── */

function chartPlanVsActual(p) {
  // Method-change (planned procurement method vs. the one actually used) is
  // computed in the JSON but deliberately not charted here: on the matched
  // subset that survives the generic-reference and sanity-ratio filters
  // below, it comes out to 19 packages ending up less open vs. 18 ending up
  // more open -- no detectable direction at this sample size. An earlier
  // version of this page reported a 10x skew toward "less open," which
  // turned out to be almost entirely package-reference join noise (see
  // Methodology). The raw counts remain in `method_change` for anyone
  // auditing, but nothing here is asserted as a finding.

  // award / estimate — fine histogram. The whole point is the spikes, so this
  // is drawn at 1-percentage-point resolution rather than in coarse buckets.
  const av = p.award_vs_estimate;
  const fine = av.fine_histogram;
  const keys = Object.keys(fine).map(Number).sort((x, z) => x - z).filter(k => k >= 0.7 && k <= 1.15);
  const fmax = Math.max(...keys.map(k => fine[k.toFixed(2)]), 1);
  const W2 = 800, H2 = 280, pL = 44, pR = 16, pT = 40, pB = 46;
  const pw2 = W2 - pL - pR, ph2 = H2 - pT - pB;
  const step = pw2 / keys.length, bw = Math.max(step * 0.8, 1.5);
  const SPIKES = { "0.90": "10% below", "0.95": "5% below", "1.00": "at estimate" };

  let body2 = "";
  for (let g = 0; g <= 1; g += 0.5) {
    const gy = pT + ph2 - g * ph2;
    body2 += `<line class="grid" x1="${pL}" y1="${gy}" x2="${W2 - pR}" y2="${gy}"/>
              <text class="ax" x="${pL - 7}" y="${gy + 3}" text-anchor="end">${int(g * fmax)}</text>`;
  }
  keys.forEach((k, i) => {
    const kk = k.toFixed(2);
    const n = fine[kk] || 0;
    const h = (n / fmax) * ph2;
    const x = pL + i * step + (step - bw) / 2;
    const yy = pT + ph2 - h;
    const spike = SPIKES[kk];
    body2 += `<rect x="${x}" y="${yy}" width="${bw}" height="${Math.max(h, 0.8)}"
                fill="${spike ? "var(--s2)" : "var(--s1)"}" opacity="${spike ? 1 : 0.5}">
                <title>${int(n)} contracts awarded at ${pct(k)} of the estimate</title></rect>`;
    if (spike) {
      body2 += `<text class="val-label hi" x="${x + bw / 2}" y="${yy - 20}" text-anchor="middle">${int(n)}</text>
                <text class="val-label hi" x="${x + bw / 2}" y="${yy - 8}" text-anchor="middle">${spike}</text>`;
    }
    if (Math.abs(k * 100 - Math.round(k * 20) * 5) < 0.01) {
      body2 += `<text class="ax" x="${x + bw / 2}" y="${H2 - 26}" text-anchor="middle">${pct(k)}</text>`;
    }
  });
  body2 += `<text class="ax" x="${pL + pw2 / 2}" y="${H2 - 8}" text-anchor="middle">awarded price as a share of the government's pre-tender estimate</text>`;
  document.getElementById("chartRatio").innerHTML = svg(W2, H2, body2);
  document.getElementById("capRatio").textContent =
    `Every matched package, at one-percentage-point resolution. Genuine price competition would `
    + `spread smoothly across this range; instead ${pct(av.discount_spikes.at_10pct_below.share)} `
    + `of contracts land within half a point of exactly 10% below the estimate.`;

  document.getElementById("pvaSpike").textContent = pct(av.discount_spikes.at_10pct_below.share);
  document.getElementById("pvaSpike5").textContent = pct(av.discount_spikes.at_5pct_below.share);
  document.getElementById("pvaCoverage").textContent =
    `Plan and award are typed into different forms, so they only join where the package reference `
    + `matches exactly — ${int(p.meta.matched_pairs)} of ${int(p.meta.plan_packages_with_estimate)} `
    + `planned packages (${pct(p.meta.match_rate_of_plan)}), after excluding `
    + `${int(p.meta.pairs_excluded_generic)} matches on a reference too generic to trust (see `
    + `Methodology) and ${int(p.meta.pairs_excluded_sanity)} at an implausible ratio. These figures `
    + `describe that matched subset, and the itemised plan itself is crawled for the busiest offices `
    + `first, not all 10,205 of them.`;

  // overrun tail — banded, not fine-grained: there's no round-number
  // convention on this side, so a 1-point histogram would just be noise.
  const OB_ORDER = ["100-105%", "105-110%", "110-115%", "115-125%", "125-150%", "150-200%", ">200%"];
  const bands = av.overrun_bands;
  const bmax = Math.max(...OB_ORDER.map(k => bands[k] || 0));
  const W3 = 800, H3 = 190, pL3 = 78, pR3 = 60, pT3 = 8;
  const rowH3 = (H3 - pT3) / OB_ORDER.length, bh3 = rowH3 * 0.56;
  const pw3 = W3 - pL3 - pR3;
  let body3 = "";
  OB_ORDER.forEach((k, i) => {
    const n = bands[k] || 0;
    const yy = pT3 + i * rowH3 + (rowH3 - bh3) / 2;
    const w = Math.max((n / bmax) * pw3, 2);
    const extreme = k === ">200%" || k === "150-200%";
    body3 += `<text class="ax-strong" x="${pL3 - 12}" y="${yy + bh3 / 2 + 4}" text-anchor="end">${k}</text>
              <rect x="${pL3}" y="${yy}" width="${w}" height="${bh3}" rx="3"
                fill="${extreme ? "var(--s2)" : "var(--s1)"}" ${extreme ? "" : 'opacity="0.55"'}>
                <title>${int(n)} packages awarded ${k} of their estimate</title></rect>
              <text class="val-label${extreme ? " hi" : ""}" x="${pL3 + w + 9}" y="${yy + bh3 / 2 + 4}">${int(n)}</text>`;
  });
  document.getElementById("chartOverrun").innerHTML = svg(W3, H3, body3);
  document.getElementById("capOverrun").textContent =
    `Matched packages awarded above their own estimate, banded by how far above. `
    + `${int(bands[">200%"] || 0)} packages were awarded at more than double what was estimated for them.`;

  const os_ = av.overrun_summary;
  document.getElementById("ovrCount").textContent = int(os_.count_above_115);
  document.getElementById("ovrValue").textContent = taka(os_.total_extra_bdt);
  document.getElementById("overrunBody").innerHTML = p.biggest_overruns.slice(0, 15).map(o => `
    <tr>
      <td class="strong">${esc(o.package_no || "—")}<div class="muted" style="font-size:0.78em;margin-top:2px">${esc(o.description || "")}</div></td>
      <td class="n">${taka(o.estimated_cost_bdt)}</td>
      <td class="n">${taka(o.awarded_bdt)}</td>
      <td class="n hi">${pct(o.ratio - 1)}</td>
      <td class="muted">${esc(o.awarded_to || "—")}</td>
      <td class="muted">${esc(o.actual_method || "—")}</td>
    </tr>`).join("");
}

/* ── 04 · Cost structure by ministry & year ───────────────────────── */

function chartCostStructure(p) {
  const cs = p.cost_structure;
  // Ranked by typical discount off estimate (1 - median ratio), deepest
  // first. This is the median, not the >115%-overrun share: the median is
  // stable on a small matched sample in a way a tail statistic isn't, which
  // is why it's the one used for a per-ministry comparison at this scale.
  const rows = cs.by_ministry.slice().sort((a, b) => (1 - a.median_ratio) < (1 - b.median_ratio) ? 1 : -1);
  const discounts = rows.map(r => 1 - r.median_ratio);
  const max = Math.max(...discounts.map(Math.abs), 0.01);
  const W = 800, H = Math.max(rows.length * 34, 150), padL = 260, padR = 200, padT = 8;
  const rowH = H / rows.length, bh = rowH * 0.56;
  const pw = W - padL - padR;

  let body = "";
  rows.forEach((r, i) => {
    const short = r.ministry.replace(/^Ministry of /, "");
    const yy = i * rowH + (rowH - bh) / 2;
    const d = discounts[i];
    const w = Math.max((Math.abs(d) / max) * pw, 2);
    body += `<text class="ax" x="${padL - 12}" y="${yy + bh / 2 + 4}" text-anchor="end">${esc(short.slice(0, 38))}</text>
             <rect x="${padL}" y="${yy}" width="${w}" height="${bh}" rx="3"
               fill="${i === 0 ? "var(--s2)" : "var(--s1)"}" ${i === 0 ? "" : 'opacity="0.55"'}>
               <title>${esc(r.ministry)}: median award is ${pct(r.median_ratio, 1)} of estimate, across ${int(r.matched_pairs)} matched packages</title></rect>
             <text class="val-label${i === 0 ? " hi" : ""}" x="${padL + w + 9}" y="${yy + bh / 2 + 4}">
               ${pct(d, 1)} below <tspan class="muted">· n=${int(r.matched_pairs)}</tspan></text>`;
  });
  document.getElementById("chartCostMinistry").innerHTML = svg(W, H, body);
  document.getElementById("capCostMinistry").textContent =
    `Typical discount off the government's own estimate (1 − median award/estimate ratio), by ministry `
    + `(ministries with ${cs.min_pairs_for_ministry}+ matched packages only). Matched-package count on hover.`;

  const yrs = cs.by_year;
  const ymax = Math.max(...yrs.map(y => y.share_at_10pct_below));
  const W2 = 800, H2 = 220, pL = 40, pR = 16, pT = 16, pB = 30;
  const pw2 = W2 - pL - pR, ph2 = H2 - pT - pB;
  const xx = i => pL + (i / (yrs.length - 1)) * pw2;
  const yy2 = v => pT + ph2 - (v / ymax) * ph2;
  let body2 = "";
  for (let g = 0; g <= Math.ceil(ymax * 10) / 10; g += 0.1) {
    const gy = yy2(g);
    body2 += `<line class="grid" x1="${pL}" y1="${gy}" x2="${W2 - pR}" y2="${gy}"/>
              <text class="ax" x="${pL - 7}" y="${gy + 3}" text-anchor="end">${pct(g)}</text>`;
  }
  const pts = yrs.map((y, i) => [xx(i), yy2(y.share_at_10pct_below)]);
  body2 += `<polyline fill="none" stroke="var(--s2)" stroke-width="2" stroke-linejoin="round"
             points="${pts.map(pt => pt.join(",")).join(" ")}"/>`;
  yrs.forEach((y, i) => {
    body2 += `<circle cx="${pts[i][0]}" cy="${pts[i][1]}" r="2.5" fill="var(--s2)">
                <title>${y.year}: ${pct(y.share_at_10pct_below, 1)} of ${int(y.matched_pairs)} matched packages at ~10% below estimate</title></circle>`;
    if (i % 2 === 0 || i === yrs.length - 1)
      body2 += `<text class="ax" x="${pts[i][0]}" y="${H2 - 8}" text-anchor="middle">${y.year}</text>`;
  });
  document.getElementById("chartCostTrend").innerHTML = svg(W2, H2, body2);
  document.getElementById("capCostTrend").textContent =
    "Share of matched packages landing within half a point of exactly 10% below the government's estimate, by year of contract signing.";
}

/* ── 05 · The ৳50 crore ceiling ───────────────────────────────────── */

function chartCeiling(cl) {
  const b = cl.bunching;
  const hist = b.fine_histogram_crore;
  const keys = Object.keys(hist).map(Number).sort((x, z) => x - z);
  const max = Math.max(...keys.map(k => hist[k.toFixed(2)]), 1);
  const W = 800, H = 260, pL = 40, pR = 16, pT = 16, pB = 40;
  const pw = W - pL - pR, ph = H - pT - pB;
  const step = pw / keys.length, bw = Math.max(step * 0.78, 1.5);

  let body = "";
  keys.forEach((k, i) => {
    const kk = k.toFixed(2);
    const n = hist[kk] || 0;
    const h = (n / max) * ph;
    const x = pL + i * step + (step - bw) / 2;
    const yy = pT + ph - h;
    const near = k >= 45 && k < 50;
    body += `<rect x="${x}" y="${yy}" width="${bw}" height="${Math.max(h, 0.8)}" rx="1"
               fill="${near ? "var(--s2)" : "var(--s1)"}" ${near ? "" : 'opacity="0.5"'}>
               <title>৳${k} crore band: ${int(n)} contracts</title></rect>`;
    if (Math.abs(k - Math.round(k)) < 0.01)
      body += `<text class="ax" x="${x + bw / 2}" y="${H - 20}" text-anchor="middle">${k}</text>`;
  });
  const fx = pL + ((50 - keys[0]) / (keys[keys.length - 1] - keys[0])) * pw;
  body += `<line x1="${fx}" y1="${pT}" x2="${fx}" y2="${pT + ph}" stroke="var(--critical)" stroke-width="1" stroke-dasharray="2 3"/>
           <text class="val-label hi" x="${fx + 6}" y="${pT + 12}">৳50 crore</text>
           <text class="ax" x="${pL + pw / 2}" y="${H - 6}" text-anchor="middle">contract value, crore taka</text>`;
  document.getElementById("chartCeiling").innerHTML = svg(W, H, body);
  document.getElementById("capCeiling").textContent =
    `Contract count by value, in ৳0.5 crore bands, ৳30-65 crore. ${int(b.just_under_45_50)} contracts `
    + `fall in the ৳45-50 crore band just under the line against ${int(b.just_over_50_55)} in the `
    + `equivalent ৳50-55 crore band just over it.`;
  document.getElementById("ceilAsym").textContent = `${b.asymmetry_ratio}×`;

  document.getElementById("ceilClusterCount").textContent = int(cl.split_clusters_total_count);
  document.getElementById("ceilBody").innerHTML = cl.split_clusters.slice(0, 15).map(c => `
    <tr>
      <td class="strong">${esc(c.procuring_entity)}<div class="muted" style="font-size:0.78em;margin-top:2px">${esc(c.ministry)}</div></td>
      <td>${esc(c.vendor)}</td>
      <td class="n hi">${taka(c.total_bdt)}</td>
      <td class="n">${int(c.count)}</td>
      <td class="muted">${esc(c.first_date)} → ${esc(c.last_date)}</td>
    </tr>`).join("");
}

/* ── 04 · Office concentration ────────────────────────────────────── */

function chartConc(a) {
  const b = a.concentration.office_top_vendor_share_buckets;
  const rows = Object.entries(b);
  const total = rows.reduce((s, [, n]) => s + n, 0);
  const max = Math.max(...rows.map(([, n]) => n));
  const W = 800, H = 190, padL = 118, padR = 96, padT = 8;
  const rowH = (H - padT) / rows.length, bh = rowH * 0.56;
  const pw = W - padL - padR;

  let body = "";
  rows.forEach(([band, n], i) => {
    const yy = padT + i * rowH + (rowH - bh) / 2;
    const w = (n / max) * pw;
    // the tail (>60%) is the story; everything else recedes
    const hot = band === "60-80" || band === "80-100";
    body += `<text class="ax-strong" x="${padL - 12}" y="${yy + bh / 2 + 4}" text-anchor="end">${band}%</text>
             <rect x="${padL}" y="${yy}" width="${Math.max(w, 2)}" height="${bh}" rx="3"
               fill="${hot ? "var(--s2)" : "var(--s1)"}" ${hot ? "" : 'opacity="0.5"'}>
               <title>${n} offices give their top supplier ${band}% of spend</title></rect>
             <text class="val-label${hot ? " hi" : ""}" x="${padL + Math.max(w, 2) + 9}"
               y="${yy + bh / 2 + 4}">${n} ${n === 1 ? "office" : "offices"}</text>`;
  });
  document.getElementById("chartConc").innerHTML = svg(W, H, body);
  document.getElementById("capConc").textContent =
    `How much of an office's total spend goes to its single largest supplier, across the `
    + `${total} offices with at least ${a.concentration.thresholds.min_contracts} contracts and `
    + `৳${a.concentration.thresholds.min_value_bdt / CR} crore in spend. Nationally the market looks `
    + `near-perfectly competitive — ${int(a.concentration.national.vendors)} vendors, HHI `
    + `${a.concentration.national.hhi} — so the tail is where anything interesting lives.`;

  document.getElementById("qualOffices").textContent = int(a.concentration.offices_qualifying);
  document.getElementById("concBody").innerHTML = a.concentration.most_concentrated_offices
    .filter(o => o.top_vendor_share >= 0.6).map(o => `
      <tr>
        <td class="strong">${esc(o.office)}</td>
        <td class="muted">${esc(o.ministry)}</td>
        <td class="n">${taka(o.value_bdt)}</td>
        <td class="n">${int(o.count)}</td>
        <td>${esc(o.top_vendor)}</td>
        <td class="n"><span class="mini">
          <span class="mini-track"><span class="mini-fill" style="width:${o.top_vendor_share * 100}%"></span></span>
          ${pct(o.top_vendor_share)}</span></td>
      </tr>`).join("");
}

/* ── 04 · Repeated price points ───────────────────────────────────── */

function chartPrice(a) {
  const pp = a.price_points;
  const top = pp.top_price_points.slice(0, 12);
  const max = Math.max(...top.map(p => p.count));
  const W = 800, H = 330, padL = 96, padR = 186, padT = 8;
  const rowH = (H - padT) / top.length, bh = rowH * 0.58;
  const pw = W - padL - padR;

  let body = "";
  top.forEach((p, i) => {
    const yy = padT + i * rowH + (rowH - bh) / 2;
    const w = (p.count / max) * pw;
    const heavy = p.ltm_share >= 0.6;
    body += `<text class="ax-strong" x="${padL - 12}" y="${yy + bh / 2 + 4}" text-anchor="end">
               ৳${(p.value_bdt / 1e5).toFixed(2).replace(/\.00$/, "")}L</text>
             <rect x="${padL}" y="${yy}" width="${w}" height="${bh}" rx="3"
               fill="${heavy ? "var(--s2)" : "var(--s1)"}" ${heavy ? "" : 'opacity="0.55"'}>
               <title>৳${int(p.value_bdt)} — ${int(p.count)} contracts, ${pct(p.ltm_share)} limited-tender</title></rect>
             <text class="val-label" x="${padL + w + 9}" y="${yy + bh / 2 + 4}">
               ${int(p.count)} <tspan fill="${heavy ? "var(--s2)" : "var(--text-3)"}">· ${pct(p.ltm_share)} LTM</tspan></text>`;
  });
  document.getElementById("legendPrice").innerHTML = legend([
    ["var(--s2)", "mostly invitation-only (≥60% LTM)"],
    ["var(--s1)", "mixed methods"],
  ]);
  document.getElementById("chartPrice").innerHTML = svg(W, H, body);
  document.getElementById("capPrice").textContent =
    `The twelve most frequently repeated exact contract values, out of ${int(pp.distinct_values)} `
    + `distinct values in the data. Bars show how many contracts sit on each price; the label gives `
    + `the share awarded by limited tendering.`;

  const p950 = pp.top_price_points.find(p => p.value_bdt === 950000);
  const t20 = pp.top_price_points.slice(0, 20);
  const wtd = t20.reduce((s, p) => s + p.ltm_share * p.count, 0) / t20.reduce((s, p) => s + p.count, 0);
  document.getElementById("pp950").textContent = p950 ? int(p950.count) : "—";
  document.getElementById("ppLtm").textContent = pct(wtd);
  document.getElementById("ppBase").textContent = pct(pp.ltm_share_overall);
}

/* ── 05 · Ministries & offices ────────────────────────────────────── */

function chartMinistries(insights, profiles, a) {
  const rows = insights.top_ministries_by_value.slice(0, 10);
  const max = Math.max(...rows.map(r => r.value_bdt));
  const totalAll = a.meta.total_value_bdt;
  const W = 800, H = 300, padL = 250, padR = 84, padT = 6;
  const rowH = (H - padT) / rows.length, bh = rowH * 0.6;
  const pw = W - padL - padR;

  let body = "";
  rows.forEach((r, i) => {
    const yy = padT + i * rowH + (rowH - bh) / 2;
    const w = (r.value_bdt / max) * pw;
    const short = r.ministry.replace(/^Ministry of /, "").replace(/, Rural Development and Co-operatives$/, "");
    body += `<text class="ax" x="${padL - 12}" y="${yy + bh / 2 + 4}" text-anchor="end">${esc(short.slice(0, 34))}</text>
             <rect x="${padL}" y="${yy}" width="${w}" height="${bh}" rx="3"
               fill="var(--s1)" opacity="${i === 0 ? 1 : 0.55}">
               <title>${esc(r.ministry)}: ${taka(r.value_bdt)} (${pct(r.value_bdt / totalAll, 1)} of all value)</title></rect>
             <text class="val-label" x="${padL + w + 9}" y="${yy + bh / 2 + 4}">${taka(r.value_bdt)}</text>`;
  });
  document.getElementById("chartMinistries").innerHTML = svg(W, H, body);
  document.getElementById("capMinistries").textContent =
    "Total contract value awarded by each ministry, 2011–2026, top ten of "
    + `${insights.top_ministries_by_value.length}+ ministries in the data.`;

  const four = rows.slice(0, 4).reduce((s, r) => s + r.value_bdt, 0);
  document.getElementById("topFourShare").textContent = pct(four / totalAll);

  document.getElementById("officesBody").innerHTML = profiles.top_offices_by_value.slice(0, 12)
    .map(o => {
      const nat = Object.entries(o.by_nature).sort((x, z) => z[1] - x[1])[0];
      return `<tr>
        <td class="strong">${esc(o.procuring_entity)}</td>
        <td class="muted">${esc(o.ministry.replace(/^Ministry of /, ""))}</td>
        <td class="n">${taka(o.value_bdt)}</td>
        <td class="n">${int(o.count)}</td>
        <td class="muted">${nat ? esc(nat[0]) : "—"}</td>
      </tr>`;
    }).join("");
  document.getElementById("natureNote").textContent =
    `"Mostly buys" is joined from the tender list, which matches `
    + `${pct(profiles.meta.nature_match_rate)} of contracts — read it as a sample per office.`;
}

/* ── 06 · Cross-ministry suppliers & ownership ────────────────────── */

function chartCross(profiles) {
  const rows = profiles.cross_departmental_vendors.slice(0, 12);
  const max = Math.max(...rows.map(r => r.distinct_ministries));
  const W = 800, H = 330, padL = 196, padR = 228, padT = 6;
  const rowH = (H - padT) / rows.length, bh = rowH * 0.58;
  const pw = W - padL - padR;

  let body = "";
  rows.forEach((r, i) => {
    const yy = padT + i * rowH + (rowH - bh) / 2;
    const w = (r.distinct_ministries / max) * pw;
    body += `<text class="ax" x="${padL - 12}" y="${yy + bh / 2 + 4}" text-anchor="end">${esc(r.company.slice(0, 30))}</text>
             <rect x="${padL}" y="${yy}" width="${w}" height="${bh}" rx="3" fill="var(--s3)" opacity="${i === 0 ? 1 : 0.6}">
               <title>${esc(r.company)}: ${r.distinct_ministries} ministries, ${taka(r.value_bdt)}</title></rect>
             <text class="val-label" x="${padL + w + 9}" y="${yy + bh / 2 + 4}">
               ${r.distinct_ministries} ministries <tspan class="muted">· ${taka(r.value_bdt)}</tspan></text>`;
  });
  document.getElementById("chartCross").innerHTML = svg(W, H, body);
  document.getElementById("capCross").textContent =
    "Suppliers holding contracts from the largest number of different ministries.";
  document.getElementById("maxMinistries").textContent = `${rows[0].distinct_ministries}`;
}

function renderOwnership(own) {
  const lede = document.getElementById("ownLede");
  const body = document.getElementById("ownBody");
  if (!own) {
    lede.textContent = "Beneficial-ownership data is still being collected.";
    return;
  }
  const m = own.meta;
  lede.innerHTML = `Beneficial owners crawled for the ${int(m.vendors_sampled)} largest vendors by value; `
    + `${int(m.vendors_with_owner_data)} had the field filled in. `
    + `<strong>${own.shared_owner_groups.length}</strong> owner names appear on two or more companies.`;
  body.innerHTML = own.shared_owner_groups.slice(0, 12).map(g => `
    <tr>
      <td class="strong">${esc(g.companies[0].owner_name_as_shown)}</td>
      <td>${g.companies.map(c => esc(c.company)
        + (c.designation ? ` <span class="muted">(${esc(c.designation)})</span>` : "")).join("<br>")}</td>
    </tr>`).join("");
}

/* ── 10 · Rising vendors ──────────────────────────────────────────── */

function renderGrowth(growth) {
  if (!growth) {
    document.getElementById("fgrowth").style.display = "none";
    return;
  }
  const ratioFmt = v => `${v.toFixed(v >= 10 ? 0 : 1)}×`;
  const ownerNameByKey = new Map(growth.owner_group_growth.map(o => [o.owner_key, o.owner_name]));
  const m = growth.meta;
  const baseYears = m.baseline_years.length, recYears = m.recent_years.length;

  document.getElementById("growersBody").innerHTML = growth.top_growers.slice(0, 15).map(g => {
    const owners = g.shared_owner_keys.map(k => ownerNameByKey.get(k)).filter(Boolean);
    return `<tr>
      <td class="strong">${esc(g.company)}</td>
      <td class="n muted">${taka(g.baseline_value_bdt / baseYears)}</td>
      <td class="n">${taka(g.recent_value_bdt / recYears)}</td>
      <td class="n hi">${ratioFmt(g.growth_ratio_value)}</td>
      <td class="muted">${owners.length ? esc(owners.join(", ")) : "—"}</td>
    </tr>`;
  }).join("");

  document.getElementById("dominantsLede").textContent =
    `Zero contracts in 2016-2019, first appearance no earlier than ${m.new_dominant_first_year_floor}, `
    + `at least ${taka(m.new_dominant_min_recent_value_bdt)} awarded since. ${int(growth.new_dominants.length)} qualify.`;
  document.getElementById("dominantsBody").innerHTML = growth.new_dominants.slice(0, 15).map(g => {
    const conc = g.recent_top_office_share
      ? `<span class="mini"><span class="mini-track"><span class="mini-fill" style="width:${g.recent_top_office_share * 100}%"></span></span>${pct(g.recent_top_office_share)}</span>`
      : "—";
    return `<tr>
      <td class="strong">${esc(g.company)}</td>
      <td class="n muted">${esc(g.first_year)}</td>
      <td class="n">${taka(g.recent_value_bdt)}</td>
      <td class="n">${int(g.recent_count)}</td>
      <td>${conc}<div class="muted" style="font-size:0.76em">${esc(g.recent_top_office || "")}</div></td>
    </tr>`;
  }).join("");

  document.getElementById("ownerGrowthLede").textContent =
    `Beneficial owners (from the ${int(m.ownership_groups_checked)} multi-company owner names already `
    + `identified in Suppliers, above) whose companies' combined activity is summed rather than read `
    + `one at a time. ${int(growth.owner_group_growth.length)} owners have 2+ of their companies active `
    + `in this data.`;
  document.getElementById("ownerGrowthBody").innerHTML = growth.owner_group_growth.slice(0, 15).map(o => `
    <tr>
      <td class="strong">${esc(o.owner_name)}</td>
      <td class="muted">${o.companies.map(c => esc(c.company)).join(", ")}</td>
      <td class="n">${taka(o.combined_recent_value_bdt)}</td>
      <td class="n hi">${o.combined_growth_ratio_value ? ratioFmt(o.combined_growth_ratio_value) : "new"}</td>
    </tr>`).join("");

  const topGrower = growth.top_growers[0];
  const topOwner = growth.owner_group_growth[0];
  if (topGrower) {
    document.getElementById("growTopBaseline").textContent = taka(topGrower.baseline_value_bdt / baseYears);
    document.getElementById("growTopRecent").textContent = taka(topGrower.recent_value_bdt / recYears);
    document.getElementById("growTopRatio").textContent = ratioFmt(topGrower.growth_ratio_value);
  }
  if (topOwner) {
    document.getElementById("growOwnerCompanies").textContent = int(topOwner.member_companies_matched);
    document.getElementById("growOwnerValue").textContent = taka(topOwner.combined_recent_value_bdt);
  }
}

/* ── Political spending: does winning translate to money? ─────────── */

const POL_TREATMENT_LABEL = {
  bnp_won: "Seat majority (binary)", bnp_vote_share: "District vote share (continuous)",
  bnp_seat_share: "District seat share (continuous)",
};

function renderPoliticalSpending(pol) {
  if (!pol) {
    document.getElementById("political").style.display = "none";
    return;
  }
  const anySignificant = ["bnp_won", "bnp_vote_share", "bnp_seat_share"].some(
    t => pol.main[t].p_value < 0.05 && pol.placebo[t].p_value >= 0.05);

  document.getElementById("polHeadline").textContent = anySignificant
    ? "A gap that survives its own placebo test — on at least one measure"
    : "No detectable effect, on any measure — real or placebo alike";

  // Grouped bars: main vs. placebo regression coefficient, one row per
  // treatment definition -- the whole point is that none of the six bars
  // stands out from zero more than any other.
  const rows = ["bnp_won", "bnp_vote_share", "bnp_seat_share"].flatMap(t => [
    [`${POL_TREATMENT_LABEL[t]} — real`, pol.main[t].coefficient, pol.main[t].p_value, false],
    [`${POL_TREATMENT_LABEL[t]} — placebo`, pol.placebo[t].coefficient, pol.placebo[t].p_value, true],
  ]);
  const max = Math.max(...rows.map(r => Math.abs(r[1])), 0.1);
  const W = 800, rowH = 34, padT = 10, padL = 300, padR = 70;
  const H = rows.length * rowH + padT * 2;
  const bh = rowH * 0.5;
  const pw = W - padL - padR;
  const zeroX = padL + pw / 2;
  let body = "";
  rows.forEach(([label, v, p, isPlacebo], i) => {
    const yy = padT + i * rowH + (rowH - bh) / 2;
    const w = (Math.abs(v) / max) * (pw / 2);
    const x = v >= 0 ? zeroX : zeroX - w;
    const sig = p < 0.05;
    body += `<text class="ax${isPlacebo ? "" : "-strong"}" x="${padL - 12}" y="${yy + bh / 2 + 4}" text-anchor="end">${esc(label)}</text>
             <rect x="${x}" y="${yy}" width="${Math.max(w, 1.5)}" height="${bh}" rx="2" fill="${sig ? "var(--s4)" : "var(--s1)"}" opacity="${isPlacebo ? 0.55 : 1}">
               <title>${esc(label)}: coefficient ${v}, p=${p}${sig ? " (significant)" : ""}</title></rect>
             <text class="val-label${sig ? " hi" : ""}" x="${v >= 0 ? x + w + 6 : x - 6}" y="${yy + bh / 2 + 4}" text-anchor="${v >= 0 ? "start" : "end"}" font-size="9">${v}${sig ? " *" : ""}</text>`;
  });
  body += `<line x1="${zeroX}" y1="${padT - 4}" x2="${zeroX}" y2="${H - padT + 4}" class="grid"/>`;
  document.getElementById("chartPolDid").innerHTML = svg(W, H, body);
  document.getElementById("capPolDid").textContent =
    "Regression coefficient (asinh scale) for each treatment definition, real test and placebo side by side. "
    + "* marks p<0.05. Bars near zero on both sides, for all three ways of defining \"won\", is what a genuine null looks like — "
    + "not one bar that happens to be small.";

  document.getElementById("polRegBody").innerHTML = ["bnp_won", "bnp_vote_share", "bnp_seat_share"].flatMap(t => [
    [`${POL_TREATMENT_LABEL[t]} — real (interim → elected)`, pol.main[t]],
    [`${POL_TREATMENT_LABEL[t]} — placebo (within interim)`, pol.placebo[t]],
  ]).map(([label, reg]) => `
    <tr>
      <td class="strong">${esc(label)}</td>
      <td class="n">${reg.coefficient}</td>
      <td class="n${reg.p_value < 0.05 ? " hi" : ""}">${reg.p_value}</td>
    </tr>`).join("");

  document.getElementById("polSimpleDidNote").textContent =
    `For reference, the plain group-means version (binary treatment, no fixed effects, easy to verify by hand): `
    + `real transition ${taka(pol.main_simple.did_bdt_per_voter)}/voter, placebo ${taka(pol.placebo_simple.did_bdt_per_voter)}/voter.`;

  document.getElementById("polScatterLede").textContent =
    "Each of the 64 matched districts: BNP-led alliance's share of the district's vote (x) against "
    + "how its per-voter e-GP spending changed from the interim government to the elected government (y). "
    + "If winning paid off, BNP strongholds (right side) should sit above the line more than BNP-weak districts (left side).";

  const scatter = pol.district_scatter;
  const W2 = 800, H2 = 320, pL = 50, pR = 20, pT = 16, pB = 34;
  const pw2 = W2 - pL - pR, ph2 = H2 - pT - pB;
  const changes = scatter.map(d => d.elected_value_per_voter_bdt - d.interim_value_per_voter_bdt);
  const yMax = Math.max(...changes.map(Math.abs), 1) * 1.08;
  const xOf = v => pL + v * pw2;
  const yOf = v => pT + ph2 / 2 - (v / yMax) * (ph2 / 2);
  let body2 = "";
  body2 += `<line x1="${pL}" y1="${yOf(0)}" x2="${W2 - pR}" y2="${yOf(0)}" class="grid"/>`;
  for (let gx = 0; gx <= 1; gx += 0.25) {
    body2 += `<text class="ax" x="${xOf(gx)}" y="${H2 - 16}" text-anchor="middle">${pct(gx)}</text>`;
  }
  body2 += `<text class="ax" x="${pL + pw2 / 2}" y="${H2 - 2}" text-anchor="middle">BNP-led alliance vote share</text>`;
  scatter.forEach((d, i) => {
    const x = xOf(d.bnp_vote_share);
    const y = yOf(changes[i]);
    const color = d.bnp_won ? "var(--s1)" : "var(--s4)";
    body2 += `<circle cx="${x}" cy="${y}" r="4" fill="${color}" fill-opacity="0.75">
      <title>${esc(d.district)}: ${pct(d.bnp_vote_share, 1)} BNP vote share, ${d.bnp_won ? "won" : "did not win"} the district; `
      + `per-voter spending ${changes[i] >= 0 ? "up" : "down"} ${taka(Math.abs(changes[i]))} from interim to elected</title></circle>`;
  });
  document.getElementById("chartPolScatter").innerHTML = svg(W2, H2, body2);
  document.getElementById("legendPolScatter").innerHTML =
    legend([["var(--s1)", "won the district"], ["var(--s4)", "did not win the district"]]);
  document.getElementById("capPolScatter").textContent =
    "Blue = district elected a BNP-led-alliance seat majority; amber = it didn't. No visible upward slope on "
    + "the blue points relative to the amber ones is exactly what the regression's non-significant interaction term says numerically.";

  const nInterim = pol.meta.interim_months.length, nElected = pol.meta.elected_months.length;
  document.getElementById("polMethodText").innerHTML =
    `<strong>Design:</strong> panel difference-in-differences, two-way fixed effects (64 districts × month), `
    + `outcome asinh(contract value ÷ registered voters), standard errors clustered by district `
    + `(t-distribution, ${pol.main.bnp_won.df} degrees of freedom). <strong>Real test:</strong> ${nInterim} `
    + `interim-government months (${pol.meta.interim_months[0]} to ${pol.meta.interim_months[nInterim - 1]}) as `
    + `pre-period, ${nElected} elected-government months as post. <strong>Placebo:</strong> the identical `
    + `districts and treatment values, but the interim government's own span split at its midpoint `
    + `(${pol.meta.placebo_split_month}) — the second half stands in for "post", and no election happened `
    + `anywhere in this window. Confined to interim-onward deliberately: e-GP use was hybrid before the interim `
    + `government made it obligatory (and the platform didn't support every tender type earlier), so national `
    + `contract counts climb roughly 6x from 2015 to 2023 purely from more of the same government activity `
    + `being captured by this data source — comparing that expansion era against anything recent would confuse `
    + `coverage growth with a spending effect. All three treatment definitions (seat-majority binary, district `
    + `vote share, district seat share) are tested on both panels, not just whichever looks best.<br><br>`
    + `<strong>An earlier version of this test got this wrong</strong> and used 2015-2025 as a single pre-period `
    + `for both the real and placebo tests. That version's placebo (Tk 1,130/voter, and p=0.043 on the continuous `
    + `vote-share specification) was <em>larger</em> than its real result (Tk 225/voter, p=0.063) — which looked `
    + `like it already invalidated the hypothesis, but for the wrong reason: both numbers were picking up e-GP's `
    + `own coverage expansion, not anything about districts or elections. Confining the panel to the stable-coverage `
    + `period fixes that, and the result changes again: all six estimates above are small and none clears `
    + `significance on both sides of its own placebo, which is a cleaner null than the flawed version produced. `
    + `<strong>Source:</strong> election results from `
    + `<a href="https://interactive.netra.news/bangladesh-election-2026-map/" target="_blank" rel="noopener">netra.news's interactive results map</a> `
    + `(Nazmul Ahasan &amp; Aaqib Md. Shatil), vote counts from Election Commission publications, union boundaries `
    + `from geoBoundaries (CC-BY 4.0) — the one non-eprocure.gov.bd source in this whole pipeline. Full results down `
    + `to union level (5,034 of them) are in <code>data/election_2026_unions.json</code> in the repository; three `
    + `constituencies (of 300) were suspended for candidate death or court dispute and aren't in the results at all.`;
}

/* ── 07 · Debarment enforcement ───────────────────────────────────── */

function chartDebar(flags) {
  const active = flags.flags.filter(f => f.flag_type === "active_debarment_violation");
  const byYear = {};
  for (const f of active) {
    const y = (f.contract_signing_date || "").slice(0, 4);
    if (y) byYear[y] = (byYear[y] || 0) + 1;
  }
  const years = Object.keys(byYear).sort();
  const max = Math.max(...years.map(y => byYear[y]), 1);
  const W = 800, H = 200, padL = 34, padR = 10, padT = 24, padB = 30;
  const pw = W - padL - padR, ph = H - padT - padB;
  const step = pw / years.length, bw = step * 0.6;

  let body = "";
  years.forEach((y, i) => {
    const n = byYear[y];
    const h = (n / max) * ph;
    const x = padL + i * step + (step - bw) / 2;
    const yy = padT + ph - h;
    body += `<rect x="${x}" y="${yy}" width="${bw}" height="${h}" rx="3" fill="var(--critical)">
               <title>${y}: ${n} contracts signed during an active ban</title></rect>
             <text class="val-label" x="${x + bw / 2}" y="${yy - 7}" text-anchor="middle">${n}</text>
             <text class="ax" x="${x + bw / 2}" y="${H - 10}" text-anchor="middle">${y}</text>`;
  });
  document.getElementById("chartDebar").innerHTML = svg(W, H, body);
  document.getElementById("capDebar").textContent =
    "Contracts signed while the winning company was under an active debarment, by year of signing.";

  document.getElementById("flagCount").textContent = int(active.length);
  document.getElementById("flagValue").textContent = taka(flags.meta.value_at_risk_bdt_active_violations);
  document.getElementById("flagFirms").textContent = int(new Set(active.map(f => f.company_key)).size);
}

function setupFlagsTable(flags) {
  const st = { q: "", type: "active_debarment_violation", shown: 15 };
  const body = document.getElementById("flagsBody");
  const more = document.getElementById("flagsMore");

  const rows = () => flags.flags.filter(f => {
    if (f.flag_type !== st.type) return false;
    if (!st.q) return true;
    const q = st.q.toLowerCase();
    return f.company.toLowerCase().includes(q)
      || (f.procuring_entity || "").toLowerCase().includes(q);
  });

  function render() {
    const rs = rows();
    body.innerHTML = rs.slice(0, st.shown).map(f => `
      <tr>
        <td class="strong">${esc(f.company)}</td>
        <td class="muted">${esc(f.district) || "—"}</td>
        <td class="muted">${esc(f.procuring_entity) || "—"}</td>
        <td class="n">${esc(f.contract_signing_date) || "—"}</td>
        <td class="n">${taka(f.value_bdt)}</td>
        <td class="n muted">${f.debar_start ? `${esc(f.debar_start)} → ${esc(f.debar_end)}` : "—"}</td>
        <td class="muted">${esc((f.debarment_reason || "—").slice(0, 90))}</td>
      </tr>`).join("")
      || `<tr><td colspan="7" style="text-align:center;padding:26px" class="muted">Nothing matches that filter.</td></tr>`;
    more.hidden = st.shown >= rs.length;
    more.textContent = `Show more (${rs.length - st.shown} remaining)`;
  }
  document.getElementById("flagSearch").addEventListener("input", e => {
    st.q = e.target.value.trim(); st.shown = 15; render();
  });
  document.getElementById("flagType").addEventListener("change", e => {
    st.type = e.target.value; st.shown = 15; render();
  });
  more.addEventListener("click", () => { st.shown += 25; render(); });
  render();
}

/* ── 11 · Topic mix (CPV category) ────────────────────────────────── */

function chartTopics(cpv) {
  const state = { metric: "count" };

  function render() {
    const byMetric = cpv.top_categories.slice().sort((a, b) => b[state.metric] - a[state.metric]);
    const rows = byMetric.slice(0, 15);
    const max = Math.max(...rows.map(r => r[state.metric]));
    const W = 800, H = 400, padL = 300, padR = 175, padT = 6;
    const rowH = (H - padT) / rows.length, bh = rowH * 0.6;
    const pw = W - padL - padR;

    let body = "";
    rows.forEach((r, i) => {
      const yy = padT + i * rowH + (rowH - bh) / 2;
      const v = r[state.metric];
      const w = Math.max((v / max) * pw, 2);
      const shareOfAll = state.metric === "count" ? r.count / cpv.meta.all_tenders : null;
      const label = state.metric === "count"
        ? `${int(v)} <tspan class="muted">· ${pct(shareOfAll, 1)}</tspan>`
        : `${taka(v)} <tspan class="muted">· ${pct(r.awarded_match_rate, 0)} awarded</tspan>`;
      const title = state.metric === "count"
        ? `${esc(r.name)}: ${int(v)} tenders (${pct(shareOfAll, 1)} of all tenders)`
        : `${esc(r.name)}: ${taka(v)} awarded so far, across ${int(r.awarded_matched)} of ${int(r.count)} tenders in this category`;
      body += `<text class="ax" x="${padL - 12}" y="${yy + bh / 2 + 4}" text-anchor="end">${esc(r.name.slice(0, 46))}</text>
               <rect x="${padL}" y="${yy}" width="${w}" height="${bh}" rx="3" fill="var(--s1)" opacity="${i === 0 ? 1 : 0.55}">
                 <title>${title}</title></rect>
               <text class="val-label${i === 0 ? " hi" : ""}" x="${padL + w + 9}" y="${yy + bh / 2 + 4}">${label}</text>`;
    });
    document.getElementById("chartTopics").innerHTML = svg(W, H, body);
    document.getElementById("capTopics").textContent = state.metric === "count"
      ? `Top 15 of ${int(cpv.meta.categories_tracked)} top-level CPV categories, by tender count, out of `
        + `${int(cpv.meta.all_tenders)} tenders overall. Shares are of all tenders, not of each other — `
        + `a tender can carry more than one category.`
      : `The same top-25-by-count categories, ranked instead by awarded contract value (joined by `
        + `tender ID against the contract list). A category's tenders that are still live, cancelled, `
        + `or otherwise unawarded contribute nothing here — see each bar's "% awarded" on hover.`;

    const top = byMetric[0];
    const ict = cpv.top_categories.find(c => c.name === "Computer and related services");
    if (state.metric === "count") {
      document.getElementById("topicTop").textContent = pct(top.count / cpv.meta.all_tenders, 1);
      document.getElementById("topicIct").textContent = ict
        ? `just ${pct(ict.count / cpv.meta.all_tenders, 1)}` : "not in the top 25";
    } else {
      document.getElementById("topicTop").textContent = taka(top.value_bdt);
      document.getElementById("topicIct").textContent = ict ? `just ${taka(ict.value_bdt)}` : "not in the top 25";
    }
  }

  document.querySelectorAll("#topicMetricGroup .map-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#topicMetricGroup .map-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.metric = btn.dataset.metric;
      render();
    });
  });

  render();
}

const ERA_SHORT = {
  "Awami League (2009–2024)": "Awami", "Interim Government (2024–2026)": "Interim",
  "Elected Government (2026–)": "Elected",
};
const ERA_COLOR = { "Awami League (2009–2024)": "var(--s1)", "Interim Government (2024–2026)": "var(--s4)",
  "Elected Government (2026–)": "var(--s2)" };

function chartTopicsEra(cpv) {
  const eras = Object.keys(cpv.meta.all_tenders_by_era);
  if (!eras.length) { document.getElementById("chartTopicsEra").parentElement.parentElement.style.display = "none"; return; }
  // Share of era total, not raw count -- eras have very different volumes,
  // so only a share is comparable across them.
  const picks = ["Construction work", "Repair, maintenance and installation services",
    "Office and computing machinery, equipment and supplies", "Medical and laboratory devices, optical and precision devices, watches and clocks, pharmaceuticals and related medical consumables",
    "Food products and beverages", "Computer and related services"];
  const rows = picks.map(name => cpv.top_categories.find(c => c.name === name)).filter(Boolean);

  const W = 800, padL = 300, padR = 40, padT = 6;
  const pw = W - padL - padR;
  // Each group: a label row, then the three era bars stacked underneath --
  // fixed, non-overlapping bands, not centred text that can drift into a bar.
  const barH = 12, gap = 3, labelBand = 20;
  const groupH = labelBand + eras.length * (barH + gap);
  const H = rows.length * groupH + 10;
  const max = Math.max(...rows.flatMap(r => eras.map(e => (r.by_era[e] || 0) / cpv.meta.all_tenders_by_era[e])));

  let body = "";
  rows.forEach((r, i) => {
    const gy = padT + i * groupH;
    body += `<text class="ax-strong" x="${padL - 12}" y="${gy + 11}" text-anchor="end">${esc(r.name.slice(0, 42))}</text>`;
    eras.forEach((e, j) => {
      const share = (r.by_era[e] || 0) / cpv.meta.all_tenders_by_era[e];
      const w = Math.max((share / max) * pw, 2);
      const yy = gy + labelBand + j * (barH + gap);
      body += `<rect x="${padL}" y="${yy}" width="${w}" height="${barH}" rx="2" fill="${ERA_COLOR[e]}">
                 <title>${esc(r.name)} — ${ERA_SHORT[e]}: ${pct(share, 1)} of that era's tenders</title></rect>
               <text class="val-label" x="${padL + w + 8}" y="${yy + barH / 2 + 3.5}" font-size="9">${pct(share, 1)}</text>`;
    });
  });
  document.getElementById("legendTopicsEra").innerHTML = legend(eras.map(e => [ERA_COLOR[e], ERA_SHORT[e]]));
  document.getElementById("chartTopicsEra").innerHTML = svg(W, H, body);
  document.getElementById("capTopicsEra").textContent =
    "Share of each era's own tenders (not raw counts, so the very different era lengths don't distort the comparison), for a representative handful of categories.";

  const constr = rows[0];
  const shares = eras.map(e => pct((constr.by_era[e] || 0) / cpv.meta.all_tenders_by_era[e], 1)).join(" → ");
  document.getElementById("topicEraLede").textContent =
    `Construction's share of all tenders runs ${shares} across the three eras, in order — while `
    + `categories like computing equipment and food products roughly double or more their share `
    + `over the same span. Not a claim about which is better: a shrinking construction share and a `
    + `growing services share is also what "the same total pie, more spent on non-construction lines" `
    + `looks like.`;
}

/* ── Geography ─────────────────────────────────────────────────────── */

const MAP_BUCKETS = 6;
// One hue (blue), stepped in both lightness and saturation -- opacity alone
// against a dark surface compresses too much in the middle of the range to
// read as a spectrum, so this steps real HSL lightness/saturation instead.
function bucketColor(i) {
  const l = 20 + i * (46 / (MAP_BUCKETS - 1));
  const s = 40 + i * (48 / (MAP_BUCKETS - 1));
  return `hsl(212, ${s.toFixed(0)}%, ${l.toFixed(0)}%)`;
}

function sparklineSvg(series, w, h, color) {
  if (series.length < 2) return "";
  const max = Math.max(...series, 1);
  const pts = series.map((v, i) => {
    const x = (i / (series.length - 1)) * (w - 2) + 1;
    const y = h - 1 - (v / max) * (h - 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <polyline points="${pts.join(" ")}" fill="none" stroke="${color}" stroke-width="1.5"
      stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}

function chartMap(geo, districtGeo) {
  const state = { metric: "value_bdt", era: "all", trendYears: 5 };

  function districtStat(dispName) {
    const d = geo.districts[dispName];
    if (!d) return null;
    return state.era === "all" ? d : d.by_era[state.era];
  }

  function trendSeries(dispName) {
    const d = geo.districts[dispName];
    if (!d) return { years: [], values: [] };
    let years = Object.keys(d.by_year).sort();
    if (state.trendYears > 0) years = years.slice(-state.trendYears);
    return { years, values: years.map(y => d.by_year[y][state.metric] || 0) };
  }

  function render() {
    const entries = Object.keys(districtGeo.paths).map(pathKey => {
      const dispName = districtGeo.canonical_display[pathKey] || pathKey;
      const stat = districtStat(dispName);
      return { pathKey, dispName, stat, value: stat ? stat[state.metric] : 0 };
    });

    // Rank-based (quantile) buckets, not value-range buckets: Dhaka is such
    // an outlier by value that a value-range split would cram nearly every
    // other district into one bucket. Ranking spreads color across the
    // whole map regardless of how skewed the underlying values are.
    const ranked = entries.filter(e => e.value > 0).sort((a, b) => a.value - b.value);
    const bucketOf = new Map();
    ranked.forEach((e, i) => bucketOf.set(e.pathKey, Math.min(Math.floor((i / ranked.length) * MAP_BUCKETS), MAP_BUCKETS - 1)));

    let body = "";
    for (const e of entries) {
      const bucket = bucketOf.has(e.pathKey) ? bucketOf.get(e.pathKey) : -1;
      const fill = bucket === -1 ? "var(--surface-2)" : bucketColor(bucket);
      const label = state.metric === "value_bdt" ? taka(e.value) : `${int(e.value)} contracts`;
      const extra = e.stat && e.stat.top_ministry ? ` · mostly ${e.stat.top_ministry.replace(/^Ministry of /, "")}` : "";
      body += `<path class="district" d="${districtGeo.paths[e.pathKey]}" fill="${fill}" data-name="${esc(e.dispName)}">
        <title>${esc(e.dispName)}: ${label}${extra}</title></path>`;
    }
    document.getElementById("chartMap").innerHTML =
      `<svg viewBox="${districtGeo.view_box}" role="img" xmlns="http://www.w3.org/2000/svg">${body}</svg>`;

    // Legend shows the actual value range each bucket covers, not just a
    // vague "less/more" -- a reader should be able to look up a shade.
    const buckets = Array.from({ length: MAP_BUCKETS }, () => []);
    ranked.forEach(e => buckets[bucketOf.get(e.pathKey)].push(e.value));
    let legendHtml = "";
    buckets.forEach((vals, i) => {
      if (!vals.length) return;
      const lo = vals[0], hi = vals[vals.length - 1];
      const fmt = state.metric === "value_bdt" ? taka : int;
      legendHtml += `<span><i class="swatch" style="background:${bucketColor(i)}"></i>${fmt(lo)}${hi > lo ? `–${fmt(hi)}` : ""}</span>`;
    });
    document.getElementById("mapLegend").innerHTML = legendHtml;

    const top = entries.filter(e => e.value > 0).sort((a, b) => b.value - a.value).slice(0, 15);
    document.getElementById("mapTableBody").innerHTML = top.map(e => {
      const { values } = trendSeries(e.dispName);
      const color = bucketColor(bucketOf.get(e.pathKey));
      const first = values[0], last = values[values.length - 1];
      const change = first > 0 ? (last - first) / first : null;
      const dir = change == null ? "flat" : change > 0.03 ? "up" : change < -0.03 ? "down" : "flat";
      const arrow = dir === "up" ? "▲" : dir === "down" ? "▼" : "→";
      const pctText = change == null ? "new" : pct(Math.abs(change), 0);
      return `
      <tr class="dist-row" data-name="${esc(e.dispName)}" style="cursor:pointer">
        <td class="strong">${esc(e.dispName)}</td>
        <td class="n">${taka(e.stat.value_bdt)}</td>
        <td class="n">${int(e.stat.count)}</td>
        <td><div class="trend-cell">${sparklineSvg(values, 56, 20, color)}
          <span class="trend-pct ${dir}">${arrow} ${pctText}</span></div></td></tr>`;
    }).join("");

    const eraLabel = state.era === "all" ? "all years, 2011–2026" : state.era;
    const windowLabel = state.trendYears > 0 ? `last ${state.trendYears} years` : "full history";
    document.getElementById("mapCaption").textContent =
      `Shaded by ${state.metric === "value_bdt" ? "total contract value" : "contract count"} `
      + `— ${eraLabel}, into ${MAP_BUCKETS} equal-sized rank groups (so the map reads as a spectrum `
      + `regardless of Dhaka's outlier size). Trend column: ${windowLabel}, first-to-last change. `
      + `${int(geo.meta.districts_mapped)} districts matched from ${int(geo.meta.contracts_scanned)} contracts nationally.`;

    if (selected) selectDistrict(selected);
  }

  const NATURE_COLOR = { "Works": "var(--s1)", "Goods": "var(--s2)", "Services": "var(--s3)" };
  function natureColor(name) { return NATURE_COLOR[name] || "var(--s4)"; }

  let selected = null;

  function selectDistrict(dispName) {
    const d = geo.districts[dispName];
    if (!d) return;
    selected = dispName;

    document.getElementById("ddName").textContent = dispName;
    document.getElementById("ddStats").innerHTML =
      `${taka(d.value_bdt)} across ${int(d.count)} contracts, all-time. `
      + `Top ministry: <strong>${esc((d.top_ministry || "—").replace(/^Ministry of /, ""))}</strong>. `
      + `Top vendor: <strong>${esc(d.top_vendor || "—")}</strong>.`;

    const natureEntries = Object.entries(d.nature_count).sort((a, b) => b[1] - a[1]);
    const natureTotal = natureEntries.reduce((s, [, n]) => s + n, 0);
    if (natureTotal) {
      const maxN = Math.max(...natureEntries.map(([, n]) => n));
      const NW = 320, rowH = 26, NH = natureEntries.length * rowH + 4, padL = 100, padR = 44;
      const npw = NW - padL - padR;
      let nbody = "";
      natureEntries.forEach(([name, n], i) => {
        const yy = i * rowH + 4, bh = rowH * 0.55;
        const w = Math.max((n / maxN) * npw, 2);
        nbody += `<text class="ax" x="${padL - 10}" y="${yy + bh / 2 + 4}" text-anchor="end">${esc(name.replace(" (Framework Agreement)", " (FA)"))}</text>
          <rect x="${padL}" y="${yy}" width="${w}" height="${bh}" rx="3" fill="${natureColor(name)}">
            <title>${esc(name)}: ${int(n)} contracts (${pct(n / natureTotal, 1)})</title></rect>
          <text class="val-label" x="${padL + w + 8}" y="${yy + bh / 2 + 4}">${pct(n / natureTotal, 0)}</text>`;
      });
      document.getElementById("chartDdNature").innerHTML = svg(NW, NH, nbody);
    } else {
      document.getElementById("chartDdNature").innerHTML = `<p class="sub" style="font-size:0.8rem">No matched nature data for this district.</p>`;
    }

    const { years, values } = trendSeries(dispName);
    if (years.length >= 2) {
      const TW = 400, TH = 130, tpL = 8, tpR = 8, tpT = 8, tpB = 20;
      const tpw = TW - tpL - tpR, tph = TH - tpT - tpB;
      const maxV = Math.max(...values, 1);
      const pts = values.map((v, i) => [tpL + (i / (values.length - 1)) * tpw, tpT + tph - (v / maxV) * tph]);
      let tbody = `<polyline fill="none" stroke="var(--s1)" stroke-width="2" stroke-linejoin="round"
        points="${pts.map(p => p.join(",")).join(" ")}"/>`;
      pts.forEach(([x, y], i) => {
        tbody += `<circle cx="${x}" cy="${y}" r="2.5" fill="var(--s1)">
          <title>${years[i]}: ${state.metric === "value_bdt" ? taka(values[i]) : int(values[i]) + " contracts"}</title></circle>`;
        if (i === 0 || i === pts.length - 1 || years.length <= 8) {
          const anchor = i === 0 ? "start" : i === pts.length - 1 ? "end" : "middle";
          tbody += `<text class="ax" x="${x}" y="${TH - 5}" text-anchor="${anchor}">${years[i]}</text>`;
        }
      });
      document.getElementById("chartDdTrend").innerHTML = svg(TW, TH, tbody);
    } else {
      document.getElementById("chartDdTrend").innerHTML = `<p class="sub" style="font-size:0.8rem">Not enough years in this window.</p>`;
    }

    document.getElementById("ddCaption").textContent =
      `Sector mix is joined from the master tender list (${pct(geo.meta.nature_match_rate, 0)} of contracts nationally match); `
      + `read shares as based on the matched subset. Trend follows the "Trend window" control above.`;

    const panel = document.getElementById("districtDetail");
    panel.hidden = false;
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  document.getElementById("chartMap").addEventListener("click", (ev) => {
    const path = ev.target.closest(".district");
    if (path) selectDistrict(path.dataset.name);
  });
  document.getElementById("mapTableBody").addEventListener("click", (ev) => {
    const row = ev.target.closest(".dist-row");
    if (row) selectDistrict(row.dataset.name);
  });
  document.getElementById("ddClose").addEventListener("click", () => {
    document.getElementById("districtDetail").hidden = true;
    selected = null;
  });

  document.querySelectorAll("#mapMetricGroup .map-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#mapMetricGroup .map-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.metric = btn.dataset.metric;
      render();
    });
  });
  document.querySelectorAll("#mapEraGroup .map-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#mapEraGroup .map-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.era = btn.dataset.era;
      render();
    });
  });
  document.querySelectorAll("#mapTrendGroup .map-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#mapTrendGroup .map-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.trendYears = Number(btn.dataset.years);
      render();
    });
  });

  render();
}

/* ── Three governments ────────────────────────────────────────────── */

function eraRow(label, hint, values, fmt, barBasis) {
  const max = Math.max(...barBasis, 0.0001);
  const cells = values.map((v, i) => {
    const w = Math.max((barBasis[i] / max) * 100, v == null ? 0 : 2);
    return `<td class="n"><div class="era-bar-cell">
      <div class="era-bar-track"><div class="era-bar-fill" style="width:${w}%"></div></div>
      <span>${v == null ? "—" : fmt(v)}</span>
    </div></td>`;
  }).join("");
  return `<tr><td class="strong">${esc(label)}${hint ? `<div class="muted" style="font-size:0.76em;font-weight:400;margin-top:2px">${esc(hint)}</div>` : ""}</td>${cells}</tr>`;
}

function renderEraComparison(analysis, pva, ceiling, flags) {
  const eras = Object.keys(analysis.by_era);
  const a = eras.map(e => analysis.by_era[e]);
  document.getElementById("eraIntro").textContent =
    `Same pipeline, same definitions, sliced at the two transition dates. ${int(a.reduce((s, x) => s + x.count, 0))} `
    + `contracts fall into one of the three windows below.`;

  const rows = [];
  rows.push(eraRow("Contracts per day", "pace of signing, not total volume",
    a.map(x => x.contracts_per_day), v => v.toFixed(0), a.map(x => x.contracts_per_day)));
  rows.push(eraRow("Spend per day", null,
    a.map(x => x.value_bdt_per_day), v => taka(v), a.map(x => x.value_bdt_per_day)));
  rows.push(eraRow("Open tendering (OTM) share", "of contract value",
    a.map(x => x.otm_share), v => pct(v, 1), a.map(x => x.otm_share)));
  rows.push(eraRow("Limited tendering (LTM) share", "of contract value",
    a.map(x => x.ltm_share), v => pct(v, 1), a.map(x => x.ltm_share)));

  if (pva) {
    const eraMap = Object.fromEntries(pva.cost_structure.by_era.map(e => [e.era, e]));
    const get = (e, k) => eraMap[e] ? eraMap[e][k] : null;
    rows.push(eraRow("Awards at ~10% below estimate", "the discount-convention finding, Finding 03",
      eras.map(e => get(e, "share_at_10pct_below")), v => pct(v, 1),
      eras.map(e => get(e, "share_at_10pct_below") || 0)));
    rows.push(eraRow("Awards >115% over estimate", null,
      eras.map(e => get(e, "share_above_115")), v => pct(v, 2),
      eras.map(e => get(e, "share_above_115") || 0)));
  }

  if (flags) {
    const eraMap = Object.fromEntries(flags.meta.active_violations_by_era.map(e => [e.era, e]));
    rows.push(eraRow("Debarment violations", "contracts signed during an active ban",
      eras.map(e => eraMap[e] ? eraMap[e].count : 0), v => int(v),
      eras.map(e => eraMap[e] ? eraMap[e].count : 0)));
  }

  if (ceiling) {
    const eraMap = Object.fromEntries(ceiling.bunching.by_era.map(e => [e.era, e]));
    rows.push(eraRow("৳50cr ceiling: split-pattern clusters", "small sample per era — see Finding 05",
      eras.map(e => ceiling.split_clusters_by_era[e] ?? 0), v => int(v),
      eras.map(e => ceiling.split_clusters_by_era[e] ?? 0)));
  }

  document.getElementById("eraBody").innerHTML = rows.join("");
  document.getElementById("eraNote").textContent =
    `Observed span: Awami League ${int(a[0].observed_span_days)} days, Interim ${int(a[1].observed_span_days)} `
    + `days, Elected ${int(a[2].observed_span_days)} days (of data seen so far) — "per day" figures divide by `
    + `these, not by the nominal calendar length, so a government still accumulating its first weeks of data `
    + `isn't compared against a full year.`;
}

/* ── Masthead + methodology text ──────────────────────────────────── */

function renderHeader(a, summary, debar, insights) {
  document.getElementById("scaleRow").innerHTML = [
    [taka(a.meta.total_value_bdt), "awarded since 2011"],
    [int(a.meta.contracts), "contracts"],
    [int(insights.meta.distinct_vendors), "suppliers"],
    [int(debar.meta.record_count), "debarment records"],
  ].map(([v, k]) => `<div class="scale-item"><div class="v num">${v}</div><div class="k">${k}</div></div>`).join("");

  document.getElementById("updated").textContent =
    `Rebuilt from eprocure.gov.bd on ${summary.meta.generated_at.slice(0, 10)}. `
    + `Covers ${a.meta.years[0]}–${a.meta.years[a.meta.years.length - 1]}.`;

  document.getElementById("coverageText").innerHTML =
    `Awarded contracts (${int(summary.meta.record_count)}), the master tender list, the debarment `
    + `register (${int(debar.meta.record_count)}), eExperience work records, Annual Procurement `
    + `Plans (both office-level and itemised), and the CPV category tree — all re-crawled daily `
    + `from <a href="https://www.eprocure.gov.bd/" target="_blank" rel="noopener">eprocure.gov.bd</a>. `
    + `District geometry for the map is the one static asset, from a separate open-data source — `
    + `see Methodology. Registration is not used: the portal publishes only aggregate counts there, `
    + `with no per-record identifier. Everything here is rebuilt by a scheduled job; the pipeline `
    + `and the raw archive are in the repository.`;
}

/* ── Boot ─────────────────────────────────────────────────────────── */

async function main() {
  try {
    const [a, insights, profiles, flags, debar, summary] = await Promise.all([
      loadJSON("data/analysis.json"),
      loadJSON("data/insights.json"),
      loadJSON("data/office_profiles.json"),
      loadJSON("data/flags.json"),
      loadJSON("data/debarments.json"),
      loadJSON("data/contracts/summary.json"),
    ]);
    const own = await loadJSON("data/ownership.json").catch(() => null);
    const pva = await loadJSON("data/plan_vs_actual.json").catch(() => null);
    const ceiling = await loadJSON("data/ceiling.json").catch(() => null);
    const cpv = await loadJSON("data/cpv_categories.json").catch(() => null);
    const geo = await loadJSON("data/geo.json").catch(() => null);
    const districtGeo = await loadJSON("data/bd_districts_geo.json").catch(() => null);
    const growth = await loadJSON("data/growth.json").catch(() => null);
    const politicalSpending = await loadJSON("data/political_spending.json").catch(() => null);

    renderHeader(a, summary, debar, insights);
    chartMonths(a);
    chartMethods(a);
    if (pva) { chartPlanVsActual(pva); chartCostStructure(pva); }
    else {
      document.getElementById("fplan").style.display = "none";
      document.getElementById("fcost").style.display = "none";
    }
    if (ceiling) chartCeiling(ceiling);
    else document.getElementById("fceiling").style.display = "none";
    chartConc(a);
    chartPrice(a);
    chartMinistries(insights, profiles, a);
    chartCross(profiles);
    renderOwnership(own);
    renderGrowth(growth);
    renderPoliticalSpending(politicalSpending);
    chartDebar(flags);
    setupFlagsTable(flags);
    if (cpv) { chartTopics(cpv); chartTopicsEra(cpv); }
    else document.getElementById("sectors").style.display = "none";
    if (geo && districtGeo) chartMap(geo, districtGeo);
    else document.getElementById("map").style.display = "none";
    renderEraComparison(a, pva, ceiling, flags);
  } catch (err) {
    document.getElementById("updated").textContent = `Could not load data: ${err.message}`;
    console.error(err);
  }
}
main();

/* Deep links (nav, the Overview teaser cards) point at <details> elements.
   Browsers scroll to the target but do not open it, which would land the
   reader on an apparently-blank card -- so open it for them. */
function openTargetCard() {
  const id = location.hash.slice(1);
  if (!id) return;
  const el = document.getElementById(id);
  if (el && el.tagName === "DETAILS") el.open = true;
}
window.addEventListener("hashchange", openTargetCard);
openTargetCard();

const expandBtn = document.getElementById("expandAllBtn");
if (expandBtn) {
  expandBtn.addEventListener("click", () => {
    const cards = document.querySelectorAll(".finding-card");
    const anyClosed = Array.from(cards).some(c => !c.open);
    cards.forEach(c => { c.open = anyClosed; });
    expandBtn.textContent = anyClosed ? "Collapse all" : "Expand all";
  });
}
