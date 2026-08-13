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
    eyebrow: 'সরকারি হিসাব থেকে',
    title: 'বাংলাদেশে বিদ্যুৎ উৎপাদন ও লোডশেডিং',
    lede: 'পিজিসিবি আর বিপিডিবি প্রতিদিন যেসব হিসাব প্রকাশ করে, সেগুলো প্রতি ঘণ্টায় জোগাড় করে এক জায়গায় সাজানো হয়েছে — কত বিদ্যুৎ তৈরি হলো, কতটা ঘাটতি থেকে গেল, কোন এলাকায় কতটা লোডশেডিং হলো, আর কেন হলো।',
    loading: 'তথ্য আসছে…',
    navNow: 'এখন', navSearch: 'আপনার এলাকা', navWhy: 'কেন হচ্ছে', navMap: 'মানচিত্র',
    navEquity: 'কে বেশি ভুগছে', navFuel: 'জ্বালানি', navZones: 'অঞ্চল',
    navSeasonal: 'আগের বছরের তুলনা', navTrend: 'সময়ের সঙ্গে', navTrust: 'হিসাব কতটা পাকা',

    vLine: 'এই মুহূর্তে দেশে <b>{mw}</b> মেগাওয়াট লোডশেডিং চলছে। গত {days} দিনে দিনের এই সময়ে সাধারণত <b>{median}</b> মেগাওয়াটের মতো হয়েছে — বেশির ভাগ দিন {lo} থেকে {hi} মেগাওয়াটের মধ্যে।',
    vPeople: 'আজ এখন পর্যন্ত যত বিদ্যুৎ দেওয়া যায়নি ({mwh} মে.ও.ঘ.), তা দিয়ে প্রায় <b>{people}</b> মানুষের একদিনের বিদ্যুৎ চলত। (মাথাপিছু বছরে ৫৬০ কিলোওয়াট-ঘণ্টা ধরে)',
    nowTitle: 'এখন যা চলছে',
    nowSub: 'পিজিসিবির সবচেয়ে সাম্প্রতিক ঘণ্টার হিসাব। সরবরাহ আর লোডশেডিং যোগ করলেই প্রকাশিত “চাহিদা” সংখ্যাটা পাওয়া যায়।',
    supply: 'সরবরাহ', loadshedding: 'লোডশেডিং', demand: 'চাহিদা (প্রকাশিত)',
    todayPeak: 'আজকের সবচেয়ে বেশি', mw: 'মেগাওয়াট', mkwh: 'মি. কিওঘ',
    asOf: 'সময়', noData: 'তথ্য নেই',
    todayChart: 'ঘণ্টায় ঘণ্টায় সরবরাহ ও লোডশেডিং',
    r7: '৭ দিন', r30: '৩০ দিন', r90: '৯০ দিন',
    smoothed: '{n} দিনের চলমান গড়',
    hoursShed: 'যত ঘণ্টা লোডশেডিং ছিল', energyShed: 'যত বিদ্যুৎ দেওয়া যায়নি',
    mwh: 'মে.ও.ঘ.',

    searchTitle: 'আপনার এলাকার অবস্থা',
    searchSub: 'জেলার নাম লিখে খুঁজুন — সেই জেলা কোন গ্রিড অঞ্চলে পড়ে, সেখানে কতটা লোডশেডিং হচ্ছে, আর আশপাশে কোন বিদ্যুৎকেন্দ্র ও সাবস্টেশন আছে তা দেখা যাবে। বিদ্যুৎকেন্দ্র বা সাবস্টেশনের নাম দিয়েও খোঁজা যায়।',
    searchPlaceholder: 'যেমন: রমনা, সাভার, ময়মনসিংহ, বগুড়া…',
    searchHint: 'সরকারি হিসাব জেলা ধরে নয়, ৯টি গ্রিড অঞ্চল ধরে প্রকাশ করা হয়। তাই আপনার জেলার সংখ্যাটি আসলে সেই পুরো অঞ্চলের।',
    resDistrict: 'জেলা', resZone: 'অঞ্চল', resPlant: 'বিদ্যুৎকেন্দ্র', resSubstation: 'সাবস্টেশন',
    resUpazila: 'উপজেলা/থানা', resPlace: 'এলাকা',
    areaRank: 'গত ৯০ দিনের হিসাবে {n}টি অঞ্চলের মধ্যে {zone} সবচেয়ে বেশি ভুগেছে এমন তালিকায় <b>{pos}</b> নম্বরে।',
    ownSubLoad: 'এই সাবস্টেশনে সর্বোচ্চ লোড', ownPlantOut: 'এই কেন্দ্রের উৎপাদন',
    areaShedNow: 'সন্ধ্যার সর্বোচ্চ চাহিদার সময় লোডশেডিং',
    areaRate: 'চাহিদার কত অংশ দেওয়া যায়নি',
    areaPerPerson: 'জনপ্রতি ঘাটতি', watts: 'ওয়াট',
    areaDays: 'গত ৯০ দিনে যত দিন লোডশেডিং হয়েছে',
    areaPlants: 'এই জেলার বিদ্যুৎকেন্দ্র', areaSubs: 'এই জেলার গ্রিড সাবস্টেশন',
    areaNone: 'এই জেলায় তালিকাভুক্ত কিছু পাওয়া যায়নি',
    areaTrend: 'এই অঞ্চলে গত ৯০ দিনের লোডশেডিং',
    running: 'চালু', stopped: 'বন্ধ',

    whyTitle: 'লোডশেডিং কেন হচ্ছে?',
    whySub: 'এনএলডিসির দৈনিক রিপোর্টে প্রতিটি বিদ্যুৎকেন্দ্রের পাশে কারণ লেখা থাকে। সন্ধ্যার সবচেয়ে বেশি চাহিদার সময় যেসব কেন্দ্র একেবারেই বিদ্যুৎ দেয়নি, তাদের ক্ষমতা কারণ ধরে ভাগ করে দেখানো হলো।',
    idleTitle: 'যত ক্ষমতা বসে ছিল, কারণ অনুযায়ী',
    idleTrend: 'গ্যাস না পেয়ে বসে থাকা ক্ষমতা',
    idleNote: 'সন্ধ্যার সর্বোচ্চ চাহিদার সময় সব মিলিয়ে <b>{cap}</b> মেগাওয়াট উৎপাদন ক্ষমতা একেবারেই কাজে লাগেনি — এর মধ্যে <b>{gas}</b> মেগাওয়াট বসে ছিল শুধু গ্যাস না পাওয়ায়। সূত্র: এনএলডিসির দৈনিক রিপোর্ট, {date}।',
    idleCap: 'বসে থাকা ক্ষমতা', plants: 'কেন্দ্র',
    causeTitle: 'বিপিডিবির নিজের হিসাবে ঘাটতির কারণ',
    cause_maintenance: 'রক্ষণাবেক্ষণে বন্ধ', cause_gas_lf: 'গ্যাস/তরল জ্বালানির সীমাবদ্ধতা',
    cause_kaptai: 'কাপ্তাই হ্রদে পানি কম', cause_coal: 'কয়লা সরবরাহের সীমাবদ্ধতা',
    navForecast: 'পূর্বাভাস মিলছে?',
    fcTitle: 'বিপিডিবি আগের দিন কী বলেছিল?',
    fcSub: 'বিপিডিবি প্রতিদিনের প্রতিবেদনে পরের দিনের জন্য “সম্ভাব্য লোডশেড” কত হবে তা লিখে রাখে। সেই পূর্বাভাসের পাশে পরদিন আসলে কী হলো, তা মিলিয়ে দেখা হলো। ২০২৫ সালে প্রায় প্রতিদিনই “শূন্য” লেখা হতো; ২০২৬-এ পূর্বাভাস বাস্তবের কাছাকাছি এসেছে, কিন্তু যেদিন শূন্য লেখা হয় সেদিন ভুল হওয়ার হার কমেনি — বরং ঘাটতির পরিমাণ বেড়েছে।',
    fcChart: 'পূর্বাভাস আর বাস্তব, পাশাপাশি',
    fcZero: 'যত দিন “শূন্য” লোডশেডের পূর্বাভাস', fcZeroNote: 'মোট যত দিনের হিসাব আছে',
    fcZeroUnit: 'দিনে “শূন্য” পূর্বাভাস',
    fcMissedInline: 'এর মধ্যে {n} দিন আসলে লোডশেডিং হয়েছে — গড়ে {mw} মেগাওয়াট',
    fcWorstNote: '{d} — সেদিনের পূর্বাভাস ছিল শূন্য',
    fcMissed: 'তার মধ্যে যত দিন লোডশেডিং হয়েছে', fcOfThose: 'ক্ষেত্রে',
    fcMean: 'ওই দিনগুলোয় গড় লোডশেডিং', fcWorst: 'সবচেয়ে খারাপ',
    fcForecast: 'পূর্বাভাস', fcActual: 'বাস্তবে যা হয়েছে',
    fcNote: 'পূর্বাভাসটি সন্ধ্যার সর্বোচ্চ চাহিদার সময়ের, সাবস্টেশন প্রান্তে মাপা — বাস্তব সংখ্যাটিও একই মাপে।',
    unitCostTitle: 'প্রতি ইউনিট বিদ্যুতে জ্বালানির খরচ',
    fuel_gas: 'গ্যাস', fuel_oil: 'তেল', fuel_coal: 'কয়লা',
    fuel_import: 'আমদানি', fuel_renewable: 'নবায়নযোগ্য',

    mapTitle: 'মানচিত্রে বিদ্যুৎ',
    mapSub: 'রং যত গাঢ়, সেই অঞ্চলে লোডশেডিং তত বেশি। বিন্দুগুলো বিদ্যুৎকেন্দ্র আর গ্রিড সাবস্টেশন — আকার ক্ষমতা বা লোড অনুযায়ী।',
    mapLoadshedding: 'লোডশেডিং', mapDemand: 'চাহিদা',
    mapNote: 'একটি জেলার রং আসলে সেই জেলা যে গ্রিড অঞ্চলে পড়ে তার হিসাব — অঞ্চলের ভেতরে জেলা ধরে আলাদা হিসাব প্রকাশ করা হয় না। কেন্দ্র ও সাবস্টেশনের অবস্থান ওপেনস্ট্রিটম্যাপ থেকে নাম মিলিয়ে বসানো; কিছু ক্ষেত্রে তা কাছের শহর পর্যন্তই ঠিক।',
    layerPlants: 'বিদ্যুৎকেন্দ্র', layerSubs: 'গ্রিড সাবস্টেশন', layerDistricts: 'জেলা',
    capacity: 'ক্ষমতা', generated: 'উৎপাদন', load: 'সর্বোচ্চ লোড',
    reason: 'কারণ', zone: 'অঞ্চল', district: 'জেলা', at: 'সময়',
    low: 'কম', high: 'বেশি', approx: 'অবস্থান আনুমানিক',

    equityTitle: 'ভোগান্তি কি সবার সমান?',
    equitySub: 'একই দিনে সব অঞ্চলে সমান লোডশেডিং হয় না। কোন অঞ্চলের নিজের চাহিদার কত অংশ কাটা পড়ছে, আর মাথাপিছু কতটা ঘাটতি পড়ছে — কর্তৃপক্ষের নিজের হিসাব থেকেই তা বের করা হয়েছে।',
    equityRate: 'নিজের চাহিদার কত অংশ কাটা পড়েছে',
    equityPerPerson: 'জনপ্রতি ঘাটতি (সন্ধ্যার সর্বোচ্চ চাহিদার সময়)',
    equityBurden: 'ভাগের তুলনায় বোঝা',
    equityNote: 'গত {days} দিনে সারা দেশে গড়ে চাহিদার <b>{nat}</b> অংশ কাটা পড়েছে। কিন্তু <b>{worst}</b> অঞ্চলে কাটা পড়েছে <b>{worstRate}</b> — জাতীয় গড়ের <b>{times} গুণ</b>। একই সময়ে <b>{best}</b> অঞ্চলে কাটা পড়েছে মাত্র <b>{bestRate}</b>।',
    equityCaveat: 'এই পার্থক্যের পেছনে ইচ্ছাকৃত পক্ষপাত থাকতে পারে, আবার সঞ্চালন লাইনের সীমাবদ্ধতা, শিল্পকারখানার চাপ বা কেন্দ্রের অবস্থানও কারণ হতে পারে। সংখ্যাগুলো ফলটা দেখায়, উদ্দেশ্য নয়।',
    equityTableTitle: 'অঞ্চল ধরে পুরো হিসাব',
    population: 'জনসংখ্যা', shedDays: 'যত দিন কাটা পড়েছে',
    natAvg: 'জাতীয় গড়', times: 'গুণ',
    w30: '৩০ দিন', w90: '৯০ দিন', w365: '১ বছর', wall: 'পুরো সময়',
    burdenHint: '১-এর বেশি মানে সেই অঞ্চল তার চাহিদার তুলনায় বেশি লোডশেডিং সইছে',

    fuelTitle: 'কোন জ্বালানি থেকে বিদ্যুৎ',
    fuelSub: 'প্রতিদিন যত বিদ্যুৎ তৈরি হয়, তার কতটা কোন জ্বালানি থেকে এলো (মিলিয়ন কিলোওয়াট-ঘণ্টা)।',
    fuelChart: 'জ্বালানি অনুযায়ী দৈনিক উৎপাদন',
    fuelAbs: 'পরিমাণ', fuelShare: 'অনুপাত', fuelTotal: 'মোট',
    fuel_total: 'মোট উৎপাদন',
    fuelMonthAbs: 'মাসে দিনে গড়ে কোন জ্বালানি থেকে কত (মিলিয়ন কি.ও.ঘ.)',
    fuelMonthShare: 'মাসে কোন জ্বালানির কত অংশ',
    fuelMonthNote: 'মাসের মোট নয়, দিনে গড়ে — তাই ছোট বা অসম্পূর্ণ মাস উৎপাদন কমে যাওয়ার মতো দেখায় না।',
    fuelYoyTitle: '{m} মাস, {a} সালের তুলনায় {b}',
    fuelYoyBody: 'উৎপাদন কিছুটা বেড়েছে, কিন্তু তার গঠন বদলে গেছে — গ্যাস কমেছে, জায়গা নিয়েছে কয়লা আর তেল। তেল গ্যাসের চেয়ে ইউনিটপ্রতি প্রায় পাঁচ গুণ দামি। উৎপাদন যতটুকু বেড়েছে, প্রয়োজন বেড়েছে তার চেয়ে অনেক বেশি — সেই ব্যবধানই লোডশেডিং। একই দিনগুলো মিলিয়ে তুলনা করা হয়েছে।',
    costTitle: 'প্রতি ইউনিট বিদ্যুতের উৎপাদন খরচ', costUnit: 'টাকা/কিলোওয়াট-ঘণ্টা',
    navCost: 'বিদ্যুতের দাম', navDemand: 'চাহিদা কত বেড়েছে',
    demTitle: 'চাহিদা কত দ্রুত বেড়েছে',
    demSub: 'সন্ধ্যার সর্বোচ্চ চাহিদা, বছরের একই দিনের সঙ্গে মিলিয়ে। কোনো বছর বাদ দেওয়া হয়নি — একটি রেখা আলাদা করে দেখতে নিচের রঙিন নামগুলোর ওপর মাউস রাখুন বা চাপ দিন। এটি প্রকাশিত চাহিদা, অর্থাৎ যতটা দেওয়া গেছে আর যতটা কাটা পড়েছে, দুইয়ের যোগফল।',
    demYearChart: 'সন্ধ্যার সর্বোচ্চ চাহিদা, শেষ পাঁচ বছর পাশাপাশি (৭ দিনের গড়)',
    demDecadeChart: 'বছরে সাধারণ দিনের সর্বোচ্চ চাহিদা, ২০১৬ থেকে',
    demGrowth: 'এক দশকে চাহিদা বেড়েছে', demGrowthNote: '{a} থেকে {b}',
    demCagr: 'বছরে গড়ে বেড়েছে', perYear: 'প্রতি বছর',
    demMedian: 'সাধারণ দিনের চাহিদা', demP95: 'ব্যস্ত দিনে',
    demPeak: 'এ বছরের ব্যস্ত দিনগুলোয়', demPeakNote: '{y} সালের ৯৫তম শতাংশ',
    eid: 'ঈদ',
    demHoliday: 'বছরের গভীরতম খাদগুলো ঈদের ছুটি — কারখানা বন্ধ থাকায় চাহিদা কয়েক দিনের জন্য অনেক নেমে যায়। ঈদ প্রতি বছর প্রায় ১১ দিন এগিয়ে আসে, তাই খাদটিও বছরে বছরে সরে যায়। শেষ {y} বছরের {n}টি ঈদেই এই পতন তথ্যে ধরা পড়েছে — {min} থেকে {max} শতাংশ পর্যন্ত।',
    demNote: 'সংখ্যাটি সাবস্টেশন প্রান্তে মাপা। যেহেতু “চাহিদা” = সরবরাহ + লোডশেডিং, তাই যে কারখানা বিদ্যুৎ পাবে না জেনে চাওয়াই ছেড়ে দিয়েছে, সে এই হিসাবে নেই — প্রকৃত চাহিদা এর চেয়ে বেশি।',
    costTitle2: 'একদিনের বিদ্যুৎ বানাতে কত খরচ',
    costSub: 'প্রতিদিনের রিপোর্টে মোট উৎপাদন খরচ আর প্রতি ইউনিটের খরচ — দুটোই লেখা থাকে। বছরের একই সময়ের সঙ্গে মিলিয়ে দেখলে বোঝা যায়, দাম বাড়ল কেন।',
    costUnitMode: 'প্রতি ইউনিট', costTotalMode: 'দৈনিক মোট',
    costYearUnit: 'প্রতি ইউনিট খরচ, বছরে একই দিনের তুলনায় (৭ দিনের গড়)',
    costYearTotal: 'দিনের মোট উৎপাদন খরচ, কোটি টাকা (৭ দিনের গড়)',
    costYearNote: 'দুই বছরের একই তারিখ পাশাপাশি রাখা হয়েছে, কারণ খরচ মৌসুমের সঙ্গে ওঠানামা করে।',
    costPerDay: 'সবশেষ দিনের উৎপাদন খরচ', crore: 'কোটি টাকা',
    costPerDayNote: 'শুধু জ্বালানি ও উৎপাদন', takaKwh: 'টাকা/ইউনিট',
    costPerUnit: 'প্রতি ইউনিট খরচ',
    costYoy: 'এক বছরে ইউনিটপ্রতি বেড়েছে', costYoyNote: '{a}-এর তুলনায়',
    costWhyTitle: 'দাম বাড়ল কেন — জ্বালানির দামে, নাকি জ্বালানির মিশ্রণে?',
    costMix: 'মিশ্রণ বদলানোয়', costPrice: 'জ্বালানির দাম বাড়ায়',
    costWhyBody: 'ইউনিটপ্রতি খরচ বেড়েছে {total} টাকা। এর মধ্যে {mix} টাকা এসেছে শুধু জ্বালানির মিশ্রণ বদলানোয়, আর {price} টাকা জ্বালানির দাম বাড়ায়। গ্যাসের অংশ {gasBefore}% থেকে নেমে {gasAfter}% হয়েছে — অথচ গ্যাসের নিজের দাম বাড়েনি, বরং ইউনিটপ্রতি {gasPriceBefore} টাকা থেকে {gasPriceAfter} টাকায় নেমেছে। অর্থাৎ বিশ্ববাজারের দাম নয়, দেশে গ্যাস কমে যাওয়াই মূল কারণ।',
    fuelLatest: 'সবশেষ দিনের ভাগ', share: 'অংশ',

    zonesTitle: 'কোন অঞ্চলে কেমন',
    zonesSub: 'এনএলডিসির রিপোর্টে সন্ধ্যার সর্বোচ্চ চাহিদার সময় প্রতিটি অঞ্চলে কত চাহিদা ছিল আর কতটা কাটা পড়েছে।',
    zoneTrend: 'অঞ্চল ধরে লোডশেডিংয়ের গতিপ্রকৃতি',
    zoneName: 'অঞ্চল', zoneShare: 'মোট লোডশেডিংয়ের কত ভাগ',

    seasonalTitle: 'এখনকার অবস্থা আগের বছরগুলোর তুলনায়',
    seasonalSub: 'লোডশেডিং বছরের সময় ধরে ওঠানামা করে — গরমকালে বেশি, শীতে কম। তাই এক বছর আগের সঙ্গে মেলাতে হলে বছরের একই সময়ের সঙ্গে মেলানো দরকার। নিচের রেখাগুলো প্রতিটি বছরের একই তারিখগুলো পাশাপাশি দেখায়।',
    seasonalChart: 'বছরে যেদিন যত বিদ্যুৎ দেওয়া যায়নি (৭ দিনের গড়)',
    seasonalNote: 'গত ৩০ দিনে দিনে গড়ে <b>{now}</b> মেগাওয়াট-ঘণ্টা বিদ্যুৎ দেওয়া যায়নি। {year} সালের ঠিক এই সময়ে সংখ্যাটা ছিল <b>{prev}</b> — অর্থাৎ এখন প্রায় <b>{times} গুণ {dir}</b>।',
    compareTitle: 'একই ৩০ দিন, আলাদা বছর',
    trendTitle: 'সময়ের সঙ্গে বদল',
    trendSub: 'পিজিসিবির খাতায় ২০১৫ সাল থেকে সারি আছে ঠিকই, কিন্তু ২০২২ সালের আগে প্রায় প্রতি ঘণ্টায় লোডশেডিংয়ের ঘরে “০” বসানো। তাই ওই সময়টাকে শূন্য না ধরে “প্রকাশ করা হয়নি” হিসেবে আলাদা করে দেখানো হয়েছে।',
    monthlyTitle: 'মাস ধরে লোডশেডিং',
    mwhPerDay: 'মেওঘ/দিন', hoursUnit: 'ঘণ্টা',
    mMean: 'গড় (মেওঘ/দিন)', mMedian: 'মধ্যমা', mP95: '৯৫তম শতাংশ (মেওয়া)',
    mMax: 'সর্বোচ্চ (মেওয়া)', mHours: 'ঘণ্টা/দিন',
    mTitle_mean_energy_shed_mwh: 'মাসে দিনে গড়ে যত বিদ্যুৎ দেওয়া যায়নি',
    mTitle_median_energy_shed_mwh: 'মাসের সাধারণ একটি দিনে যত দেওয়া যায়নি',
    mTitle_p95_loadshed: 'মাসের খারাপ দিনগুলোর মাত্রা (৯৫তম শতাংশ)',
    mTitle_max_loadshed: 'মাসের সবচেয়ে খারাপ এক ঘণ্টা',
    mTitle_mean_hours_shed: 'দিনে গড়ে কত ঘণ্টা লোডশেডিং ছিল',
    mNote_mean_energy_shed_mwh: 'মোট ঘাটতিকে দিন দিয়ে ভাগ করা। মাসের দৈর্ঘ্য বা অসম্পূর্ণ মাসে বিভ্রান্ত করে না — মানুষ আসলে যত বিদ্যুৎ পায়নি, এটাই তার পরিমাপ।',
    mNote_median_energy_shed_mwh: 'মাসের মাঝামাঝি দিনটি। কয়েকটি ভয়াবহ দিন গড়কে টেনে তোলে; মধ্যমা বলে সাধারণ দিনটা কেমন ছিল।',
    mNote_p95_loadshed: 'মাসের সবচেয়ে খারাপ দিনগুলোর মাত্রা, তবে একটিমাত্র ভুল সংখ্যায় নষ্ট হয় না।',
    mNote_max_loadshed: 'সবচেয়ে ভঙ্গুর মাপকাঠি — একটিমাত্র ভুল টাইপ করা ঘণ্টা পুরো মাসের ছবি বদলে দিতে পারে। তুলনার জন্য এটি ব্যবহার না করাই ভালো, তবু লুকানো হয়নি।',
    mNote_mean_hours_shed: 'কত গভীর নয়, কত দীর্ঘ — দিনে কত ঘণ্টা বিদ্যুৎ ছিল না।',
    mDisagree: 'মাপকাঠি বদলালে উত্তরও বদলায়: গড় ঘাটতির হিসাবে সবচেয়ে খারাপ মাস <b>{a}</b>, কিন্তু “সর্বোচ্চ মেগাওয়াট” ধরলে <b>{b}</b>। তাই আমরা কোনো একটি বেছে না নিয়ে সবগুলোই দিচ্ছি — আপনি নিজে মিলিয়ে দেখুন।',
    mAgree: 'এই মুহূর্তে সব মাপকাঠিই একই মাসকে সবচেয়ে খারাপ বলছে।',
    notReported: 'প্রকাশ করা হয়নি',

    trustTitle: 'এই হিসাব কতটা পাকা',
    trustSub: 'এখানে কর্তৃপক্ষের নিজের সংখ্যাই তুলে ধরা হয়েছে। তবে সংখ্যাগুলো কীভাবে বানানো হয়, আর কোথায় দুই সরকারি সূত্র নিজেরাই মেলে না — সেটাও জানা দরকার।',
    identityTitle: 'প্রকাশিত “চাহিদা” আসলে একটা যোগফল, আলাদা কোনো মাপ নয়',
    identityBody: 'পিজিসিবির ঘণ্টাভিত্তিক তালিকায় {rate} ক্ষেত্রে চাহিদা = সরবরাহ + লোডশেডিং, একেবারে হুবহু। বিপিডিবির দৈনিক রিপোর্টেও শক্তির হিসাবে চাহিদা = উৎপাদন + যা দেওয়া যায়নি, {erate} ক্ষেত্রে হুবহু মেলে। মানে “চাহিদা” আলাদা করে মাপা হয় না — লোডশেডিংয়ের সংখ্যা থেকেই সেটা বানানো। তাই এই দুটো সংখ্যা দিয়ে একে অন্যকে যাচাই করা যায় না, আর আসল চাহিদা এর চেয়ে বেশিও হতে পারে।',
    sameSourceTitle: 'দুটো আলাদা পাতা, সংখ্যা একটাই',
    sameSourceBody: 'বিপিডিবির “area-wise demand” পাতা আর এনএলডিসির দৈনিক রিপোর্টের সন্ধ্যাকালীন হিসাব — যত দিন মিলিয়ে দেখা হয়েছে ({days} দিন), তার {match} দিনেই সংখ্যা অবিকল এক। অর্থাৎ এটা দ্বিতীয় কোনো স্বাধীন সূত্র নয়, একই হিসাবই আরেক জায়গায় ছাপা।',
    coverageTitle: 'কোন বছরে আসলে কতটা তথ্য আছে',
    coverageBody: 'পিজিসিবির তালিকায় ২০১৫ সাল থেকে সারি থাকলেও চাহিদা ও সরবরাহের ঘর প্রায় পুরোটাই ফাঁকা, আর ২০২২ সালের আগে লোডশেডিংয়ের ঘরে প্রায় সব সময় “০”। নিচের হিসাবে দেখুন কোন বছরে কতটা সত্যিই লেখা আছে।',
    year: 'বছর', rows: 'সারি', withDemand: 'চাহিদা লেখা আছে', nonzeroShed: 'শূন্যের বেশি লোডশেডিং',
    outlierTitle: 'অসম্ভব সংখ্যা',
    outlierBody: 'দেশের মোট উৎপাদন ক্ষমতাই প্রায় ২৯,০০০ মেগাওয়াট। এর চেয়ে বড় লোডশেডিংয়ের সংখ্যাকে টাইপের ভুল ধরে সরিয়ে রাখা হয়েছে — সব মিলিয়ে {n}টি।',

    sourcesTitle: 'তথ্যসূত্র',
    footerNote: 'তথ্য প্রতি ঘণ্টায় আপনাআপনি সংগ্রহ হয়। এই পাতায় কোনো সংখ্যা হাতে বদলানো হয় না — যা প্রকাশিত, তা-ই দেখানো। কিছু চোখে খটকা লাগলে নিচের লিংক থেকে মূল উৎসে মিলিয়ে নিতে পারেন।',
    builtAt: 'সবশেষ হালনাগাদ', dataFrom: 'তথ্যের পরিসর',
  },
  en: {
    brand: 'Electricity Dashboard', allProto: 'All prototypes',
    eyebrow: 'Built from official figures',
    title: 'Bangladesh electricity generation & load-shedding',
    lede: 'PGCB and BPDB publish these figures every day; this page collects them every hour and puts them side by side — how much was generated, how much fell short, which areas were shed, and why.',
    loading: 'Loading…',
    navNow: 'Right now', navSearch: 'Your area', navWhy: 'Why', navMap: 'Map',
    navEquity: 'Who bears it', navFuel: 'Fuel', navZones: 'Zones',
    navSeasonal: 'Vs. past years', navTrend: 'Over time', navTrust: 'Data integrity',

    vLine: 'There is <b>{mw}</b> MW of load-shedding right now. At this hour over the last {days} readings it has typically been <b>{median}</b> MW, most days between {lo} and {hi} MW.',
    vPeople: 'The electricity not supplied so far today ({mwh} MWh) would have run a day\u2019s power for about <b>{people}</b> people. (At 560 kWh per person per year.)',
    nowTitle: 'Right now',
    nowSub: 'The most recent hourly reading from PGCB. Supply plus load-shedding is exactly the published “demand”.',
    supply: 'Supply', loadshedding: 'Load-shedding', demand: 'Demand (published)',
    todayPeak: 'Today’s highest', mw: 'MW', mkwh: 'MkWh',
    asOf: 'as of', noData: 'no data',
    todayChart: 'Supply and load-shedding, hour by hour',
    r7: '7 days', r30: '30 days', r90: '90 days',
    smoothed: '{n}-day rolling average',
    hoursShed: 'Hours with load-shedding', energyShed: 'Electricity not supplied',
    mwh: 'MWh',

    searchTitle: 'The situation in your area',
    searchSub: 'Type a district name to see which grid zone it belongs to, how much load-shedding that zone is getting, and which power stations and substations are nearby. You can also search by plant or substation name.',
    searchPlaceholder: 'e.g. Ramna, Savar, Mymensingh, Bogura…',
    searchHint: 'The official figures are published for nine grid zones, not for individual districts. So the number shown for your district is really its whole zone’s.',
    resDistrict: 'district', resZone: 'zone', resPlant: 'power station', resSubstation: 'substation',
    resUpazila: 'upazila / thana', resPlace: 'area',
    areaRank: 'Over the last 90 days, {zone} ranks <b>{pos}</b> of {n} zones for how much of its demand was cut.',
    ownSubLoad: 'Peak load served by this substation', ownPlantOut: 'This station\u2019s output',
    areaShedNow: 'Load-shedding at the evening peak',
    areaRate: 'Share of its own demand not supplied',
    areaPerPerson: 'Shortfall per person', watts: 'W',
    areaDays: 'Days with load-shedding in the last 90',
    areaPlants: 'Power stations in this district', areaSubs: 'Grid substations in this district',
    areaNone: 'None listed for this district',
    areaTrend: 'Load-shedding in this zone, last 90 days',
    running: 'running', stopped: 'stopped',

    whyTitle: 'Why is there load-shedding?',
    whySub: 'The NLDC daily report prints a reason beside every power station. These are the stations that generated nothing at all at the evening peak, grouped by the reason given.',
    idleTitle: 'Idle capacity, by stated reason',
    idleTrend: 'Capacity idled by gas shortage',
    idleNote: 'At the evening peak, <b>{cap}</b> MW of generating capacity produced nothing at all — <b>{gas}</b> MW of it sitting idle for want of gas alone. Source: NLDC daily report, {date}.',
    idleCap: 'Idle capacity', plants: 'stations',
    causeTitle: 'The shortfall, as BPDB itself attributes it',
    cause_maintenance: 'Shut down / maintenance', cause_gas_lf: 'Gas / liquid fuel limitation',
    cause_kaptai: 'Low water in Kaptai lake', cause_coal: 'Coal supply limitation',
    navForecast: 'The forecast',
    fcTitle: 'What BPDB said the day before',
    fcSub: 'Every daily report carries BPDB’s own forecast of the next day’s “probable load shed”, set here against what actually happened. In 2025 it read zero on almost every day; in 2026 the forecasts became far more realistic, but on the days it still says zero it is wrong just as often — and by more.',
    fcChart: 'Forecast and outcome, side by side',
    fcZero: 'Days forecast at zero load-shedding', fcZeroNote: 'of all days with both figures',
    fcZeroUnit: 'days forecast at zero',
    fcMissedInline: 'on {n} of them it then shed — {mw} MW on average',
    fcWorstNote: '{d} — forecast that day was zero',
    fcMissed: 'Of those, days that then shed', fcOfThose: 'of them',
    fcMean: 'Average shed on those days', fcWorst: 'worst',
    fcForecast: 'Forecast', fcActual: 'What happened',
    fcNote: 'The forecast is for the evening peak at the sub-station end; the outcome is measured the same way.',
    unitCostTitle: 'Fuel cost per unit of electricity',
    fuel_gas: 'Gas', fuel_oil: 'Oil', fuel_coal: 'Coal',
    fuel_import: 'Imports', fuel_renewable: 'Renewables',

    mapTitle: 'Electricity on the map',
    mapSub: 'The darker the shade, the more load-shedding in that zone. Dots are power stations and grid substations, sized by capacity or load.',
    mapLoadshedding: 'Load-shedding', mapDemand: 'Demand',
    mapNote: 'A district takes the colour of the grid zone it sits in — no district-level breakdown is published inside a zone. Plant and substation positions come from matching names against OpenStreetMap; some are only accurate to the nearest town.',
    layerPlants: 'Power stations', layerSubs: 'Grid substations', layerDistricts: 'Districts',
    capacity: 'Capacity', generated: 'Generated', load: 'Peak load',
    reason: 'Reason', zone: 'Zone', district: 'District', at: 'at',
    low: 'less', high: 'more', approx: 'approximate position',

    equityTitle: 'Is the burden shared evenly?',
    equitySub: 'Zones are not shed equally on the same day. How much of a zone’s own demand gets cut, and how much shortfall falls on each resident — worked out from the authorities’ own table.',
    equityRate: 'Share of its own demand that was cut',
    equityPerPerson: 'Shortfall per person, at the evening peak',
    equityBurden: 'Burden vs. its share',
    equityNote: 'Over the last {days} days, <b>{nat}</b> of national demand was cut on average. But <b>{worst}</b> lost <b>{worstRate}</b> — <b>{times}×</b> the national average — while <b>{best}</b> lost only <b>{bestRate}</b>.',
    equityCaveat: 'A gap like this may reflect deliberate priority, but it can equally reflect transmission limits, industrial load, or where the power stations happen to sit. The numbers show the outcome, not the intent.',
    equityTableTitle: 'The full picture, zone by zone',
    population: 'Population', shedDays: 'Days shed',
    natAvg: 'national average', times: '×',
    w30: '30 days', w90: '90 days', w365: '1 year', wall: 'All',
    burdenHint: 'Above 1 means the zone takes more load-shedding than its share of demand',

    fuelTitle: 'What the electricity is made from',
    fuelSub: 'The fuel split of each day’s generation, in million kilowatt-hours.',
    fuelChart: 'Daily generation by fuel',
    fuelAbs: 'Amount', fuelShare: 'Share', fuelTotal: 'Total',
    fuel_total: 'Total generation',
    fuelMonthAbs: 'Generation by fuel, average per day (million kWh)',
    fuelMonthShare: 'Share of generation by fuel',
    fuelMonthNote: 'A daily average rather than a monthly total, so a short or incomplete month cannot look like a fall in generation.',
    fuelYoyTitle: '{m}: {b} against {a}',
    fuelYoyBody: 'Generation rose a little, but what it is made from has shifted — gas fell and coal and oil took its place, and oil costs about five times as much per unit. Output grew far less than the country needed, and that difference became load-shedding. The comparison is against the same days of the year.',
    costTitle: 'Production cost per unit', costUnit: 'Tk per kWh',
    navCost: 'What it costs', navDemand: 'Demand growth',
    demTitle: 'How fast demand has grown',
    demSub: 'Evening-peak demand, laid over the same days of earlier years. No year is left out — hover or tap a year in the legend to isolate it. This is demand as published: what was served plus what was shed.',
    demYearChart: 'Evening-peak demand, the last five years side by side (7-day average)',
    demDecadeChart: 'Demand on an ordinary day, by year, since 2016',
    demGrowth: 'Growth over the decade', demGrowthNote: '{a} to {b}',
    demCagr: 'Average growth', perYear: 'a year',
    demMedian: 'Demand on an ordinary day', demP95: 'on a busy day',
    demPeak: 'On this year’s busiest days', demPeakNote: '95th percentile, {y}',
    eid: 'Eid',
    demHoliday: 'The deepest troughs of each year are the Eid holidays: industry closes and demand falls for several days. Eid moves about eleven days earlier each year, so the dip moves with it. All {n} Eids across the last {y} years show the fall in this data — between {min}% and {max}%.',
    demNote: 'Measured at the sub-station end. Since “demand” here is supply plus load-shedding, a factory that stopped asking for power it knew would not arrive does not appear in it — true demand is higher than this line.',
    costTitle2: 'What a day of electricity costs to make',
    costSub: 'Each daily report prints both the total cost of generation and the cost per unit. Laid over the same days a year earlier, they show not just that electricity got dearer but why.',
    costUnitMode: 'Per unit', costTotalMode: 'Daily total',
    costYearUnit: 'Cost per unit, against the same days a year earlier (7-day average)',
    costYearTotal: 'Total cost of a day’s generation, crore taka (7-day average)',
    costYearNote: 'The two years are laid over the same dates because cost moves with the season.',
    costPerDay: 'Cost of the latest day’s generation', crore: 'crore Tk',
    costPerDayNote: 'fuel and generation only', takaKwh: 'Tk/unit',
    costPerUnit: 'Cost per unit',
    costYoy: 'Change per unit in a year', costYoyNote: 'against {a}',
    costWhyTitle: 'Why it rose — the price of fuel, or the mix of it?',
    costMix: 'from the mix changing', costPrice: 'from fuel prices',
    costWhyBody: 'The unit cost rose {total} taka. Of that, {mix} taka came from nothing but a change in the mix of fuels burned, and {price} taka from fuel prices themselves. Gas fell from {gasBefore}% of generation to {gasAfter}% — while the price of gas did not rise at all, easing from {gasPriceBefore} to {gasPriceAfter} taka a unit. The driver is the loss of domestic gas, not the world market.',
    fuelLatest: 'Split on the latest day', share: 'share',

    zonesTitle: 'Zone by zone',
    zonesSub: 'Demand and load-shedding in each zone at the evening peak, as published in the NLDC daily report.',
    zoneTrend: 'Load-shedding trend by zone',
    zoneName: 'Zone', zoneShare: 'Share of all load-shedding',

    seasonalTitle: 'How now compares with previous years',
    seasonalSub: 'Load-shedding swings with the season — heavier in summer, lighter in winter. So “versus a year ago” only means something against the same point in the calendar. Each line below is one year, laid over the same dates.',
    seasonalChart: 'Electricity not supplied, by day of year (7-day average)',
    seasonalNote: 'Over the last 30 days an average of <b>{now}</b> MWh a day went unsupplied. At the same point in {year} it was <b>{prev}</b> — about <b>{times}× {dir}</b> now.',
    compareTitle: 'The same 30 days, different years',
    trendTitle: 'Over time',
    trendSub: 'PGCB’s archive holds rows back to 2015, but before 2022 the load-shedding column reads “0” in almost every hour. That period is marked “not reported” rather than drawn as zero.',
    monthlyTitle: 'Load-shedding by month',
    mwhPerDay: 'MWh/day', hoursUnit: 'hours',
    mMean: 'Mean (MWh/day)', mMedian: 'Median', mP95: '95th pct (MW)',
    mMax: 'Maximum (MW)', mHours: 'Hours/day',
    mTitle_mean_energy_shed_mwh: 'Electricity not supplied, average per day',
    mTitle_median_energy_shed_mwh: 'Electricity not supplied on a typical day',
    mTitle_p95_loadshed: 'How deep the bad days ran (95th percentile)',
    mTitle_max_loadshed: 'The single worst hour of the month',
    mTitle_mean_hours_shed: 'Hours of the day affected, on average',
    mNote_mean_energy_shed_mwh: 'Total shortfall divided by days. Unaffected by month length or an incomplete month, and it measures the thing people actually lost.',
    mNote_median_energy_shed_mwh: 'The middle day of the month. A few catastrophic days pull the mean up; the median says what an ordinary day was like.',
    mNote_p95_loadshed: 'How deep the worst days ran, without a single mis-keyed hour deciding the month.',
    mNote_max_loadshed: 'The most fragile measure — one mistyped hour can rewrite a month. We would not compare periods with it, but we are not hiding it either.',
    mNote_mean_hours_shed: 'Not how deep but how long: hours of the day with no power.',
    mDisagree: 'The measure changes the answer: by average shortfall the worst month is <b>{a}</b>, but by “maximum MW” it is <b>{b}</b>. Rather than pick one for you, all of them are here — check us against each.',
    mAgree: 'At present every measure agrees on which month was worst.',
    notReported: 'not reported',

    trustTitle: 'How solid are these figures?',
    trustSub: 'This page shows the authorities’ own numbers. But it also matters how those numbers are built, and where two official sources fail to agree with each other.',
    identityTitle: 'The published “demand” is an arithmetic identity, not a measurement',
    identityBody: 'In PGCB’s hourly table, demand equals supply plus load-shedding exactly in {rate} of rows. BPDB’s daily report does the same with energy: demand = generated + not supplied, exact in {erate} of days. So “demand” is never measured independently — it is built from the load-shedding figure. The two cannot be used to check each other, and real demand may well be higher.',
    sameSourceTitle: 'Two different pages, one set of numbers',
    sameSourceBody: 'BPDB’s “area-wise demand” page and the NLDC daily report’s evening-peak table agree exactly on {match} of the {days} days compared. It is not a second independent source — it is the same figure printed elsewhere.',
    coverageTitle: 'How much each year actually holds',
    coverageBody: 'PGCB’s table has rows going back to 2015, but the demand and supply columns are almost entirely empty, and before 2022 the load-shedding column reads “0” nearly every hour. The table below shows what is really there.',
    year: 'Year', rows: 'Rows', withDemand: 'Has demand', nonzeroShed: 'Load-shedding above zero',
    outlierTitle: 'Impossible values',
    outlierBody: 'National installed capacity is about 29,000 MW. Load-shedding figures larger than that are treated as typing errors and set aside — {n} in total.',

    sourcesTitle: 'Sources',
    footerNote: 'Data is collected automatically every hour. No figure on this page is edited by hand — what was published is what is shown. If something looks wrong, the links below go to the original source.',
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
  bn: { gas_shortage: 'গ্যাসের সংকট', fuel_shortage: 'তেলের সংকট',
        maintenance: 'রক্ষণাবেক্ষণে বন্ধ', fault: 'যান্ত্রিক ত্রুটি',
        contract_ended: 'চুক্তি শেষ', not_needed: 'চাহিদা কম, তাই বন্ধ',
        other: 'অন্যান্য', none: 'কারণ লেখা নেই' },
  en: { gas_shortage: 'Gas shortage', fuel_shortage: 'Liquid fuel shortage',
        maintenance: 'Maintenance / overhaul', fault: 'Mechanical fault',
        contract_ended: 'Contract ended', not_needed: 'Low demand / reserve',
        other: 'Other', none: 'No reason stated' },
};

const FUEL_NAMES = {
  bn: { gas: 'গ্যাস', coal: 'কয়লা', hfo: 'ফার্নেস তেল', hsd: 'ডিজেল',
        hydro: 'জলবিদ্যুৎ', solar: 'সৌর', wind: 'বাতাস', import: 'আমদানি',
        renewable: 'নবায়নযোগ্য', oil: 'তেল' },
  en: { gas: 'Gas', coal: 'Coal', hfo: 'Furnace oil', hsd: 'Diesel',
        hydro: 'Hydro', solar: 'Solar', wind: 'Wind', import: 'Import',
        renewable: 'Renewables', oil: 'Oil' },
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

/** Population in the unit each language actually reads in: crore for Bengali,
 *  millions for English. */
function fmtPop(n) {
  if (!n) return '—';
  return LANG === 'bn'
    ? `${fmt(n / 1e7, 2)} কোটি মানুষ`
    : `${fmt(n / 1e6, 1)} million people`;
}

/** Clock time with both parts in the reader's own digits. */
const fmtHour = (h) => `${fmt(h)}:${fmt(0)}${fmt(0)}`;

const pct = (x) => (x === null || x === undefined) ? '—'
  : new Intl.NumberFormat(locale(), { style: 'percent', maximumFractionDigits: 1 }).format(x);

/* ══════════════════════════════════ colours ═══════════════════════════════ */

const C = {
  supply: '#2a78d6', loadshed: '#eb6834',
  s: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300'],
  surface: '#ffffff', grid: '#ebeae5', muted: '#74757e', text2: '#4a4b52',
};

// Sequential ramps run light -> dark, so the darkest shade always means the
// most load-shedding. Each stays inside one hue family and ships a scale legend.
const RAMP_SHED = ['#fdeadb', '#fbc9a5', '#f39a68', '#dd6631', '#a2380f'];
const RAMP_DEM  = ['#e7f0fa', '#c2dbf1', '#8dbce5', '#4a8ecd', '#1c5698'];

const FUEL_ORDER = ['gas', 'coal', 'hfo', 'import', 'renewable', 'hsd'];
const fuelColor = (f) => C.s[FUEL_ORDER.indexOf(f)] || C.s[5];

/* ══════════════════════════════════ svg utils ═════════════════════════════ */

const NS = 'http://www.w3.org/2000/svg';
const MUTED_LINE = '#B9C4CE';
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
    el('line', { class: 'axis-line', x1: 0, x2: w, y1: h - 0.5, y2: h - 0.5 }, svg);

    // A sparkline still needs to say what span it covers, or the shape is
    // uninterpretable. First and last date only — there is no room for a scale.
    if (opts.axis) {
      const ax = document.createElement('div');
      ax.className = 'spark-axis';
      ax.innerHTML = `<span>${opts.axis[0]}</span><span>${opts.axis[1]}</span>`;
      cell.appendChild(ax);
    }
  });
}

/* ══════════════════════════════════ data ═════════════════════════════════ */

const D = {};
const load = (name) => fetch(`data/${name}.json`, { cache: 'no-cache' })
  .then(r => (r.ok ? r.json() : null)).catch(() => null);

async function loadAll() {
  // data/daily.json is published as the full open-data export but the page
  // itself needs only the monthly rollup and today's row from latest.json.
  const [meta, latest, monthly, integrity, plants, subs, fuelmix, zones, reasons, districts, equity, seasonal, places, official, cost, demand] =
    await Promise.all([
      load('meta'), load('latest'), load('monthly'), load('integrity'),
      load('plants'), load('substations'), load('fuelmix'), load('zones'),
      load('reasons'), load('geo/districts'), load('equity'), load('seasonal'),
      load('places'), load('official'), load('cost'), load('demand'),
    ]);
  Object.assign(D, { meta, latest, monthly, integrity, plants, subs,
                     fuelmix, zones, reasons, districts, equity, seasonal, places, official, cost, demand });

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
    tile(t('loadshedding'), fmt(l.loadshed), t('mw'),
         `${t('todayPeak')}: ${fmt(today.max_loadshed)} ${t('mw')}`, C.loadshed) +
    tile(t('demand'), fmt(l.demand), t('mw'),
         LANG === 'bn' ? 'সরবরাহ + লোডশেড' : 'supply + load-shed', null) +
    tile(t('energyShed'), fmt(today.energy_shed_mwh), t('mwh'),
         `${t('hoursShed')}: ${fmt(today.hours_shed)}`, null);

  renderHourly(D.range || 7);
}

// Over a month or a quarter the hour-to-hour swing is noise against the trend,
// so the longer views are smoothed: 3 days at 30, a week at 90.
const SMOOTH_HOURS = { 7: 0, 30: 72, 90: 168 };

function rollingMean(rows, keys, win) {
  if (!win) return rows;
  const half = Math.floor(win / 2);
  return rows.map((row, i) => {
    const lo = Math.max(0, i - half), hi = Math.min(rows.length, i + half + 1);
    const out = { x: row.x };
    for (const k of keys) {
      let sum = 0;
      for (let j = lo; j < hi; j++) sum += rows[j][k];
      out[k] = sum / (hi - lo);
    }
    return out;
  });
}

function renderHourly(days) {
  const host = document.getElementById('hourly-chart');
  if (!D.hourly || !D.hourly.rows) { host.innerHTML = `<p class="loading">${t('noData')}</p>`; return; }
  const raw = D.hourly.rows.slice(-days * 24).map(r => ({
    x: r[0], supply: r[2] || 0, loadshed: r[3] || 0,
  }));
  const win = SMOOTH_HOURS[days] || 0;
  const rows = rollingMean(raw, ['supply', 'loadshed'], win);

  const noteEl = document.getElementById('hourly-smooth');
  if (noteEl) {
    noteEl.textContent = win
      ? t('smoothed').replace('{n}', fmt(win / 24)) : '';
  }
  stackedArea(host, rows, [
    { key: 'supply', label: t('supply'), color: C.supply },
    { key: 'loadshed', label: t('loadshedding'), color: C.loadshed },
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
      `<th class="num">${t('loadshedding')}</th><th class="num">${t('zoneShare')}</th></tr></thead><tbody>` +
      rows.map(r => `<tr><td>${zoneName(r.k)}</td><td class="num">${fmt(r.demand)}</td>` +
        `<td class="num">${fmt(r.shed)}</td><td class="num">${pct(r.shed / tot)}</td></tr>`).join('') +
      `</tbody>`;
  }

  const daily = (z.areawise_daily || []).slice(-365);
  const axis = daily.length
    ? [fmtDate(daily[0].date, { month: 'short', year: 'numeric' }),
       fmtDate(daily[daily.length - 1].date, { month: 'short', year: 'numeric' })]
    : null;
  sparkGrid(document.getElementById('zone-chart'),
    zoneKeys.map(k => {
      const vals = daily.map(d => (d[k] && d[k][1]) || 0);
      return {
        title: zoneName(k),
        stat: `${fmt(Math.max(...vals, 0))} ${t('mw')}`,
        values: vals,
      };
    }), { color: C.loadshed, axis });
}

// The same month looks different under each measure, and choosing one is
// itself an editorial act — so all four are offered and the reader picks.
const METRICS = [
  { key: 'mean_energy_shed_mwh', label: 'mMean', unit: 'mwh', digits: 0 },
  { key: 'median_energy_shed_mwh', label: 'mMedian', unit: 'mwh', digits: 0 },
  { key: 'p95_loadshed', label: 'mP95', unit: 'mw', digits: 0 },
  { key: 'max_loadshed', label: 'mMax', unit: 'mw', digits: 0 },
  { key: 'mean_hours_shed', label: 'mHours', unit: 'hours', digits: 1 },
];

function renderMetricSeg() {
  const seg = document.getElementById('metric-seg');
  if (!seg) return;
  D.metric = D.metric || METRICS[0].key;
  seg.innerHTML = METRICS.map(m =>
    `<button type="button" data-k="${m.key}" aria-pressed="${D.metric === m.key}">${t(m.label)}</button>`
  ).join('');
  seg.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    D.metric = b.dataset.k;
    renderMetricSeg();
    renderTrend();
  }));
}

function renderTrend() {
  const m = D.monthly || [];
  const start = (D.integrity && D.integrity.reporting_start) || '2022-01-01';
  const spec = METRICS.find(x => x.key === (D.metric || METRICS[0].key)) || METRICS[0];
  const rows = m.map(r => ({ x: r.month, v: r[spec.key] || 0, month: r.month }));

  const titleEl = document.getElementById('monthly-title');
  if (titleEl) titleEl.textContent = t('mTitle_' + spec.key);
  const noteEl = document.getElementById('metric-note');
  if (noteEl) noteEl.textContent = t('mNote_' + spec.key);

  // Where the measures disagree, say so rather than let the choice pass unseen.
  const warn = document.getElementById('metric-warning');
  if (warn) {
    const recent = m.filter(r => r.month >= start.slice(0, 7) && r.reported_days > 5);
    const worstBy = (k) => recent.slice().sort((a, b) => (b[k] || 0) - (a[k] || 0))[0];
    const a1 = worstBy('mean_energy_shed_mwh'), a2 = worstBy('max_loadshed');
    warn.innerHTML = (a1 && a2 && a1.month !== a2.month)
      ? `<div class="note warn">${t('mDisagree')
          .replace('{a}', fmtDate(a1.month + '-01', { month: 'long', year: 'numeric' }))
          .replace('{b}', fmtDate(a2.month + '-01', { month: 'long', year: 'numeric' }))}</div>`
      : `<div class="note">${t('mAgree')}</div>`;
  }

  barChart(document.getElementById('monthly-chart'), rows, 'v', {
    height: 280, color: C.loadshed, label: t(spec.label), digits: spec.digits,
    missing: (r) => r.month < start.slice(0, 7),
    xlabel: (r) => fmtDate(r.month + '-01', { month: 'short', year: 'numeric' }),
    xtip: (r) => fmtDate(r.month + '-01', { month: 'long', year: 'numeric' }),
  });
  const host = document.getElementById('monthly-chart');
  const lg = document.createElement('div');
  lg.className = 'legend';
  const unit = { mwh: t('mwhPerDay'), mw: t('mw'), hours: t('hoursUnit') }[spec.unit];
  lg.innerHTML =
    `<span class="legend-item"><i class="swatch" style="background:${C.loadshed}"></i>${t('loadshedding')} (${unit})</span>` +
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
    if (v === null || v === undefined) return '#e9e8e3';
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
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
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
        fillOpacity: 0.8, color: '#ffffff', weight: 1,
      }),
      onEachFeature: (feat, layer) => {
        const p = feat.properties;
        const name = LANG === 'bn' && p.name_bn ? p.name_bn : p.name_en;
        const v = vals[p.zone];
        layer.bindPopup(
          `<b>${name}</b><br>${t('zone')}: ${zoneName(p.zone)}<br>` +
          `${metric === 'loadshed' ? t('loadshedding') : t('demand')}: <b>${fmt(v)}</b> ${t('mw')}`);
        layer.on('mouseover', () => layer.setStyle({ weight: 2.5, color: '#2a5fd6' }));
        layer.on('mouseout', () => layer.setStyle({ weight: 1, color: '#ffffff' }));
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
        (p.remarks ? `<i style="color:#74757e">${p.remarks}</i><br>` : '') +
        (p.geo !== 'osm' ? `<span style="color:#74757e;font-size:.9em">${t('approx')}</span>` : ''));
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
        color: C.surface, weight: 1.5, fillColor: C.s[5], fillOpacity: 0.85,
      });
      m.bindPopup(`<b>${s.name}</b><br>${t('load')}: <b>${fmt(s.load_mw)}</b> ${t('mw')}` +
        (s.hour !== null && s.hour !== undefined ? `<br>${t('at')}: ${fmtHour(s.hour)}` : '') +
        (s.geo !== 'osm' ? `<br><span style="color:#74757e;font-size:.9em">${t('approx')}</span>` : ''));
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
  seg.innerHTML = [['loadshed', 'mapLoadshedding'], ['demand', 'mapDemand']].map(([k, lbl]) =>
    `<button type="button" data-metric="${k}" aria-pressed="${D.mapMetric === k}">${t(lbl)}</button>`).join('');
  seg.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    D.mapMetric = b.dataset.metric;
    renderMapSeg();
    renderMap();
  }));
}

/* ════════════════════════════ search: your area ══════════════════════════ */

let SEARCH_INDEX = null;

/* Romanised Bengali place names vary mostly in their vowels and in which
 * aspirated digraph the writer picked: Ramna / Romna / Romana, Dhaka / Dacca,
 * Bogra / Bogura. Reducing a name to its consonant skeleton collapses all of
 * those onto one key, so any of the spellings finds the place.            */
const DIGRAPHS = [
  [/ksh|kkh/g, 'k'], [/chh|ch/g, 'c'], [/sh|ss/g, 's'], [/kh/g, 'k'],
  [/gh/g, 'g'], [/jh/g, 'j'], [/th/g, 't'], [/dh/g, 'd'], [/ph/g, 'f'],
  [/bh/g, 'b'], [/zh/g, 'j'], [/ng|nk/g, 'n'], [/ee|ii/g, 'i'], [/oo|uu/g, 'u'],
];

function phonetic(name) {
  let t = (name || '').toLowerCase().normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z\s]/g, '');
  for (const [re, to] of DIGRAPHS) t = t.replace(re, to);
  t = t.replace(/c|q/g, 'k').replace(/z/g, 'j').replace(/[vw]/g, 'b')
       .replace(/x/g, 'ks').replace(/y/g, 'i');
  t = t.replace(/h/g, '');                  // aspiration is written inconsistently
  t = t.replace(/[aeiou]/g, '');            // consonant skeleton
  t = t.replace(/(.)\1+/g, '$1');           // collapse doubles
  return t.replace(/\s+/g, '');
}

/** Levenshtein, capped — only used to rescue near-miss typing. */
function editDistance(a, b, cap = 2) {
  if (Math.abs(a.length - b.length) > cap) return cap + 1;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1,
                        prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      best = Math.min(best, cur[j]);
    }
    if (best > cap) return cap + 1;
    prev = cur;
  }
  return prev[b.length];
}

// Names still in daily use that OpenStreetMap now files under the 2018 spelling.
const NAME_ALIASES = {
  Dhaka: ['Dacca'], Chattogram: ['Chittagong', 'Ctg'], Cumilla: ['Comilla'],
  Barishal: ['Barisal'], Jashore: ['Jessore'], Bogura: ['Bogra'],
  Chapainawabganj: ['Nawabganj', 'Chapai'], Netrokona: ['Netrakona'],
  Jhalokati: ['Jhalakathi'], Moulvibazar: ['Maulvibazar', 'Moulavibazar'],
  Khagrachari: ['Khagrachhari'], Munshiganj: ['Munshigonj'],
  Sunamganj: ['Sunamgonj'], Brahmanbaria: ['Bramhanbaria', 'B.Baria'],
};

function indexEntry(kind, label_en, label_bn, district, zone, extra) {
  const aliases = NAME_ALIASES[label_en] || [];
  const keys = [label_en, ...aliases].map(phonetic).filter(Boolean);
  return Object.assign({
    kind, key: label_en, en: label_en, bn: label_bn || label_en,
    district, zone, aliases,
    lc: (label_en || '').toLowerCase(),
    ph: keys,
  }, extra || {});
}

function buildSearchIndex() {
  const idx = [];

  (D.zones && D.zones.zones ? D.zones.zones : []).forEach(z =>
    idx.push(indexEntry('zone', ZONE_NAMES.en[z], ZONE_NAMES.bn[z], null, z)));

  ((D.places && D.places.places) || []).forEach(p =>
    idx.push(indexEntry(p.k, p.n, p.b, p.d, p.z,
                        { lat: p.lat, lon: p.lon, districtBn: p.db })));

  // A plant or substation whose name could not be matched to a location has
  // no zone, so the area panel would come up blank. Leaving it in the results
  // promises an answer the data cannot give, so it is left out.
  ((D.plants && D.plants.plants) || []).forEach(p => {
    if (p.zone) idx.push(indexEntry('plant', p.name, p.name, p.district, p.zone));
  });

  ((D.subs && D.subs.substations) || []).forEach(s => {
    if (s.zone) idx.push(indexEntry('substation', s.name, s.name, s.district, s.zone));
  });

  return idx;
}

const KIND_RANK = { district: 0, upazila: 1, place: 2, zone: 3, plant: 4, substation: 5 };

function searchMatches(q) {
  const raw = q.trim();
  if (raw.length < 2) return [];
  const lc = raw.toLowerCase();
  const ph = phonetic(raw);
  const bengali = /[ঀ-৿]/.test(raw);

  const scored = [];
  for (const e of (SEARCH_INDEX || [])) {
    let s = null;
    if (bengali) {
      if (e.bn === raw) s = 0;
      else if (e.bn && e.bn.startsWith(raw)) s = 1;
      else if (e.bn && e.bn.includes(raw)) s = 3;
    } else {
      if (e.lc === lc) s = 0;
      else if (e.lc.startsWith(lc)) s = 1;
      else if (e.aliases.some(a => a.toLowerCase().startsWith(lc))) s = 2;
      else if (e.lc.includes(lc)) s = 3;
      else if (ph && e.ph.includes(ph)) s = 4;                     // Romna → Ramna
      else if (ph.length >= 3 && e.ph.some(k => editDistance(ph, k) <= 1)) s = 5;
    }
    if (s !== null) scored.push([s, e]);
  }

  scored.sort((a, b) => a[0] - b[0]
    || KIND_RANK[a[1].kind] - KIND_RANK[b[1].kind]
    || a[1].en.length - b[1].en.length
    || a[1].en.localeCompare(b[1].en));

  // one row per place name: an upazila and a settlement of the same name in the
  // same district are the same answer to the user
  const out = [], seen = new Set();
  for (const [, e] of scored) {
    const k = `${e.lc}|${e.district}`;
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(e);
    if (out.length >= 8) break;
  }
  return out;
}

/** English district name -> its Bengali name, from the district boundaries. */
let DISTRICT_BN = null;
function districtBn(nameEn) {
  if (!nameEn) return null;
  if (!DISTRICT_BN) {
    DISTRICT_BN = new Map(((D.districts && D.districts.features) || [])
      .map(f => [f.properties.name_en,
                 (f.properties.name_bn || '').replace(/\s*জেলা\s*$/, '')])
      .filter(([, bn]) => bn));
  }
  return DISTRICT_BN.get(nameEn) || null;
}

function equityForZone(zone, win = '90') {
  const w = D.equity && D.equity.windows && D.equity.windows[win];
  if (!w) return null;
  return (w.zones || []).find(z => z.zone === zone) || null;
}

function zoneSeries(zone, n = 90) {
  const peak = (D.zones && D.zones.nldc_evening_peak) || [];
  return peak.slice(-n).map(d => ({ date: d.date, v: (d[zone] && d[zone][1]) || 0 }));
}

function renderArea(entry) {
  const host = document.getElementById('area-result');
  if (!entry) { host.innerHTML = ''; return; }

  const zone = entry.zone;
  const district = entry.kind === 'district' ? entry.key : entry.district;
  // A locality resolves upward: the figures exist only per grid zone, so say
  // so plainly instead of implying we have Ramna-level data.
  const districtLabel = (LANG === 'bn' && districtBn(district)) || district;
  const resolved = entry.kind !== 'district' && entry.kind !== 'zone' && district
    ? `<div class="resolve">${LANG === 'bn' ? entry.bn : entry.en} → ${districtLabel} ` +
      `${t('resDistrict')} → ${zoneName(zone)} ${t('resZone')}</div>` : '';
  const eq = equityForZone(zone);
  const series = zoneSeries(zone);
  const latest = series.length ? series[series.length - 1] : null;

  const title = entry.kind === 'district'
    ? (LANG === 'bn' ? entry.bn : entry.en)
    : (LANG === 'bn' ? entry.bn : entry.en);

  const sub = [
    entry.kind !== 'zone' ? `${t('zone')}: <b>${zoneName(zone)}</b>` : null,
    district && entry.kind !== 'district'
      ? `${t('district')}: <b>${(LANG === 'bn' && districtBn(district)) || district}</b>` : null,
  ].filter(Boolean).join(' · ');

  // Rank makes it personal: "2nd worst of 9" lands where "4.7%" does not.
  const w90 = D.equity && D.equity.windows && D.equity.windows['90'];
  let rankLine = '';
  if (w90 && eq) {
    const ordered = w90.zones.slice().sort((a, b) => (b.shed_rate || 0) - (a.shed_rate || 0));
    const pos = ordered.findIndex(z => z.zone === zone) + 1;
    if (pos > 0) {
      rankLine = `<div class="ranknote ${pos <= 3 ? 'bad' : pos > ordered.length - 3 ? 'ok' : ''}">` +
        t('areaRank').replace('{zone}', zoneName(zone))
                     .replace('{pos}', fmt(pos))
                     .replace('{n}', fmt(ordered.length)) + `</div>`;
    }
  }

  const tile = (label, value, unit, note) => `
    <div class="stat">
      <div class="stat-label">${label}</div>
      <div class="stat-value">${value}<span class="stat-unit">${unit || ''}</span></div>
      ${note ? `<div class="stat-note">${note}</div>` : ''}
    </div>`;

  const inDistrict = (arr) => district ? arr.filter(x => x.district === district) : [];
  const plants = inDistrict((D.plants && D.plants.plants) || [])
    .sort((a, b) => (b.capacity_mw || 0) - (a.capacity_mw || 0));
  const subs = inDistrict((D.subs && D.subs.substations) || [])
    .sort((a, b) => (b.load_mw || 0) - (a.load_mw || 0));

  // Many names are several things at once — Savar is an upazila, a settlement
  // AND a grid substation. The results list shows one row per name, so the
  // panel looks up every kind that name matches and shows each one's own
  // measured figure alongside the zone aggregate.
  const nkey = (x) => (x || '').toLowerCase()
    .replace(/\b(sadar\s+)?(upazila|sub-?district|thana|paurashava|city corporation|district)\b/g, '')
    .replace(/[^a-z0-9]/g, '');
  const sameName = (list) => {
    const hit = list.filter(x => nkey(x.name) === nkey(entry.en));
    return hit.find(x => x.district && x.district === district) || hit[0] || null;
  };

  let ownTile = '';
  const subRec = sameName((D.subs && D.subs.substations) || []);
  if (subRec) {
    ownTile += tile(t('ownSubLoad'), fmt(subRec.load_mw), t('mw'),
      (subRec.hour !== null && subRec.hour !== undefined
        ? `${t('at')} ${fmtHour(subRec.hour)} · ` : '') + fmtDate(D.subs.date));
  }
  const plantRec = sameName((D.plants && D.plants.plants) || []);
  if (plantRec) {
    ownTile += tile(t('ownPlantOut'), fmt(plantRec.peak_mw), t('mw'),
      `${t('capacity')} ${fmt(plantRec.capacity_mw)} ${t('mw')}` +
      ((plantRec.peak_mw || 0) <= 0 && plantRec.reason
        ? ` · ${REASON_NAMES[LANG][plantRec.reason] || ''}` : ''));
  }

  host.innerHTML = `
    <div class="card arearesult">
      <div class="area-head">
        <span class="area-name">${title}</span>
        <span class="area-zone">${sub}</span>
      </div>
      ${resolved}
      ${rankLine}

      <div class="grid g4">
        ${ownTile}
        ${tile(t('areaShedNow'), fmt(latest ? latest.v : null), t('mw'),
               latest ? fmtDate(latest.date) : '')}
        ${tile(t('areaRate'), eq ? pct(eq.shed_rate) : '—', '',
               eq ? `${t('natAvg')}: ${pct(D.equity.windows['90'].national_shed_rate)}` : '')}
        ${tile(t('areaPerPerson'), eq ? fmt(eq.watts_per_person, 1) : '—', t('watts'), '')}
        ${tile(t('areaDays'), eq ? `${fmt(eq.shed_days)} / ${fmt(eq.days)}` : '—', '', '')}
      </div>

      <div class="chart-head" style="margin-top:16px">
        <span class="chart-title">${t('areaTrend')}</span>
      </div>
      <div class="chartbox" id="area-chart"></div>

      <div class="grid g2" style="margin-top:16px">
        <div>
          <div class="chart-title">${t('areaPlants')}</div>
          ${plants.length ? `<ul class="mini-list">${plants.map(p => `
            <li><span>${p.name}<br><span class="mini-reason">${
              (p.peak_mw || 0) > 0 ? t('running')
                : (REASON_NAMES[LANG][p.reason] || t('stopped'))
            }</span></span>
            <span class="n">${fmt(p.peak_mw)} / ${fmt(p.capacity_mw)} ${t('mw')}</span></li>`
          ).join('')}</ul>` : `<p class="chart-note">${t('areaNone')}</p>`}
        </div>
        <div>
          <div class="chart-title">${t('areaSubs')}</div>
          ${subs.length ? `<ul class="mini-list">${subs.map(s => `
            <li><span>${s.name}</span><span class="n">${fmt(s.load_mw)} ${t('mw')}</span></li>`
          ).join('')}</ul>` : `<p class="chart-note">${t('areaNone')}</p>`}
        </div>
      </div>

      <p class="chart-note" style="margin-top:14px">${t('searchHint')}</p>
    </div>`;

  lineChart(document.getElementById('area-chart'),
    series.map(d => ({ x: d.date, v: d.v })), 'v', {
      color: C.loadshed, area: true, zero: true, height: 200,
      label: t('loadshedding'),
      xlabel: (r) => fmtDate(r.x, { day: 'numeric', month: 'short' }),
      xtip: (r) => fmtDate(r.x),
    });

  if (MAP && entry.zone) {
    const target = plants.find(p => p.lat) || subs.find(s => s.lat);
    if (target) MAP.setView([target.lat, target.lon], 9);
  }
}

function renderSearch() {
  DISTRICT_BN = null;
  SEARCH_INDEX = buildSearchIndex();
  const input = document.getElementById('area-search');
  const list = document.getElementById('area-results');
  if (!input) return;

  input.placeholder = t('searchPlaceholder');
  let active = -1, current = [];

  const close = () => { list.classList.remove('on'); active = -1; };

  const paint = () => {
    if (!current.length) { close(); return; }
    list.innerHTML = current.map((e, i) =>
      `<button type="button" data-i="${i}" class="${i === active ? 'active' : ''}">
         <span>${LANG === 'bn' ? e.bn : e.en}</span>
         <span class="res-kind">${t('res' + e.kind.charAt(0).toUpperCase() + e.kind.slice(1))}</span>
       </button>`).join('');
    list.classList.add('on');
    list.querySelectorAll('button').forEach(b =>
      b.addEventListener('click', () => choose(+b.dataset.i)));
  };

  const choose = (i) => {
    const e = current[i];
    if (!e) return;
    input.value = LANG === 'bn' ? e.bn : e.en;
    close();
    D.selectedArea = e;
    renderArea(e);
    document.getElementById('area-result').scrollIntoView({ block: 'nearest' });
  };

  input.addEventListener('input', () => { current = searchMatches(input.value); active = -1; paint(); });
  input.addEventListener('focus', () => { if (current.length) list.classList.add('on'); });
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      if (!current.length) return;
      active = (active + (ev.key === 'ArrowDown' ? 1 : -1) + current.length) % current.length;
      paint();
    } else if (ev.key === 'Enter') {
      ev.preventDefault();
      choose(active >= 0 ? active : 0);
    } else if (ev.key === 'Escape') { close(); }
  });
  document.addEventListener('click', (ev) => {
    if (!ev.target.closest('.searchbox')) close();
  });

  if (D.selectedArea) {
    const again = SEARCH_INDEX.find(e => e.kind === D.selectedArea.kind &&
                                         e.key === D.selectedArea.key);
    if (again) { D.selectedArea = again; renderArea(again); }
  }
}

/* ═══════════════════════════ equity: who bears it ════════════════════════ */

function renderEquitySeg() {
  const seg = document.getElementById('equity-seg');
  if (!seg) return;
  D.equityWin = D.equityWin || '90';
  const opts = [['30', 'w30'], ['90', 'w90'], ['365', 'w365'], ['all', 'wall']];
  const have = (D.equity && D.equity.windows) || {};
  seg.innerHTML = opts.filter(([k]) => have[k]).map(([k, lbl]) =>
    `<button type="button" data-win="${k}" aria-pressed="${D.equityWin === k}">${t(lbl)}</button>`
  ).join('');
  seg.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    D.equityWin = b.dataset.win;
    renderEquitySeg();
    renderEquity();
  }));
}

function renderEquity() {
  const eq = D.equity;
  if (!eq) return;
  const w = eq.windows[D.equityWin || '90'];
  if (!w || !w.zones.length) return;

  const byRate = w.zones.slice().sort((a, b) => (b.shed_rate || 0) - (a.shed_rate || 0));
  const byHead = w.zones.slice().sort((a, b) => (b.watts_per_person || 0) - (a.watts_per_person || 0));

  hBars(document.getElementById('equity-rate'),
    byRate.map(z => ({
      label: zoneName(z.zone), value: (z.shed_rate || 0) * 100, color: C.loadshed,
      note: `${fmt(z.shed_days)} / ${fmt(z.days)} ${t('shedDays')}`,
    })),
    { fmtValue: (v) => pct(v / 100), valueLabel: t('equityRate') });

  hBars(document.getElementById('equity-head'),
    byHead.map(z => ({
      label: zoneName(z.zone), value: z.watts_per_person || 0, color: C.loadshed,
      note: fmtPop(z.population),
    })),
    { fmtValue: (v) => `${fmt(v, 1)} ${t('watts')}`, valueLabel: t('equityPerPerson') });

  const worst = byRate[0], best = byRate[byRate.length - 1];
  const natRate = w.national_shed_rate || 0;
  document.getElementById('equity-note').innerHTML =
    `<div class="note warn">` +
    t('equityNote')
      .replace('{days}', fmt(w.days))
      .replace('{nat}', pct(natRate))
      .replace('{worst}', zoneName(worst.zone))
      .replace('{worstRate}', pct(worst.shed_rate))
      .replace('{times}', fmt(natRate ? worst.shed_rate / natRate : 0, 1))
      .replace('{best}', zoneName(best.zone))
      .replace('{bestRate}', pct(best.shed_rate)) +
    `<p style="margin-top:8px;font-size:.85rem">${t('equityCaveat')}</p></div>`;

  const rows = w.zones.slice().sort((a, b) => (b.burden || 0) - (a.burden || 0));
  document.getElementById('equity-table').innerHTML =
    `<thead><tr>
       <th>${t('zoneName')}</th>
       <th class="num">${t('population')}</th>
       <th class="num">${t('loadshedding')} (${t('mw')})</th>
       <th class="num">${t('equityRate')}</th>
       <th class="num">${t('areaPerPerson')} (${t('watts')})</th>
       <th class="num">${t('equityBurden')}</th>
       <th class="num">${t('shedDays')}</th>
     </tr></thead><tbody>` +
    rows.map(z => `<tr>
       <td>${zoneName(z.zone)}</td>
       <td class="num">${fmt(z.population)}</td>
       <td class="num">${fmt(z.mean_loadshed)}</td>
       <td class="num">${pct(z.shed_rate)}</td>
       <td class="num">${fmt(z.watts_per_person, 1)}</td>
       <td class="num"><b>${fmt(z.burden, 2)}</b></td>
       <td class="num">${fmt(z.shed_days)} / ${fmt(z.days)}</td>
     </tr>`).join('') + `</tbody>`;

  const src = eq.population_source || {};
  document.getElementById('equity-source').textContent =
    `${LANG === 'bn' ? src.bn : src.en} · ${t('burdenHint')}`;
}

/* ═════════════════════════ now vs the same time before ═══════════════════ */

// Years are ordered, so they take an ordinal one-hue ramp (older = lighter).
// The current year is lifted out in the load-shedding colour so the comparison
// reads at a glance instead of hunting the legend.
const YEAR_RAMP = ['#86b6ef', '#3987e5', '#256abf', '#0d366b'];

const MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];

/** Several lines over a shared x index, drawn back-to-front by emphasis. */
function multiLine(host, lines, opts = {}) {
  const drawn = lines.filter(l => l.values.some(v => v !== null && v !== undefined));
  if (!drawn.length) { host.innerHTML = `<p class="loading">${t('noData')}</p>`; return; }
  const f = frame(host, { height: opts.height || 300, padL: 52 });
  const { svg, padL, padT, iw, ih } = f;

  const n = opts.length || Math.max(...drawn.map(l => l.values.length));
  const all = drawn.flatMap(l => l.values).filter(v => v !== null && v !== undefined);
  // A price is a level, not a magnitude: a line chart of it may sit on a
  // non-zero baseline without misleading, because nothing here encodes value
  // by length from the axis. Quantities keep their zero.
  const lo = opts.baseline === 'auto' ? Math.min(...all) * 0.94 : 0;
  const y = yAxis(f, lo, Math.max(...all, 1) * 1.04, opts.yfmt);
  const x = (i) => padL + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);

  // Month ticks along the bottom instead of raw day numbers. On a phone twelve
  // Bengali month names run into each other, so label every other month once
  // the slots get narrower than a name.
  const monthStep = iw / 12 < 40 ? 2 : 1;
  MONTH_STARTS.forEach((d, m) => {
    if (m % monthStep) return;
    const lb = el('text', { x: x(d - 1), y: padT + ih + 17, 'text-anchor': 'middle' }, svg);
    lb.textContent = opts.monthLabel ? opts.monthLabel(m) : String(m + 1);
  });
  el('line', { class: 'axis-line', x1: padL, x2: padL + iw, y1: padT + ih, y2: padT + ih }, svg);

  const order = drawn.slice().sort((a, b) => (a.emphasis ? 1 : 0) - (b.emphasis ? 1 : 0));
  const marks = new Map();          // label -> the <polyline>s drawn for it
  const ends = [];                  // end-of-line label positions

  for (const l of order) {
    const parts = [];
    // break the path wherever a run of days is missing
    let run = [];
    const flush = () => {
      if (run.length > 1) {
        parts.push(el('polyline', {
          points: run.join(' '), fill: 'none', stroke: l.color,
          'stroke-width': l.emphasis ? 2.8 : 1.8,
          'stroke-linejoin': 'round', 'stroke-linecap': 'round',
        }, svg));
      }
      run = [];
    };
    l.values.forEach((v, i) => {
      if (v === null || v === undefined) flush();
      else run.push(`${x(i)},${y(v)}`);
    });
    flush();
    marks.set(l.label, parts);

    // Anchor each label at that year's own peak, not its end: every line
    // finishes on 31 December near zero, so end labels pile up in one corner,
    // whereas the peaks fall at different times and heights.
    let best = -1, bestV = -Infinity;
    l.values.forEach((v, i) => {
      if (v !== null && v !== undefined && v > bestV) { bestV = v; best = i; }
    });
    if (best >= 0) ends.push({ l, i: best, y: y(bestV) });
  }

  // Shade alone cannot separate five years on thin overlapping lines, so every
  // line is named at its own peak. Two labels only collide when they are close
  // on *both* axes: pushing apart on y alone moved labels that never overlapped
  // while leaving genuine collisions — visible on a phone, where the text is
  // wider relative to the plot.
  ends.sort((a, b) => a.y - b.y);
  const labels = [];
  for (const e of ends) {
    const atRight = x(e.i) > padL + iw * 0.86;
    el('circle', { cx: x(e.i), cy: y(e.l.values[e.i]), r: e.l.emphasis ? 4 : 3,
                   fill: e.l.color, stroke: C.surface, 'stroke-width': 1.5 }, svg);
    const tx = el('text', {
      x: atRight ? x(e.i) - 7 : x(e.i) + 7,
      y: Math.max(padT + 9, Math.min(e.y + 3, padT + ih - 2)),
      'text-anchor': atRight ? 'end' : 'start',
      class: 'year-label', fill: e.l.color,
      'font-weight': e.l.emphasis ? 700 : 600,
    }, svg);
    tx.textContent = e.l.label;
    labels.push(tx);
  }

  // Nudge collisions apart by measuring what was actually drawn. Guessing a
  // label's size in user units is wrong on a phone: font-size is set in CSS
  // pixels and so does not shrink with the viewBox, leaving the text far wider
  // relative to the plot than on a desktop. getBBox reports the real extent.
  const boxes = [];
  for (const tx of labels) {
    let b;
    try { b = tx.getBBox(); } catch { break; }
    for (let guard = 0; guard < 8; guard++) {
      const hit = boxes.find(o => b.x < o.x + o.width && o.x < b.x + b.width &&
                                  b.y < o.y + o.height && o.y < b.y + b.height);
      if (!hit) break;
      const shifted = hit.y + hit.height + 2 - b.y;
      tx.setAttribute('y', +tx.getAttribute('y') + shifted);
      b = tx.getBBox();
    }
    boxes.push(b);
  }

  // Named events, drawn under the lines so they explain a dip without
  // competing with it. Marks carrying a key belong to one line and are shown
  // only while that line is the highlighted one.
  const markEls = new Map();
  for (const a of (opts.marks || [])) {
    const ax = x(Math.max(0, Math.min(n - 1, a.index)));
    const g = el('g', { opacity: 0 }, svg);
    el('line', { x1: ax, x2: ax, y1: padT + 14, y2: padT + ih,
                 stroke: MUTED_LINE, 'stroke-width': 1,
                 'stroke-dasharray': '3 3' }, g);
    const tx = el('text', { x: ax, y: padT + 9, 'text-anchor': 'middle',
                            class: 'mark-label' }, g);
    tx.textContent = a.label;
    const k = a.key || '';
    if (!markEls.has(k)) markEls.set(k, []);
    markEls.get(k).push(g);
  }
  const defaultMarkKey = (drawn.find(l => l.emphasis) || drawn[drawn.length - 1] || {}).label;
  const showMarks = (key) => {
    for (const [k, gs] of markEls) {
      const on = !k || k === (key || defaultMarkKey);
      for (const g of gs) g.setAttribute('opacity', on ? 1 : 0);
    }
  };
  showMarks(null);

  const cross = el('line', { y1: padT, y2: padT + ih, stroke: C.muted,
                             'stroke-width': 1, opacity: 0 }, svg);
  const hit = el('rect', { x: padL, y: padT, width: iw, height: ih, fill: 'transparent' }, svg);
  hit.addEventListener('pointermove', (ev) => {
    const bb = svg.getBoundingClientRect();
    const px = (ev.clientX - bb.left) * (f.width / bb.width);
    let i = Math.round(((px - padL) / iw) * (n - 1));
    i = Math.max(0, Math.min(n - 1, i));
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i));
    cross.setAttribute('opacity', 0.5);
    const body = order.slice().reverse()
      .filter(l => l.values[i] !== null && l.values[i] !== undefined)
      .map(l => tipRow(l.color, l.label, fmt(l.values[i])))
      .join('');
    showTip(f, x(i), `<div class="tip-date">${opts.xtip ? opts.xtip(i) : i + 1}</div>${body}`);
  });
  hit.addEventListener('pointerleave', () => {
    hideTip(f); cross.setAttribute('opacity', 0);
  });

  const box = document.createElement('div');
  box.className = 'legend legend-interactive';
  box.innerHTML = drawn.map(l =>
    `<button type="button" class="legend-item" data-k="${l.label}">
       <i class="swatch" style="background:${l.color}"></i>${l.label}</button>`).join('');
  host.appendChild(box);

  const focus = (key) => {
    for (const [k, parts] of marks) {
      const on = !key || k === key;
      for (const el_ of parts) {
        el_.setAttribute('opacity', on ? 1 : 0.15);
        el_.setAttribute('stroke-width', key && k === key ? 3 :
          (drawn.find(d => d.label === k).emphasis ? 2.8 : 1.8));
      }
    }
    box.querySelectorAll('.legend-item').forEach(b =>
      b.classList.toggle('dim', !!key && b.dataset.k !== key));
    showMarks(key);
  };
  box.querySelectorAll('.legend-item').forEach(b => {
    b.addEventListener('pointerenter', () => focus(b.dataset.k));
    b.addEventListener('focus', () => focus(b.dataset.k));
    b.addEventListener('click', () => {
      const on = b.classList.toggle('pinned');
      box.querySelectorAll('.legend-item').forEach(o => { if (o !== b) o.classList.remove('pinned'); });
      focus(on ? b.dataset.k : null);
    });
  });
  box.addEventListener('pointerleave', () => {
    const pinned = box.querySelector('.legend-item.pinned');
    focus(pinned ? pinned.dataset.k : null);
  });
}

function renderSeasonal() {
  const sn = D.seasonal;
  if (!sn || !sn.series) return;

  const years = Object.keys(sn.series).sort();
  const current = years[years.length - 1];
  const past = years.slice(0, -1);

  const lines = past.map((yr, i) => ({
    label: fmtYear(yr),
    color: YEAR_RAMP[Math.max(0, YEAR_RAMP.length - past.length + i)] || YEAR_RAMP[0],
    values: sn.series[yr],
  })).concat([{
    label: fmtYear(current), color: C.loadshed,
    values: sn.series[current], emphasis: true,
  }]);

  const monthName = (m) => new Intl.DateTimeFormat(locale(), { month: 'short' })
    .format(new Date(2021, m, 1));

  multiLine(document.getElementById('seasonal-chart'), lines, {
    height: 320, length: 365,
    monthLabel: monthName,
    xtip: (i) => {
      const d = new Date(2021, 0, 1);
      d.setDate(i + 1);
      return new Intl.DateTimeFormat(locale(), { day: 'numeric', month: 'long' }).format(d);
    },
    yfmt: (v) => fmt(v),
  });

  // ---- like-for-like window tiles ------------------------------------
  const cmp = sn.compare || [];
  if (!cmp.length) return;
  const now = cmp[0];
  const host = document.getElementById('seasonal-compare');

  const delta = (v) => {
    if (!now.mean_energy_shed_mwh || !v) return '';
    const ratio = now.mean_energy_shed_mwh / v;
    const worse = ratio >= 1;
    const txt = ratio >= 1
      ? `${fmt(ratio, 1)}${t('times')} ${LANG === 'bn' ? 'বেশি' : 'more'}`
      : `${fmt(1 / ratio, 1)}${t('times')} ${LANG === 'bn' ? 'কম' : 'less'}`;
    return `<div class="stat-note" style="color:${worse ? 'var(--critical)' : 'var(--good)'}">
              ${LANG === 'bn' ? 'এখন' : 'now'} ${txt}</div>`;
  };

  host.innerHTML = cmp.map((c, i) => `
    <div class="stat">
      <div class="stat-label">${i === 0
        ? (LANG === 'bn' ? 'গত ৩০ দিন' : 'Last 30 days')
        : `${fmtYear(c.year)} · ${LANG === 'bn' ? 'একই সময়' : 'same period'}`}</div>
      <div class="stat-value">${fmt(c.mean_energy_shed_mwh)}<span class="stat-unit">${t('mwh')}</span></div>
      <div class="stat-note">${LANG === 'bn' ? 'দিনে গড়ে' : 'per day'} · ${
        fmt(c.mean_hours_shed, 1)} ${LANG === 'bn' ? 'ঘণ্টা' : 'hrs'}</div>
      ${i === 0 ? '' : delta(c.mean_energy_shed_mwh)}
    </div>`).join('');

  const yearAgo = cmp.find(c => c.year === now.year - 1);
  const noteEl = document.getElementById('seasonal-note');
  if (yearAgo && yearAgo.mean_energy_shed_mwh && now.mean_energy_shed_mwh) {
    const ratio = now.mean_energy_shed_mwh / yearAgo.mean_energy_shed_mwh;
    noteEl.innerHTML = `<div class="note ${ratio >= 1 ? 'warn' : ''}">` +
      t('seasonalNote')
        .replace('{now}', fmt(now.mean_energy_shed_mwh))
        .replace('{prev}', fmt(yearAgo.mean_energy_shed_mwh))
        .replace('{year}', fmtYear(yearAgo.year))
        .replace('{times}', fmt(ratio >= 1 ? ratio : 1 / ratio, 1))
        .replace('{dir}', ratio >= 1
          ? (LANG === 'bn' ? 'বেশি' : 'more')
          : (LANG === 'bn' ? 'কম' : 'less')) +
      `</div>`;
  }
}


/* ═══════════════════════════ the plain-language answer ═══════════════════ */

// Bangladesh's electricity use averages roughly 560 kWh per person per year.
// Dividing the shortfall by a day of that turns an abstract MWh figure into
// "how many people's daily electricity went missing". The assumption is stated
// on screen rather than buried here.
const PER_CAPITA_KWH_DAY = 560 / 365;

function dailyShedSeries() {
  const rows = (D.hourly && D.hourly.rows) || [];
  const byDay = new Map();
  for (const r of rows) {
    const day = r[0].slice(0, 10);
    byDay.set(day, (byDay.get(day) || 0) + (r[3] || 0));
  }
  return [...byDay.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1));
}

function renderVerdict() {
  const host = document.getElementById('verdict');
  const l = D.latest;
  if (!host || !l) return;

  // Compare like with like: today is still in progress, so ranking its
  // part-day total against completed days would understate it. Instead the
  // current reading is compared with the same hour on previous days.
  const rows = (D.hourly && D.hourly.rows) || [];
  const nowHour = (l.observed_at || '').slice(11, 13);
  const today = (l.observed_at || '').slice(0, 10);
  const sameHour = rows
    .filter(r => r[0].slice(11, 13) === nowHour && r[0].slice(0, 10) !== today
                 && r[3] !== null && r[3] !== undefined)
    .slice(-90)
    .map(r => r[3]);
  if (sameHour.length < 10 || l.loadshed === null || l.loadshed === undefined) {
    host.innerHTML = ''; return;
  }
  const history = sameHour.slice().sort((a, b) => a - b);
  const at = (q) => history[Math.floor(q * (history.length - 1))];
  const v = l.loadshed;
  const median = at(0.5), lo = at(0.25), hi = at(0.75);

  const days = dailyShedSeries();
  const todayEnergy = days.length ? days[days.length - 1][1] : 0;

  const people = (todayEnergy * 1000) / PER_CAPITA_KWH_DAY;  // MWh -> kWh -> people
  host.innerHTML = `
    <div class="verdict">
      <div class="verdict-body">
        <p class="verdict-line">${t('vLine')
          .replace('{mw}', `<b>${fmt(l.loadshed)}</b>`)
          .replace('{median}', `<b>${fmt(median)}</b>`)
          .replace('{lo}', fmt(lo)).replace('{hi}', fmt(hi))
          .replace('{days}', fmt(history.length))
          .replace('{hour}', fmt(+nowHour))}</p>
        <p class="verdict-sub">${t('vPeople')
          .replace('{people}', `<b>${fmtPeople(people)}</b>`)
          .replace('{mwh}', fmt(todayEnergy))}</p>
      </div>
    </div>`;
}

/** People-scale rounding: crore / lakh in Bengali, million in English. */
function fmtPeople(n) {
  if (!n || n <= 0) return '—';
  if (LANG === 'bn') {
    return n >= 1e7 ? `${fmt(n / 1e7, 1)} কোটি` : `${fmt(n / 1e5, 1)} লাখ`;
  }
  return n >= 1e6 ? `${fmt(n / 1e6, 1)} million` : `${fmt(n / 1e3, 0)} thousand`;
}

/* ═══════════════════════════ how demand has grown ════════════════════════ */

function renderDemand() {
  const d = D.demand;
  if (!d) return;
  const years = Object.keys(d.by_year).sort();
  const ramp = ['#9DC4EE', '#6BA5E8', '#3987e5', '#1c5cab'];

  const lines = years.slice(0, -1).map((y, i) => ({
    label: fmtYear(y), color: ramp[Math.max(0, ramp.length - (years.length - 1) + i)],
    values: d.by_year[y],
  })).concat([{ label: fmtYear(years[years.length - 1]), color: C.loadshed,
                values: d.by_year[years[years.length - 1]], emphasis: true }]);

  const monthName = (m) => new Intl.DateTimeFormat(locale(), { month: 'short' })
    .format(new Date(2021, m, 1));
  // Eid moves about eleven days earlier each year, so a single set of rules
  // would misexplain four of the five lines. Each year carries its own marks;
  // only the highlighted year's are shown, so isolating a line from the legend
  // lets the reader check that year's dip for themselves.
  const marks = (d.holidays || []).map(h => ({
    index: h.doy - 1, key: fmtYear(h.year),
    label: `${t('eid')} ${fmtYear(h.year)}`,
  }));

  multiLine(document.getElementById('dem-year'), lines, {
    height: 300, length: 365, monthLabel: monthName, baseline: 'auto', marks,
    xtip: (i) => {
      const x = new Date(2021, 0, 1); x.setDate(i + 1);
      return new Intl.DateTimeFormat(locale(), { day: 'numeric', month: 'long' }).format(x);
    },
    yfmt: (v) => fmt(v),
  });

  // the decade behind those five years
  const a = d.annual;
  barChart(document.getElementById('dem-decade'),
    a.map(x => ({ x: x.year, v: x.median, year: x.year, p95: x.p95, days: x.days })),
    'v', {
      height: 240, color: C.supply, label: t('demMedian'),
      xlabel: (r) => fmtYear(r.year),
      xtip: (r) => `${fmtYear(r.year)} · ${t('demP95')} ${fmt(r.p95)} ${t('mw')}`,
    });

  const hol = d.holidays || [];
  const noteEl = document.querySelector('[data-i18n="demHolidayNote"]');
  if (noteEl && hol.length) {
    const drops = hol.map(h => h.drop_pct);
    noteEl.textContent = t('demHoliday')
      .replace('{n}', fmt(hol.length))
      .replace('{y}', fmt(new Set(hol.map(h => h.year)).size))
      .replace('{min}', fmt(Math.min(...drops), 0))
      .replace('{max}', fmt(Math.max(...drops), 0));
  }

  const g = d.growth;
  const tile = (label, value, unit, note) => `
    <div class="stat">
      <div class="stat-label">${label}</div>
      <div class="stat-value">${value}<span class="stat-unit">${unit || ''}</span></div>
      ${note ? `<div class="stat-note">${note}</div>` : ''}
    </div>`;
  const last = a[a.length - 1];
  document.getElementById('dem-tiles').innerHTML =
    tile(t('demGrowth'), `+${fmt(g.total_pct, 0)}%`, '',
         t('demGrowthNote').replace('{a}', fmtYear(g.from)).replace('{b}', fmtYear(g.to))) +
    tile(t('demCagr'), `${fmt(g.cagr_pct, 1)}%`, t('perYear'),
         `${fmt(g.median_from)} → ${fmt(g.median_to)} ${t('mw')}`) +
    tile(t('demPeak'), fmt(last.p95), t('mw'),
         t('demPeakNote').replace('{y}', fmtYear(last.year)));
}

/* ═════════════════════ what the electricity costs to make ════════════════ */

function renderCostSeg() {
  const seg = document.getElementById('costmode-seg');
  if (!seg) return;
  D.costMode = D.costMode || 'unit';
  seg.innerHTML = [['unit', 'costUnitMode'], ['total', 'costTotalMode']].map(([k, l]) =>
    `<button type="button" data-k="${k}" aria-pressed="${D.costMode === k}">${t(l)}</button>`
  ).join('');
  seg.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    D.costMode = b.dataset.k;
    renderCostSeg();
    renderCost();
  }));
}

function renderCost() {
  const c = D.cost;
  if (!c) return;
  const unitMode = (D.costMode || 'unit') === 'unit';
  const store = unitMode ? c.unit_by_year : c.crore_by_year;
  const years = Object.keys(store).sort();
  if (!years.length) return;

  const el_ = document.getElementById('costyear-title');
  if (el_) el_.textContent = unitMode ? t('costYearUnit') : t('costYearTotal');

  const ramp = ['#86b6ef', '#3987e5', '#256abf', '#0d366b'];
  const lines = years.slice(0, -1).map((y, i) => ({
    label: fmtYear(y), color: ramp[Math.max(0, ramp.length - (years.length - 1) + i)],
    values: store[y],
  })).concat([{ label: fmtYear(years[years.length - 1]), color: C.loadshed,
                values: store[years[years.length - 1]], emphasis: true }]);

  const monthName = (m) => new Intl.DateTimeFormat(locale(), { month: 'short' })
    .format(new Date(2021, m, 1));
  multiLine(document.getElementById('costyear-chart'), lines, {
    height: 300, length: 365, monthLabel: monthName,
    baseline: unitMode ? 'auto' : 'zero',
    xtip: (i) => {
      const d = new Date(2021, 0, 1); d.setDate(i + 1);
      return new Intl.DateTimeFormat(locale(), { day: 'numeric', month: 'long' }).format(d);
    },
    yfmt: (v) => fmt(v, unitMode ? 1 : 0),
  });

  // headline tiles
  const tile = (label, value, unit, note) => `
    <div class="stat">
      <div class="stat-label">${label}</div>
      <div class="stat-value">${value}<span class="stat-unit">${unit || ''}</span></div>
      ${note ? `<div class="stat-note">${note}</div>` : ''}
    </div>`;
  const d = c.decomposition;
  document.getElementById('cost-tiles').innerHTML =
    tile(t('costPerDay'), fmt(c.latest.total_cost_crore), t('crore'),
         `${fmtDate(c.latest.date)} · ${t('costPerDayNote')}`) +
    tile(t('costPerUnit'), fmt(c.latest.cost_per_kwh, 2), t('takaKwh'), '') +
    (d ? tile(t('costYoy'), `${d.change > 0 ? '+' : ''}${fmt(d.change, 2)}`, t('takaKwh'),
              t('costYoyNote').replace('{a}', fmtDate(d.from + '-01', { month: 'long', year: 'numeric' }))) : '');

  // why it moved
  const box = document.getElementById('cost-decomp');
  if (!box) return;
  if (!d) { box.innerHTML = ''; return; }
  const mixPct = Math.abs(d.mix_effect) / (Math.abs(d.mix_effect) + Math.abs(d.price_effect));
  box.innerHTML = `<div class="note">
      <div class="note-title">${t('costWhyTitle')}</div>
      <div class="decomp">
        <div class="decomp-bar">
          <i style="width:${(100 * mixPct).toFixed(1)}%;background:${C.loadshed}"></i>
          <i style="width:${(100 * (1 - mixPct)).toFixed(1)}%;background:${C.supply}"></i>
        </div>
        <div class="decomp-key">
          <span><i class="swatch" style="background:${C.loadshed}"></i>${t('costMix')} <b>${d.mix_effect > 0 ? '+' : ''}${fmt(d.mix_effect, 2)}</b></span>
          <span><i class="swatch" style="background:${C.supply}"></i>${t('costPrice')} <b>${d.price_effect > 0 ? '+' : ''}${fmt(d.price_effect, 2)}</b></span>
        </div>
      </div>
      <p style="margin-top:10px;font-size:.88rem">${t('costWhyBody')
        .replace('{total}', fmt(d.change, 2))
        .replace('{mix}', fmt(d.mix_effect, 2))
        .replace('{price}', fmt(d.price_effect, 2))
        .replace('{gasBefore}', fmt(100 * d.shares_before.gas, 0))
        .replace('{gasAfter}', fmt(100 * d.shares_after.gas, 0))
        .replace('{gasPriceBefore}', fmt(d.prices_before.gas, 2))
        .replace('{gasPriceAfter}', fmt(d.prices_after.gas, 2))}</p>
    </div>`;
}

/* ══════════════════════ fuel: month by month, year on year ═══════════════ */

const FUEL_GROUPS = ['gas', 'coal', 'import', 'oil', 'renewable'];
const GROUP_COLOR = {
  gas: C.s[0], coal: C.s[1], import: C.s[2], oil: C.s[3], renewable: C.s[5],
};

/** Stacked bars over months — bars, not an area, because months are discrete. */
function stackedBars(host, rows, series, opts = {}) {
  if (!rows.length) { host.innerHTML = `<p class="loading">${t('noData')}</p>`; return; }
  const f = frame(host, { height: opts.height || 300, padL: 52 });
  const { svg, padL, padT, iw, ih } = f;
  const totals = rows.map(r => series.reduce((a, s) => a + (r[s.key] || 0), 0));
  const ymax = (opts.share ? 100 : Math.max(...totals, 1) * 1.08);
  const y = yAxis(f, 0, ymax, opts.yfmt);
  const bw = iw / rows.length;
  const gap = Math.min(4, bw * 0.22);

  rows.forEach((row, i) => {
    let acc = 0;
    const scale = opts.share ? 100 / (totals[i] || 1) : 1;
    for (const s of series) {
      const v = (row[s.key] || 0) * scale;
      if (v <= 0) continue;
      const y0 = y(acc), y1 = y(acc + v);
      const rect = el('rect', {
        x: padL + i * bw + gap / 2, width: Math.max(1, bw - gap),
        y: y1, height: Math.max(1, y0 - y1), fill: s.color,
        stroke: '#ffffff', 'stroke-width': 1,
      }, svg);
      rect.addEventListener('pointerenter', () => {
        const body = series.map(q => tipRow(q.color, q.label,
          opts.share ? pct((row[q.key] || 0) / (totals[i] || 1))
                     : fmt(row[q.key] || 0, 1))).join('');
        showTip(f, padL + i * bw + bw / 2,
          `<div class="tip-date">${opts.xtip ? opts.xtip(row) : row.month}</div>${body}` +
          (opts.share ? '' : tipRow(null, t('fuelTotal'), fmt(totals[i], 1))));
      });
      rect.addEventListener('pointerleave', () => hideTip(f));
      acc += v;
    }
  });

  const step = Math.max(1, Math.round(rows.length / 7));
  for (let i = 0; i < rows.length; i += step) {
    const lb = el('text', { x: padL + i * bw + bw / 2, y: padT + ih + 18,
                            'text-anchor': 'middle' }, svg);
    lb.textContent = opts.xlabel ? opts.xlabel(rows[i]) : rows[i].month;
  }
  el('line', { class: 'axis-line', x1: padL, x2: padL + iw, y1: padT + ih, y2: padT + ih }, svg);
  legend(host, series);
}

function renderFuelModeSeg() {
  const seg = document.getElementById('fuelmode-seg');
  if (!seg) return;
  D.fuelMode = D.fuelMode || 'abs';
  seg.innerHTML = [['abs', 'fuelAbs'], ['share', 'fuelShare']].map(([k, l]) =>
    `<button type="button" data-k="${k}" aria-pressed="${D.fuelMode === k}">${t(l)}</button>`
  ).join('');
  seg.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    D.fuelMode = b.dataset.k;
    renderFuelModeSeg();
    renderFuelMonthly();
  }));
}

function renderFuelMonthly() {
  const fm = D.fuelmix;
  if (!fm || !fm.monthly || !fm.monthly.length) return;
  const share = D.fuelMode === 'share';
  const el_ = document.getElementById('fuelmonth-title');
  if (el_) el_.textContent = share ? t('fuelMonthShare') : t('fuelMonthAbs');

  stackedBars(document.getElementById('fuelmonth-chart'), fm.monthly,
    FUEL_GROUPS.map(k => ({ key: k, label: FUEL_NAMES[LANG][k] || k,
                            color: GROUP_COLOR[k] })), {
      height: 300, share,
      yfmt: (v) => (share ? `${fmt(v)}%` : fmt(v)),
      xlabel: (r) => fmtDate(r.month + '-01', { month: 'short', year: '2-digit' }),
      xtip: (r) => fmtDate(r.month + '-01', { month: 'long', year: 'numeric' }),
    });

  // the same month a year apart — the only fair comparison for a seasonal system
  const c = fm.same_month;
  const box = document.getElementById('fuel-yoy');
  if (!box) return;
  if (!c) { box.innerHTML = ''; return; }
  const arrow = (v) => (v > 0 ? '+' : '') + fmt(v, 1) + '%';
  const cls = (v) => (v > 5 ? 'up' : v < -5 ? 'down' : '');
  const label = fmtDate(c.now.month + '-01', { month: 'long' });
  box.innerHTML = `<div class="note">
      <div class="note-title">${t('fuelYoyTitle')
        .replace('{m}', label)
        .replace('{a}', fmtYear(c.before.month.slice(0, 4)))
        .replace('{b}', fmtYear(c.now.month.slice(0, 4)))}</div>
      <div class="yoy-row">${['total', 'gas', 'coal', 'oil', 'import'].map(k =>
        `<span class="yoy ${cls(c.changes[k])}"><b>${t('fuel_' + k) || k}</b> ${arrow(c.changes[k])}</span>`
      ).join('')}</div>
      <p style="margin-top:8px;font-size:.88rem">${t('fuelYoyBody')}</p>
    </div>`;
}

/* ═══════════════ BPDB's own report: causes, forecast, unit cost ══════════ */

const CAUSE_ORDER = ['maintenance', 'gas_lf', 'kaptai', 'coal'];
const CAUSE_COLOR = {
  maintenance: C.s[0], gas_lf: C.s[1], kaptai: C.s[2], coal: C.s[3],
};

function renderCauses() {
  const host = document.getElementById('cause-chart');
  const rows = (D.official && D.official.causes) || [];
  if (!host || !rows.length) return;
  const recent = rows.slice(-180).map(r => ({
    x: r.date,
    maintenance: r.maintenance || 0, gas_lf: r.gas_lf || 0,
    kaptai: r.kaptai || 0, coal: r.coal || 0,
  }));
  stackedArea(host, recent,
    CAUSE_ORDER.map(k => ({ key: k, label: t('cause_' + k), color: CAUSE_COLOR[k] })), {
      height: 230,
      totalLabel: LANG === 'bn' ? 'মোট ঘাটতি' : 'Total shortfall',
      xlabel: (r) => fmtDate(r.x, { day: 'numeric', month: 'short' }),
      xtip: (r) => fmtDate(r.x),
      yfmt: (v) => fmt(v),
    });
}

function renderForecast() {
  const o = D.official;
  if (!o || !o.forecast || !o.forecast.length) return;
  const s = o.forecast_summary;

  const tile = (label, value, unit, note) => `
    <div class="stat">
      <div class="stat-label">${label}</div>
      <div class="stat-value">${value}<span class="stat-unit">${unit || ''}</span></div>
      ${note ? `<div class="stat-note">${note}</div>` : ''}
    </div>`;

  // The practice changed between years, so the two are shown apart rather
  // than blended into one average that describes neither.
  const yrs = Object.keys(s.by_year || {}).sort();
  document.getElementById('fc-tiles').innerHTML = yrs.map(y => {
    const v = s.by_year[y];
    return `
      <div class="stat">
        <div class="stat-label">${fmtYear(y)}</div>
        <div class="stat-value">${fmt(v.forecast_zero)} / ${fmt(v.days)}<span class="stat-unit">${t('fcZeroUnit')}</span></div>
        <div class="stat-note">${t('fcMissedInline')
          .replace('{n}', fmt(v.forecast_zero_but_shed))
          .replace('{mw}', fmt(v.mean_shed_on_those_days))}</div>
      </div>`;
  }).join('') + `
      <div class="stat">
        <div class="stat-label">${t('fcWorst')}</div>
        <div class="stat-value">${fmt(s.worst ? s.worst.actual_loadshed : null)}<span class="stat-unit">${t('mw')}</span></div>
        <div class="stat-note">${s.worst ? t('fcWorstNote').replace('{d}', fmtDate(s.worst.date)) : ''}</div>
      </div>`;

  const rows = o.forecast.slice(-180).map(r => ({
    x: r.date, f: r.forecast_loadshed || 0, a: r.actual_loadshed || 0,
  }));
  const host = document.getElementById('fc-chart');
  const f = frame(host, { height: 260 });
  const { svg, padL, padT, iw, ih } = f;
  const ymax = Math.max(...rows.map(r => Math.max(r.f, r.a)), 1) * 1.08;
  const y = yAxis(f, 0, ymax, (v) => fmt(v));
  const x = (i) => padL + (rows.length === 1 ? iw / 2 : (i / (rows.length - 1)) * iw);

  // actual as an area, forecast as a line over it — the gap is the story
  const up = rows.map((r, i) => `${x(i)},${y(r.a)}`).join(' ');
  el('polygon', { points: `${padL},${y(0)} ${up} ${padL + iw},${y(0)}`,
                  fill: C.loadshed, 'fill-opacity': 0.18 }, svg);
  el('polyline', { points: up, fill: 'none', stroke: C.loadshed, 'stroke-width': 2,
                   'stroke-linejoin': 'round' }, svg);
  el('polyline', { points: rows.map((r, i) => `${x(i)},${y(r.f)}`).join(' '),
                   fill: 'none', stroke: C.supply, 'stroke-width': 2,
                   'stroke-dasharray': '5 3', 'stroke-linejoin': 'round' }, svg);

  const step = Math.max(1, Math.round(rows.length / 6));
  for (let i = 0; i < rows.length; i += step) {
    const lb = el('text', { x: x(i), y: padT + ih + 18, 'text-anchor': 'middle' }, svg);
    lb.textContent = fmtDate(rows[i].x, { day: 'numeric', month: 'short' });
  }
  el('line', { class: 'axis-line', x1: padL, x2: padL + iw, y1: padT + ih, y2: padT + ih }, svg);

  const cross = el('line', { y1: padT, y2: padT + ih, stroke: C.muted,
                             'stroke-width': 1, opacity: 0 }, svg);
  const hit = el('rect', { x: padL, y: padT, width: iw, height: ih, fill: 'transparent' }, svg);
  hit.addEventListener('pointermove', (ev) => {
    const bb = svg.getBoundingClientRect();
    const px = (ev.clientX - bb.left) * (f.width / bb.width);
    let i = Math.round(((px - padL) / iw) * (rows.length - 1));
    i = Math.max(0, Math.min(rows.length - 1, i));
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i));
    cross.setAttribute('opacity', 0.55);
    showTip(f, x(i), `<div class="tip-date">${fmtDate(rows[i].x)}</div>` +
      tipRow(C.supply, t('fcForecast'), fmt(rows[i].f)) +
      tipRow(C.loadshed, t('fcActual'), fmt(rows[i].a)));
  });
  hit.addEventListener('pointerleave', () => {
    hideTip(f); cross.setAttribute('opacity', 0);
  });
  legend(host, [{ label: t('fcForecast'), color: C.supply },
                { label: t('fcActual'), color: C.loadshed }]);
}

function renderUnitCost() {
  const host = document.getElementById('unitcost-chart');
  const rows = (D.official && D.official.unit_cost) || [];
  if (!host || !rows.length) return;
  const last = rows.slice(-30);
  const keys = ['gas', 'coal', 'import', 'renewable', 'oil'];
  const items = keys.map(k => {
    const v = last.map(r => r[k]).filter(x => x !== undefined && x !== null);
    return v.length ? { label: t('fuel_' + k), value: v.reduce((a, b) => a + b, 0) / v.length,
                        color: k === 'oil' ? C.loadshed : C.supply } : null;
  }).filter(Boolean).sort((a, b) => a.value - b.value);
  hBars(host, items, {
    fmtValue: (v) => `${fmt(v, 2)} ${LANG === 'bn' ? 'টাকা' : 'Tk'}`,
    valueLabel: t('unitCostTitle'),
  });
}

/* ══════════════════════════════════ boot ═════════════════════════════════ */

function renderAll() {
  renderStatic();
  renderUpdated();
  renderRangeSeg();
  renderNow();
  renderVerdict();
  renderSearch();
  renderWhy();
  renderEquitySeg();
  renderEquity();
  renderCauses();
  renderForecast();
  renderUnitCost();
  renderFuelModeSeg();
  renderFuelMonthly();
  renderCostSeg();
  renderCost();
  renderDemand();
  renderMapSeg();
  renderMap();
  renderFuel();
  renderZones();
  renderSeasonal();
  renderMetricSeg();
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
    renderEquity();
    renderCauses();
    renderForecast();
    renderUnitCost();
    renderFuelMonthly();
    renderCost();
    renderDemand();
    if (D.selectedArea) renderArea(D.selectedArea);
    renderFuel();
    renderZones();
    renderSeasonal();
    renderTrend();
  }, 220);
});

loadAll().then(renderAll).catch(err => {
  console.error(err);
  document.getElementById('updated-text').textContent = 'Failed to load data.';
});
