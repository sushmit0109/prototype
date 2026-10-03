#!/usr/bin/env python3
"""Master comparative analysis across pay commissions.

Produces, from ladders.json + the chained price index + World Bank macro series:

  fixation_tables.csv  every (era-transition, grade, old step) -> new step,
                       raise %, step shift, whether the sum hit a step exactly
  anomaly_summary.csv  per (transition, grade): steps collapsed, officers
                       demoted, worst demotion, raise spread top-to-bottom
  real_terms_2026.csv  each grade/step's raise against compounded inflation,
                       nominal GDP per capita, and the phased-release schedule
  discrepancies.md     the written register: internal inconsistencies, breaks
                       across commissions, and what each order fixed or repeated

The economics in one line: a nominal raise is only a raise if it beats the
price level over the SAME interval. Pay orders quote the nominal number; this
converts every one of them to the real number.
"""
import csv, json, pathlib, sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from payfix import grade_table, anomalies, phase_pay

OUTD = ROOT / "06_structured"
REF = ROOT / "09_reference"
EFF = {"nps_1973": 1973, "nps_1977": 1977, "nps_1985": 1985, "nps_1991": 1991,
       "nps_1997": 1997, "nps_2005": 2005, "nps_2009": 2009, "nps_2015": 2015,
       "nps_2026": 2026}
ORDER = list(EFF)


def load():
    lad = json.loads((OUTD / "ladders.json").read_text())
    px = {int(r["year"]): float(r["index_2010_100"])
          for r in csv.DictReader(open(REF / "bd_price_index.csv"))}
    gdp = json.load(open(REF / "wb_NY.GDP.PCAP.CN.json"))[1]
    gdp = {int(x["date"]): x["value"] for x in gdp if x["value"] is not None}
    return lad, px, gdp


def transitions(lad):
    present = [e for e in ORDER if e in lad and lad[e]]
    return list(zip(present, present[1:]))


def main():
    lad, px, gdp = load()
    fx, summ = [], []

    for a, b in transitions(lad):
        ya, yb = EFF[a], EFF[b]
        infl = px[yb] / px[ya] if ya in px and yb in px else None
        for g in range(1, 21):
            la = lad[a].get(str(g)); lb = lad[b].get(str(g))
            if not la or not lb:
                continue
            A, B = la["steps"], lb["steps"]
            if len(A) < 2 or len(B) < 2:
                continue
            rows = grade_table(g, A, B)
            an = anomalies(rows)
            for r in rows:
                real = (r["new_basic"] / r["old_basic"]) / infl if infl else None
                fx.append({
                    "from_era": a, "to_era": b, "grade": g,
                    "old_step": r["old_step"], "old_basic": r["old_basic"],
                    "new_step": r["new_step"], "new_basic": r["new_basic"],
                    "raise_pct": r["raise_pct"], "step_shift": r["step_shift"],
                    "landed_exactly": r["exact"],
                    "inflation_mult": round(infl, 4) if infl else "",
                    "real_mult": round(real, 4) if real else "",
                    "real_pct": round((real - 1) * 100, 2) if real else "",
                    "src_from": la["source"], "src_to": lb["source"],
                })
            summ.append({
                "from_era": a, "to_era": b, "grade": g,
                "old_steps": an["n_old_steps"], "distinct_new": an["n_distinct_new"],
                "collapsed": an["collapsed_steps"], "demoted": an["n_demoted"],
                "worst_demotion": an["max_demotion"],
                "raise_step1": an["raise_top"], "raise_top_step": an["raise_bottom"],
                "raise_spread_pts": (round(an["raise_top"] - an["raise_bottom"], 2)
                                     if an["raise_top"] is not None else ""),
                "inflation_mult": round(infl, 4) if infl else "",
                "real_pct_step1": (round(((1 + an["raise_top"] / 100) / infl - 1) * 100, 2)
                                   if infl and an["raise_top"] is not None else ""),
                "real_pct_topstep": (round(((1 + an["raise_bottom"] / 100) / infl - 1) * 100, 2)
                                     if infl and an["raise_bottom"] is not None else ""),
            })

    for name, rows in (("fixation_tables.csv", fx), ("anomaly_summary.csv", summ)):
        if rows:
            with open(OUTD / name, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
            print(f"{name}: {len(rows)} rows")

    # phased release for 2026 only
    if "nps_2015" in lad and "nps_2026" in lad:
        ph = []
        for g in range(1, 21):
            l15 = lad["nps_2015"].get(str(g)); l26 = lad["nps_2026"].get(str(g))
            if not l15 or not l26 or len(l15["steps"]) < 2:
                continue
            for r in grade_table(g, l15["steps"], l26["steps"]):
                for tag, yr in (("p1", 2026), ("p2", 2027), ("full", 2027)):
                    pay, pct = phase_pay(r["old_basic"], r["new_basic"], g, tag)
                    real = (pay / r["old_basic"]) / (px[yr] / px[2015])
                    ph.append({"grade": g, "old_step": r["old_step"],
                               "old_basic": r["old_basic"], "phase": tag,
                               "share_released": pct, "basic_drawn": pay,
                               "vs_2015_nominal": round(pay / r["old_basic"], 4),
                               "real_vs_2015": round(real, 4),
                               "real_pct": round((real - 1) * 100, 2)})
        with open(OUTD / "phased_release.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(ph[0].keys()))
            w.writeheader(); w.writerows(ph)
        print(f"phased_release.csv: {len(ph)} rows")

    if summ:
        print("\nANOMALY SUMMARY BY TRANSITION (all grades pooled)")
        by = defaultdict(list)
        for s in summ:
            by[(s["from_era"], s["to_era"])].append(s)
        print(f"  {'transition':24} {'grades':>6} {'collapsed':>10} {'demoted':>8} "
              f"{'worst':>6} {'spread':>7} {'real@1':>8} {'real@top':>9}")
        for k, v in by.items():
            tot_col = sum(x["collapsed"] for x in v)
            tot_dem = sum(x["demoted"] for x in v)
            worst = min(x["worst_demotion"] for x in v)
            spr = [x["raise_spread_pts"] for x in v if x["raise_spread_pts"] != ""]
            r1 = [x["real_pct_step1"] for x in v if x["real_pct_step1"] != ""]
            rt = [x["real_pct_topstep"] for x in v if x["real_pct_topstep"] != ""]
            print(f"  {k[0][4:]+' -> '+k[1][4:]:24} {len(v):>6} {tot_col:>10} "
                  f"{tot_dem:>8} {worst:>6} "
                  f"{(sum(spr)/len(spr) if spr else 0):>6.1f} "
                  f"{(sum(r1)/len(r1) if r1 else 0):>7.1f}% "
                  f"{(sum(rt)/len(rt) if rt else 0):>8.1f}%")


if __name__ == "__main__":
    main()
