/* The Civil Service Paybook.
   Every figure on the page is derived here from the primitives in
   data/payscale.json, so the page and the CSVs behind it cannot drift apart.
   The fixation routine is article 5 of the 2026 order, written out verbatim. */
(function(){
  const slot = document.getElementById("loadstate");
  fetch("data/payscale.json")
    .then(r => { if(!r.ok) throw new Error("HTTP "+r.status); return r.json(); })
    .then(DATA => { if(slot) slot.remove(); boot(DATA); })
    .catch(err => {
      if(slot) slot.textContent =
        "The figures could not be loaded (" + err.message + "). " +
        "The page needs data/payscale.json beside it.";
    });

function boot(DATA){
const PX=DATA.px, LAD=DATA.ladders, EFF=DATA.eff;
const ERAS=Object.keys(EFF).filter(e=>LAD[e]).sort((a,b)=>EFF[a]-EFF[b]);
const CAD={govt_civil:"Civil (general)",police:"Police",bdr_bgb:"Border guard",
  banks_financial_institutions:"Banks & financial",
  autonomous_public_bodies:"Autonomous bodies",judicial_service:"Judicial service",
  members_of_parliament:"Members of Parliament"};
const LINE=["--l1","--l2","--l3","--l4","--l5"];
const fmt=n=>n==null||isNaN(n)?"—":Math.round(n).toLocaleString("en-US");
const pc=n=>(n>=0?"+":"")+n.toFixed(1)+"%";
const cv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const esc=s=>String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const yr=e=>EFF[e];
const px=y=>PX[y]!=null?PX[y]:PX[Math.max(...Object.keys(PX).map(Number))];
const lad=(e,g)=>(LAD[e]||{})[String(g)]||null;

/* ---------- article 5, verbatim from the order ---------- */
function fixPay(oldBasic, oldL, newL){
  if(oldBasic<=oldL[0])
    return {rule:"5(ka)",diff:0,target:newL[0],newBasic:newL[0],newStep:0,exact:true};
  const diff=oldBasic-oldL[0], target=newL[0]+diff;
  let i=newL.findIndex(v=>v>=target);
  if(i<0) return {rule:"5(kha) — ceiling",diff,target,newBasic:newL[newL.length-1],
                  newStep:newL.length-1,exact:false,capped:true};
  return {rule:newL[i]===target?"5(kha)(a)":"5(kha)(aa)",diff,target,
          newBasic:newL[i],newStep:i,exact:newL[i]===target};
}
/* phased release: share of the rise actually paid in each window */
const PHASES=[
  {id:"p1",  label:"July 2026 — first phase",  lo:0.40, hi:0.50, year:2026},
  {id:"p2",  label:"January 2027 — second phase", lo:0.70, hi:0.75, year:2027},
  {id:"full",label:"July 2027 — scale in full", lo:1, hi:1, year:2027}];
function phasePay(oldB,newB,grade,ph){
  const share=grade<=9?ph.lo:ph.hi;
  return {pay:Math.round(oldB+(newB-oldB)*share), share};
}
/* rows for a whole grade across one transition */
function gradeRows(from,to,grade){
  const a=lad(from,grade), b=lad(to,grade);
  if(!a||!b) return null;
  return a.map((old,i)=>{
    const f=fixPay(old,a,b);
    return {i, old, ...f, raise:(f.newBasic/old-1)*100, move:f.newStep-i};
  });
}
function inflMult(from,to){ return px(yr(to))/px(yr(from)); }

/* =================== verdict strip =================== */
const F="nps_2015", T="nps_2026";
const INF=inflMult(F,T);
(function(){
  /* "verified" means checked step by step against the gazette's own table, which
     is true of 2015 and 2026 only; the rest are expanded from printed increment
     bands, which is a weaker claim and is labelled as such */
  let gaz=0; for(const e of [F,T]) for(const g in LAD[e]) gaz+=LAD[e][g].length;
  let steps=0; for(const e of ERAS) for(const g in LAD[e]) steps+=LAD[e][g].length;
  document.getElementById("s-steps").textContent=gaz.toLocaleString("en-US");
  document.getElementById("s-steps-all").textContent=steps.toLocaleString("en-US");
  const r10=gradeRows(F,T,10), r20=gradeRows(F,T,20);
  const worst=Math.min(...Array.from({length:19},(_,k)=>k+2)
    .map(g=>{const r=gradeRows(F,T,g);return r?Math.min(...r.map(x=>x.move)):0;}));
  let collapsed=0,demoted=0,tot=0;
  for(let g=2;g<=20;g++){const r=gradeRows(F,T,g); if(!r)continue;
    collapsed+=r.length-new Set(r.map(x=>x.newBasic)).size;
    demoted+=r.filter(x=>x.move<0).length; tot+=r.length;}
  const realEntry=(2/INF-1)*100, realTop=(r10[r10.length-1].newBasic/r10[r10.length-1].old/INF-1)*100;
  document.getElementById("verdictstrip").innerHTML=[
    ["Prices, 2015 → 2026","+115.3%","consumer price index, World Bank and IMF chained",""],
    ["The scale","+100%","at the first step of grades 1 to 11","" ],
    ["A new entrant, grade 10",pc(realEntry),"real change against 2015",realEntry<0?"dn":"up"],
    ["A grade 10 officer at the top step",pc(realTop),"real change against 2015",realTop<0?"dn":"up"],
    ["Seniority positions erased",String(collapsed),"steps that stop being distinguishable in pay","dn"],
    ["Moved down the ladder",demoted+" of "+tot,"worst move "+worst+" stages","dn"]
  ].map(([k,v,n,c])=>`<div class="vd"><div class="k">${k}</div>
    <div class="v ${c}">${v}</div><div class="n">${n}</div></div>`).join("");
  document.getElementById("scopenote").innerHTML=
    "The 2026 order covers the civil service only. Judicial officers, defence, "+
    "police and the Border Guard, state industrial workers, apprentices, outsourced "+
    "and contract staff are outside it — the single national ladder built in 2015 "+
    "no longer covers them.";
})();

/* =================== calculator =================== */
/* The 1973 order set TEN national scales, not twenty grades: its scale 10 is the
   bottom of its system, where 1977's grade 10 is mid-table. Comparing them by
   number is meaningless -- it reported +107% real at entry where a like-for-like
   bottom-to-bottom reading gives -15% -- so 1973 is not paired with 1977 here. */
const INCOMPARABLE=new Set(["nps_1973"]);
const PAIRS=[];
for(let i=1;i<ERAS.length;i++){
  if(INCOMPARABLE.has(ERAS[i-1])||INCOMPARABLE.has(ERAS[i])) continue;
  PAIRS.push([ERAS[i-1],ERAS[i]]);
}
const elPair=document.getElementById("c-pair"), elGrade=document.getElementById("c-grade"),
      elStep=document.getElementById("c-step"), elPhase=document.getElementById("c-phase");
PAIRS.forEach(([a,b],i)=>{const o=document.createElement("option");
  o.value=i; o.textContent=yr(a)+" scale → "+yr(b)+" scale"; elPair.append(o);});
elPair.value=PAIRS.length-1;
for(let g=1;g<=20;g++){const o=document.createElement("option"); o.value=g;
  o.textContent="Grade "+g+(g===1?" — Secretary":g===9?" — BCS entry":g===20?" — lowest":"");
  elGrade.append(o);}
elGrade.value=10;
PHASES.forEach((p,i)=>{const o=document.createElement("option");o.value=i;
  o.textContent=p.label;elPhase.append(o);});
elPhase.value=2;

function renderCalc(){
  const [from,to]=PAIRS[+elPair.value], g=+elGrade.value;
  const a=lad(from,g), b=lad(to,g);
  const isNew=(to===T);
  elPhase.closest(".ctl").hidden=!isNew;
  const der=document.getElementById("c-derive"), out=document.getElementById("c-out");
  if(!a||!b){
    elStep.disabled=true;
    der.innerHTML="<div class='step'>No readable ladder for grade "+g+
      " in both the "+yr(from)+" and "+yr(to)+" scales. Try another grade or pair.</div>";
    out.innerHTML=""; document.getElementById("gt-body").innerHTML="";
    document.getElementById("gt-note").textContent=""; return;
  }
  elStep.disabled=false;
  elStep.max=a.length; if(+elStep.value>a.length) elStep.value=a.length;
  const si=+elStep.value-1, oldB=a[si];
  document.getElementById("c-step-o").textContent=si+1;
  const f=fixPay(oldB,a,b), ph=PHASES[+elPhase.value];
  const infl=inflMult(from,to), raise=(f.newBasic/oldB-1)*100, real=(f.newBasic/oldB/infl-1)*100;

  der.innerHTML=[
    `<div class="step"><span class="tag">basic</span><span>On the ${yr(from)} scale,
      step ${si+1} of grade ${g} pays <b>৳${fmt(oldB)}</b>. The scale runs
      <b>৳${fmt(a[0])}</b> to <b>৳${fmt(a[a.length-1])}</b> over ${a.length} steps.</span></div>`,
    f.diff===0
      ? `<div class="step"><span class="tag">${f.rule}</span><span>Pay is at or below the
          starting step, so it is fixed at the new scale's starting step.</span></div>`
      : `<div class="step"><span class="tag">5(kha)</span><span>Subtract the old scale's
          starting step: ৳${fmt(oldB)} − ৳${fmt(a[0])} = <b>৳${fmt(f.diff)}</b>.</span></div>
         <div class="step"><span class="tag">5(kha)</span><span>Add that difference to the
          new scale's starting step: ৳${fmt(b[0])} + ৳${fmt(f.diff)} =
          <b>৳${fmt(f.target)}</b>.</span></div>
         <div class="step"><span class="tag">${f.rule}</span><span>${f.exact
            ? "That amount is itself a step on the new ladder, so it is the new basic."
            : "That amount is not a step on the new ladder, so pay rises to the next step above it"+
              (f.capped?", which is the ceiling of the scale.":".")}</span></div>`,
    `<div class="step"><span class="tag">result</span><span>New basic
      <b>৳${fmt(f.newBasic)}</b> — step <b>${f.newStep+1}</b> of ${b.length} on the
      ${yr(to)} scale, against step ${si+1} of ${a.length} before.</span></div>`
  ].join("");

  const cells=[
    ["Old basic","৳"+fmt(oldB),"step "+(si+1)+" · "+yr(from)+" scale",""],
    ["New basic","৳"+fmt(f.newBasic),"step "+(f.newStep+1)+" · "+yr(to)+" scale",""],
    ["Raise",pc(raise),"nominal, on fixation",raise>0?"up":"dn"],
    ["After inflation",pc(real),"prices rose "+((infl-1)*100).toFixed(1)+"% between the scales",
      real>=0?"up":"dn"],
    ["Step position",(f.newStep-si>=0?"+":"")+(f.newStep-si),
      f.newStep<si?"moved down the ladder":f.newStep>si?"moved up":"unchanged",
      f.newStep<si?"dn":f.newStep>si?"up":""]
  ];
  if(isNew){
    const p=phasePay(oldB,f.newBasic,g,ph);
    cells.push(["Actually paid","৳"+fmt(p.pay),
      (p.share*100)+"% of the rise · "+ph.label.split(" — ")[0],""]);
  }
  out.innerHTML=cells.map(([k,v,n,c])=>`<div class="og"><div class="k">${k}</div>
    <div class="v ${c}">${v}</div><div class="n">${n}</div></div>`).join("");

  const rows=gradeRows(from,to,g);
  document.getElementById("gt-cap").textContent=
    "Grade "+g+", every step of the "+yr(from)+" scale fixed into the "+yr(to)+" scale";
  document.getElementById("gt-body").innerHTML=rows.map(r=>`
    <tr class="${r.i===si?"hl":""}"><td class="num">${r.i+1}</td>
      <td class="num">${fmt(r.old)}</td><td class="num">${fmt(r.newBasic)}</td>
      <td class="num">${r.newStep+1}</td>
      <td class="num ${r.move<0?"dn":r.move>0?"up":""}">${r.move>0?"+":""}${r.move}</td>
      <td class="num">${r.raise.toFixed(1)}%</td>
      <td class="num ${r.raise/100+1<infl?"dn":"up"}">${pc((r.newBasic/r.old/infl-1)*100)}</td></tr>`).join("");
  const dist=new Set(rows.map(r=>r.newBasic)).size, dem=rows.filter(r=>r.move<0).length;
  document.getElementById("gt-note").innerHTML=
    `${rows.length} steps on the ${yr(from)} scale become <b>${dist}</b> distinct amounts on
     the ${yr(to)} scale — ${rows.length-dist} seniority positions stop being
     distinguishable in pay. <b>${dem}</b> of ${rows.length} land lower in the ladder
     than they stood.`;
}
[elPair,elGrade,elStep,elPhase].forEach(el=>el.addEventListener("input",renderCalc));

/* =================== svg helpers =================== */
function svg(w,h,body){return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"
  role="img" style="min-width:${Math.min(w,560)}px">${body}</svg>`;}
function axisText(x,y,t,anchor,size,fill){
  return `<text x="${x}" y="${y}" text-anchor="${anchor||"middle"}"
    font-family="${cv("--mono")}" font-size="${size||11}"
    fill="${fill||cv("--ink-3")}">${t}</text>`;}
function path(d,stroke,w,dash){
  return `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="${w||2}"
    ${dash?`stroke-dasharray="${dash}"`:""} stroke-linejoin="round" stroke-linecap="round"/>`;}

/* =================== regressivity chart =================== */
let RG=[2,6,10,16,20];
(function(){
  const box=document.getElementById("rg-chips");
  [2,4,6,9,10,13,16,20].forEach(g=>{
    const b=document.createElement("button"); b.textContent="Grade "+g;
    b.setAttribute("aria-pressed",RG.includes(g));
    b.onclick=()=>{RG.includes(g)?RG=RG.filter(x=>x!==g):RG.push(g);
      if(!RG.length)RG=[g]; box.querySelectorAll("button").forEach((bb,i)=>
        bb.setAttribute("aria-pressed",RG.includes([2,4,6,9,10,13,16,20][i])));
      drawRegress();};
    box.append(b);});
})();
function drawRegress(){
  const W=980,H=400,L=58,R=18,Tp=18,B=46;
  const iw=W-L-R, ih=H-Tp-B, maxS=19, lo=30, hi=150;
  const X=s=>L+(s-1)/(maxS-1)*iw, Y=v=>Tp+ih-(v-lo)/(hi-lo)*ih;
  let s=`<rect x="0" y="0" width="${W}" height="${H}" fill="${cv("--panel")}"/>`;
  for(let v=lo;v<=hi;v+=20){
    s+=`<line x1="${L}" y1="${Y(v)}" x2="${W-R}" y2="${Y(v)}" stroke="${cv("--rule-2")}"/>`;
    s+=axisText(L-9,Y(v)+4,v+"%","end");}
  for(let k=1;k<=maxS;k+=2) s+=axisText(X(k),H-B+20,k);
  s+=axisText(L+iw/2,H-B+40,"Step held on the 2015 scale","middle",12,cv("--ink-2"));
  const infl=(INF-1)*100;
  s+=path(`M${L} ${Y(infl)} L${W-R} ${Y(infl)}`,cv("--cpi"),2,"7 5");
  s+=axisText(W-R-4,Y(infl)-8,"inflation "+infl.toFixed(1)+"%","end",11.5,cv("--cpi"));
  const leg=[];
  RG.forEach((g,gi)=>{
    const rows=gradeRows(F,T,g); if(!rows) return;
    const col=cv(LINE[gi%LINE.length]);
    s+=path(rows.map((r,i)=>(i?"L":"M")+X(r.i+1)+" "+Y(Math.max(lo,Math.min(hi,r.raise)))).join(" "),col,2.2);
    const last=rows[rows.length-1];
    s+=`<circle cx="${X(last.i+1)}" cy="${Y(Math.max(lo,Math.min(hi,last.raise)))}" r="3.5" fill="${col}"/>`;
    leg.push(`<span><i class="sw" style="background:${col}"></i>Grade ${g}</span>`);
  });
  document.getElementById("chart-regress").innerHTML=svg(W,H,s);
  document.getElementById("leg-regress").innerHTML=
    leg.join("")+`<span><i class="sw" style="background:${cv("--cpi")}"></i>Inflation 2015–2026</span>`;
  const g=RG.slice().sort((a,b)=>(lad(F,b)||[]).length-(lad(F,a)||[]).length)[0];
  const rows=gradeRows(F,T,g);
  const spread=rows[0].raise-rows[rows.length-1].raise;
  document.getElementById("regress-finding").textContent=
    `In grade ${g} the same order is worth ${rows[0].raise.toFixed(0)}% to a new entrant and `+
    `${rows[rows.length-1].raise.toFixed(0)}% to the most senior officer`;
  document.getElementById("regress-detail").innerHTML=
    `That is a spread of <b>${spread.toFixed(1)} percentage points</b> inside one grade, `+
    `for the same job. Across all grades the widest spread is <b>79.5 points</b>, at grade 20. `+
    `The raise is progressive between grades — the lowest grades get the largest multiple at `+
    `entry — and sharply regressive within them. Only the first is in the announcement.`;
}

/* =================== compression diagram =================== */
let CPG=10;
(function(){
  const box=document.getElementById("cp-chips");
  [2,4,6,8,10,13,16,20].forEach(g=>{
    const b=document.createElement("button"); b.textContent="Grade "+g;
    b.setAttribute("aria-pressed",g===CPG);
    b.onclick=()=>{CPG=g;box.querySelectorAll("button").forEach(bb=>
      bb.setAttribute("aria-pressed",bb.textContent==="Grade "+g));drawCompress();};
    box.append(b);});
})();
function drawCompress(){
  const rows=gradeRows(F,T,CPG); if(!rows) return;
  const a=lad(F,CPG), b=lad(T,CPG);
  const W=980,rowH=26,Tp=44,B=24;
  const H=Tp+B+Math.max(a.length,b.length)*rowH;
  const xL=250, xR=W-250;
  const yA=i=>Tp+i*rowH+rowH/2, yB=i=>Tp+i*rowH+rowH/2;
  let s=`<rect x="0" y="0" width="${W}" height="${H}" fill="${cv("--panel")}"/>`;
  s+=axisText(xL,26,"2015 scale — step and basic","end",12,cv("--ink-2"));
  s+=axisText(xR,26,"2026 scale — step and basic","start",12,cv("--ink-2"));
  const landed={};
  rows.forEach(r=>{(landed[r.newStep]=landed[r.newStep]||[]).push(r.i);});
  rows.forEach(r=>{
    const y1=yA(r.i), y2=yB(r.newStep);
    const many=landed[r.newStep].length>1;
    const col=many?cv("--loss"):r.move<0?cv("--warn"):cv("--accent");
    s+=`<path d="M${xL+8} ${y1} C${xL+120} ${y1}, ${xR-120} ${y2}, ${xR-8} ${y2}"
      fill="none" stroke="${col}" stroke-width="${many?2:1.4}" opacity="${many?.85:.5}"/>`;
  });
  a.forEach((v,i)=>{
    s+=axisText(xL,yA(i)+4,`${i+1}`,"end",11,cv("--ink-3"));
    s+=axisText(xL-26,yA(i)+4,"৳"+fmt(v),"end",11.5,cv("--ink-2"));});
  b.forEach((v,i)=>{
    const n=(landed[i]||[]).length;
    s+=axisText(xR,yB(i)+4,`${i+1}`,"start",11,cv("--ink-3"));
    s+=axisText(xR+26,yB(i)+4,"৳"+fmt(v)+(n>1?`  · ${n} steps here`:""),"start",11.5,
      n>1?cv("--loss"):cv("--ink-2"));});
  document.getElementById("chart-compress").innerHTML=svg(W,H,s);
  const dist=new Set(rows.map(r=>r.newBasic)).size;
  const dem=rows.filter(r=>r.move<0).length, worst=Math.min(...rows.map(r=>r.move));
  document.getElementById("cp-cap").innerHTML=
    `Grade ${CPG}. Red lines converge where two or more 2015 steps are fixed onto the same
     2026 step. ${rows.length} steps become ${dist} distinct amounts; ${dem} officers in
     ${rows.length} land lower in the ladder, the worst by ${Math.abs(worst)} stages.`;
  document.getElementById("demote-range").textContent=
    `${dem} of ${rows.length} officers in grade ${CPG}`;
}

/* =================== macro chart =================== */
let MG=10, MMODE="idx";
(function(){
  const box=document.getElementById("m-chips");
  [1,6,10,16,20].forEach(g=>{
    const b=document.createElement("button"); b.textContent="Grade "+g;
    b.setAttribute("aria-pressed",g===MG);
    b.onclick=()=>{MG=g;box.querySelectorAll("button").forEach(bb=>
      bb.setAttribute("aria-pressed",bb.textContent==="Grade "+g));drawMacro();};
    box.append(b);});
  document.getElementById("m-idx").onclick=()=>{MMODE="idx";syncM();};
  document.getElementById("m-real").onclick=()=>{MMODE="real";syncM();};
  function syncM(){document.getElementById("m-idx").setAttribute("aria-pressed",MMODE==="idx");
    document.getElementById("m-real").setAttribute("aria-pressed",MMODE==="real");drawMacro();}
})();
/* entry pay for a grade in a given year, on the scale in force that year */
function entryPay(g,y){
  let e=null; for(const k of ERAS) if(yr(k)<=y && lad(k,g)) e=k;
  return e?lad(e,g)[0]:null;
}
function drawMacro(){
  const W=980,H=420,L=62,R=118,Tp=20,B=46;
  const iw=W-L-R, ih=H-Tp-B;
  const y0=2015, y1=2028;
  const gdpN=DATA.gdp_nominal_pc, gdpP=DATA.gdp_ppp_pc;
  const base={pay:entryPay(MG,2015),cpi:px(2015),gn:gdpN[2015],gp:gdpP[2015]};
  const series=[];
  const payAt=y=>entryPay(MG,y);
  /* Each panel keeps one footing. The nominal panel compares taka with taka;
     the real panel compares constant-taka pay with constant-dollar income. Mixing
     a nominal pay line with a real income line on one axis compares nothing. */
  if(MMODE==="idx"){
    series.push({k:"Pay — grade "+MG+" entry",c:cv("--l1"),
      pts:range(y0,y1).map(y=>[y,payAt(y)/base.pay*100])});
    series.push({k:"Consumer prices",c:cv("--cpi"),dash:"6 4",
      pts:range(y0,y1).map(y=>[y,px(y)/base.cpi*100])});
    series.push({k:"GDP per head, nominal taka",c:cv("--l3"),
      pts:range(y0,y1).filter(y=>gdpN[y]).map(y=>[y,gdpN[y]/base.gn*100])});
  }else{
    series.push({k:"Pay — grade "+MG+" entry, in 2015 taka",c:cv("--l1"),
      pts:range(y0,y1).map(y=>[y,payAt(y)/px(y)*px(2015)/base.pay*100])});
    series.push({k:"Holding 2015 purchasing power",c:cv("--cpi"),dash:"6 4",
      pts:[[y0,100],[y1,100]]});
    series.push({k:"Real income per head (PPP)",c:cv("--l5"),
      pts:range(y0,y1).filter(y=>gdpP[y]).map(y=>[y,gdpP[y]/base.gp*100])});
  }
  const vals=series.flatMap(s=>s.pts.map(p=>p[1]));
  const lo=Math.min(80,Math.floor(Math.min(...vals)/20)*20);
  const hi=Math.ceil(Math.max(...vals)/20)*20;
  const X=y=>L+(y-y0)/(y1-y0)*iw, Y=v=>Tp+ih-(v-lo)/(hi-lo)*ih;
  let s=`<rect x="0" y="0" width="${W}" height="${H}" fill="${cv("--panel")}"/>`;
  for(let v=lo;v<=hi;v+=20){
    s+=`<line x1="${L}" y1="${Y(v)}" x2="${W-R}" y2="${Y(v)}" stroke="${cv("--rule-2")}"/>`;
    s+=axisText(L-9,Y(v)+4,v,"end");}
  for(let y=y0;y<=y1;y+=2) s+=axisText(X(y),H-B+20,y);
  /* the projection region */
  s+=`<rect x="${X(2026)}" y="${Tp}" width="${X(y1)-X(2026)}" height="${ih}"
       fill="${cv("--ink-3")}" opacity=".07"/>`;
  s+=axisText(X(2027),Tp+14,"projected","middle",11,cv("--ink-3"));
  const leg=[];
  series.forEach(ser=>{
    s+=path(ser.pts.map((p,i)=>(i?"L":"M")+X(p[0])+" "+Y(p[1])).join(" "),ser.c,2.2,ser.dash);
    const last=ser.pts[ser.pts.length-1];
    s+=`<circle cx="${X(last[0])}" cy="${Y(last[1])}" r="3.5" fill="${ser.c}"/>`;
    s+=axisText(X(last[0])+8,Y(last[1])+4,Math.round(last[1]),"start",11.5,ser.c);
    leg.push(`<span><i class="sw" style="background:${ser.c}"></i>${ser.k}</span>`);});
  document.getElementById("chart-macro").innerHTML=svg(W,H,s);
  document.getElementById("leg-macro").innerHTML=leg.join("");
  document.getElementById("macro-cap").textContent= MMODE==="idx"
    ? "2015 = 100. The pay line steps once, in 2026; every other line compounds annually. Shaded years use IMF projections."
    : "Entry pay in constant 2015 taka. The flat line is the pay that would hold 2015 purchasing power exactly.";
  const gN=gdpN[2025]/gdpN[2015], gP=gdpP[2025]/gdpP[2015];
  const payM=entryPay(MG,2026)/entryPay(MG,2015);
  /* Nominal measures are compared against nominal pay; the PPP series is real,
     so it is compared against pay after inflation, not before. */
  const payReal=payM/INF;
  document.getElementById("macro-body").innerHTML=[
    ["Pay — grade "+MG+" entry, nominal",payM,null],
    ["Consumer prices",INF,INF/payM],
    ["GDP per head, nominal taka (to 2025)",gN,gN/payM],
    ["Pay after inflation",payReal,null],
    ["Real income per head, PPP (to 2025)",gP,gP/payReal]
  ].map(([k,m,r])=>`<tr><td>${k}</td><td class="num">${m.toFixed(3)}×</td>
    <td class="num ${r==null?"":r>1?"dn":"up"}">${r==null?"—":(r>1?"pay trails by ":"pay leads by ")+
    (Math.abs(1-1/r)*100).toFixed(1)+"%"}</td></tr>`).join("");
  document.getElementById("ppp-growth").textContent=((gP-1)*100).toFixed(0)+"%";
  const pFull=2/(px(2027)/px(2015))-1;
  document.getElementById("phase-head").textContent=
    "The rise is phased; prices are not";
  document.getElementById("phase-detail").innerHTML=
    `Officers receive 40% of their rise (grades 1–9) or 50% (grades 10–20) from July 2026, `+
    `70% or 75% from January 2027, and the whole amount only from 1 July 2027. The split `+
    `favours lower grades, which is deliberate. But by the date the scale is finally paid in `+
    `full, prices have risen a further ${((px(2027)/px(2026)-1)*100).toFixed(1)}%, so a `+
    `doubled scale is worth <b>${pc(pFull*100)}</b> against 2015 rather than the `+
    `${pc((2/INF-1)*100)} it was worth on the day it was announced.`;
}
const range=(a,b)=>Array.from({length:b-a+1},(_,i)=>a+i);

/* =================== history =================== */
(function(){
  const rows=[];
  for(let i=1;i<ERAS.length;i++){
    const from=ERAS[i-1], to=ERAS[i];
    if(INCOMPARABLE.has(from)||INCOMPARABLE.has(to)) continue;
    let collapsed=0,demoted=0,tot=0,worst=0,sp=[],r1=[],rt=[];
    for(let g=1;g<=20;g++){
      const r=gradeRows(from,to,g); if(!r||r.length<2) continue;
      collapsed+=r.length-new Set(r.map(x=>x.newBasic)).size;
      demoted+=r.filter(x=>x.move<0).length; tot+=r.length;
      worst=Math.min(worst,...r.map(x=>x.move));
      sp.push(r[0].raise-r[r.length-1].raise);
      r1.push(r[0].raise); rt.push(r[r.length-1].raise);}
    if(!tot) continue;
    const infl=inflMult(from,to);
    const med=arr=>{const s=[...arr].sort((a,b)=>a-b);return s[Math.floor(s.length/2)];};
    const a1=lad(from,1), a20=lad(from,20), b1=lad(to,1), b20=lad(to,20);
    rows.push({from,to,collapsed,demoted,tot,worst,spread:med(sp),
      real1:(1+med(r1)/100)/infl-1, realT:(1+med(rt)/100)/infl-1,
      hier:b1&&b20?b1[0]/b20[0]:null});
  }
  document.getElementById("hist-body").innerHTML=rows.map(r=>`
    <tr><td>${yr(r.from)} → ${yr(r.to)}</td>
      <td class="num">${r.collapsed}</td>
      <td class="num">${r.demoted} of ${r.tot}</td>
      <td class="num dn">${r.worst}</td>
      <td class="num">${r.spread.toFixed(1)} pts</td>
      <td class="num ${r.real1<0?"dn":"up"}">${pc(r.real1*100)}</td>
      <td class="num ${r.realT<0?"dn":"up"}">${pc(r.realT*100)}</td>
      <td class="num">${r.hier?r.hier.toFixed(2)+"×":"—"}</td></tr>`).join("");

  /* hierarchy ratio chart */
  const pts=ERAS.filter(e=>lad(e,1)&&lad(e,20)).map(e=>[yr(e),lad(e,1)[0]/lad(e,20)[0]]);
  const W=980,H=280,L=56,R=24,Tp=22,B=42, iw=W-L-R, ih=H-Tp-B;
  const lo=6, hi=13.6;
  const X=y=>L+(y-1977)/(2026-1977)*iw, Y=v=>Tp+ih-(v-lo)/(hi-lo)*ih;
  let s=`<rect x="0" y="0" width="${W}" height="${H}" fill="${cv("--panel")}"/>`;
  for(let v=6;v<=13;v+=1){
    s+=`<line x1="${L}" y1="${Y(v)}" x2="${W-R}" y2="${Y(v)}" stroke="${cv("--rule-2")}"/>`;
    s+=axisText(L-9,Y(v)+4,v+"×","end");}
  s+=path(pts.map((p,i)=>(i?"L":"M")+X(p[0])+" "+Y(p[1])).join(" "),cv("--l1"),2.4);
  /* the first and last points sit on the plot edges, so centring their labels
     pushes them over the y-axis ticks and off the right edge */
  pts.forEach((p,i)=>{
    const edge=i===0?"start":i===pts.length-1?"end":"middle";
    s+=`<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="4" fill="${cv("--l1")}"/>`;
    s+=axisText(X(p[0]),Y(p[1])-12,p[1].toFixed(2)+"×",edge,11,cv("--ink-2"));
    s+=axisText(X(p[0]),H-B+20,p[0],edge,11);});
  document.getElementById("chart-hier").innerHTML=svg(W,H,s);
  const first=pts[0], last=pts[pts.length-1], prev=pts[pts.length-2];
  document.getElementById("hier-head").textContent=
    "The clearest thing the 2026 order does right";
  document.getElementById("hier-detail").innerHTML=
    `A grade 1 officer now starts on <b>${last[1].toFixed(2)}×</b> a grade 20 employee,
     down from ${prev[1].toFixed(2)}× in 2015 and ${first[1].toFixed(2)}× in 1977 — the
     flattest the service has been in the recorded history of its pay scales, and by far
     the largest single narrowing. Add the shortened higher-grade timeline (8 years for
     the first, 14 for the second, against 10 and 16) and the new third higher grade for
     posts with no promotion path, and the order is plainly aimed at people who spend a
     career in one grade. Its failure is not its direction; it is the size of the envelope
     and the way seniority is treated inside it.`;
})();

/* =================== services =================== */
(function(){
  const CD=DATA.cadre;
  const years=[...new Set(Object.values(CD).flatMap(v=>Object.keys(v)))]
    .sort((a,b)=>+a-+b);
  const se=document.getElementById("sv-era"), sg=document.getElementById("sv-grade");
  years.forEach(y=>{const o=document.createElement("option");o.value=y;
    o.textContent=y+" scale";se.append(o);});
  se.value=years.includes("2009")?"2009":years[years.length-1];
  for(let g=1;g<=20;g++){const o=document.createElement("option");o.value=g;
    o.textContent="Grade "+g;sg.append(o);}
  sg.value=10;
  function draw(){
    const y=se.value, g=sg.value;
    const base=(CD.govt_civil&&CD.govt_civil[y]&&CD.govt_civil[y][g])||null;
    const rows=Object.keys(CAD).filter(c=>CD[c]&&CD[c][y]&&CD[c][y][g])
      .map(c=>({c,...CD[c][y][g]}));
    document.getElementById("sv-cap").textContent=
      `Grade ${g} on the ${y} scale, as printed in each service chapter`;
    document.getElementById("sv-body").innerHTML= rows.length
      ? rows.map(r=>`<tr${r.c==="govt_civil"?' class="hl"':""}><td>${CAD[r.c]}</td>
          <td class="num">৳${fmt(r.s)}</td><td class="num">৳${fmt(r.m)}</td>
          <td class="num">${base?(r.s/base.s).toFixed(2)+"×":"—"}</td></tr>`).join("")
      : `<tr><td colspan="4">No service chapter in the ${y} gazette carries a readable
         grade ${g}. The 2026 order has only one chapter: the civil service.</td></tr>`;
  }
  se.onchange=sg.onchange=draw; draw();
  document.getElementById("excluded").innerHTML=
    "The order's own scope clause puts these outside it: "+
    DATA.allowances.scope_2026.excluded.map(esc).join(", ")+
    ". Each is to be covered by a separate instrument. Until those appear, there is no "+
    "way to compare a 2026 police inspector with a 2026 civil officer of the same grade, "+
    "because they are no longer on the same instrument — the convergence the 2015 order "+
    "achieved has been undone structurally rather than by any change in the numbers.";
})();

/* =================== allowances =================== */
(function(){
  /* Every figure here is read from articles 12-30 of the gazette. An allowance is
     a percentage of basic, a flat taka amount, or something paid per occurrence,
     and the item's own `basis` says which -- reading every number as a percentage
     once turned the \u09f3200 tiffin allowance into "200% of basic". */
  const PCT = new Set(["rate_of_basic","uplift_pct"]);
  const describe = v => {
    if(!v) return "<em>not in this order</em>";
    const flat = v.basis === "flat";
    const bits = [];
    if(v.rate != null) bits.push(flat ? "\u09f3"+fmt(v.rate) : v.rate+"% of basic");
    if(v.bands) bits.push(v.bands.map(b =>
      `grades ${b.grades}: ${b.dhaka}% Dhaka / ${b.other_city}% other city / ${b.elsewhere}% elsewhere`).join("; "));
    for(const [k,val] of Object.entries(v)){
      if(["basis","rate","bands","note","effective","interim"].includes(k)) continue;
      if(val == null) continue;
      const label = k.replace(/_/g," ").replace(/^grade (\d+) (\d+)$/,"grades $1\u2013$2");
      if(PCT.has(k)){ bits.push(label.replace(/ pct$/,"")+": "+val+"%"); continue; }
      const money = typeof val === "number" && val >= 50 && (flat || /cap/.test(label));
      bits.push(label+": "+(money ? "\u09f3"+fmt(val) : val));
    }
    if(v.note) bits.push('<span style="color:var(--ink-3)">'+esc(v.note)+"</span>");
    if(v.interim) bits.push('<span style="color:var(--warn)">until then: '+esc(v.interim)+"</span>");
    if(v.effective) bits.push('<b style="color:var(--warn)">from '+esc(v.effective)+"</b>");
    return bits.join("<br>") || "\u2014";
  };
  const C = DATA.allowances.commencement;
  document.getElementById("al-body").innerHTML = DATA.allowances.items.map(it => `
    <tr><td><b>${esc(it.en)}</b><br><span class="bn" style="color:var(--ink-3)">${esc(it.bn)}</span>
          ${it.article ? `<br><span class="num" style="font-size:11px;color:var(--ink-3)">article ${esc(it.article)}</span>` : ""}</td>
      <td style="text-align:left;font-size:13px">${describe(it.y2015)}</td>
      <td style="text-align:left;font-size:13px">${describe(it.y2026)}</td>
      <td style="text-align:left;font-size:13px;color:${
        /CUT|real cut|no longer rises|does not rise|cap becomes the rate|deepest|frozen/.test(it.direction) ? cv("--loss")
        : /NEW|raised|doubled|caps raised|progressive/.test(it.direction) ? cv("--gain")
        : cv("--ink-2")}">${esc(it.direction)}</td></tr>`).join("");
  if(C) document.getElementById("al-note").innerHTML =
    "<b>Article "+esc(C.article)+".</b> "+esc(C.rule)+" "+esc(C.interim)+
    " <b>"+esc(C.implication)+"</b>";
  document.getElementById("sx-body").innerHTML=DATA.allowances.structural_changes
    .map(c=>`<tr><td class="num">${c.year}</td>
      <td style="text-align:left">${esc(c.change)}</td></tr>`).join("");
})();

/* =================== register =================== */
(function(){
  const list=document.getElementById("discrep-list");
  function draw(scope){
    const items=DATA.register.filter(r=>scope==="all"||r.scope===scope);
    list.innerHTML=items.map(r=>`<div class="item">
      <div class="hd"><h3>${esc(r.title)}</h3>
        <span class="sev ${r.severity}">${r.severity==="good"?"works":r.severity}</span></div>
      <p>${esc(r.body)}</p>
      <div class="chk"><b>Check it:</b> ${esc(r.check)}</div></div>`).join("");
  }
  document.getElementById("rg-scope").querySelectorAll("button").forEach(b=>{
    b.onclick=()=>{document.getElementById("rg-scope").querySelectorAll("button")
      .forEach(x=>x.setAttribute("aria-pressed",x===b));draw(b.dataset.scope);};});
  draw("all");
})();

/* =================== footer =================== */
document.getElementById("limits").innerHTML=
  "<b>Known limits.</b> Basic pay only — allowances are tabulated but not added into "+
  "any figure on this page, and they can exceed half of basic. Scales before 2015 are "+
  "expanded from printed increment bands and agree with the same scale as reprinted in "+
  "other service chapters, but they are not step-verified against an original table the "+
  "way 2015 and 2026 are. The 1973 order set only ten national scales and its top four "+
  "were marked not implemented in the gazette itself, so it is shown but not used as a "+
  "baseline. Years from 2026 onward use IMF projected inflation and are shaded as such.";
document.getElementById("src").innerHTML=
  "Primary source: <span class='bn'>"+esc(DATA.meta.gazette_2026)+"</span>. "+
  "Prepared "+esc(DATA.meta.generated)+".";

renderCalc(); drawRegress(); drawCompress(); drawMacro();
window.addEventListener("resize",()=>{drawRegress();drawCompress();drawMacro();});
}
})();
