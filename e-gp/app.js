const SEVERITY_ORDER = ["critical", "high", "medium", "low"];
const SEVERITY_LABEL = { critical: "Critical", high: "High", medium: "Medium", low: "Low" };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtInt(n) {
  return n == null ? "—" : n.toLocaleString("en-US");
}
function fmtBDT(n) {
  if (n == null) return "—";
  if (n >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(2)} L`;
  return n.toLocaleString("en-US");
}
function fmtBDTFull(n) {
  if (n == null) return "—";
  return `৳${(n / 1e7).toLocaleString("en-US", { maximumFractionDigits: 1 })} Cr`;
}
async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

/* ── Headline story cards ──────────────────────────────────────────── */

function headlineCard(number, sentence, tone) {
  const div = document.createElement("div");
  div.className = `headline-card${tone ? " tone-" + tone : ""}`;
  div.innerHTML = `
    <div class="headline-number${tone ? " tone-" + tone : ""}">${number}</div>
    <div class="headline-sentence">${sentence}</div>
  `;
  return div;
}

// OTM (Open Tendering Method) is the fully-open, competitive route. Everything else --
// LTM (Limited/invitation-only), RFQ variants, DPM (direct, no bidding at all), etc. --
// is some degree of less-than-fully-open. LTM alone is ~44% of contracts by count but
// only ~15% by value (used for smaller purchases); DPM itself is rare (<1%). The
// interesting, defensible headline is the value-weighted share that bypassed OTM.
function nonOpenTenderShare(insights) {
  let otm = 0, total = 0;
  for (const methods of Object.values(insights.procurement_method_by_year)) {
    for (const [method, s] of Object.entries(methods)) {
      total += s.value_bdt;
      if (method === "OTM") otm += s.value_bdt;
    }
  }
  return total ? 1 - otm / total : null;
}

function cancellationShare(funnel) {
  if (!funnel) return null;
  const closed = (funnel.by_status["Cancelled"] || 0) + (funnel.by_status["Rejected"] || 0);
  return closed / funnel.record_count;
}

function renderHeadlines(debarments, contractsSummary, flags, insights) {
  const grid = document.getElementById("headlineGrid");
  const activeViolations = flags.meta.by_type.active_debarment_violation || 0;
  const topVendor = insights.top_vendors_by_value[0];
  const nonOpenShare = nonOpenTenderShare(insights);
  const cancelShare = cancellationShare(insights.tender_funnel);

  grid.append(
    headlineCard(
      `৳${fmtBDT(Object.values(insights.national_by_year).reduce((s, y) => s + y.value_bdt, 0))} Cr`,
      `Total value of ${fmtInt(contractsSummary.meta.record_count)} government contracts signed since 2011, across every ministry.`,
    ),
    headlineCard(
      fmtInt(activeViolations),
      `Contracts worth ৳${fmtBDT(flags.meta.value_at_risk_bdt_active_violations)} were signed with a company <strong>while it was formally banned</strong> from government bidding, across ${new Set(flags.flags.filter(f => f.flag_type === "active_debarment_violation").map(f => f.company_key)).size} companies. See Debarment below.`,
      activeViolations > 0 ? "critical" : "good",
    ),
    topVendor && headlineCard(
      `৳${fmtBDT(topVendor.value_bdt)} Cr`,
      `${esc(topVendor.company)} is the single largest recipient in the dataset -- ${fmtInt(topVendor.count)} contracts across ${fmtInt(topVendor.distinct_procuring_entities)} different government offices.`,
    ),
    nonOpenShare != null && headlineCard(
      `${(nonOpenShare * 100).toFixed(0)}%`,
      `of contract value nationally bypassed fully open tendering (OTM) -- awarded instead through limited/invitation-only tendering, quotation, or direct methods.`,
    ),
    cancelShare != null && headlineCard(
      `${(cancelShare * 100).toFixed(0)}%`,
      `of tenders on the portal end up cancelled or rejected rather than awarded.`,
    ),
  );
}

/* ── Overview: year chart + ministry bars ─────────────────────────── */

function renderYearChart(insights) {
  const container = document.getElementById("yearChart");
  const years = Object.keys(insights.national_by_year).filter(y => y !== "unknown").sort();
  const values = years.map(y => insights.national_by_year[y].value_bdt);
  const max = Math.max(...values, 1);
  const W = 640, H = 220, padL = 60, padB = 24, padT = 12, padR = 12;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const x = i => padL + (i / (years.length - 1 || 1)) * plotW;
  const y = v => padT + plotH - (v / max) * plotH;

  const gridlines = [0, 0.25, 0.5, 0.75, 1].map(f => {
    const gy = padT + plotH - f * plotH;
    return `<line class="chart-gridline" x1="${padL}" y1="${gy}" x2="${W - padR}" y2="${gy}" />
            <text class="chart-axis-label" x="${padL - 6}" y="${gy + 3}" text-anchor="end">${fmtBDTFull(f * max)}</text>`;
  }).join("");

  const points = years.map((yr, i) => `${x(i)},${y(values[i])}`).join(" ");
  const dots = years.map((yr, i) => `
    <circle class="chart-dot" cx="${x(i)}" cy="${y(values[i])}" r="3">
      <title>${yr}: ${fmtBDTFull(values[i])} (${fmtInt(insights.national_by_year[yr].count)} contracts)</title>
    </circle>
    <text class="chart-axis-label" x="${x(i)}" y="${H - 6}" text-anchor="middle">${yr}</text>
  `).join("");

  container.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
      ${gridlines}
      <polyline class="chart-line" points="${points}" />
      ${dots}
    </svg>
  `;
}

function renderMinistryBars(insights) {
  const container = document.getElementById("ministryBars");
  const rows = insights.top_ministries_by_value.slice(0, 10);
  const max = Math.max(...rows.map(r => r.value_bdt), 1);
  for (const r of rows) {
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <span class="bar-label" title="${esc(r.ministry)}">${esc(r.ministry)}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${(100 * r.value_bdt / max).toFixed(1)}%"></span></span>
      <span class="bar-value">${fmtBDTFull(r.value_bdt)}</span>
    `;
    container.appendChild(row);
  }
}

/* ── Vendors: tabbed, searchable, paginated ───────────────────────── */

const VENDOR_TABS = {
  value: {
    key: "top_vendors_by_value",
    columns: ["Company", "Contracts", "Total value (BDT)", "Procuring entities", "Ministries", "Years active"],
    row: v => `<td>${esc(v.company)}</td><td>${fmtInt(v.count)}</td><td>${fmtBDTFull(v.value_bdt)}</td>
               <td>${fmtInt(v.distinct_procuring_entities)}</td><td>${fmtInt(v.distinct_ministries)}</td><td>${fmtInt(v.years_active)}</td>`,
  },
  count: {
    key: "top_vendors_by_count",
    columns: ["Company", "Contracts", "Total value (BDT)", "Procuring entities", "Ministries", "Years active"],
    row: v => `<td>${esc(v.company)}</td><td>${fmtInt(v.count)}</td><td>${fmtBDTFull(v.value_bdt)}</td>
               <td>${fmtInt(v.distinct_procuring_entities)}</td><td>${fmtInt(v.distinct_ministries)}</td><td>${fmtInt(v.years_active)}</td>`,
  },
  concentrated: {
    key: "concentrated_vendors",
    columns: ["Company", "Contracts", "Total value (BDT)", "Top procuring entity", "Share with them"],
    row: v => `<td>${esc(v.company)}</td><td>${fmtInt(v.count)}</td><td>${fmtBDTFull(v.value_bdt)}</td>
               <td>${esc(v.top_entity)}</td><td>${(v.top_entity_share * 100).toFixed(0)}%</td>`,
  },
};

function setupVendorTable(insights) {
  const state = { tab: "value", search: "", shown: 10 };
  const head = document.getElementById("vendorsHead");
  const body = document.getElementById("vendorsBody");
  const showMoreBtn = document.getElementById("vendorsShowMore");

  function currentRows() {
    const cfg = VENDOR_TABS[state.tab];
    const all = insights[cfg.key];
    if (!state.search) return all;
    const q = state.search.toLowerCase();
    return all.filter(v => v.company.toLowerCase().includes(q));
  }

  function render() {
    const cfg = VENDOR_TABS[state.tab];
    head.innerHTML = `<tr>${cfg.columns.map(c => `<th>${c}</th>`).join("")}</tr>`;
    const rows = currentRows();
    body.innerHTML = rows.slice(0, state.shown).map(v => `<tr>${cfg.row(v)}</tr>`).join("")
      || `<tr><td colspan="${cfg.columns.length}" style="text-align:center;color:var(--muted)">No vendors match "${esc(state.search)}"</td></tr>`;
    showMoreBtn.hidden = state.shown >= rows.length;
    showMoreBtn.textContent = `Show 10 more (${rows.length - state.shown} left)`;
  }

  document.getElementById("vendorTabs").addEventListener("click", e => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    for (const t of document.querySelectorAll("#vendorTabs .tab")) {
      t.classList.toggle("active", t === btn);
      t.setAttribute("aria-selected", t === btn ? "true" : "false");
    }
    state.tab = btn.dataset.tab;
    state.shown = 10;
    render();
  });
  document.getElementById("vendorSearch").addEventListener("input", e => {
    state.search = e.target.value.trim();
    state.shown = 10;
    render();
  });
  showMoreBtn.addEventListener("click", () => { state.shown += 10; render(); });

  render();
}

/* ── Tender funnel ─────────────────────────────────────────────────── */

const STATUS_GROUP = {
  "Contract Awarded": "awarded",
  "Live": "open", "Being processed": "open", "Re-Tendered": "open", "To be Re-Tendered": "open",
  "Cancelled": "closed", "Rejected": "closed",
};
function statusGroup(status) {
  if (STATUS_GROUP[status]) return STATUS_GROUP[status];
  return status.startsWith("Amendment") ? "open" : "other";
}

function renderFunnel(insights) {
  const container = document.getElementById("funnelBars");
  const funnel = insights.tender_funnel;
  if (!funnel) {
    document.getElementById("tenders").style.display = "none";
    return;
  }
  const grouped = { awarded: 0, open: 0, closed: 0, other: 0 };
  for (const [status, n] of Object.entries(funnel.by_status)) {
    grouped[statusGroup(status)] += n;
  }
  const labels = { awarded: "Contract awarded", open: "Still open / processing", closed: "Cancelled / rejected", other: "Other" };
  const max = Math.max(...Object.values(grouped), 1);
  for (const key of ["awarded", "open", "closed", "other"]) {
    if (!grouped[key]) continue;
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <span class="bar-label">${labels[key]}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${(100 * grouped[key] / max).toFixed(1)}%"></span></span>
      <span class="bar-value">${fmtInt(grouped[key])}</span>
    `;
    container.appendChild(row);
  }
}

/* ── Debarment: severity bars, flag-type bars, filterable table ──── */

function renderSeverityBars(debarments) {
  const container = document.getElementById("severityBars");
  const counts = debarments.summary.by_severity;
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  for (const sev of SEVERITY_ORDER) {
    const n = counts[sev] || 0;
    const row = document.createElement("div");
    row.className = "severity-row";
    row.innerHTML = `
      <span class="severity-tag ${sev}">${SEVERITY_LABEL[sev]}</span>
      <span class="severity-track"><span class="severity-fill ${sev}" style="width:${(100 * n / total).toFixed(1)}%"></span></span>
      <span class="severity-count">${fmtInt(n)}</span>
    `;
    container.appendChild(row);
  }
}

function renderFlagTypeBars(flags) {
  const container = document.getElementById("flagTypeBars");
  const active = flags.meta.by_type.active_debarment_violation || 0;
  const post = flags.meta.by_type.post_debarment_award || 0;
  const max = Math.max(active, post, 1);
  const rows = [
    ["critical", "Active violation", active],
    ["low", "Post-debarment", post],
  ];
  for (const [tone, label, n] of rows) {
    const row = document.createElement("div");
    row.className = "severity-row";
    row.innerHTML = `
      <span class="severity-tag ${tone}">${label}</span>
      <span class="severity-track"><span class="severity-fill ${tone}" style="width:${(100 * n / max).toFixed(1)}%"></span></span>
      <span class="severity-count">${fmtInt(n)}</span>
    `;
    container.appendChild(row);
  }
}

function setupFlagsTable(flags) {
  const state = { search: "", severity: "", shown: 20 };
  const body = document.getElementById("flagsBody");
  const showMoreBtn = document.getElementById("flagsShowMore");

  function currentRows() {
    return flags.flags.filter(f => {
      if (state.severity && f.severity !== state.severity) return false;
      if (!state.search) return true;
      const q = state.search.toLowerCase();
      return f.company.toLowerCase().includes(q) || (f.procuring_entity || "").toLowerCase().includes(q);
    });
  }

  function render() {
    const rows = currentRows();
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--muted)">No flags match your filter.</td></tr>`;
      showMoreBtn.hidden = true;
      return;
    }
    body.innerHTML = rows.slice(0, state.shown).map(f => {
      const window = f.debar_start && f.debar_end ? `${f.debar_start} → ${f.debar_end}` : "—";
      return `<tr>
        <td><span class="badge ${f.severity}">${f.severity}</span></td>
        <td>${f.flag_type === "active_debarment_violation" ? "Active violation" : "Post-debarment"}</td>
        <td>${esc(f.company)}</td>
        <td>${esc(f.district) || "—"}</td>
        <td>${esc(f.procuring_entity) || "—"}</td>
        <td>${f.contract_signing_date || "—"}</td>
        <td>${window}</td>
        <td>৳${fmtBDT(f.value_bdt)}</td>
        <td class="desc">${esc(f.debarment_reason) || "—"}</td>
      </tr>`;
    }).join("");
    showMoreBtn.hidden = state.shown >= rows.length;
    showMoreBtn.textContent = `Show 20 more (${rows.length - state.shown} left)`;
  }

  document.getElementById("flagSearch").addEventListener("input", e => {
    state.search = e.target.value.trim();
    state.shown = 20;
    render();
  });
  document.getElementById("flagSeverityFilter").addEventListener("change", e => {
    state.severity = e.target.value;
    state.shown = 20;
    render();
  });
  showMoreBtn.addEventListener("click", () => { state.shown += 20; render(); });

  render();
}

/* ── Coverage line + methodology footer text ──────────────────────── */

function renderCoverage(debarments, contractsSummary) {
  const banner = document.getElementById("coverageBanner");
  const years = contractsSummary.meta.years;
  const yearRange = years.length ? `${years[0]}–${years[years.length - 1]}` : "no data yet";
  banner.innerHTML = `<strong>${fmtInt(contractsSummary.meta.record_count)}</strong> contracts (${yearRange}) ·
    <strong>${fmtInt(debarments.meta.record_count)}</strong> debarment records ·
    updated ${contractsSummary.meta.generated_at.slice(0, 10)}`;

  const cov = document.getElementById("methodologyCoverage");
  cov.innerHTML = `
    Built from the eContracts award list (${fmtInt(contractsSummary.meta.record_count)} records,
    ${yearRange}) and the debarment register (${fmtInt(debarments.meta.record_count)} records),
    both re-crawled from <a href="https://www.eprocure.gov.bd/" target="_blank" rel="noopener">eprocure.gov.bd</a>
    daily. Not yet built: award detail pages (beneficial ownership), eExperience, registration,
    and Annual Procurement Plans line items -- see the
    <a href="https://github.com/sushmit0109/prototype/tree/main/e-gp" target="_blank" rel="noopener">README</a>
    for full source-by-source status.
  `;
}

/* ── Boot ──────────────────────────────────────────────────────────── */

async function main() {
  try {
    const [debarments, contractsSummary, flags, insights] = await Promise.all([
      loadJSON("data/debarments.json"),
      loadJSON("data/contracts/summary.json"),
      loadJSON("data/flags.json"),
      loadJSON("data/insights.json"),
    ]);
    renderCoverage(debarments, contractsSummary);
    renderHeadlines(debarments, contractsSummary, flags, insights);
    renderYearChart(insights);
    renderMinistryBars(insights);
    setupVendorTable(insights);
    renderFunnel(insights);
    renderSeverityBars(debarments);
    renderFlagTypeBars(flags);
    setupFlagsTable(flags);
  } catch (err) {
    document.getElementById("coverageBanner").textContent = `Could not load data: ${err.message}`;
    console.error(err);
  }
}

main();
