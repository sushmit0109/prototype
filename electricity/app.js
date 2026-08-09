/* Bangladesh electricity & load-shedding dashboard.
 *
 * Reads only the pre-built JSON in ./data (produced by pipeline/build_site.py);
 * no government page is parsed in the browser. Charts are hand-drawn SVG so the
 * page carries no charting dependency — Leaflet is the only external library.
 */
'use strict';

/* ══════════════════════════════════════════ i18n ══════════════════════════ */

const STR = {
  bn: {
    brand: 'বিদ্যুৎ ড্যাশবোর্ড', allProto: 'সব প্রোটোটাইপ',
    eyebrow: 'সরকারি তথ্যের ভিত্তিতে',
    title: 'বাংলাদেশের বিদ্যুৎ উৎপাদন ও লোডশেডিং',
    lede: 'পিজিসিবি ও বিপিডিবির প্রকাশিত তথ্য প্রতি ঘণ্টায় সংগ্রহ করে এখানে একসঙ্গে দেখানো হচ্ছে — কত বিদ্যুৎ উৎপাদন হলো, কতটা ঘাটতি থাকল, কোন অঞ্চলে কতটা লোডশেড হলো, আর কেন হলো।',
    loading: 'তথ্য আসছে…',
    navNow: 'এই মুহূর্তে', navWhy: 'কেন লোডশেডিং', navMap: 'মানচিত্র',
    navFuel: 'জ্বালানি', navZones: 'অঞ্চলভিত্তিক', navTrend: 'দীর্ঘমেয়াদি',
    navTrust: 'তথ্যের নির্ভরযোগ্যতা',

    nowTitle: 'এই মুহূর্তে',
    nowSub: 'পিজিসিবির সর্বশেষ ঘণ্টাভিত্তিক হিসাব। সরবরাহ ও লোডশেড যোগ করলেই প্রকাশিত “চাহিদা” পাওয়া যায়।',
    supply: 'সরবরাহ', loadshed: 'লোডশেড', demand: 'চাহিদা (প্রকাশিত)',
    todayPeak: 'আজকের সর্বোচ্চ লোডশেড', mw: 'মেগাওয়াট', mkwh: 'মি. কি.ও.ঘ.',
    asOf: 'সময়', noData: 'তথ্য নেই',
    todayChart: 'ঘণ্টাভিত্তিক সরবরাহ ও লোডশেড',
    r7: '৭ দিন', r30: '৩০ দিন', r90: '৯০ দিন', ryear: 'এ বছর',
    hoursShed: 'লোডশেড হয়েছে এমন ঘণ্টা', energyShed: 'সরবরাহ করা যায়নি',
    mwh: 'মেগাওয়াট-ঘণ্টা',

    whyTitle: 'লোডশেডিং কেন হচ্ছে?',
    whySub: 'এনএলডিসির দৈনিক প্রতিবেদনে প্রতিটি বিদ্যুৎকেন্দ্রের পাশে কারণ লেখা থাকে। যেসব কেন্দ্র সন্ধ্যার সর্বোচ্চ চাহিদার সময় একেবারেই উৎপাদন করেনি, তাদের ক্ষমতা কারণ অনুযায়ী সাজানো হলো।',
    mapSub: 'জেলার রং তার অঞ্চলের সন্ধ্যাকালীন হিসাব অনুযায়ী। বিন্দুগুলো বিদ্যুৎকেন্দ্র ও গ্রিড উপকেন্দ্র — আকার ক্ষমতা বা লোড অনুযায়ী।',
    fuelSub: 'দৈনিক উৎপাদিত বিদ্যুতের জ্বালানিভিত্তিক ভাগ (মিলিয়ন কিলোওয়াট-ঘণ্টা)।',
    zonesSub: 'এনএলডিসির প্রতিবেদনে সন্ধ্যার সর্বোচ্চ চাহিদার সময়ের অঞ্চলভিত্তিক চাহিদা ও লোডশেড।',
    trendSub: 'পিজিসিবির সংরক্ষিত তথ্য ২০১৫ সাল থেকে থাকলেও, ২০২২ সালের আগে প্রায় প্রতিটি ঘণ্টায় লোডশেড “০” লেখা আছে। তাই আগের সময়টা “তথ্য প্রকাশ করা হয়নি” হিসেবে আলাদা করে দেখানো হয়েছে।',
    trustSub: 'এখানে কর্তৃপক্ষের প্রকাশিত সংখ্যাই তুলে ধরা হয়েছে। কিন্তু সংখ্যাগুলো কীভাবে তৈরি হয়, আর কোথায় দুই সরকারি সূত্র একে অপরের সঙ্গে মেলে না — সেটাও দেখানো দরকার।',
    idleTitle: 'অলস ক্ষমতা, কারণ অনুযায়ী',
    idleTrend: 'গ্যাস সংকটে বসে থাকা ক্ষমতা',
    idleNote: 'সন্ধ্যার সর্বোচ্চ চাহিদার সময় মোট <b>{cap}</b> মেগাওয়াট উৎপাদন ক্ষমতা একেবারেই ব্যবহার হয়নি — এর মধ্যে <b>{gas}</b> মেগাওয়াট শুধু গ্যাস সংকটের কারণে। উৎস: এনএলডিসি দৈনিক প্রতিবেদন, {date}।',
    idleCap: 'অলস ক্ষমতা', plants: 'কেন্দ্র',

    mapTitle: 'মানচিত্রে বিদ্যুৎ',
    mapLoadshed: 'লোডশেড', mapDemand: 'চাহিদা',
    mapNote: 'জেলার রং সেই জেলার অঞ্চলভিত্তিক (জোন) হিসাব অনুযায়ী — জোনের ভেতরে জেলাভিত্তিক আলাদা হিসাব প্রকাশ করা হয় না। বিদ্যুৎকেন্দ্র ও উপকেন্দ্রের অবস্থান ওপেনস্ট্রিটম্যাপ থেকে নাম মিলিয়ে বসানো; কিছু ক্ষেত্রে তা কাছের শহর পর্যন্তই নির্ভুল।',
    layerPlants: 'বিদ্যুৎকেন্দ্র', layerSubs: 'গ্রিড উপকেন্দ্র', layerDistricts: 'জেলা',
    capacity: 'ক্ষমতা', generated: 'উৎপাদন', idle: 'অলস', load: 'সর্বোচ্চ লোড',
    reason: 'কারণ', zone: 'অঞ্চল', at: 'সময়',
    low: 'কম', high: 'বেশি', approx: 'আনুমানিক অবস্থান',

    fuelTitle: 'কোন জ্বালানি থেকে বিদ্যুৎ',
    fuelChart: 'জ্বালানিভিত্তিক দৈনিক উৎপাদন',
    costTitle: 'প্রতি ইউনিট উৎপাদন খরচ', costUnit: 'টাকা/কিলোওয়াট-ঘণ্টা',
    fuelLatest: 'সর্বশেষ দিনের জ্বালানি ভাগ',
    share: 'অংশ',

    zonesTitle: 'অঞ্চলভিত্তিক চিত্র', zoneTrend: 'অঞ্চলভিত্তিক লোডশেডের প্রবণতা',
    zoneName: 'অঞ্চল', zoneShare: 'লোডশেডের হার',

    trendTitle: 'দীর্ঘমেয়াদি প্রবণতা',
    monthlyTitle: 'মাসভিত্তিক সর্বোচ্চ লোডশেড',
    notReported: 'তথ্য প্রকাশ করা হয়নি',

    trustTitle: 'তথ্য কতটা নির্ভরযোগ্য',
    identityTitle: 'প্রকাশিত “চাহিদা” আসলে একটি যোগফল, আলাদা কোনো পরিমাপ নয়',
    identityBody: 'পিজিসিবির ঘণ্টাভিত্তিক তালিকায় {rate} ক্ষেত্রে চাহিদা = সরবরাহ + লোডশেড, হুবহু। বিপিডিবির দৈনিক প্রতিবেদনেও শক্তির হিসাবে চাহিদা = উৎপাদন + সরবরাহ করা যায়নি, {erate} ক্ষেত্রে হুবহু মেলে। অর্থাৎ “চাহিদা” সংখ্যাটি স্বাধীনভাবে মাপা হয় না — এটি লোডশেডের হিসাব থেকেই তৈরি। তাই এই দুটি সংখ্যা দিয়ে একে অপরকে যাচাই করা যায় না; প্রকৃত চাহিদা এর চেয়ে বেশিও হতে পারে।',
    sameSourceTitle: 'দুটি আলাদা পাতা, কিন্তু সংখ্যা একই',
    sameSourceBody: 'বিপিডিবির “area-wise demand” পাতা আর এনএলডিসির দৈনিক প্রতিবেদনের সন্ধ্যাকালীন হিসাব — {days} দিনের মধ্যে {match} দিনেই সংখ্যা হুবহু এক। অর্থাৎ এটি দ্বিতীয় কোনো স্বাধীন সূত্র নয়, একই হিসাবেরই আরেক রূপ।',
    coverageTitle: 'কোন বছরে কতটা তথ্য আছে',
    coverageBody: 'পিজিসিবির তালিকায় ২০১৫ সাল থেকে সারি আছে, কিন্তু চাহিদা ও সরবরাহের ঘর প্রায় পুরোটাই ফাঁকা, আর ২০২২ সালের আগে লোডশেডের ঘরে প্রায় সব সময় “০”। নিচের হিসাবে দেখুন কোন বছরে আসলে কতটা প্রকাশ করা হয়েছে।',
    year: 'বছর', rows: 'সারি', withDemand: 'চাহিদা আছে', nonzeroShed: 'শূন্যের বেশি লোডশেড',
    outlierTitle: 'অসম্ভব সংখ্যা',
    outlierBody: 'দেশের মোট উৎপাদন ক্ষমতা প্রায় ২৯,০০০ মেগাওয়াট। এর চেয়ে বড় লোডশেডের সংখ্যা টাইপিং ভুল ধরে নিয়ে বাদ দেওয়া হয়েছে — মোট {n}টি।',
    of: 'এর মধ্যে',

    sourcesTitle: 'তথ্যসূত্র',
    footerNote: 'তথ্য সংগ্রহ করা হয় প্রতি ঘণ্টায়, স্বয়ংক্রিয়ভাবে। এই পাতায় কোনো সংখ্যা হাতে বদলানো হয় না — যা প্রকাশিত, তা-ই দেখানো হয়। কোনো অসঙ্গতি চোখে পড়লে উৎসের লিংক থেকে মিলিয়ে দেখা যাবে।',
    builtAt: 'সর্বশেষ হালনাগাদ', dataFrom: 'তথ্যের পরিসর',
  },
  en: {
    brand: 'Electricity Dashboard', allProto: 'All prototypes',
    eyebrow: 'Built from official data',
    title: 'Bangladesh electricity generation & load-shedding',
    lede: 'PGCB and BPDB publish these figures; this page collects them every hour and puts them side by side — how much was generated, how much was short, which areas were shed, and why.',
    loading: 'Loading…',
    navNow: 'Right now', navWhy: 'Why', navMap: 'Map',
    navFuel: 'Fuel', navZones: 'By zone', navTrend: 'Long view',
    navTrust: 'Data integrity',

    nowTitle: 'Right now',
    nowSub: 'The latest hourly reading from PGCB. Supply plus load-shed is exactly the published “demand”.',
    supply: 'Supply', loadshed: 'Load-shed', demand: 'Demand (published)',
    todayPeak: 'Today’s peak load-shed', mw: 'MW', mkwh: 'MkWh',
    asOf: 'as of', noData: 'no data',
    todayChart: 'Hourly supply and load-shed',
    r7: '7 days', r30: '30 days', r90: '90 days', ryear: 'This year',
    hoursShed: 'Hours with load-shedding', energyShed: 'Energy not supplied',
    mwh: 'MWh',

    whyTitle: 'Why is there load-shedding?',
    whySub: 'The NLDC daily report prints a reason beside every power station. These are the stations that generated nothing at all at the evening peak, grouped by the reason given.',
    mapSub: 'Districts are shaded by their zone’s evening-peak figure. Dots are power stations and grid substations, sized by capacity or load.',
    fuelSub: 'The fuel split of each day’s generation, in million kilowatt-hours.',
    zonesSub: 'Zone demand and load-shed at the evening peak, as published in the NLDC daily report.',
    trendSub: 'PGCB’s archive holds rows back to 2015, but before 2022 the load-shed column reads “0” in almost every hour. That period is marked “not reported” rather than drawn as zero.',
    trustSub: 'This page shows the authorities’ own published figures. But it also matters how those figures are constructed, and where two official sources describing the same day do not agree.',
    idleTitle: 'Idle capacity, by stated reason',
    idleTrend: 'Capacity idled by gas shortage',
    idleNote: 'At the evening peak, <b>{cap}</b> MW of generating capacity produced nothing at all — <b>{gas}</b> MW of it for gas shortage alone. Source: NLDC daily report, {date}.',
    idleCap: 'Idle capacity', plants: 'plants',

    mapTitle: 'Electricity on the map',
    mapLoadshed: 'Load-shed', mapDemand: 'Demand',
    mapNote: 'Districts are shaded by their zone’s figure — no district-level breakdown is published inside a zone. Plant and substation positions come from matching names against OpenStreetMap; some are only accurate to the nearest town.',
    layerPlants: 'Power plants', layerSubs: 'Grid substations', layerDistricts: 'Districts',
    capacity: 'Capacity', generated: 'Generated', idle: 'Idle', load: 'Peak load',
    reason: 'Reason', zone: 'Zone', at: 'at',
    low: 'low', high: 'high', approx: 'approximate position',

    fuelTitle: 'What the electricity is made from',
    fuelChart: 'Daily generation by fuel',
    costTitle: 'Production cost per unit', costUnit: 'Tk per kWh',
    fuelLatest: 'Fuel split, latest day',
    share: 'share',

    zonesTitle: 'By zone', zoneTrend: 'Load-shedding trend by zone',
    zoneName: 'Zone', zoneShare: 'Share of load-shed',

    trendTitle: 'The long view',
    monthlyTitle: 'Monthly peak load-shed',
    notReported: 'not reported',

    trustTitle: 'How reliable is this data?',
    identityTitle: 'The published “demand” is an arithmetic identity, not a measurement',
    identityBody: 'In PGCB’s hourly table, demand equals supply plus load-shed exactly in {rate} of rows. BPDB’s daily report does the same with energy: demand = generated + unserved, exact in {erate} of days. So “demand” is not measured independently — it is derived from the load-shed figure. The two numbers therefore cannot be used to check each other, and true demand may well be higher.',
    sameSourceTitle: 'Two different pages, the same numbers',
    sameSourceBody: 'BPDB’s “area-wise demand” page and the NLDC daily report’s evening-peak table agree exactly on {match} of {days} days compared. It is not a second independent source — it is the same figure republished.',
    coverageTitle: 'How much data each year actually holds',
    coverageBody: 'PGCB’s table has rows going back to 2015, but the demand and supply columns are almost entirely empty, and before 2022 the load-shed column reads “0” nearly every hour. The table below shows what is actually populated.',
    year: 'Year', rows: 'Rows', withDemand: 'Has demand', nonzeroShed: 'Load-shed above zero',
    outlierTitle: 'Impossible values',
    outlierBody: 'National installed capacity is about 29,000 MW. Load-shed figures larger than that are treated as typing errors and set aside — {n} in total.',
    of: 'of',

    sourcesTitle: 'Sources',
    footerNote: 'Data is collected automatically every hour. No figure on this page is edited by hand — what was published is what is shown. Every source is linked so any number here can be checked against the original.',
    builtAt: 'Last updated', dataFrom: 'Data range',
  },
};

const ZONE_NAMES = {
  bn: { dhaka: 'ঢাকা', chattogram: 'চট্টগ্রাম', cumilla: 'কুমিল্লা',
        mymensingh: 'ময়মনসিংহ', sylhet: 'সিলেট', khulna: 'খুলনা',
        barishal: 'বরিশাল', rajshahi: 'রাজশাহী', rangpur: 'রংপুর' },
  en: { dhaka: 'Dhaka', chattogram: 'Chattogram', cumilla: 'Cumilla',
        mymensingh: 'Mymensingh', sylhet: 'Sylhet', khulna: 'Khulna',
        barishal: 'Barishal', rajshahi: 'Rajshahi', rangpur: 'Rangpur' },
};

const REASON_NAMES = {
  bn: { gas_shortage: 'গ্যাস সংকট', fuel_shortage: 'তরল জ্বালানির সংকট',
        maintenance: 'রক্ষণাবেক্ষণ', fault: 'যান্ত্রিক ত্রুটি',
        contract_ended: 'চুক্তি শেষ', not_needed: 'চাহিদা কম / রিজার্ভ',
        other: 'অন্যান্য', none: 'কারণ উল্লেখ নেই' },
  en: { gas_shortage: 'Gas shortage', fuel_shortage: 'Liquid fuel shortage',
        maintenance: 'Maintenance / overhaul', fault: 'Mechanical fault',
        contract_ended: 'Contract ended', not_needed: 'Low demand / reserve',
        other: 'Other', none: 'No reason stated' },
};

const FUEL_NAMES = {
  bn: { gas: 'গ্যাস', coal: 'কয়লা', hfo: 'ফার্নেস তেল', hsd: 'ডিজেল',
        hydro: 'জলবিদ্যুৎ', solar: 'সৌর', wind: 'বায়ু', import: 'আমদানি',
        renewable: 'নবায়নযোগ্য' },
  en: { gas: 'Gas', coal: 'Coal', hfo: 'Furnace oil', hsd: 'Diesel',
        hydro: 'Hydro', solar: 'Solar', wind: 'Wind', import: 'Import',
        renewable: 'Renewables' },
};

let LANG = localStorage.getItem('bd-elec-lang') || 'bn';
const t = (k) => (STR[LANG] && STR[LANG][k]) || STR.en[k] || k;
const zoneName = (z) => ZONE_NAMES[LANG][z] || z;

/* ══════════════════════════════════ formatting ════════════════════════════ */

const locale = () => (LANG === 'bn' ? 'bn-BD' : 'en-GB');

function fmt(v, digits = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return new Intl.NumberFormat(locale(), {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  }).format(v);
}

function fmtDate(iso, opts) {
  if (!iso) return '—';
  const d = new Date(iso.length <= 10 ? iso + 'T00:00:00' : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(locale(), opts || { day: 'numeric', month: 'short', year: 'numeric' }).format(d);
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(locale(), {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(d);
}

/** Years are labels, not quantities — no thousands separator. */
const fmtYear = (y) => new Intl.NumberFormat(locale(), { useGrouping: false }).format(+y);

const pct = (x) => (x === null || x === undefined) ? '—'
  : new Intl.NumberFormat(locale(), { style: 'percent', maximumFractionDigits: 1 }).format(x);

/* ══════════════════════════════════ colours ═══════════════════════════════ */

const C = {
  supply: '#3987e5', loadshed: '#d95926',
  s: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9'],
  surface: '#1a1d27', grid: '#262b40', muted: '#8890b0',
};

// Single-hue sequential ramps, near-surface -> prominent.
const RAMP_SHED = ['#33251d', '#6b3a1e', '#a04a20', '#cf5c26', '#f0803f'];
const RAMP_DEM  = ['#1e2a3d', '#22456e', '#2a5f9f', '#3178cd', '#4d97ec'];

const FUEL_ORDER = ['gas', 'coal', 'hfo', 'import', 'renewable', 'hsd'];
const fuelColor = (f) => C.s[FUEL_ORDER.indexOf(f)] || C.s[6];

/* ══════════════════════════════════ svg utils ═════════════════════════════ */

const NS = 'http://www.w3.org/2000/svg';
function el(name, attrs = {}, parent = null) {
  const n = document.createElementNS(NS, name);
  for (const k in attrs) if (attrs[k] !== null && attrs[k] !== undefined) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}

function niceTicks(min, max, count = 5) {
  if (min === max) { max = min + 1; }
  const span = max - min;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const norm = step0 / mag;
  const step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(v);
  return out;
}

/** Shared scaffolding: surface, y grid + labels, x labels, hover surface. */
function frame(host, { height = 260, padL = 46, padR = 14, padT = 14, padB = 28 } = {}) {
  host.innerHTML = '';
  const width = Math.max(host.clientWidth || 640, 280);
  const svg = el('svg', {
    class: 'chart', viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: 'none', role: 'img',
  }, host);
  svg.style.height = height + 'px';
  const tip = document.createElement('div');
  tip.className = 'tip';
  host.appendChild(tip);
  return { svg, tip, width, height, padL, padR, padT, padB,
           iw: width - padL - padR, ih: height - padT - padB };
}

function yAxis(f, ymin, ymax, fmtFn = (v) => fmt(v)) {
  const { svg, padL, padT, iw, ih } = f;
  const ticks = niceTicks(ymin, ymax, 4);
  const y = (v) => padT + ih - ((v - ymin) / (ymax - ymin || 1)) * ih;
  for (const tk of ticks) {
    el('line', { class: 'grid-line', x1: padL, x2: padL + iw, y1: y(tk), y2: y(tk) }, svg);
    const lb = el('text', { class: 'tick-num', x: padL - 7, y: y(tk) + 3.5, 'text-anchor': 'end' }, svg);
    lb.textContent = fmtFn(tk);
  }
  return y;
}

function showTip(f, x, html) {
  const { tip, width } = f;
  tip.innerHTML = html;
  tip.classList.add('on');
  const w = tip.offsetWidth || 170;
  let left = x + 14;
  if (left + w > width) left = Math.max(4, x - w - 14);
  tip.style.left = left + 'px';
  tip.style.top = '10px';
}
const hideTip = (f) => f.tip.classList.remove('on');

function tipRow(color, label, value) {
  return `<div class="tip-row"><span class="tip-key">` +
    (color ? `<i class="swatch" style="background:${color}"></i>` : '') +
    `${label}</span><span>${value}</span></div>`;
}

/* ═════════════════════════════ chart: stacked area ════════════════════════ */

/** Stacked area over time. series: [{key,label,color}], rows: [{x, ...}] */
function stackedArea(host, rows, series, opts = {}) {
  if (!rows.length) { host.innerHTML = `<p class="loading">${t('noData')}</p>`; return; }
  const f = frame(host, { height: opts.height || 280 });
  const { svg, padL, padT, iw, ih } = f;

  const totals = rows.map(r => series.reduce((a, s) => a + (r[s.key] || 0), 0));
  const ymax = Math.max(...totals, 1) * 1.06;
  const y = yAxis(f, 0, ymax, opts.yfmt);
  const x = (i) => padL + (rows.length === 1 ? iw / 2 : (i / (rows.length - 1)) * iw);

  // paint from the top of the stack down so each band sits over the next
  let acc = rows.map(() => 0);
  const bands = series.map(s => {
    const lower = acc.slice();
    acc = acc.map((v, i) => v + (rows[i][s.key] || 0));
    return { s, lower, upper: acc.slice() };
  });

  for (const b of bands.slice().reverse()) {
    const up = b.upper.map((v, i) => `${x(i)},${y(v)}`).join(' ');
    const dn = b.lower.map((v, i) => `${x(i)},${y(v)}`).reverse().join(' ');
    el('polygon', { points: `${up} ${dn}`, fill: b.s.color, 'fill-opacity': 0.92,
                    stroke: C.surface, 'stroke-width': 2, 'stroke-linejoin': 'round' }, svg);
  }

  // x labels — a handful, never every point
  const step = Math.max(1, Math.round(rows.length / 6));
  for (let i = 0; i < rows.length; i += step) {
    const lb = el('text', { x: x(i), y: padT + ih + 18, 'text-anchor': 'middle' }, svg);
    lb.textContent = opts.xlabel ? opts.xlabel(rows[i]) : rows[i].x;
  }
  el('line', { class: 'axis-line', x1: padL, x2: padL + iw, y1: padT + ih, y2: padT + ih }, svg);

  // crosshair + tooltip
  const cross = el('line', { class: 'axis-line', y1: padT, y2: padT + ih, stroke: C.muted,
                             'stroke-width': 1, opacity: 0 }, svg);
  const dots = series.map(s => el('circle', { r: 4, fill: s.color, stroke: C.surface,
                                              'stroke-width': 2, opacity: 0 }, svg));
  const hit = el('rect', { x: padL, y: padT, width: iw, height: ih, fill: 'transparent' }, svg);

  hit.addEventListener('pointermove', (ev) => {
    const bb = svg.getBoundingClientRect();
    const px = (ev.clientX - bb.left) * (f.width / bb.width);
    let i = Math.round(((px - padL) / iw) * (rows.length - 1));
    i = Math.max(0, Math.min(rows.length - 1, i));
    const r = rows[i];
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i));
    cross.setAttribute('opacity', 0.6);
    bands.forEach((b, k) => {
      dots[k].setAttribute('cx', x(i));
      dots[k].setAttribute('cy', y(b.upper[i]));
      dots[k].setAttribute('opacity', (r[b.s.key] || 0) > 0 ? 1 : 0);
    });
    const body = series.map(s => tipRow(s.color, s.label, fmt(r[s.key] || 0, opts.tipDigits || 0))).join('');
    const totRow = opts.totalLabel
      ? tipRow(null, opts.totalLabel, fmt(totals[i], opts.tipDigits || 0)) : '';
    showTip(f, x(i), `<div class="tip-date">${opts.xtip ? opts.xtip(r) : r.x}</div>${body}${totRow}`);
  });
  hit.addEventListener('pointerleave', () => {
    hideTip(f); cross.setAttribute('opacity', 0);
    dots.forEach(d => d.setAttribute('opacity', 0));
  });

  legend(host, series);
}

function legend(host, series) {
  const box = document.createElement('div');
  box.className = 'legend';
  box.innerHTML = series.map(s =>
    `<span class="legend-item"><i class="swatch" style="background:${s.color}"></i>${s.label}</span>`
  ).join('');
  host.appendChild(box);
}

/* ═══════════════════════════════ chart: line ══════════════════════════════ */

function lineChart(host, rows, key, opts = {}) {
  const pts = rows.filter(r => r[key] !== null && r[key] !== undefined);
  if (!pts.length) { host.innerHTML = `<p class="loading">${t('noData')}</p>`; return; }
  const f = frame(host, { height: opts.height || 230 });
  const { svg, padL, padT, iw, ih } = f;

  const vals = pts.map(r => r[key]);
  const lo = opts.zero ? 0 : Math.min(...vals) * 0.97;
  const hi = Math.max(...vals) * 1.05;
  const y = yAxis(f, lo, hi, opts.yfmt);
  const x = (i) => padL + (pts.length === 1 ? iw / 2 : (i / (pts.length - 1)) * iw);
  const color = opts.color || C.s[0];

  if (opts.area) {
    const up = pts.map((r, i) => `${x(i)},${y(r[key])}`).join(' ');
    el('polygon', { points: `${padL},${y(lo)} ${up} ${padL + iw},${y(lo)}`,
                    fill: color, 'fill-opacity': 0.16 }, svg);
  }
  el('polyline', {
    points: pts.map((r, i) => `${x(i)},${y(r[key])}`).join(' '),
    fill: 'none', stroke: color, 'stroke-width': 2,
    'stroke-linejoin': 'round', 'stroke-linecap': 'round',
  }, svg);

  const step = Math.max(1, Math.round(pts.length / 5));
  for (let i = 0; i < pts.length; i += step) {
    const lb = el('text', { x: x(i), y: padT + ih + 18, 'text-anchor': 'middle' }, svg);
    lb.textContent = opts.xlabel ? opts.xlabel(pts[i]) : pts[i].x;
  }
  el('line', { class: 'axis-line', x1: padL, x2: padL + iw, y1: padT + ih, y2: padT + ih }, svg);

  const dot = el('circle', { r: 4.5, fill: color, stroke: C.surface, 'stroke-width': 2, opacity: 0 }, svg);
  const hit = el('rect', { x: padL, y: padT, width: iw, height: ih, fill: 'transparent' }, svg);
  hit.addEventListener('pointermove', (ev) => {
    const bb = svg.getBoundingClientRect();
    const px = (ev.clientX - bb.left) * (f.width / bb.width);
    let i = Math.round(((px - padL) / iw) * (pts.length - 1));
    i = Math.max(0, Math.min(pts.length - 1, i));
    dot.setAttribute('cx', x(i)); dot.setAttribute('cy', y(pts[i][key]));
    dot.setAttribute('opacity', 1);
    showTip(f, x(i), `<div class="tip-date">${opts.xtip ? opts.xtip(pts[i]) : pts[i].x}</div>` +
      tipRow(color, opts.label || key, fmt(pts[i][key], opts.digits || 0)));
  });
  hit.addEventListener('pointerleave', () => { hideTip(f); dot.setAttribute('opacity', 0); });
}

/* ════════════════════════════ chart: bars (vertical) ══════════════════════ */

function barChart(host, rows, key, opts = {}) {
  if (!rows.length) { host.innerHTML = `<p class="loading">${t('noData')}</p>`; return; }
  const f = frame(host, { height: opts.height || 250 });
  const { svg, padL, padT, iw, ih } = f;
  const vals = rows.map(r => r[key] || 0);
  const y = yAxis(f, 0, Math.max(...vals, 1) * 1.08, opts.yfmt);
  const bw = iw / rows.length;
  const gap = Math.min(2, bw * 0.18);

  rows.forEach((r, i) => {
    const v = r[key] || 0;
    const missing = opts.missing && opts.missing(r);
    const h = missing ? ih : Math.max(0, padT + ih - y(v));
    const rect = el('rect', {
      x: padL + i * bw + gap / 2, width: Math.max(1, bw - gap),
      y: missing ? padT : y(v), height: Math.max(missing ? ih : 1, h),
      fill: missing ? C.grid : (opts.color || C.s[1]),
      'fill-opacity': missing ? 0.55 : 0.95, rx: Math.min(3, bw / 3),
    }, svg);
    rect.addEventListener('pointerenter', () => {
      showTip(f, padL + i * bw + bw / 2,
        `<div class="tip-date">${opts.xtip ? opts.xtip(r) : r.x}</div>` +
        (missing ? `<div class="tip-row"><span class="tip-key">${t('notReported')}</span></div>`
                 : tipRow(opts.color || C.s[1], opts.label || key, fmt(v, opts.digits || 0))));
    });
    rect.addEventListener('pointerleave', () => hideTip(f));
  });

  const step = Math.max(1, Math.round(rows.length / 6));
  for (let i = 0; i < rows.length; i += step) {
    const lb = el('text', { x: padL + i * bw + bw / 2, y: padT + ih + 18, 'text-anchor': 'middle' }, svg);
    lb.textContent = opts.xlabel ? opts.xlabel(rows[i]) : rows[i].x;
  }
  el('line', { class: 'axis-line', x1: padL, x2: padL + iw, y1: padT + ih, y2: padT + ih }, svg);
}

/* ═══════════════════════════ chart: horizontal bars ═══════════════════════ */

function hBars(host, items, opts = {}) {
  host.innerHTML = '';
  if (!items.length) { host.innerHTML = `<p class="loading">${t('noData')}</p>`; return; }
  const width = Math.max(host.clientWidth || 500, 260);
  const rowH = opts.rowH || 34;
  const labelW = Math.min(Math.max(width * 0.34, 96), 190);
  const height = items.length * rowH + 8;
  const svg = el('svg', { class: 'chart', viewBox: `0 0 ${width} ${height}` }, host);
  svg.style.height = height + 'px';
  const tip = document.createElement('div'); tip.className = 'tip'; host.appendChild(tip);
  const f = { tip, width };

  const max = Math.max(...items.map(i => i.value), 1);
  const barMax = width - labelW - 62;

  items.forEach((it, i) => {
    const yy = i * rowH + 6;
    const lab = el('text', { x: labelW - 10, y: yy + rowH / 2 - 2, 'text-anchor': 'end' }, svg);
    lab.textContent = it.label;
    lab.setAttribute('fill', '#b3b9d4');

    const w = Math.max(2, (it.value / max) * barMax);
    const bar = el('rect', { x: labelW, y: yy + 4, width: w, height: rowH - 16,
                             fill: it.color || C.s[1], rx: 4 }, svg);
    const val = el('text', { class: 'tick-num', x: labelW + w + 8, y: yy + rowH / 2 - 2 }, svg);
    val.textContent = opts.fmtValue ? opts.fmtValue(it.value) : fmt(it.value);

    bar.addEventListener('pointerenter', () => {
      tip.innerHTML = `<div class="tip-date">${it.label}</div>` +
        tipRow(it.color || C.s[1], opts.valueLabel || '', opts.fmtValue ? opts.fmtValue(it.value) : fmt(it.value)) +
        (it.note ? `<div class="tip-row"><span class="tip-key">${it.note}</span></div>` : '');
      tip.classList.add('on');
      tip.style.left = Math.min(labelW + w, width - 180) + 'px';
      tip.style.top = Math.max(0, yy - 10) + 'px';
    });
    bar.addEventListener('pointerleave', () => tip.classList.remove('on'));
  });
}

/* ═════════════════════════════ small multiples ════════════════════════════ */

function sparkGrid(host, panels, opts = {}) {
  host.innerHTML = '';
  const grid = document.createElement('div');
  grid.className = 'grid g3';
  host.appendChild(grid);

  panels.forEach(p => {
    const cell = document.createElement('div');
    cell.style.cssText = 'border:1px solid var(--border);border-radius:10px;padding:10px 12px';
    const head = document.createElement('div');
    head.style.cssText = 'display:flex;justify-content:space-between;align-items:baseline;gap:8px';
    head.innerHTML = `<span style="font-size:.84rem;font-weight:600">${p.title}</span>` +
                     `<span style="font-size:.78rem;color:var(--muted);font-variant-numeric:tabular-nums">${p.stat}</span>`;
    cell.appendChild(head);

    const box = document.createElement('div');
    box.style.cssText = 'position:relative;margin-top:6px';
    cell.appendChild(box);
    grid.appendChild(cell);

    const w = 260, h = 56;
    const svg = el('svg', { class: 'chart', viewBox: `0 0 ${w} ${h}`,
                            preserveAspectRatio: 'none' }, box);
    svg.style.height = h + 'px';
    const vals = p.values;
    if (!vals.length) return;
    const max = Math.max(...vals, 1);
    const x = (i) => (vals.length === 1 ? w / 2 : (i / (vals.length - 1)) * w);
    const y = (v) => h - 4 - (v / max) * (h - 10);
    const pts = vals.map((v, i) => `${x(i)},${y(v)}`).join(' ');
    el('polygon', { points: `0,${h} ${pts} ${w},${h}`, fill: opts.color || C.loadshed,
                    'fill-opacity': 0.2 }, svg);
    el('polyline', { points: pts, fill: 'none', stroke: opts.color || C.loadshed,
                     'stroke-width': 1.8, 'stroke-linejoin': 'round' }, svg);
  });
}

/* ══════════════════════════════════ data ═════════════════════════════════ */

const D = {};
const load = (name) => fetch(`data/${name}.json`, { cache: 'no-cache' })
  .then(r => (r.ok ? r.json() : null)).catch(() => null);

async function loadAll() {
  // data/daily.json is published as the full open-data export but the page
  // itself needs only the monthly rollup and today's row from latest.json.
  const [meta, latest, monthly, integrity, plants, subs, fuelmix, zones, reasons, districts] =
    await Promise.all([
      load('meta'), load('latest'), load('monthly'), load('integrity'),
      load('plants'), load('substations'), load('fuelmix'), load('zones'),
      load('reasons'), load('geo/districts'),
    ]);
  Object.assign(D, { meta, latest, monthly, integrity, plants, subs,
                     fuelmix, zones, reasons, districts });

  // Hourly data is split per month; pull only the last few so a visit costs a
  // few hundred KB rather than the whole archive.
  const months = (meta && meta.coverage && meta.coverage.hourly && meta.coverage.hourly.months) || [];
  const wanted = months.slice(-4);
  const parts = await Promise.all(wanted.map(m => load(`hourly/${m}`)));
  D.hourly = { rows: parts.filter(Boolean).flatMap(p => p.rows || []) };
  D.hourly.rows.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
}

/* ═══════════════════════════════ renderers ═══════════════════════════════ */

function renderStatic() {
  document.documentElement.lang = LANG;
  document.body.dataset.lang = LANG;
  document.querySelectorAll('[data-i18n]').forEach(n => {
    const k = n.getAttribute('data-i18n');
    if (STR[LANG][k]) n.textContent = STR[LANG][k];
  });
  document.querySelectorAll('[data-lang-btn]').forEach(b => {
    b.setAttribute('aria-pressed', String(b.dataset.langBtn === LANG));
  });
}

function renderUpdated() {
  const m = D.meta, l = D.latest;
  if (!m) return;
  const node = document.getElementById('updated-text');
  const obs = l && l.observed_at;
  const ageH = obs ? (Date.now() - new Date(obs).getTime()) / 36e5 : 999;
  document.getElementById('live-dot').classList.toggle('stale', ageH > 6);
  const cov = m.coverage || {};
  node.innerHTML =
    `${t('builtAt')}: <b>${fmtDateTime(m.built_at)}</b> · ` +
    `${t('dataFrom')}: ${fmtDate(cov.daily && cov.daily.from)} – ${fmtDate(cov.daily && cov.daily.to)} · ` +
    `${fmt(cov.hourly && cov.hourly.rows)} ${LANG === 'bn' ? 'ঘণ্টার তথ্য' : 'hourly records'}`;
}

function renderNow() {
  const host = document.getElementById('now-tiles');
  const l = D.latest;
  if (!l) { host.innerHTML = `<p class="loading">${t('noData')}</p>`; return; }
  const today = l.today || {};

  const tile = (label, value, unit, note, color) => `
    <div class="stat">
      <div class="stat-label">${color ? `<i class="swatch" style="background:${color}"></i>` : ''}${label}</div>
      <div class="stat-value">${value}<span class="stat-unit">${unit || ''}</span></div>
      ${note ? `<div class="stat-note">${note}</div>` : ''}
    </div>`;

  host.innerHTML =
    tile(t('supply'), fmt(l.supply), t('mw'),
         `${t('asOf')} ${fmtDateTime(l.observed_at)}`, C.supply) +
    tile(t('loadshed'), fmt(l.loadshed), t('mw'),
         `${t('todayPeak')}: ${fmt(today.max_loadshed)} ${t('mw')}`, C.loadshed) +
    tile(t('demand'), fmt(l.demand), t('mw'),
         LANG === 'bn' ? 'সরবরাহ + লোডশেড' : 'supply + load-shed', null) +
    tile(t('energyShed'), fmt(today.energy_shed_mwh), t('mwh'),
         `${t('hoursShed')}: ${fmt(today.hours_shed)}`, null);

  renderHourly(D.range || 7);
}

function renderHourly(days) {
  const host = document.getElementById('hourly-chart');
  if (!D.hourly || !D.hourly.rows) { host.innerHTML = `<p class="loading">${t('noData')}</p>`; return; }
  const rows = D.hourly.rows.slice(-days * 24).map(r => ({
    x: r[0], supply: r[2] || 0, loadshed: r[3] || 0,
  }));
  stackedArea(host, rows, [
    { key: 'supply', label: t('supply'), color: C.supply },
    { key: 'loadshed', label: t('loadshed'), color: C.loadshed },
  ], {
    height: 300,
    totalLabel: t('demand'),
    xlabel: (r) => fmtDate(r.x.slice(0, 10), { day: 'numeric', month: 'short' }),
    xtip: (r) => fmtDateTime(r.x),
    yfmt: (v) => fmt(v),
  });
}

function renderRangeSeg() {
  const seg = document.getElementById('range-seg');
  const opts = [[7, 'r7'], [30, 'r30'], [90, 'r90']];
  D.range = D.range || 7;
  seg.innerHTML = opts.map(([d, k]) =>
    `<button type="button" data-days="${d}" aria-pressed="${D.range === d}">${t(k)}</button>`).join('');
  seg.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    D.range = +b.dataset.days;
    renderRangeSeg();
    renderHourly(D.range);
  }));
}

function renderWhy() {
  const p = D.plants;
  if (!p) return;
  const items = (p.idle_by_reason || [])
    .filter(r => r.idle_mw > 0)
    .sort((a, b) => b.idle_mw - a.idle_mw)
    // One entity (idle capacity), one colour: the reasons are nominal and each
    // bar is already named, so a hue per bar would encode nothing.
    .map(r => ({
      label: REASON_NAMES[LANG][r.reason] || r.reason,
      value: r.idle_mw,
      color: C.loadshed,
      note: `${fmt(r.plants)} ${t('plants')}`,
    }));
  hBars(document.getElementById('reason-chart'), items, {
    valueLabel: t('idleCap'),
    fmtValue: (v) => `${fmt(v)} ${t('mw')}`,
  });

  const hist = (D.reasons || []).map(r => ({ x: r.date, v: r.gas_shortage || 0 }));
  lineChart(document.getElementById('reason-trend'), hist, 'v', {
    color: C.loadshed, area: true, zero: true, label: t('idleCap'), height: 230,
    xlabel: (r) => fmtDate(r.x, { day: 'numeric', month: 'short' }),
    xtip: (r) => fmtDate(r.x),
  });

  const totalIdle = (p.idle_by_reason || []).reduce((a, r) => a + r.idle_mw, 0);
  const gas = (p.idle_by_reason || []).find(r => r.reason === 'gas_shortage');
  document.getElementById('idle-note').innerHTML =
    `<div class="note warn"><div class="note-title">⚡ ${t('idleTitle')}</div>` +
    t('idleNote')
      .replace('{cap}', fmt(totalIdle))
      .replace('{gas}', fmt(gas ? gas.idle_mw : 0))
      .replace('{date}', fmtDate(p.date)) + `</div>`;
}

function renderFuel() {
  const fm = D.fuelmix;
  if (!fm || !fm.daily || !fm.daily.length) return;
  const rows = fm.daily.map(d => ({
    x: d.date,
    gas: d.gas || 0, coal: d.coal || 0, hfo: d.hfo || 0, import: d.import || 0,
    renewable: (d.hydro || 0) + (d.solar || 0) + (d.wind || 0),
    hsd: d.hsd || 0,
    cost: d.cost_per_kwh,
  }));

  stackedArea(document.getElementById('fuel-chart'), rows,
    FUEL_ORDER.map(f => ({ key: f, label: FUEL_NAMES[LANG][f], color: fuelColor(f) })), {
      height: 290, tipDigits: 1,
      totalLabel: LANG === 'bn' ? 'মোট' : 'Total',
      xlabel: (r) => fmtDate(r.x, { day: 'numeric', month: 'short' }),
      xtip: (r) => fmtDate(r.x),
      yfmt: (v) => fmt(v),
    });
  document.getElementById('fuel-note').textContent = t('mkwh');

  lineChart(document.getElementById('cost-chart'), rows, 'cost', {
    color: C.s[3], area: true, digits: 2, label: t('costUnit'), height: 230,
    xlabel: (r) => fmtDate(r.x, { day: 'numeric', month: 'short' }),
    xtip: (r) => fmtDate(r.x),
    yfmt: (v) => fmt(v, 1),
  });

  const last = rows[rows.length - 1];
  const total = FUEL_ORDER.reduce((a, f) => a + (last[f] || 0), 0) || 1;
  hBars(document.getElementById('fuelmix-latest'),
    FUEL_ORDER.map(f => ({ label: FUEL_NAMES[LANG][f], value: last[f] || 0, color: fuelColor(f) }))
      .filter(i => i.value > 0)
      .sort((a, b) => b.value - a.value),
    { fmtValue: (v) => `${pct(v / total)}`, valueLabel: t('share') });
}

function renderZones() {
  const z = D.zones;
  if (!z) return;
  const peak = z.nldc_evening_peak || [];
  const last = peak[peak.length - 1];
  const zoneKeys = z.zones || [];

  const table = document.getElementById('zone-table');
  if (last) {
    const tot = zoneKeys.reduce((a, k) => a + ((last[k] && last[k][1]) || 0), 0) || 1;
    const rows = zoneKeys
      .map(k => ({ k, demand: last[k] && last[k][0], shed: (last[k] && last[k][1]) || 0 }))
      .sort((a, b) => b.shed - a.shed);
    table.innerHTML =
      `<thead><tr><th>${t('zoneName')}</th><th class="num">${t('demand').replace(' (প্রকাশিত)', '').replace(' (published)', '')}</th>` +
      `<th class="num">${t('loadshed')}</th><th class="num">${t('zoneShare')}</th></tr></thead><tbody>` +
      rows.map(r => `<tr><td>${zoneName(r.k)}</td><td class="num">${fmt(r.demand)}</td>` +
        `<td class="num">${fmt(r.shed)}</td><td class="num">${pct(r.shed / tot)}</td></tr>`).join('') +
      `</tbody>`;
  }

  const daily = (z.areawise_daily || []).slice(-365);
  sparkGrid(document.getElementById('zone-chart'),
    zoneKeys.map(k => {
      const vals = daily.map(d => (d[k] && d[k][1]) || 0);
      return {
        title: zoneName(k),
        stat: `${fmt(Math.max(...vals, 0))} ${t('mw')}`,
        values: vals,
      };
    }), { color: C.loadshed });
}

function renderTrend() {
  const m = D.monthly || [];
  const start = (D.integrity && D.integrity.reporting_start) || '2022-01-01';
  const rows = m.map(r => ({ x: r.month, v: r.max_loadshed || 0, month: r.month }));
  barChart(document.getElementById('monthly-chart'), rows, 'v', {
    height: 280, color: C.loadshed, label: t('loadshed'),
    missing: (r) => r.month < start.slice(0, 7),
    xlabel: (r) => fmtDate(r.month + '-01', { month: 'short', year: 'numeric' }),
    xtip: (r) => fmtDate(r.month + '-01', { month: 'long', year: 'numeric' }),
  });
  const host = document.getElementById('monthly-chart');
  const lg = document.createElement('div');
  lg.className = 'legend';
  lg.innerHTML =
    `<span class="legend-item"><i class="swatch" style="background:${C.loadshed}"></i>${t('loadshed')} (${t('mw')})</span>` +
    `<span class="legend-item"><i class="swatch" style="background:${C.grid}"></i>${t('notReported')}</span>`;
  host.appendChild(lg);
}

function renderTrust() {
  const g = D.integrity;
  const host = document.getElementById('trust-body');
  if (!g) { host.innerHTML = `<p class="loading">${t('noData')}</p>`; return; }

  const idRate = pct(g.demand_identity && g.demand_identity.rate);
  const enRate = pct(g.energy_identity && g.energy_identity.rate);
  const sameDays = g.areawise_days_compared || 0;
  const matched = (g.areawise_vs_nldc || [])
    .filter(p => p.nldc_peak_loadshed === p.areawise_loadshed).length;

  const cov = (g.completeness || []).filter(c => +c.year >= 2015);
  const covRows = cov.map(c =>
    `<tr><td class="num">${fmtYear(c.year)}</td><td class="num">${fmt(c.rows)}</td>` +
    `<td class="num">${fmt(c.with_demand)}</td><td class="num">${fmt(c.nonzero_loadshed)}</td>` +
    `<td class="num">${pct(c.rows ? c.nonzero_loadshed / c.rows : 0)}</td></tr>`).join('');

  host.innerHTML = `
    <div class="grid g2">
      <div class="note">
        <div class="note-title">① ${t('identityTitle')}</div>
        ${t('identityBody').replace('{rate}', idRate).replace('{erate}', enRate)}
      </div>
      <div class="note">
        <div class="note-title">② ${t('sameSourceTitle')}</div>
        ${t('sameSourceBody').replace('{match}', fmt(matched)).replace('{days}', fmt(sameDays))}
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="note-title">③ ${t('coverageTitle')}</div>
      <p style="color:var(--text2);font-size:.9rem;margin:6px 0 14px">${t('coverageBody')}</p>
      <div class="tablewrap"><table>
        <thead><tr><th class="num">${t('year')}</th><th class="num">${t('rows')}</th>
        <th class="num">${t('withDemand')}</th><th class="num">${t('nonzeroShed')}</th>
        <th class="num">%</th></tr></thead>
        <tbody>${covRows}</tbody>
      </table></div>
    </div>

    <div class="note warn" style="margin-top:14px">
      <div class="note-title">④ ${t('outlierTitle')}</div>
      ${t('outlierBody').replace('{n}', fmt(g.outliers && g.outliers.count))}
    </div>`;
}

function renderSources() {
  const m = D.meta;
  if (!m) return;
  document.getElementById('source-list').innerHTML = (m.sources || []).map(s =>
    `<li><a href="${s.url}" target="_blank" rel="noopener">${LANG === 'bn' ? s.name_bn : s.name_en}</a></li>`
  ).join('');
  document.getElementById('footer-note').textContent = t('footerNote');
}

/* ══════════════════════════════════ map ══════════════════════════════════ */

let MAP = null, LAYERS = {}, LAYER_CTRL = null;

function zoneValues(metric) {
  const peak = (D.zones && D.zones.nldc_evening_peak) || [];
  const last = peak[peak.length - 1];
  const out = {};
  if (!last) return out;
  (D.zones.zones || []).forEach(k => {
    const v = last[k];
    out[k] = v ? (metric === 'loadshed' ? v[1] : v[0]) : null;
  });
  return out;
}

/** Rank-based bins: with only nine zones a linear scale leaves most of the
 *  ramp unused, so each zone is placed by its position in the sorted order.
 *  Zeros always take the lowest step, so "no load-shed" reads as no load-shed. */
function makeBinner(values, ramp) {
  const nums = values.filter(v => v !== null && v !== undefined && v > 0)
                     .sort((a, b) => a - b);
  return (v) => {
    if (v === null || v === undefined) return '#20242f';
    if (v <= 0 || !nums.length) return ramp[0];
    const rank = nums.filter(n => n < v).length;
    const i = Math.min(ramp.length - 1,
                       Math.floor((rank / Math.max(nums.length - 1, 1)) * (ramp.length - 1)));
    return ramp[i];
  };
}

function renderMap() {
  const holder = document.getElementById('map-el');
  if (!MAP) {
    // NB: the enclosing <section> owns id="map" for the nav anchor, so the
    // Leaflet container needs a distinct id or L.map() grabs the section.
    holder.innerHTML = '<div id="map-canvas"></div>';
    MAP = L.map('map-canvas', { scrollWheelZoom: false, zoomControl: true })
      .setView([23.75, 90.4], 7);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 12, minZoom: 6,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    }).addTo(MAP);
  }
  // A re-render (metric switch, language switch) rebuilds every overlay, so the
  // previous layers and their control must come off first or they stack up.
  Object.values(LAYERS).forEach(l => { if (l && MAP.hasLayer(l)) MAP.removeLayer(l); });
  LAYERS = {};
  if (LAYER_CTRL) { MAP.removeControl(LAYER_CTRL); LAYER_CTRL = null; }

  const metric = D.mapMetric || 'loadshed';
  const ramp = metric === 'loadshed' ? RAMP_SHED : RAMP_DEM;
  const vals = zoneValues(metric);
  const max = Math.max(...Object.values(vals).filter(v => v !== null), 1);
  const binner = makeBinner(Object.values(vals), ramp);

  if (D.districts) {
    LAYERS.districts = L.geoJSON(D.districts, {
      style: (feat) => ({
        fillColor: binner(vals[feat.properties.zone]),
        fillOpacity: 0.75, color: '#2e3350', weight: 1,
      }),
      onEachFeature: (feat, layer) => {
        const p = feat.properties;
        const name = LANG === 'bn' && p.name_bn ? p.name_bn : p.name_en;
        const v = vals[p.zone];
        layer.bindPopup(
          `<b>${name}</b><br>${t('zone')}: ${zoneName(p.zone)}<br>` +
          `${metric === 'loadshed' ? t('loadshed') : t('demand')}: <b>${fmt(v)}</b> ${t('mw')}`);
        layer.on('mouseover', () => layer.setStyle({ weight: 2, color: '#6c8cff' }));
        layer.on('mouseout', () => layer.setStyle({ weight: 1, color: '#2e3350' }));
      },
    }).addTo(MAP);
  }

  // power plants — size by capacity, colour by whether they ran
  if (D.plants && D.plants.plants) {
    const g = L.layerGroup();
    D.plants.plants.forEach(p => {
      if (p.lat === null || p.lon === null) return;
      const cap = p.capacity_mw || 0;
      const ran = (p.peak_mw || 0) > 0;
      const m = L.circleMarker([p.lat, p.lon], {
        radius: Math.max(4, Math.min(16, Math.sqrt(cap) * 0.55)),
        color: C.surface, weight: 2,
        fillColor: ran ? C.supply : C.loadshed, fillOpacity: 0.88,
      });
      m.bindPopup(
        `<b>${p.name}</b><br>${t('zone')}: ${zoneName(p.zone)}<br>` +
        `${t('capacity')}: <b>${fmt(cap)}</b> ${t('mw')}<br>` +
        `${t('generated')}: <b>${fmt(p.peak_mw)}</b> ${t('mw')}<br>` +
        (ran ? '' : `${t('reason')}: <b>${REASON_NAMES[LANG][p.reason] || p.reason}</b><br>`) +
        (p.remarks ? `<i style="color:#8890b0">${p.remarks}</i><br>` : '') +
        (p.geo !== 'osm' ? `<span style="color:#8890b0;font-size:.9em">${t('approx')}</span>` : ''));
      g.addLayer(m);
    });
    LAYERS.plants = g.addTo(MAP);
  }

  // grid substations — size by peak load served
  if (D.subs && D.subs.substations) {
    const g = L.layerGroup();
    D.subs.substations.forEach(s => {
      if (s.lat === null || s.lon === null) return;
      const m = L.circleMarker([s.lat, s.lon], {
        radius: Math.max(3, Math.min(11, Math.sqrt(s.load_mw || 1) * 0.55)),
        color: C.surface, weight: 1.5, fillColor: C.s[6], fillOpacity: 0.8,
      });
      m.bindPopup(`<b>${s.name}</b><br>${t('load')}: <b>${fmt(s.load_mw)}</b> ${t('mw')}` +
        (s.hour !== null && s.hour !== undefined ? `<br>${t('at')}: ${fmt(s.hour)}:00` : '') +
        (s.geo !== 'osm' ? `<br><span style="color:#8890b0;font-size:.9em">${t('approx')}</span>` : ''));
      g.addLayer(m);
    });
    LAYERS.subs = g;
  }

  const overlays = {};
  if (LAYERS.districts) overlays[t('layerDistricts')] = LAYERS.districts;
  if (LAYERS.plants) overlays[t('layerPlants')] = LAYERS.plants;
  if (LAYERS.subs) overlays[t('layerSubs')] = LAYERS.subs;
  LAYER_CTRL = L.control.layers(null, overlays, { collapsed: false }).addTo(MAP);

  document.getElementById('map-ramp').innerHTML =
    `<span>${t('low')}</span><span class="ramp-bar">` +
    ramp.map(c => `<i style="background:${c}"></i>`).join('') +
    `</span><span>${t('high')} (${fmt(max)} ${t('mw')})</span>`;
  document.querySelector('[data-i18n="mapNote"]').textContent = t('mapNote');
}

function renderMapSeg() {
  const seg = document.getElementById('map-seg');
  D.mapMetric = D.mapMetric || 'loadshed';
  seg.innerHTML = [['loadshed', 'mapLoadshed'], ['demand', 'mapDemand']].map(([k, lbl]) =>
    `<button type="button" data-metric="${k}" aria-pressed="${D.mapMetric === k}">${t(lbl)}</button>`).join('');
  seg.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    D.mapMetric = b.dataset.metric;
    renderMapSeg();
    renderMap();
  }));
}

/* ══════════════════════════════════ boot ═════════════════════════════════ */

function renderAll() {
  renderStatic();
  renderUpdated();
  renderRangeSeg();
  renderNow();
  renderWhy();
  renderMapSeg();
  renderMap();
  renderFuel();
  renderZones();
  renderTrend();
  renderTrust();
  renderSources();
}

document.querySelectorAll('[data-lang-btn]').forEach(b => {
  b.addEventListener('click', () => {
    LANG = b.dataset.langBtn;
    localStorage.setItem('bd-elec-lang', LANG);
    renderAll();
  });
});

let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    renderHourly(D.range || 7);
    renderWhy();
    renderFuel();
    renderZones();
    renderTrend();
  }, 220);
});

loadAll().then(renderAll).catch(err => {
  console.error(err);
  document.getElementById('updated-text').textContent = 'Failed to load data.';
});
