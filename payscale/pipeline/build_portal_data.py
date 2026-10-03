#!/usr/bin/env python3
"""Assemble the single JSON payload the portal runs on.

Everything the page computes — fixation, raises, compression, real terms — is
derived in the browser from these primitives, so the numbers on screen and the
numbers in the CSVs come from one source. Only the editorial register at the
bottom is written rather than derived, and every entry in it names the figure
the page can check it against.

Output: scratch/portal_data.json
"""
import csv, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTD = ROOT / "06_structured"
REF = ROOT / "09_reference"
SCRATCH = ROOT / "scratch"; SCRATCH.mkdir(exist_ok=True)

EFF = {"nps_1973": 1973, "nps_1977": 1977, "nps_1985": 1985, "nps_1991": 1991,
       "nps_1997": 1997, "nps_2005": 2005, "nps_2009": 2009, "nps_2015": 2015,
       "nps_2026": 2026}

# Each entry is an editorial reading of a number the page itself derives. `check`
# names what on the page the reader can test it against, so nothing here is a
# claim the data cannot carry.
REGISTER = [
    {"id": "demotion", "scope": "internal", "severity": "high",
     "title": "Almost everyone is moved down the ladder, and that is normally a punishment",
     "body": "Article 5 fixes pay by adding the officer's distance above the old "
             "starting step to the new starting step, then rounding up to the next "
             "printed step. Because the 2026 ladder rises in smaller proportional "
             "jumps than the 2015 one, the resulting amount almost always sits "
             "lower in the new ladder than the officer sat in the old. Across "
             "grades 12-20, 17 of 19 step positions land lower than they started, "
             "by as much as eight stages. Under rule 4(3) of the Government "
             "Servants (Discipline and Appeal) Rules 2018, reduction to a lower "
             "stage in a pay scale is a major penalty — it requires a charge, a "
             "hearing and a right of appeal. Here it reaches nearly the whole "
             "service by arithmetic, with no process at all.",
     "check": "Open the calculator at any grade and a step above 8; compare the "
              "step number held in 2015 with the step number landed on in 2026."},

    {"id": "compression", "scope": "internal", "severity": "high",
     "title": "Seniority is erased: distinct steps collapse onto one another",
     "body": "Officers who were on different steps in 2015 — different years of "
             "service, different pay — are fixed onto the same 2026 step. In every "
             "grade from 8 to 20, 19 occupied steps compress into 11 or 12 distinct "
             "amounts. Up to eight separate seniority positions disappear. In "
             "accounting terms this is a write-off of accrued service: increments "
             "already earned, already paid for by years worked, stop being "
             "distinguishable in pay.",
     "check": "The compression diagram maps each 2015 step to the 2026 step it "
              "lands on; converging lines are collapsed seniority."},

    {"id": "regressive-by-seniority", "scope": "internal", "severity": "high",
     "title": "The raise is advertised as doubling, but only a first-day entrant doubles",
     "body": "At step 1 the new scale is exactly 2.00× the old for grades 1-11, and "
             "more than that — up to 2.42× at grade 20 — for grades 12-20. At the "
             "top step the same grades get between 1.42× and 1.87×. The gap between "
             "the best-treated and worst-treated officer inside a single grade "
             "reaches 79.5 percentage points. The raise is not regressive across "
             "grades; it is regressive across seniority, which is harder to see and "
             "was not announced.",
     "check": "The regressivity chart plots the raise at every step of the chosen "
              "grade; it slopes down with seniority in all 19 grades."},

    {"id": "grade-3-ceiling", "scope": "internal", "severity": "low",
     "title": "One grade's ceiling breaks the doubling rule",
     "body": "Every grade's maximum is 2.00× its 2015 maximum, give or take rounding "
             "— except grade 3, whose ceiling goes from ৳71,530 to ৳148,800, a factor "
             "of 2.08. Grades 2 to 5 also gain extra steps (grade 2 goes from 5 steps "
             "to 7, grade 3 from 7 to 9), while grades 8 to 20 keep 19. The order "
             "states no principle that would produce either result.",
     "check": "The scale table lists start, ceiling and step count for both scales."},

    {"id": "allowance-freeze", "scope": "internal", "severity": "medium",
     "title": "The education allowance is frozen in taka, which is a cut",
     "body": "Education support stays at ৳500 per child, two children, ৳1,000 "
             "maximum — the same figures as 2015. Prices have risen 115% since. The "
             "only change is the age limit, 21 to 23. The Bangla New Year allowance "
             "moves the other way in rate, 20% of basic to 15%, though because basic "
             "doubles the taka paid still rises by half.",
     "check": "The allowance table shows the 2015 and 2026 figures side by side with "
              "the real change after inflation."},

    {"id": "house-rent-lag", "scope": "internal", "severity": "medium",
     "title": "The most progressive change in the order is deferred by 18 months",
     "body": "House rent is restructured so the lowest grades draw the highest "
             "percentage — 60% of basic in Dhaka for grades 16-20 against 40% for "
             "grades 1-4. That is the clearest redistributive move in the whole "
             "order, and it does not start until 1 January 2028, a year and a half "
             "after the pay scale itself.",
     "check": "Allowance table, house rent row, effective date column."},

    {"id": "phasing", "scope": "internal", "severity": "medium",
     "title": "The full scale is not paid until the middle of 2027",
     "body": "From July 2026 officers receive 40% of their rise (grades 1-9) or 50% "
             "(grades 10-20); from January 2027, 70% or 75%; the whole amount only "
             "from 1 July 2027. The split favours lower grades, which is deliberate "
             "and defensible. But prices do not phase in: by the time the scale is "
             "paid in full, roughly a further year of inflation has gone through it.",
     "check": "Set the calculator's date control to each of the three phases."},

    {"id": "cadre-split", "scope": "cross-scale", "severity": "high",
     "title": "2015 unified basic pay across services. 2026 splits it again",
     "body": "Until 2009 the same grade number paid different money depending on "
             "service. The 2015 order ended that: one ladder for every cadre. The "
             "2026 order applies only to the civil service — judicial service, "
             "defence, police and BGB, state industrial workers, apprentices, "
             "outsourced and contract staff are all outside it, to be covered by "
             "separate instruments later. Whatever those instruments say, the single "
             "national ladder that existed from 2015 no longer exists.",
     "check": "The inter-service chart shows the spread closing to 1.00× in 2015; "
              "2026 has no comparable figure because there is only one service in it."},

    {"id": "not-fixed", "scope": "cross-scale", "severity": "high",
     "title": "The compression problem is older than this order, and this order does not fix it",
     "body": "Every transition since 1977 has collapsed steps and pushed officers "
             "down the ladder, because every one of them has used the same "
             "difference-and-round-up method against a flatter new ladder. 2009→2015 "
             "collapsed 145 step positions across the grades and demoted 263; "
             "2015→2026 collapses 119 and demotes 264. On the one measure that did "
             "change, it got worse: the spread between the best- and worst-treated "
             "officer within a grade widened from 38.7 points in 2015 to 57.5 points "
             "in 2026.",
     "check": "The transition history table lists collapsed, demoted and spread for "
              "every pay commission since 1973."},

    {"id": "hierarchy-flatter", "scope": "cross-scale", "severity": "good",
     "title": "What the order does fix: the gap between the top and bottom of the service",
     "body": "In 2015 a grade 1 officer started on 9.45 times a grade 20 employee. "
             "In 2026 the ratio is 7.80 — the flattest the Bangladesh civil service "
             "hierarchy has been in its recorded history. The ratio has narrowed at "
             "almost every commission since 1977, when it stood at 12.50, but 2026 "
             "makes by far the largest single move. The shortened higher-grade "
             "timeline (8 years instead of 10 for the first, 14 instead of 16 for "
             "the second) and the new third higher grade for posts with no promotion "
             "path are real gains for people who spend a career in one grade.",
     "check": "Vertical ratio appears in the transition history table for every era."},

    {"id": "macro-income", "scope": "macro", "severity": "high",
     "title": "The economy grew; civil service pay did not keep its share",
     "body": "Nominal GDP per head rose 3.30× between 2015 and 2025 while the pay "
             "scale rose 2.00×. Measured in constant international dollars, real "
             "income per head rose 62% over the same period. A doubling that trails "
             "both the price index and national income by that margin is not a pay "
             "rise in any economic sense; it is a partial catch-up on eleven years "
             "of erosion, and an incomplete one.",
     "check": "The macro benchmark chart indexes pay, prices, nominal GDP per head "
              "and real GDP per head to 2015 = 100."},

    {"id": "macro-ppp", "scope": "macro", "severity": "medium",
     "title": "Purchasing power parity does not rescue the number either",
     "body": "The honest domestic test is the consumer price index, because civil "
             "servants buy in taka at home. Prices rose 2.153× from 2015 to 2026, so "
             "a 2.000× scale is 7.1% short at the one point where it doubles. "
             "Purchasing power parity is the right tool for comparing Bangladeshi "
             "pay with another country's, not for asking whether this year's rise "
             "covers this year's cost of living — and on the PPP series real income "
             "per head grew faster than pay anyway.",
     "check": "Toggle the macro chart between nominal taka and constant taka."},

    {"id": "erosion-clock", "scope": "macro", "severity": "high",
     "title": "The new scale opens below the old one, before a day of it is worked",
     "body": "Prices rose 2.153× between 2015 and 2026 and the scale rose 2.000×, so "
             "for grades 1 to 11 a step-1 officer in 2026 is already 7.1% worse off "
             "in real terms than a step-1 officer was in 2015. Because the rise is "
             "paid in phases, the full scale only arrives on 1 July 2027, by which "
             "point the shortfall is 12.4%. Grades 12 to 20 do open ahead — 12.6% at "
             "grade 20 — but on the IMF's own projected inflation path that advantage "
             "is gone about fourteen months after the scale is paid in full. The gap "
             "between commissions is the real policy lever and nobody votes on it: "
             "the 2015 scale ran eleven years, the longest on record.",
     "check": "The erosion chart carries the index forward on the IMF's published "
              "path; the crossing points are marked."},
]


def main():
    lad = json.loads((OUTD / "ladders.json").read_text())
    px, pq = {}, {}
    for r in csv.DictReader(open(REF / "bd_price_index.csv")):
        y = int(r["year"])
        px[y] = round(float(r["index_2010_100"]), 4)
        pq[y] = r["index_quality"]

    def wb(fn):
        try:
            d = json.load(open(REF / fn))[1]
            return {int(x["date"]): x["value"] for x in d if x["value"] is not None}
        except Exception:
            return {}

    gdp_n = wb("wb_NY.GDP.PCAP.CN.json")
    gdp_ppp = wb("wb_NY.GDP.PCAP.PP.KD.json")

    # cadre start/max from the validated crosswalk (context for inter-service view)
    cadre = {}
    try:
        for r in csv.DictReader(open(OUTD / "crosswalk.csv")):
            if r.get("ladder_ok") != "True":
                continue
            cadre.setdefault(r["cadre"], {}).setdefault(r["era_year"], {})[r["grade"]] = {
                "s": int(r["start_basic"]), "m": int(r["max_basic"])}
    except FileNotFoundError:
        pass

    # per-transition anomaly figures, already computed by analyse.py
    anom = []
    try:
        for r in csv.DictReader(open(OUTD / "anomaly_summary.csv")):
            anom.append({k: (float(v) if k not in ("from_era", "to_era") and v
                             else v) for k, v in r.items()})
    except FileNotFoundError:
        pass

    allow = json.loads((REF / "allowances_2015_2026.json").read_text())

    payload = {
        "eff": EFF,
        "ladders": {e: {g: v["steps"] for g, v in gs.items()} for e, gs in lad.items()},
        "ladder_src": {e: {g: v["source"] for g, v in gs.items()} for e, gs in lad.items()},
        "px": px, "pq": pq,
        "gdp_nominal_pc": gdp_n, "gdp_ppp_pc": gdp_ppp,
        "cadre": cadre,
        "anomalies": anom,
        "allowances": allow,
        "register": REGISTER,
        "special_posts": {
            "2015": {"cabinet_secretary": 86000, "senior_secretary": 82000},
            "2026": {"cabinet_secretary": 172000, "senior_secretary": 164000},
        },
        "phasing": {
            "p1": {"from": "2026-07-01", "to": "2026-12-31", "g1_9": 0.40, "g10_20": 0.50},
            "p2": {"from": "2027-01-01", "to": "2027-06-30", "g1_9": 0.70, "g10_20": 0.75},
            "full": {"from": "2027-07-01", "g1_9": 1.0, "g10_20": 1.0},
        },
        "meta": {
            "gazette_2026": "চাকরি (বেতন ও ভাতাদি) আদেশ, ২০২৬ — Bangladesh Gazette, "
                            "Extraordinary, 17 September 2026, pp. 25193-25211",
            "generated": "2026-10-03",
        },
    }
    p = SCRATCH / "portal_data.json"
    p.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"portal_data.json  {p.stat().st_size/1024:.0f} KB   "
          f"{len(anom)} anomaly rows, {len(REGISTER)} register entries")
    for e in sorted(payload["ladders"], key=lambda k: EFF.get(k, 0)):
        gs = payload["ladders"][e]
        ns = [len(v) for v in gs.values()]
        print(f"  {e:10} {len(gs):>2} grades, steps {min(ns)}–{max(ns)}")


if __name__ == "__main__":
    main()
