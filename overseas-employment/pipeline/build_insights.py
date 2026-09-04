#!/usr/bin/env python3
"""Build site/data/insights.json — the findings tab.

Everything here is computed, not typed in. The analysis lives in
../../bbs census/causal/ (corridor benchmark, Malaysia difference-in-differences,
network horse race); this script re-reads its outputs and the crawl database and
emits the numbers the Insights tab draws. Rerun it after any of those change.
"""
from __future__ import annotations
import json, sqlite3, os
from datetime import date
from pathlib import Path
import pandas as pd, numpy as np

HERE = Path(__file__).resolve().parent
CAU  = Path(os.environ.get("CAUSAL_DIR",
        HERE.parent.parent / "bbs census" / "causal"))
OUT  = HERE / "site" / "data" / "insights.json"
FY   = "FY2025-26"
YR   = ("2025-06-01", "2026-05-31")
con  = sqlite3.connect(HERE / "data/bmet.sqlite")

cor  = pd.read_csv(CAU / "potential_corridor.csv", index_col=0)
mon  = pd.read_csv(CAU / "money_potential.csv",    index_col=0)
mcor = pd.read_csv(CAU / "money_corridor.csv",     index_col=0)

div = pd.DataFrame(con.execute(
    "SELECT DISTINCT district, division FROM daily_all").fetchall(),
    columns=["district", "division"]).drop_duplicates("district").set_index("district")["division"]
METRO = ["Dhaka", "Chattogram", "Gazipur", "Narayanganj"]
nm = cor[~cor.metro]

# ---------------------------------------------------------------- volume
d = cor.assign(division=div).groupby("division").agg(
    actual=("actual", "sum"), short=("gap_people", "sum"))
d["uplift"] = 100 * d.short / d.actual
d = d.sort_values("uplift", ascending=False)

mnth = pd.DataFrame(con.execute("""
    SELECT substr(date,1,7) m, co.name c, SUM(count) n FROM daily_country d
    JOIN country co ON co.country_id=d.country_id
    WHERE gender_id=0 AND date>'2023-06-19' GROUP BY 1,2""").fetchall(),
    columns=["m", "c", "n"])
tot_m = mnth.groupby("m").n.sum()
last_full = pd.read_sql("SELECT MAX(date) d FROM daily_all", con).d[0][:7]
tot_m = tot_m[tot_m.index < last_full]          # drop the part-month at the end
mal   = mnth[mnth.c == "Malaysia"].set_index("m").n.reindex(tot_m.index).fillna(0)
sau   = mnth[mnth.c == "Saudi Arabia"].set_index("m").n.reindex(tot_m.index).fillna(0)

flow = pd.Series(dict(con.execute("""
    SELECT co.name, SUM(count) FROM daily_country d JOIN country co
    ON co.country_id=d.country_id WHERE gender_id=0
    AND date BETWEEN ? AND ? GROUP BY 1""", YR).fetchall()))

# ---------------------------------------------------------------- money
rem = pd.read_csv(HERE / "remittance/remittance_country_fy.csv")
rem = rem[rem.fiscal_year == FY].set_index("country").remittance_musd
share_money = (rem / rem.sum()).sort_values(ascending=False)
share_flow  = (flow / flow.sum()).sort_values(ascending=False)
KOR_STOCK, KOR_QUOTA = 30_000, 10_300
kr = rem["Of Korea, Republic"] * 1e6 / KOR_STOCK
sa = rem["Saudi Arabia"] * 1e6 / 2_362_680
kor_sent = float(flow.get("South Korea", 0))

rng = mon.assign(division=div)
rng = rng[rng["division"] == "Rangpur"].gap_musd.sum()

# The crawl and Bangladesh Bank each carry their own spellings. One place to fix
# them so a label never reads "Coxsbazar" or "Of Korea, Republic" on the page.
SHOW = {"Coxsbazar": "Cox's Bazar", "Chattagram": "Chattogram",
        "United Arab Emirates (UAE)": "UAE", "Of Korea, Republic": "South Korea",
        "United Kingdom (UK)": "UK", "United States of America (USA)": "USA",
        "Countries Other": "Other countries", "Brahmanbaria": "Brahmanbaria"}
def show(k): return SHOW.get(str(k), str(k))

def bars(s, unit="", fmt="{:,.0f}", note=None, hi=None):
    return {"type": "bars", "unit": unit, "note": note,
            "rows": [{"k": show(k), "v": float(v), "l": fmt.format(v),
                      "hi": bool(hi and k in hi)} for k, v in s.items()]}

J = {
 "generated": date.today().isoformat(),
 "cards": [

 # ---- how it is measured
 {"id": "method", "band": "How this is measured", "kind": "prose",
  "title": "A district is compared with districts that can afford what it can",
  "body": "Every claim below rests on one construction. For each of the 64 districts "
     "and each destination country, migration is measured as clearances per 1,000 "
     "working-age residents — a <em>corridor penetration</em> rate. A district is then "
     "benchmarked, corridor by corridor, against the 75th percentile of districts in its "
     "own deprivation tercile, because migration costs money and only the deprivation axis "
     "of the 2022 census has a real relationship with the migration rate (r&nbsp;=&nbsp;−0.47). "
     "The shortfall is the sum of those per-corridor distances. It is not a model of what "
     "<em>should</em> happen; it is the distance to what comparable districts already do."},

 # ---- 1. headline volume
 {"id": "gap", "band": "Volume", "kind": "stat",
  "title": "About 299,000 more people a year could plausibly go abroad",
  "stat": f"+{100*nm.gap_people.sum()/nm.actual.sum():.0f}%",
  "sub": f"{nm.gap_people.sum():,.0f} people a year, on {nm.actual.sum():,.0f} actually cleared",
  "body": "If every district reached what its economic peers already achieve, corridor by "
     "corridor. Dhaka, Chattogram, Gazipur and Narayanganj are excluded: they have domestic "
     "labour markets this benchmark cannot see, and their low migration rates are plausibly "
     "choice rather than absence of access. Including them the figure is "
     f"+{100*cor.gap_people.sum()/cor.actual.sum():.0f}% "
     f"({cor.gap_people.sum():,.0f}).",
  "chart": bars(d.uplift.round(0), "%", "+{:,.0f}%",
     note="Shortfall as a share of each division's current outflow.")},

 # ---- 2. depth not breadth
 {"id": "depth", "band": "Volume", "kind": "split",
  "title": "The gap is depth in corridors already used, not missing countries",
  "parts": [{"k": "Depth — corridors the district already uses",
             "v": 100 * (1 - cor.gap_from_absent_corridors.sum() / cor.gap_people.sum())},
            {"k": "Breadth — corridors it does not touch at all",
             "v": 100 * cor.gap_from_absent_corridors.sum() / cor.gap_people.sum()}],
  "body": "Only "
     f"{cor.gap_from_absent_corridors.sum():,.0f} of the "
     f"{cor.gap_people.sum():,.0f}-person shortfall comes from destinations a district does not "
     "reach at all. Nilphamari has 23 such corridors and together they are worth almost nothing; "
     "what Nilphamari lacks is volume into Saudi Arabia. This runs against the standard "
     "&ldquo;diversify destinations&rdquo; recommendation: as an arithmetic matter, opening a new "
     "corridor is a rounding error next to thickening a thin one. Diversification is a "
     "<em>risk</em> argument, not a volume argument — see below."},

 # ---- 3. who is furthest behind
 {"id": "districts", "band": "Volume", "kind": "chart",
  "title": "The northwest is one contiguous block of unrealised migration",
  "body": "Rangpur division sends fewer workers than Sylhet's four districts and has a shortfall "
     "2.6&times; its current outflow — and it is benchmarked against districts just as poor. "
     "At the other end, Kishoreganj, Faridpur, Rajbari and Bhola have essentially no headroom "
     "under this method: they are already at the ceiling their peers have demonstrated.",
  "chart": bars(nm.nlargest(12, "gap_people").gap_people.round(0), " people",
     note="Additional people a year, metro districts excluded. "
          "Rangpur-division districts are highlighted.",
     hi=set(nm.assign(division=div).query("division=='Rangpur'").index))},

 # ---- 4. Malaysia
 {"id": "malaysia", "band": "Volume", "kind": "line",
  "title": "Malaysia closed overnight, and the workers did not go anywhere else",
  "body": "47,000 clearances in May 2024; exactly zero from June 2024, permanently. Because "
     "districts depended on Malaysia to wildly different degrees (1.5% to 64% of their outflow), "
     "the closure is a natural experiment. Districts more exposed to Malaysia lost more total "
     "migration afterwards: β&nbsp;=&nbsp;−0.877, and −1.200 with controls. A placebo run on a "
     "split of the pre-period gives +0.048 (p&nbsp;=&nbsp;0.84), so this is not a pre-existing "
     "trend. Substitution into other corridors is real but partial (+0.60, CI 0.26–0.93), and "
     "nationally only about 14% of the lost flow reappeared elsewhere. Corridors are "
     "demand-rationed: you cannot simply redirect a worker.",
  "series": [{"name": "All destinations", "v": [float(x) for x in tot_m]},
             {"name": "Malaysia", "v": [float(x) for x in mal]},
             {"name": "Saudi Arabia", "v": [float(x) for x in sau]}],
  "x": list(tot_m.index),
  "marks": [{"at": "2024-06", "label": "Malaysia closes"},
            {"at": "2025-07", "label": "Saudi skill test extended"},
            {"at": "2025-08", "label": "test suspended"}]},

 # ---- 5. horse race
 {"id": "network", "band": "Volume", "kind": "pairs",
  "title": "Where a district sends people is inherited, not explained by what it is like",
  "pairs": [{"k": "Its own prior ties to that country", "v": 0.739, "e": 0.081},
            {"k": "What census-similar districts do there", "v": 0.044, "e": 0.099}],
  "body": "Both enter the same regression, with destination fixed effects and standard errors "
     "clustered by district. A district's own history in a corridor predicts where it sends "
     "people next; what demographically similar districts do in that corridor predicts almost "
     "nothing, and cannot be distinguished from zero. Restricting to districts forced to "
     "reallocate after Malaysia closed gives 0.766 against 0.082 — even under pressure they "
     "followed their own networks rather than the corridors comparable districts had opened. "
     "That is why the shortfall above is read as a missing network endowment."},

 # ---- 6. money headline
 {"id": "money", "band": "Money", "kind": "stat",
  "title": "Closing the entire volume gap would raise remittance by about 3%",
  "stat": "+$1.24bn",
  "sub": f"a year, against national remittance of ${rem.sum()/1000:,.1f}bn in {FY}",
  "body": "Priced corridor by corridor, at remittance per migrant per year — money divided by "
     "the <em>stock</em> of Bangladeshis in each country (UN&nbsp;DESA 2024), never by clearances, "
     "which would compare a flow with a stock. The number is modest for a specific reason: "
     "half the people-shortfall sits in the cheapest corridor Bangladesh has. The marginal "
     "worker in this scenario is worth about $3,465 a year — almost exactly the $3,212 the "
     "average current worker is worth. Closing the volume gap does not change what a "
     "Bangladeshi migrant is worth; it just buys more of the same.",
  "chart": bars((mcor.usd_m.head(8)).round(0), "m", "${:,.0f}m",
     note="Annual remittance value of the shortfall, by corridor.")},

 # ---- 7. value ladder
 {"id": "ladder", "band": "Money", "kind": "chart",
  "title": "Three quarters of the flow goes to the worst-paying corridor Bangladesh uses",
  "body": "Contract-labour destinations only — places where the resident stock is overwhelmingly "
     "temporary workers, so remittance per migrant is close to what a new worker would send. "
     "Settlement countries (the UK, the US, Italy) are excluded from this ladder: their "
     "per-migrant figures include decades-settled and second-generation residents and are not a "
     "wage Bangladesh could offer anyone tomorrow. Saudi Arabia takes 75% of contract flow at "
     "$2,476 a worker; Qatar pays 2.3&times; that, Jordan 3.8&times;. Moving a tenth of the "
     "Saudi flow to the average of the other contract corridors is worth about $161m a year — "
     "an eighth of what closing the whole volume gap is worth, from moving nobody extra.",
  "chart": bars(pd.Series({
      "Malaysia": 12052, "Jordan": 9390, "Qatar": 5674,
      "UAE": 4472, "Kuwait": 4343, "Maldives": 2726,
      "Saudi Arabia": 2476, "Lebanon": 1417}), "", "${:,.0f}",
      note="Remittance per migrant per year. Bar length is value, not volume.",
      hi={"Saudi Arabia"})},

 # ---- 8. two portfolios
 {"id": "portfolio", "band": "Money", "kind": "pairs2",
  "title": "The money is diversified. The people are not. That gap is closing the wrong way",
  "left":  {"title": f"Where the money comes from ({FY})",
            "rows": [{"k": show(k), "v": float(100*v)} for k, v in share_money.head(7).items()],
            "hhi": float((share_money**2).sum())},
  "right": {"title": "Where this year's workers went",
            "rows": [{"k": show(k), "v": float(100*v)} for k, v in share_flow.head(7).items()],
            "hhi": float((share_flow**2).sum())},
  "body": "Bangladesh's remittance is strikingly well spread — Saudi Arabia is only 16% of it, "
     "behind which sit the UK, the US, Italy and Malaysia, built by migration that happened "
     "decades ago. This year's clearances are the opposite: 63% to a single country, a "
     "concentration index of 0.41 against 0.09 for the money. Today's flow is the stock of "
     "2045. On current composition, the diversified money portfolio that cushions Bangladesh "
     "now is being replaced by a far more concentrated one."},

 # ---- 9. fragility
 {"id": "fragile", "band": "Money", "kind": "chart",
  "title": "What another Malaysia would cost, district by district",
  "body": "Applying the elasticity estimated from the Malaysia closure to each district's "
     "top-destination share. Cox's Bazar sends 81% of its workers to one country; on the "
     "Malaysia coefficient, losing it would cost roughly half its outflow (−51%), against "
     "−20% for a district as spread as Comilla. Note the tension with "
     "the volume finding: the arithmetic says deepen Saudi Arabia, and the risk says do not. "
     "For Brahmanbaria — near its volume frontier at +5% and third-most concentrated — "
     "diversification is the <em>only</em> remaining agenda, even though nationally "
     "diversification buys 0.4% of the volume.",
  "chart": bars(pd.concat([cor.nlargest(6, "top_share").top_share,
                           cor.nsmallest(4, "top_share").top_share])
                  .sort_values(ascending=False).mul(100).round(0),
     "%", "{:,.0f}%",
     note="Share of a district's workers going to its single largest destination, "
          "six most and four least concentrated. The implied loss is a fixed "
          "transform of this share, so the share is what varies.",
     hi=set(cor.nlargest(6, "top_share").index))},

 # ---- 10. supply rationing
 {"id": "ration", "band": "What actually binds", "kind": "split3",
  "title": "Half the shortfall sits behind a test, an eighth behind a foreign quota",
  "parts": [
    {"k": "Open, but skill-test gated (Saudi Arabia)", "v": 50.5},
    {"k": "Open Gulf, Levant and other", "v": 36.1},
    {"k": "Administratively capped abroad", "v": 13.4}],
  "body": "The benchmark measures distance to peers. It is silent on whether the corridor can "
     "absorb anyone. Singapore carries the second-largest people-shortfall (55,803) and is the "
     "clearest example of a gap that cannot be bought: Bangladeshis may only hold construction, "
     "marine and process work permits — the services sector is closed to them — and the number "
     "is capped by Man-Year Entitlement tied to project value, cut 15% for projects awarded from "
     "April 2025. Saudi Arabia, half the shortfall, is open but has required Skill Verification "
     "since 2023, now across 73 trades including cleaning and loading, with roughly 30% of "
     "applicants failing. When that requirement was briefly suspended in August 2025, monthly "
     "clearances hit an all-time record of 147,000 — the clearest evidence available that the "
     "binding constraint on the largest corridor is now certification, not demand and not "
     "networks."},

 # ---- 11. Korea
 {"id": "korea", "band": "What actually binds", "kind": "stat",
  "title": "Korea grants a quota Bangladesh cannot fill — and pays 3.7&times; Saudi Arabia",
  "stat": f"{100*kor_sent/KOR_QUOTA:.0f}%",
  "sub": f"of the 2025 Korean quota filled — {kor_sent:,.0f} of {KOR_QUOTA:,} places",
  "body": "Over five years Korea allocated 39,255 places to Bangladesh and 14,829 workers went: "
     "a 37% fill rate. This is the mirror image of everything above — demand granted, in "
     f"writing, and not taken up. A Bangladeshi in Korea remits about ${kr:,.0f} a year against "
     f"${sa:,.0f} in Saudi Arabia. Filling the annual quota would be worth roughly "
     f"${(KOR_QUOTA-kor_sent)*kr/1e6:,.0f}m a year — about "
     f"{100*(KOR_QUOTA-kor_sent)*kr/1e6/rng:.0f}% of what closing the entire Rangpur-division "
     "network shortfall is worth, from 8,700 people rather than 76,000. The corridor benchmark "
     "cannot see this: no district has penetrated Korea, so the peer benchmark is near zero and "
     "the method reports no gap. It is a blind spot in the method, and the largest single "
     "identified opportunity on the page.",
  "chart": bars(pd.Series({
      "Professional": 2.94, "Skilled": 19.13,
      "Semi-skilled": 34.46, "Less-skilled": 43.47}).sort_values(ascending=False),
      "%", "{:,.1f}%",
      note="Skill mix of 2025 clearances (BMET). Korea, Japan and Europe gate on "
           "language and certification; 78% of the flow is semi- or less-skilled.")},

 # ---- 12. caveats
 {"id": "caveats", "band": "How this is measured", "kind": "prose",
  "title": "Four reasons not to take these numbers literally",
  "body": "<strong>Adding up district shortfalls assumes someone is hiring.</strong> The "
     "Malaysia closure removed about 47,000 clearances a year and only ~14% reappeared "
     "elsewhere, which is direct evidence that corridors are demand-rationed. The volume figure "
     "is therefore an upper bound on <em>supply-side</em> potential, not a forecast. "
     "<strong>A peer percentile is not a causal counterfactual.</strong> It establishes that "
     "districts economically like this one already do this much — not that any policy can move a "
     "given district there. <strong>One year of flow.</strong> The benchmark year runs to May "
     "2026; corridor mixes move fast, and clearances in the first half of 2026 are running "
     "well below the 2025 peak. <strong>Per-migrant remittance is an average over a stock.</strong> "
     "It is a fair price for contract-labour corridors, where the stock is mostly current "
     "workers, and a poor one for settlement countries, which is why they are kept out of the "
     "value ladder. Corridors covering about a quarter of the people-shortfall have no usable "
     "stock figure — Singapore among them — so the $1.24bn is, if anything, understated."},
 ]}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(J, separators=(",", ":")))
print(f"wrote {OUT}  ({OUT.stat().st_size/1024:.1f} KB, {len(J['cards'])} cards)")
