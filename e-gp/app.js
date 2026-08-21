const SEVERITY_ORDER = ["critical", "high", "medium", "low"];
const SEVERITY_LABEL = { critical: "Critical", high: "High", medium: "Medium", low: "Low" };

function fmtInt(n) {
  return n == null ? "—" : n.toLocaleString("en-US");
}

function fmtBDT(n) {
  if (n == null) return "—";
  if (n >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(2)} L`;
  return n.toLocaleString("en-US");
}

function kpi(label, value, sub, tone) {
  const div = document.createElement("div");
  div.className = "kpi";
  div.innerHTML = `
    <div class="kpi-label">${label}</div>
    <div class="kpi-value${tone ? " " + tone : ""}">${value}</div>
    ${sub ? `<div class="kpi-sub">${sub}</div>` : ""}
  `;
  return div;
}

async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

function renderCoverage(debarments, contractsSummary, flags) {
  const banner = document.getElementById("coverageBanner");
  const years = contractsSummary.meta.years;
  const yearRange = years.length ? `${years[0]}–${years[years.length - 1]}` : "no data yet";
  banner.innerHTML = `
    <span><strong>${fmtInt(contractsSummary.meta.record_count)}</strong> contracts (${yearRange})</span>
    <span>·</span>
    <span><strong>${fmtInt(debarments.meta.record_count)}</strong> debarment records</span>
    <span>·</span>
    <span>debarments updated ${debarments.meta.generated_at.slice(0, 16).replace("T", " ")} UTC</span>
    <span>·</span>
    <span>contracts updated ${contractsSummary.meta.generated_at.slice(0, 16).replace("T", " ")} UTC</span>
  `;
}

function renderKPIs(debarments, flags) {
  const grid = document.getElementById("kpiGrid");
  const activeViolations = flags.meta.by_type.active_debarment_violation || 0;
  const postDebarment = flags.meta.by_type.post_debarment_award || 0;
  grid.append(
    kpi("Debarred entities", fmtInt(debarments.meta.record_count),
        `${fmtInt(debarments.summary.repeat_offenders.length)} repeat offenders`),
    kpi("Contracts scanned", fmtInt(flags.meta.contracts_scanned)),
    kpi("Active debarment violations", fmtInt(activeViolations),
        "signed while debarment was in force", activeViolations > 0 ? "critical" : ""),
    kpi("Value in active violations", `৳${fmtBDT(flags.meta.value_at_risk_bdt_active_violations)}`),
    kpi("Post-debarment awards", fmtInt(postDebarment), "recidivism tracking, not a violation"),
  );
}

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

function renderFlags(flags) {
  const body = document.getElementById("flagsBody");
  if (!flags.flags.length) {
    document.getElementById("flagsTable").replaceWith(
      Object.assign(document.createElement("div"), {
        className: "empty-state",
        textContent: "No flagged awards in the crawled data so far.",
      })
    );
    return;
  }
  for (const f of flags.flags) {
    const tr = document.createElement("tr");
    const window = f.debar_start && f.debar_end ? `${f.debar_start} → ${f.debar_end}` : "—";
    tr.innerHTML = `
      <td><span class="badge ${f.severity}">${f.severity}</span></td>
      <td>${f.flag_type === "active_debarment_violation" ? "Active violation" : "Post-debarment"}</td>
      <td>${f.company}</td>
      <td>${f.district || "—"}</td>
      <td>${f.procuring_entity || "—"}</td>
      <td>${f.contract_signing_date || "—"}</td>
      <td>${window}</td>
      <td>৳${fmtBDT(f.value_bdt)}</td>
      <td class="desc">${f.debarment_reason || "—"}</td>
    `;
    body.appendChild(tr);
  }
}

async function main() {
  try {
    const [debarments, contractsSummary, flags] = await Promise.all([
      loadJSON("data/debarments.json"),
      loadJSON("data/contracts/summary.json"),
      loadJSON("data/flags.json"),
    ]);
    renderCoverage(debarments, contractsSummary, flags);
    renderKPIs(debarments, flags);
    renderSeverityBars(debarments);
    renderFlags(flags);
  } catch (err) {
    document.getElementById("coverageBanner").textContent = `Could not load data: ${err.message}`;
    console.error(err);
  }
}

main();
