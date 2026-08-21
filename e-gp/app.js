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

/* ── 03 · Office concentration ────────────────────────────────────── */

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
  const W = 800, H = 330, padL = 96, padR = 128, padT = 8;
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
  const W = 800, H = 330, padL = 196, padR = 168, padT = 6;
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
    + `register (${int(debar.meta.record_count)}), eExperience work records and Annual Procurement `
    + `Plans — all re-crawled daily from `
    + `<a href="https://www.eprocure.gov.bd/" target="_blank" rel="noopener">eprocure.gov.bd</a>. `
    + `Registration is not used: the portal publishes only aggregate counts there, with no `
    + `per-record identifier. Everything here is rebuilt by a scheduled job; the pipeline and the `
    + `raw archive are in the repository.`;
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

    renderHeader(a, summary, debar, insights);
    chartMonths(a);
    chartMethods(a);
    chartConc(a);
    chartPrice(a);
    chartMinistries(insights, profiles, a);
    chartCross(profiles);
    renderOwnership(own);
    chartDebar(flags);
    setupFlagsTable(flags);
  } catch (err) {
    document.getElementById("updated").textContent = `Could not load data: ${err.message}`;
    console.error(err);
  }
}
main();
