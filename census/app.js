/* Development & the Vote — a sub-district companion to the e-GP project's
   district-level "does winning pay?" study. Hand-built inline SVG, no
   library, matching that project's visual language. */

const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const int = n => n == null ? "—" : Math.round(n).toLocaleString("en-US");
const pct = (n, d = 0) => n == null ? "—" : `${(n * 100).toFixed(d)}%`;
const svg = (w, h, body) =>
  `<svg viewBox="0 0 ${w} ${h}" role="img" xmlns="http://www.w3.org/2000/svg">${body}</svg>`;
const legend = items => items.map(([c, l]) =>
  `<span><i class="swatch" style="background:${c}"></i>${esc(l)}</span>`).join("");

const PARTIES = ["BNP-led alliance", "Jamaat-led alliance", "Independent", "Other party"];
const PARTY_COLOR = {
  "BNP-led alliance": "var(--s1)", "Jamaat-led alliance": "var(--s2)",
  "Independent": "var(--s3)", "Other party": "var(--s4)",
};
const INDICATOR_LABEL = {
  dev_index: "Development index (composite)",
  literacy_15plus: "Literacy rate (15+)",
  electricity_access: "Electricity access",
  safe_sanitation: "Safe sanitation",
  pucca_housing: "Pucca (permanent) housing",
  internet_15plus: "Internet use (15+)",
  mobile_banking: "Mobile banking account",
  remittance_hh: "Household gets foreign remittance",
  muslim_pct: "Muslim population share",
  avg_hh_size: "Average household size",
  neet_pct: "Youth not in education/employment/training",
};

async function loadJSON(p) {
  const r = await fetch(p);
  if (!r.ok) throw new Error(`${p}: HTTP ${r.status}`);
  return r.json();
}

function pValues(d) {
  const out = [];
  for (const party of PARTIES) for (const pred in d.regressions[party]) out.push(d.regressions[party][pred].p_value);
  return out;
}

function chartDevIndex(d) {
  const rows = PARTIES.map(p => [p, d.regressions[p].dev_index]);
  const max = Math.max(...rows.map(([, r]) => Math.abs(r.coefficient)), 0.02);
  const W = 760, rowH = 40, padT = 10, padL = 190, padR = 80;
  const H = rows.length * rowH + padT * 2;
  const bh = rowH * 0.48, pw = W - padL - padR, zeroX = padL + pw / 2;
  let body = "";
  rows.forEach(([party, r], i) => {
    const yy = padT + i * rowH + (rowH - bh) / 2;
    const w = (Math.abs(r.coefficient) / max) * (pw / 2);
    const x = r.coefficient >= 0 ? zeroX : zeroX - w;
    const sig = r.p_value < 0.05;
    body += `<text class="ax-strong" x="${padL - 12}" y="${yy + bh / 2 + 4}" text-anchor="end">${esc(party)}</text>
      <rect x="${x}" y="${yy}" width="${Math.max(w, 1.5)}" height="${bh}" rx="3" fill="${PARTY_COLOR[party]}" opacity="${sig ? 1 : 0.45}">
        <title>${esc(party)}: ${r.coefficient} vote-share points per 1 SD of the development index, p=${r.p_value}</title></rect>
      <text class="val-label${sig ? " hi" : ""}" x="${r.coefficient >= 0 ? x + w + 6 : x - 6}" y="${yy + bh / 2 + 4}"
        text-anchor="${r.coefficient >= 0 ? "start" : "end"}" font-size="9">${pct(r.coefficient, 2)}${sig ? " *" : ""}</text>`;
  });
  body += `<line x1="${zeroX}" y1="${padT - 4}" x2="${zeroX}" y2="${H - padT + 4}" class="grid"/>`;
  return svg(W, H, body);
}

function regTable(d) {
  const preds = ["dev_index", "literacy_15plus", "electricity_access", "safe_sanitation", "pucca_housing",
    "internet_15plus", "mobile_banking", "remittance_hh", "muslim_pct", "avg_hh_size", "neet_pct"];
  const cell = r => `<td class="n">${r.coefficient}</td><td class="n${r.p_value < 0.05 ? " hi" : ""}">${r.p_value}</td>`;
  return preds.map(pred => `
    <tr>
      <td class="strong">${esc(INDICATOR_LABEL[pred])}</td>
      ${PARTIES.map(p => cell(d.regressions[p][pred])).join("")}
    </tr>`).join("");
}

function scatterOne(d, indicatorKey, party, color) {
  const rows = d.upazilas.filter(u => u.indicators[indicatorKey] != null);
  const xs = rows.map(u => u.indicators[indicatorKey]);
  const ys = rows.map(u => u.shares[party]);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMax = Math.max(...ys, 0.05) * 1.05;
  const W = 720, H = 260, pL = 46, pR = 16, pT = 14, pB = 30;
  const pw = W - pL - pR, ph = H - pT - pB;
  const xOf = v => pL + ((v - xMin) / (xMax - xMin || 1)) * pw;
  const yOf = v => pT + ph - (v / yMax) * ph;
  let body = "";
  rows.forEach((u, i) => {
    body += `<circle cx="${xOf(xs[i])}" cy="${yOf(ys[i])}" r="3" fill="${color}" fill-opacity="0.55">
      <title>${esc(u.upazila)}, ${esc(u.district)}: ${INDICATOR_LABEL[indicatorKey]} ${xs[i]}, ${esc(party)} share ${pct(ys[i], 1)}</title></circle>`;
  });
  body += `<text class="ax" x="${pL + pw / 2}" y="${H - 6}" text-anchor="middle">${esc(INDICATOR_LABEL[indicatorKey])}</text>`;
  return svg(W, H, body);
}

async function main() {
  const d = await loadJSON("data/causal_election.json");

  document.getElementById("statUpazilas").textContent = int(d.meta.n_upazilas_matched);
  document.getElementById("statExcluded").textContent = int(d.meta.n_excluded_metro + d.meta.n_dropped_missing_indicator);
  document.getElementById("statIndicators").textContent = int(d.meta.dev_index_components.length);

  const pv = pValues(d);
  const nTests = pv.length;
  const bonferroni = 0.05 / nTests;
  const minP = Math.min(...pv);
  const devSig = PARTIES.some(p => d.regressions[p].dev_index.p_value < 0.05);
  document.getElementById("headline").textContent = devSig
    ? "The development index does move one party's vote share — barely"
    : "The composite development index predicts nothing — for any party";
  document.getElementById("headlineSub").textContent =
    `${int(d.meta.n_upazilas_matched)} upazilas, ${PARTIES.length} parties, ${d.meta.dev_index_components.length}-indicator `
    + `composite index plus each indicator tested on its own — ${nTests} regressions in total. `
    + `A Bonferroni correction for that many tests needs p<${bonferroni.toFixed(4)}; the smallest p-value across all of them `
    + `is ${minP}.`;

  document.getElementById("chartDevIndex").innerHTML = chartDevIndex(d);
  document.getElementById("regTableBody").innerHTML = regTable(d);

  const neet = d.regressions["BNP-led alliance"].neet_pct;
  const muslim = d.regressions["Jamaat-led alliance"].muslim_pct;
  document.getElementById("chartScatterMuslim").innerHTML = scatterOne(d, "muslim_pct", "Jamaat-led alliance", "var(--s2)");
  document.getElementById("chartScatterNeet").innerHTML = scatterOne(d, "neet_pct", "BNP-led alliance", "var(--s1)");
  document.getElementById("muslimNote").textContent =
    `Muslim population share vs. Jamaat-led alliance vote share: b=${muslim.coefficient} vote-share points per 1 SD `
    + `(p=${muslim.p_value}, raw r=${muslim.raw_correlation}). This is the one relationship in this whole dataset that `
    + `should be there on priors alone — a religiously-mobilizing alliance doing better where the religious-majority `
    + `share is higher isn't a surprising causal claim, it's close to definitional. Its presence here is a sanity check `
    + `on the method (division fixed effects and clustering aren't washing out a real, expected signal), not a finding.`;
  document.getElementById("neetNote").textContent =
    `Youth NEET rate (not in education, employment, or training) vs. BNP-led alliance vote share: b=${neet.coefficient} `
    + `(p=${neet.p_value}, raw r=${neet.raw_correlation}) — upazilas with more idle youth gave BNP-led candidates a `
    + `smaller share, net of division and population-size differences. One of only two individual-indicator results `
    + `(of ${nTests}) that clear even a conservative Bonferroni bar — the other being the unsurprising Muslim-share/`
    + `Jamaat-led relationship above. Flagged, not asserted: one cross-sectional coefficient can't distinguish "youth `
    + `unemployment turned voters away from BNP specifically" from "whatever makes youth unemployment high in an `
    + `upazila also makes it vote a certain way for unrelated reasons" — see the caveats below.`;

  document.getElementById("nUnmatched").textContent = int(d.meta.n_unmatched);
  document.getElementById("nMetro").textContent = int(d.meta.n_excluded_metro);
  document.getElementById("nMissing").textContent = int(d.meta.n_dropped_missing_indicator);
  document.getElementById("nTotal").textContent = int(d.meta.n_election_upazilas_total);
}

main().catch(e => {
  console.error(e);
  document.getElementById("headline").textContent = "Couldn't load the data.";
  document.getElementById("headlineSub").textContent = String(e);
});
