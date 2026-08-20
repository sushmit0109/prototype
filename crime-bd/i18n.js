/* ------------------------------------------------------------------
   English and Bangla strings for the dashboard.

   The Bangla is written as Bangla, not translated word for word from the
   English — sentence order, verb placement and the choice between
   এখতিয়ার and অধিক্ষেত্র follow how these things are actually written in
   Bangladeshi reporting, and the offence names are the ones the police
   use on their own Bangla returns.

   Numerals switch with the language: Bangla prose with Western digits
   reads like a machine wrote it.
   ------------------------------------------------------------------ */
'use strict';

const BN_DIGITS = ['০','১','২','৩','৪','৫','৬','৭','৮','৯'];
const toBnDigits = (s) => String(s).replace(/[0-9]/g, (d) => BN_DIGITS[+d]);

const I18N = {
  en: {
    dir: 'ltr',
    langName: 'বাংলা',
    months: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
    monthsLong: ['January','February','March','April','May','June','July','August','September','October','November','December'],

    title: 'Bangladesh Crime Statistics',
    intro: 'Every offence recorded by Bangladesh Police, by the jurisdiction that recorded it and the month it was filed. Click a division or a city to follow it through every chart; drag the timeline to change the period.',
    backToPrototypes: '← Prototypes',
    themeBtn: '◐ Theme',

    offence: 'Offence',
    allOffences: 'All offences',
    // Dacoity, robbery and burglary reported as one family
    robberyGroup: 'Dacoity, robbery & burglary',
    robberyGroupShort: 'Robbery & burglary',
    nOffences: (n) => `${n} offences`,
    selectAll: 'Select all',
    clearSel: 'Clear',
    measure: 'Measure',
    cases: 'Cases',
    per100k: 'Per 100k',
    showing: 'Showing',
    resetAll: 'Reset all',
    bangladesh: 'Bangladesh',

    kCases: 'Cases',
    kPerMonth: 'Per month',
    kHighest: 'Highest',
    kMostCases: 'Most cases',
    kHighestRate: 'Highest rate',
    kBusiest: 'Busiest month',
    monthsCounted: (n) => `${n} months counted`,
    perHundredK: 'per 100k residents / yr',
    vsPrevious: (n) => `vs the previous ${n} counted months`,
    casesPerMonth: 'cases per month',
    casesWord: 'cases',
    per100kYr: 'per 100k / yr',
    population: 'Population',
    share: 'Share',

    timeline: 'Timeline',
    timelineHint: 'Monthly cases for the current selection. Bands behind the line mark who was governing; drag across the chart to choose a period, click once to clear.',
    allYears: 'All years',
    last12: 'Last 12 months',
    dragHint: 'Drag the chart to choose a period',
    handoverKey: 'Handover month — split between governments',
    handoverNote: 'handover month — see how it is apportioned below',

    divisionsTitle: 'Divisions — Range jurisdictions',
    divisionsHint: 'The eight Ranges police everything in a division outside its metropolitan cities. Click one to filter the whole dashboard to it.',
    citiesTitle: 'Cities — metropolitan forces',
    citiesHint: 'Eight metropolitan forces, each policing one city. Colour is the value. Markers mark where each city is, not how far its jurisdiction reaches — a metropolitan area is a subset of its district, and those boundaries are not published as open data. Click one to filter.',
    markerNote: "Marker shows the city, not the jurisdiction's extent · click to filter",
    equalBins: 'equal-count bins',
    divisionWord: 'division',
    railNote: 'Rail network — no territory or population',
    cityForce: 'division · city force',
    rangeForce: 'division · Range',

    ranksTitle: 'Jurisdictions ranked',
    ranksHint: 'All seventeen reporting units for the current offence and period. Click one to filter.',
    ranksHintRate: 'Cases per 100,000 residents a year. Railway Range has no population and is omitted.',
    offencesTitle: 'Offences ranked',
    offencesHint: (scope) => `What ${scope}'s caseload is made of over the selected period. Click one to filter.`,
    trendNote: 'trend compares the two halves of the selected period',
    clickToFilter: 'click to filter',

    seasonTitle: 'Year against year',
    grid: 'Grid',
    lines: 'Lines',
    seasonHintLines: 'Every year on the same twelve months, so a seasonal shape separates from a rising or falling level.',
    seasonHintGrid: 'One cell per month. Reading down a column shows how a given month changed year on year; reading across a row shows that year’s season.',
    notPublished: 'grey = not yet published',
    runsTo: (m) => `2026 runs to ${m}`,

    smallTitle: 'Every offence, month by month',
    byYear: 'By year',
    byGovernment: 'By government',
    smallHintYear: (scope) => `Each year on the same twelve months, one panel per offence, for ${scope}. Each panel keeps its own vertical scale. Click a panel to filter to that offence.`,
    smallHintGov: (scope) => `The whole record for ${scope}, one panel per offence, with each government shaded behind it. Each panel keeps its own vertical scale. Click a panel to filter to that offence.`,
    rulesAreHandovers: 'vertical rules are the two handovers',
    maxWord: 'max',

    tenureTitle: 'Across the two transitions',
    tenureHint: 'Recorded crime under each government, as cases per month. The periods are of very different lengths, so totals would say nothing.',
    tenureScope: 'This panel always compares the full periods, so it does not follow the timeline selection; the offence and area filters do apply.',
    handoverAt: (m) => `Change in cases per month at the ${m} handover.`,
    noChange: 'no change',
    monthsWord: 'months',

    sourceLead: 'Source:',
    sourceBody: 'Bangladesh Police, monthly Crime Statistics —',
    sourceTail: 'Division boundaries from geoBoundaries (BGD ADM1); population from the 2022 Population and Housing Census (BBS).',
    caveatLead: 'Reading this data.',
    caveatBody: 'These are cases <em>recorded</em> by police, not crimes committed. A figure rises when more cases are filed — which can mean more offending, better reporting, or a policing drive — and falls when people stop coming forward. <strong>2020 is left out of the analysis</strong> because the Covid general holiday halved recorded crime for months and drags every comparison with it; the data is kept in the repository. <em>Other Cases</em> carries about a third of all cases and is not broken down at source. <em>Recovery</em> categories — arms, explosives, narcotics, smuggling — count police-initiated seizures, so they track enforcement effort as much as underlying activity. Per-100,000 rates use city-corporation populations for metropolitan forces and division-minus-cities for Ranges; police boundaries do not follow those exactly, so rates are sound for comparison but not exact. Railway Range polices the rail network nationwide, so it appears in the rankings but has no territory on the map and no population denominator.',
    footMeta: (a, b, n, u, c, total, first) =>
      `Analysis covers ${a} to ${b} — ${n} monthly sheets across ${u} jurisdictions and ${c} offence categories, counting dacoity, robbery and burglary as one. ${total} sheets from ${first} are held in the repository, with all fifteen source columns intact.`,

    tenures: { t1: 'Awami League', t2: 'Interim government', t3: 'Elected government' },
    tenuresShort: { t1: 'AL', t2: 'Interim', t3: 'Elected' },

    crimes: ['Dacoity','Robbery','Murder','Speedy Trial','Riot','Woman & Child Repression','Kidnapping','Police Assault','Burglary','Theft','Other Cases','RC Arms Act','RC Explosive Act','RC Narcotics','RC Smuggling'],
    crimesShort: ['Dacoity','Robbery','Murder','Speedy Trial','Riot','Woman & child','Kidnapping','Police Assault','Burglary','Theft','Other Cases','Arms Act','Explosive Act','Narcotics','Smuggling'],
  },

  bn: {
    dir: 'ltr',
    langName: 'English',
    months: ['জানু','ফেব্রু','মার্চ','এপ্রিল','মে','জুন','জুলাই','আগস্ট','সেপ্ট','অক্টো','নভে','ডিসে'],
    monthsLong: ['জানুয়ারি','ফেব্রুয়ারি','মার্চ','এপ্রিল','মে','জুন','জুলাই','আগস্ট','সেপ্টেম্বর','অক্টোবর','নভেম্বর','ডিসেম্বর'],

    title: 'বাংলাদেশের অপরাধ পরিসংখ্যান',
    intro: 'বাংলাদেশ পুলিশের নথিভুক্ত প্রতিটি অপরাধ — কোন এখতিয়ারে মামলা হয়েছে আর কোন মাসে, সেই হিসাবে সাজানো। কোনো বিভাগ বা মহানগরে ক্লিক করলে প্রতিটি চার্টে সেটিই দেখা যাবে; সময়রেখা টেনে সময়সীমা বদলানো যায়।',
    backToPrototypes: '← প্রোটোটাইপ',
    themeBtn: '◐ থিম',

    offence: 'অপরাধ',
    allOffences: 'সব ধরনের অপরাধ',
    robberyGroup: 'ডাকাতি, দস্যুতা ও সিঁধেল চুরি',
    robberyGroupShort: 'ডাকাতি-দস্যুতা-সিঁধেল চুরি',
    nOffences: (n) => `${n} ধরনের অপরাধ`,
    selectAll: 'সবগুলো',
    clearSel: 'বাছাই মুছুন',
    measure: 'পরিমাপ',
    cases: 'মামলা',
    per100k: 'প্রতি লাখে',
    showing: 'দেখানো হচ্ছে',
    resetAll: 'সব আগের অবস্থায়',
    bangladesh: 'সারা দেশ',

    kCases: 'মামলা',
    kPerMonth: 'মাসে গড়ে',
    kHighest: 'সর্বোচ্চ',
    kMostCases: 'সবচেয়ে বেশি মামলা',
    kHighestRate: 'সর্বোচ্চ হার',
    kBusiest: 'সবচেয়ে বেশি মামলার মাস',
    monthsCounted: (n) => `${n} মাসের হিসাব`,
    perHundredK: 'প্রতি লাখ মানুষে, বছরে',
    vsPrevious: (n) => `হিসাবে ধরা আগের ${n} মাসের তুলনায়`,
    casesPerMonth: 'মাসে গড় মামলা',
    casesWord: 'মামলা',
    per100kYr: 'প্রতি লাখে, বছরে',
    population: 'জনসংখ্যা',
    share: 'অংশ',

    timeline: 'সময়রেখা',
    timelineHint: 'বাছাই করা অংশের মাসভিত্তিক মামলা। রেখার পেছনের রঙিন পটি বলছে তখন কারা ক্ষমতায় ছিল। চার্টের উপর টেনে সময়সীমা বেছে নিন, একবার ক্লিক করলে তা মুছে যাবে।',
    allYears: 'সব বছর',
    last12: 'শেষ ১২ মাস',
    dragHint: 'সময়সীমা বাছতে চার্টের উপর টানুন',
    handoverKey: 'হস্তান্তরের মাস — দুই সরকারের মধ্যে ভাগ করা',
    handoverNote: 'ক্ষমতা হস্তান্তরের মাস — কীভাবে ভাগ করা হয়েছে তা নিচে দেখুন',

    divisionsTitle: 'বিভাগ — রেঞ্জ এখতিয়ার',
    divisionsHint: 'মহানগর এলাকার বাইরে গোটা বিভাগের দায়িত্ব আটটি রেঞ্জের। যেকোনো একটিতে ক্লিক করলে পুরো ড্যাশবোর্ড সেই রেঞ্জেই সীমাবদ্ধ হবে।',
    citiesTitle: 'মহানগর — মেট্রোপলিটন পুলিশ',
    citiesHint: 'আটটি মেট্রোপলিটন পুলিশ, প্রত্যেকে একটি করে শহরের দায়িত্বে। রঙেই সংখ্যাটা বোঝানো হয়েছে। চিহ্নগুলো শহরের অবস্থান দেখায়, এখতিয়ারের বিস্তার নয় — মহানগর এলাকা জেলার একটি অংশমাত্র, আর সেই সীমানা উন্মুক্ত তথ্য হিসেবে প্রকাশিত নয়। বাছাই করতে ক্লিক করুন।',
    markerNote: 'চিহ্নটি শহরের অবস্থান, এখতিয়ারের বিস্তার নয় · বাছাই করতে ক্লিক করুন',
    equalBins: 'সমান-সংখ্যক ভাগ',
    divisionWord: 'বিভাগ',
    railNote: 'রেল নেটওয়ার্ক — নির্দিষ্ট এলাকা বা জনসংখ্যা নেই',
    cityForce: 'বিভাগ · মহানগর পুলিশ',
    rangeForce: 'বিভাগ · রেঞ্জ',

    ranksTitle: 'এখতিয়ার অনুযায়ী ক্রম',
    ranksHint: 'বাছাই করা অপরাধ ও সময়ের জন্য সতেরোটি ইউনিটই। বাছাই করতে ক্লিক করুন।',
    ranksHintRate: 'প্রতি লাখ মানুষে বছরে কত মামলা। রেলওয়ে রেঞ্জের নিজস্ব জনসংখ্যা নেই, তাই সেটি বাদ।',
    offencesTitle: 'অপরাধ অনুযায়ী ক্রম',
    offencesHint: (scope) => `বাছাই করা সময়ে ${scope}-এর মামলাগুলো কী কী নিয়ে গড়া। বাছাই করতে ক্লিক করুন।`,
    trendNote: 'ধারা মানে বাছাই করা সময়ের প্রথমার্ধ ও শেষার্ধের তুলনা',
    clickToFilter: 'বাছাই করতে ক্লিক করুন',

    seasonTitle: 'বছরে বছরে তুলনা',
    grid: 'ছক',
    lines: 'রেখা',
    seasonHintLines: 'প্রতিটি বছরকে একই বারো মাসের উপর বসানো হয়েছে, যাতে মৌসুমি ওঠানামা আর সার্বিক বাড়া-কমা আলাদা করে বোঝা যায়।',
    seasonHintGrid: 'প্রতিটি ঘর এক মাস। একটি কলাম ধরে নিচে নামলে দেখা যায় ওই মাসটি বছরে বছরে কেমন বদলেছে; একটি সারি ধরে ডানে গেলে দেখা যায় সেই বছরের মৌসুমি চেহারা।',
    notPublished: 'ধূসর = এখনও প্রকাশিত হয়নি',
    runsTo: (m) => `২০২৬ সালের হিসাব ${m} পর্যন্ত`,

    smallTitle: 'প্রতিটি অপরাধ, মাসে মাসে',
    byYear: 'বছর ধরে',
    byGovernment: 'সরকার ধরে',
    smallHintYear: (scope) => `${scope}-এর জন্য প্রতিটি অপরাধের আলাদা প্যানেল, প্রতিটি বছর একই বারো মাসের উপর। প্রতিটি প্যানেলের নিজস্ব মাপকাঠি। কোনো প্যানেলে ক্লিক করলে সেই অপরাধেই সীমাবদ্ধ হবে।`,
    smallHintGov: (scope) => `${scope}-এর পুরো সময়কাল, প্রতিটি অপরাধের আলাদা প্যানেল, পেছনে কোন সরকার কখন ছিল তা রঙে দেখানো। প্রতিটি প্যানেলের নিজস্ব মাপকাঠি। কোনো প্যানেলে ক্লিক করলে সেই অপরাধেই সীমাবদ্ধ হবে।`,
    rulesAreHandovers: 'খাড়া দাগ দুটি ক্ষমতা হস্তান্তরের মুহূর্ত',
    maxWord: 'সর্বোচ্চ',

    tenureTitle: 'দুই দফা ক্ষমতা হস্তান্তরের হিসাব',
    tenureHint: 'প্রতিটি সরকারের আমলে নথিভুক্ত অপরাধ, মাসে গড় মামলা হিসেবে। সময়কালগুলোর দৈর্ঘ্য এক নয়, তাই মোট সংখ্যা দিয়ে তুলনা চলে না।',
    tenureScope: 'এই অংশটি সবসময় পুরো সময়কাল ধরেই তুলনা করে, তাই সময়রেখার বাছাই এখানে খাটে না; অপরাধ ও এলাকার বাছাই অবশ্য খাটে।',
    handoverAt: (m) => `${m}-এর হস্তান্তরে মাসিক গড় মামলার পরিবর্তন।`,
    noChange: 'অপরিবর্তিত',
    monthsWord: 'মাস',

    sourceLead: 'তথ্যসূত্র:',
    sourceBody: 'বাংলাদেশ পুলিশের মাসভিত্তিক অপরাধ পরিসংখ্যান —',
    sourceTail: 'বিভাগের সীমানা geoBoundaries (BGD ADM1) থেকে; জনসংখ্যা ২০২২ সালের আদমশুমারি (বিবিএস) থেকে।',
    caveatLead: 'তথ্যগুলো কীভাবে পড়বেন।',
    caveatBody: 'এগুলো পুলিশের <em>নথিভুক্ত</em> মামলা, সংঘটিত অপরাধ নয়। মামলার সংখ্যা বাড়ে যখন বেশি মামলা হয় — তার কারণ হতে পারে অপরাধ বেড়েছে, কিংবা মানুষ আগের চেয়ে বেশি অভিযোগ করছে, কিংবা পুলিশ বিশেষ অভিযান চালাচ্ছে — আর কমে যখন মানুষ অভিযোগ করা ছেড়ে দেয়। <strong>২০২০ সাল এই বিশ্লেষণের বাইরে রাখা হয়েছে</strong>, কারণ কোভিডের সাধারণ ছুটিতে কয়েক মাস ধরে নথিভুক্ত অপরাধ অর্ধেকে নেমেছিল এবং তা সব তুলনাকেই টেনে নামায়; তথ্যটি অবশ্য সংরক্ষিত আছে। <em>অন্যান্য মামলা</em> এককভাবে প্রায় এক-তৃতীয়াংশ, অথচ উৎসেই তার কোনো বিভাজন নেই। <em>উদ্ধার</em> সংক্রান্ত ধরনগুলো — অস্ত্র, বিস্ফোরক, মাদক, চোরাচালান — পুলিশের নিজের অভিযানে হওয়া মামলা, তাই এগুলো অপরাধের চেয়ে অভিযানের তৎপরতাই বেশি বোঝায়। প্রতি লাখের হিসাবে মহানগরের ক্ষেত্রে সিটি করপোরেশনের জনসংখ্যা আর রেঞ্জের ক্ষেত্রে বিভাগ থেকে মহানগর বাদ দিয়ে হিসাব করা হয়েছে; পুলিশি সীমানা ঠিক এভাবে চলে না, তাই হারগুলো তুলনার জন্য নির্ভরযোগ্য হলেও নিখুঁত নয়। রেলওয়ে রেঞ্জ সারা দেশের রেলপথ দেখে, তাই তালিকায় থাকলেও মানচিত্রে তার এলাকা নেই, জনসংখ্যার ভিত্তিও নেই।',
    footMeta: (a, b, n, u, c, total, first) =>
      `বিশ্লেষণের সময়কাল ${a} থেকে ${b} — ${u}টি এখতিয়ার আর ${c} ধরনের অপরাধ নিয়ে মোট ${n} মাসের হিসাব; ডাকাতি, দস্যুতা ও সিঁধেল চুরি একসঙ্গে ধরা হয়েছে। ${first} থেকে শুরু করে ${total} মাসের তথ্য সংরক্ষিত আছে, উৎসের পনেরোটি কলামই অক্ষত।`,

    tenures: { t1: 'আওয়ামী লীগ', t2: 'অন্তর্বর্তী সরকার', t3: 'নির্বাচিত সরকার' },
    tenuresShort: { t1: 'আ.লীগ', t2: 'অন্তর্বর্তী', t3: 'নির্বাচিত' },

    crimes: ['ডাকাতি','দস্যুতা','খুন','দ্রুত বিচার','দাঙ্গা','নারী ও শিশু নির্যাতন','অপহরণ','পুলিশ আক্রান্ত','সিঁধেল চুরি','চুরি','অন্যান্য মামলা','অস্ত্র আইন (উদ্ধার)','বিস্ফোরক আইন (উদ্ধার)','মাদকদ্রব্য (উদ্ধার)','চোরাচালান (উদ্ধার)'],
    crimesShort: ['ডাকাতি','দস্যুতা','খুন','দ্রুত বিচার','দাঙ্গা','নারী ও শিশু','অপহরণ','পুলিশ আক্রান্ত','সিঁধেল চুরি','চুরি','অন্যান্য','অস্ত্র','বিস্ফোরক','মাদক','চোরাচালান'],
  },
};

/* Jurisdiction and division names. Kept apart from the string table because
   they key off the data file rather than the UI. */
const NAMES_BN = {
  units: {
    DMP: ['ঢাকা মেট্রোপলিটন', 'ঢাকা মহানগর'],
    CMP: ['চট্টগ্রাম মেট্রোপলিটন', 'চট্টগ্রাম মহানগর'],
    KMP: ['খুলনা মেট্রোপলিটন', 'খুলনা মহানগর'],
    RMP: ['রাজশাহী মেট্রোপলিটন', 'রাজশাহী মহানগর'],
    BMP: ['বরিশাল মেট্রোপলিটন', 'বরিশাল মহানগর'],
    SMP: ['সিলেট মেট্রোপলিটন', 'সিলেট মহানগর'],
    GMP: ['গাজীপুর মেট্রোপলিটন', 'গাজীপুর মহানগর'],
    RPMP: ['রংপুর মেট্রোপলিটন', 'রংপুর মহানগর'],
    'Dhaka Range': ['ঢাকা রেঞ্জ', 'ঢাকা রেঞ্জ'],
    'Chittagong Range': ['চট্টগ্রাম রেঞ্জ', 'চট্টগ্রাম রেঞ্জ'],
    'Rajshahi Range': ['রাজশাহী রেঞ্জ', 'রাজশাহী রেঞ্জ'],
    'Rangpur Range': ['রংপুর রেঞ্জ', 'রংপুর রেঞ্জ'],
    'Khulna Range': ['খুলনা রেঞ্জ', 'খুলনা রেঞ্জ'],
    'Mymensingh Range': ['ময়মনসিংহ রেঞ্জ', 'ময়মনসিংহ রেঞ্জ'],
    'Sylhet Range': ['সিলেট রেঞ্জ', 'সিলেট রেঞ্জ'],
    'Barishal Range': ['বরিশাল রেঞ্জ', 'বরিশাল রেঞ্জ'],
    'Ralway Range': ['রেলওয়ে রেঞ্জ', 'রেলওয়ে রেঞ্জ'],
  },
  divisions: {
    Dhaka: 'ঢাকা', Chattogram: 'চট্টগ্রাম', Khulna: 'খুলনা', Rajshahi: 'রাজশাহী',
    Barishal: 'বরিশাল', Sylhet: 'সিলেট', Rangpur: 'রংপুর', Mymensingh: 'ময়মনসিংহ',
  },
};
