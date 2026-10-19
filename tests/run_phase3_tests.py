"""Phase 3 test runner.  ALL DATA IS SYNTHETIC.

Runs: SQLite build -> SQL validation checks -> SQL business queries vs the independent
pandas reference -> raw-CSV reconciliation -> aggregation-rule guard rails -> designed
scenarios -> DAX/M structural review. Writes:
    docs/phase3_validation_report.md   (actual results of this run)
    tests/kpi_expected_values.csv      (pandas reference values)
    tests/dax_validation_checklist.md  (expected values to compare in Power BI)

Usage: python tests/run_phase3_tests.py        (exit code 1 if any test fails)
"""
import csv
import math
import re
import sqlite3
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_database
import kpi_reference as ref
import lint_dax_m

ROOT = ref.ROOT
RESULTS = []          # (section, name, passed, detail)


def record(section, name, passed, detail=""):
    RESULTS.append((section, name, bool(passed), detail))


def split_blocks(path, marker):
    txt = path.read_text()
    if marker == "check":
        parts = re.split(r"^-- @check (.*)$", txt, flags=re.M)[1:]
        return [(parts[i], parts[i + 1]) for i in range(0, len(parts), 2)]
    parts = re.split(r"^-- @query (\S+) (\S+)$", txt, flags=re.M)[1:]
    return [(parts[i], parts[i + 1], parts[i + 2]) for i in range(0, len(parts), 3)]


def clean_sql(sql):
    return re.sub(r"(?m)^--.*$", "", sql).strip().rstrip(";")


def same(a, b, rel=1e-9, abs_=1e-9):
    if (a is None or (isinstance(a, float) and math.isnan(a))) and (b is None or (isinstance(b, float) and math.isnan(b))):
        return True
    if a is None or b is None:
        return False
    if isinstance(a, str) or isinstance(b, str):
        return str(a) == str(b)
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_)


def main():
    t = ref.load()
    db_file = ROOT / "sql" / "cre_synthetic.sqlite"
    con = build_database.build(db_file)

    # ---- 1. SQL validation checks --------------------------------------
    for name, sql in split_blocks(ROOT / "sql" / "02_validation.sql", "check"):
        v = con.execute(clean_sql(sql)).fetchall()
        record("SQL validation", name.strip(), v == [(0,)], f"violations={v[0][0] if v else '?'}")

    # ---- 2. SQL business queries vs independent pandas reference -------
    sql_results = {}
    for qid, name, sql in split_blocks(ROOT / "sql" / "03_business_queries.sql", "query"):
        cur = con.execute(clean_sql(sql))
        cols = [c[0] for c in cur.description]
        sql_results[qid] = pd.DataFrame(cur.fetchall(), columns=cols)
        record("SQL queries", f"{qid} {name} runs", len(sql_results[qid]) > 0, f"{len(sql_results[qid])} rows")

    for qid, fn in ref.REFERENCES.items():
        exp, got = fn(t), sql_results[qid]
        exp_cols = list(exp.columns)
        key = exp_cols[0]
        got = got.rename(columns={got.columns[0]: key})
        miss = set(exp[key].astype(str)) ^ set(got[key].astype(str))
        if miss:
            record("SQL vs pandas", f"{qid}: same slices", False, f"mismatch {sorted(miss)[:5]}")
            continue
        g = got.set_index(got[key].astype(str))
        bad, cells = [], 0
        for _, row in exp.iterrows():
            for c in exp_cols[1:]:
                cells += 1
                if not same(row[c], g.loc[str(row[key]), c]):
                    bad.append(f"{row[key]}.{c}: pandas={row[c]} sql={g.loc[str(row[key]), c]}")
        record("SQL vs pandas", f"{qid}: {len(exp)} slices x {len(exp_cols) - 1} KPIs ({cells} values)",
               not bad, "; ".join(bad[:3]) or "all equal (rel tol 1e-9)")

    # ---- 3. Raw-CSV reconciliation (csv module only; no pandas, no SQL) --
    def csv_sum(table, col):
        with open(ROOT / "data" / "clean" / f"{table}.csv", newline="") as fh:
            return sum(float(r[col]) for r in csv.DictReader(fh))
    for table, col, view_sql in [
        ("fact_opex", "ActualCostINR", "SELECT SUM(ActualCostINR) FROM fact_opex"),
        ("fact_budget", "BudgetINR", "SELECT SUM(BudgetINR) FROM fact_budget"),
        ("fact_space_usage", "ElectricityKWh", "SELECT SUM(ElectricityKWh) FROM fact_space_usage"),
        ("fact_space_usage", "Headcount", "SELECT SUM(Headcount) FROM fact_space_usage"),
        ("fact_projects", "ActualCostINR", "SELECT SUM(ActualCostINR) FROM fact_projects"),
        ("dim_location", "FloorAreaM2", "SELECT SUM(FloorAreaM2) FROM dim_location"),
    ]:
        a, b = csv_sum(table, col), con.execute(view_sql).fetchone()[0]
        record("CSV reconciliation", f"SUM({table}.{col}) CSV == SQLite", math.isclose(a, b, rel_tol=1e-12), f"{a:,.2f}")
    om_cost = con.execute("SELECT SUM(ActualCostINR) FROM vw_office_month").fetchone()[0]
    record("CSV reconciliation", "vw_office_month cost == fact_opex CSV total",
           math.isclose(om_cost, csv_sum("fact_opex", "ActualCostINR"), rel_tol=1e-12), f"{om_cost:,.2f}")

    # ---- 4. Aggregation-rule guard rails (negative controls) -----------
    om, c = ref._om(t), ref._cost(t)
    correct_area_m = om.FloorAreaM2.sum()
    wrong = c.merge(t["dim_location"], on="LocationID").FloorAreaM2.sum()   # area summed over opex rows
    record("Aggregation rules", "Area summed over fact_opex rows is exactly 5x area-months (the trap the dictionary warns about)",
           math.isclose(wrong, 5 * correct_area_m), f"wrong={wrong:,.0f} right={correct_area_m:,.0f}")
    q4 = sql_results["Q04"].set_index("Slice")
    cc01 = c[c.CategoryID == "CC01"].ActualCostINR.sum()
    record("Aggregation rules", "Category filter changes numerator only (CC01 opex per m2 uses full area-months)",
           same(q4.loc["CC01", "opex_per_m2_month"], cc01 / correct_area_m), f"{q4.loc['CC01', 'opex_per_m2_month']:.4f}")
    record("Aggregation rules", "Category opex per m2 values add up to the 'ALL' value",
           same(q4.drop("ALL").opex_per_m2_month.sum(), q4.loc["ALL", "opex_per_m2_month"], rel=1e-9))
    q2 = sql_results["Q02"].set_index("Slice")
    mean_of_ratios = q2.drop("PORTFOLIO").desk_utilisation.mean()
    record("Aggregation rules", "Portfolio desk utilisation is a ratio of sums, differing from the average of office ratios",
           not math.isclose(q2.loc["PORTFOLIO", "desk_utilisation"], mean_of_ratios, rel_tol=1e-6),
           f"ratio-of-sums={q2.loc['PORTFOLIO', 'desk_utilisation']:.4f} avg-of-ratios={mean_of_ratios:.4f}")
    q11 = sql_results["Q11"].set_index("Slice")
    avg_idx = q11.drop("PORTFOLIO").cost_vs_progress_index.mean()
    record("Aggregation rules", "Portfolio cost-vs-progress index is budget-weighted, not the average of project indices",
           not math.isclose(q11.loc["PORTFOLIO", "cost_vs_progress_index"], avg_idx, rel_tol=1e-6),
           f"weighted={q11.loc['PORTFOLIO', 'cost_vs_progress_index']:.4f} simple-avg={avg_idx:.4f}")
    record("Aggregation rules", "Pandas risk-rule recomputation matches stored RiskLevel (0 mismatches)",
           ref.risk_rule_mismatches(t) == 0, f"mismatches={ref.risk_rule_mismatches(t)}")
    record("Aggregation rules", "No 'Not Started' projects in clean data (exclusion rule cannot be exercised here)",
           (t["fact_projects"].Status == "Not Started").sum() == 0, "count=0")

    # ---- 5. DAX time-comparison semantics, simulated in pandas ---------
    months = c.groupby("MonthStart").ActualCostINR.sum()
    fy = c.groupby("FiscalYear").ActualCostINR.sum()

    def prior_total(selected, shift):
        """Mimics measures [Actual Opex INR Prior Month/Year]: only if EVERY month has a prior month."""
        idx = pd.to_datetime(pd.Index(selected))
        prior = (idx - pd.DateOffset(months=shift)).strftime("%Y-%m-%d")
        if not set(prior) <= set(months.index):
            return None
        return months.loc[list(prior)].sum()
    fy26 = [m for m in months.index if m >= "2025-10-01"]
    p = prior_total(fy26, 12)
    record("DAX semantics (simulated)", "FY26 YoY via month-shift equals fiscal-year YoY from SQL Q05",
           p is not None and same(months.loc[fy26].sum() / p - 1, sql_results["Q05"].set_index("Slice").loc["FY26", "yoy_pct"]),
           f"{months.loc[fy26].sum() / p - 1:.6f}")
    record("DAX semantics (simulated)", "YoY is BLANK for a 24-month selection and for FY25 (prior months missing)",
           prior_total(list(months.index), 12) is None and prior_total([m for m in months.index if m < "2025-10-01"], 12) is None)
    record("DAX semantics (simulated)", "MoM is BLANK for Oct 2024 (no prior month) and defined for Nov 2024",
           prior_total(["2024-10-01"], 1) is None and prior_total(["2024-11-01"], 1) is not None)

    # ---- 6. Designed scenarios vs data dictionary ----------------------
    q14 = sql_results["Q14"].set_index("Slice").value
    sc = [
        ("Pune electricity variance ~31%", abs(q14["S1 Pune electricity variance pct"] - 0.31) < 0.01),
        ("Other offices' POOLED electricity variance ~3% (3.4%)", abs(q14["S1 other offices pooled electricity variance pct"] - 0.03) < 0.01),
        ("PRJ016 is 93 days overdue", q14["S1 PRJ016 days overdue"] == 93),
        ("PRJ016 cost-vs-progress index 1.28", abs(q14["S1 PRJ016 cost-vs-progress index"] - 1.28) < 0.005),
        ("PRJ016 budget consumed 89.6%", abs(q14["S1 PRJ016 budget consumed"] - 0.896) < 0.0005),
        ("Chennai desk utilisation ~34%", abs(q14["S2 Chennai desk utilisation"] - 0.34) < 0.005),
        ("Other offices' utilisation within 42-78%", q14["S2 other offices min utilisation"] > 0.415 and q14["S2 other offices max utilisation"] < 0.785),
        ("Warsaw facility-management variance ~8.5%", abs(q14["S3 Warsaw facility-management variance pct"] - 0.085) < 0.002),
        ("Warsaw other categories pooled ~3%", abs(q14["S3 Warsaw other categories pooled variance pct"] - 0.03) < 0.005),
    ]
    for n, ok in sc:
        record("Designed scenarios", n, ok)
    per_office = sql_results["Q07"].set_index("Slice").drop(["PORTFOLIO", "LOC04"]).electricity_variance_pct
    record("Designed scenarios", "Individual non-Pune offices' electricity variance spans a WIDE range (so '~3%' is a pooled figure only)",
           per_office.min() < 0 and per_office.max() > 0.09, f"{per_office.min():.1%} to {per_office.max():.1%}")

    # ---- 7. DAX / M structural review (+ lint self-test) ---------------
    dp, dn = lint_dax_m.lint_dax()
    mp, mn = lint_dax_m.lint_m()
    record("DAX/M structural review", f"dax/measures.dax: {dn[0]}, no structural problems", not dp, "; ".join(dp[:3]) or "none found")
    record("DAX/M structural review", f"powerquery/*.m: {mn[0]}, no structural problems", not mp, "; ".join(mp[:3]) or "none found")
    src = (ROOT / "dax" / "measures.dax").read_text()
    mutants = {
        "typo in function name": src.replace("DIVIDE ( [Occupied Desk-Months]", "DIVDE ( [Occupied Desk-Months]", 1),
        "unknown column": src.replace("fact_opex[ActualCostINR]", "fact_opex[ActualCost]", 1),
        "undefined measure": src.replace("[Desk-Months] )\n\nMEASURE _Measures[Desk Assignment", "[Desk-Months Typo] )\n\nMEASURE _Measures[Desk Assignment", 1),
        "unbalanced parenthesis": src.replace("SUM ( dim_location[Desks] )", "SUM ( dim_location[Desks] ", 1),
    }
    with tempfile.TemporaryDirectory() as d:
        caught = []
        for label, text in mutants.items():
            fp = Path(d) / "m.dax"
            fp.write_text(text)
            caught.append((label, text != src and bool(lint_dax_m.lint_dax(fp)[0])))
    record("DAX/M structural review", "Lint self-test: deliberately broken copies are all flagged",
           all(ok for _, ok in caught), ", ".join(f"{l}={'caught' if ok else 'MISSED'}" for l, ok in caught))

    write_outputs(t, sql_results)
    passed = sum(r[2] for r in RESULTS)
    print(f"{passed}/{len(RESULTS)} tests passed")
    for s, n, ok, d in RESULTS:
        if not ok:
            print("FAIL", s, "|", n, "|", d)
    return passed == len(RESULTS)


def fmt(v, kind):
    return {"pct": f"{v:.2%}", "inr": f"{v:,.2f}", "num": f"{v:,.4f}", "int": f"{v:,.0f}"}[kind]


def write_outputs(t, sql):
    exp = ref.expected_values_long(t)
    exp.to_csv(ROOT / "tests" / "kpi_expected_values.csv", index=False, float_format="%.10g")

    # ---- DAX checklist generated from the pandas reference --------------
    R = {q: f(t).set_index("Slice") for q, f in ref.REFERENCES.items()}
    P = R["Q02"].loc["PORTFOLIO"]
    cases = [
        ("No filters (whole portfolio, Oct 2024 - Sep 2026)", [
            ("Offices", 12, "int"), ("Total Floor Area m2", R["Q01"].loc["PORTFOLIO", "total_floor_area"], "int"),
            ("Total Desks", R["Q01"].loc["PORTFOLIO", "total_desks"], "int"),
            ("Usable Area Ratio", R["Q01"].loc["PORTFOLIO", "usable_area_ratio"], "num"),
            ("Floor Area per Desk m2", R["Q01"].loc["PORTFOLIO", "floor_area_per_desk"], "num"),
            ("Desk Utilisation %", P.desk_utilisation, "num"), ("Desk Assignment Ratio", P.desk_assignment_ratio, "num"),
            ("Usable Area per Employee m2", P.usable_area_per_employee, "num"),
            ("Actual Opex INR", R["Q03"].loc["PORTFOLIO", "actual_opex"], "inr"),
            ("Budget INR", R["Q03"].loc["PORTFOLIO", "budget"], "inr"),
            ("Budget Variance INR", R["Q03"].loc["PORTFOLIO", "budget_variance"], "inr"),
            ("Budget Variance %", R["Q03"].loc["PORTFOLIO", "budget_variance_pct"], "num"),
            ("Opex per m2 per Month INR", R["Q06"].loc["PORTFOLIO", "opex_per_m2_month"], "num"),
            ("Opex per Employee per Month INR", R["Q06"].loc["PORTFOLIO", "opex_per_employee_month"], "num"),
            ("Opex per Occupied Desk per Month INR", R["Q06"].loc["PORTFOLIO", "opex_per_occupied_desk_month"], "num"),
            ("Electricity Intensity kWh per m2 per Month", R["Q07"].loc["PORTFOLIO", "electricity_kwh_per_m2_month"], "num"),
            ("Implied Electricity Tariff INR per kWh", R["Q07"].loc["PORTFOLIO", "implied_tariff_inr_per_kwh"], "num"),
            ("Electricity Variance %", R["Q07"].loc["PORTFOLIO", "electricity_variance_pct"], "num"),
            ("Utilities Share %", R["Q08"].loc["PORTFOLIO", "utilities_share"], "num"),
            ("Opex YoY %  (24 months selected)", "BLANK", None), ("Opex MoM %  (24 months selected)", "BLANK", None),
            ("Imputed Rows % Space Usage", R["Q13"].loc["fact_space_usage", "imputed_row_pct"], "num"),
            ("Imputed Rows % Opex", R["Q13"].loc["fact_opex", "imputed_row_pct"], "num"),
            ("Imputed Rows % Budget", R["Q13"].loc["fact_budget", "imputed_row_pct"], "num"),
            ("Projects", R["Q12"].loc["PORTFOLIO", "projects"], "int"),
            ("Overdue Projects", R["Q12"].loc["PORTFOLIO", "overdue_projects"], "int"),
            ("High Risk Projects", R["Q12"].loc["PORTFOLIO", "high_risk_projects"], "int"),
            ("Cost vs Progress Index", R["Q11"].loc["PORTFOLIO", "cost_vs_progress_index"], "num"),
            ("Project Budget Consumed %", R["Q11"].loc["PORTFOLIO", "budget_consumed"], "num"),
            ("Avg Days Late Completed", R["Q12"].loc["PORTFOLIO", "avg_days_late_completed"], "num"),
            ("Max Days Overdue", R["Q12"].loc["PORTFOLIO", "max_days_overdue"], "int"),
            ("Risk Rule Mismatches", 0, "int"),
        ]),
        ("Slicer: dim_location = LOC04 (Pune)", [
            ("Electricity Variance %", R["Q07"].loc["LOC04", "electricity_variance_pct"], "num"),
            ("Budget Variance %", R["Q03"].loc["LOC04", "budget_variance_pct"], "num"),
            ("Overdue Projects", R["Q12"].loc["LOC04", "overdue_projects"], "int")]),
        ("Slicer: dim_location = LOC05 (Chennai)", [
            ("Desk Utilisation %", R["Q02"].loc["LOC05", "desk_utilisation"], "num"),
            ("Opex per Occupied Desk per Month INR", R["Q06"].loc["LOC05", "opex_per_occupied_desk_month"], "num")]),
        ("Slicer: dim_location = LOC11 (Warsaw) and dim_cost_category = CC04 (Facility Management)", [
            ("Budget Variance %", R["Q04"].loc["CC04", "budget_variance_pct"] if False else
             float(ref._cost(t).query("LocationID=='LOC11' and CategoryID=='CC04'").pipe(lambda d: (d.ActualCostINR.sum() - d.BudgetINR.sum()) / d.BudgetINR.sum())), "num")]),
        ("Slicer: dim_cost_category = CC01 (rule 4: denominator must NOT change)", [
            ("Actual Opex INR", R["Q04"].loc["CC01", "actual_opex"], "inr"),
            ("Opex per m2 per Month INR", R["Q04"].loc["CC01", "opex_per_m2_month"], "num"),
            ("Area-Months m2 (same as unfiltered)", float(ref._om(t).FloorAreaM2.sum()), "int")]),
        ("Slicer: dim_date[FiscalYear] = FY26", [
            ("Actual Opex INR", R["Q05"].loc["FY26", "actual_opex"], "inr"),
            ("Opex per m2 per Month INR", R["Q05"].loc["FY26", "opex_per_m2_month"], "num"),
            ("Opex YoY %", R["Q05"].loc["FY26", "yoy_pct"], "num")]),
        ("Slicer: dim_date[FiscalYear] = FY25", [("Opex YoY %", "BLANK", None), ("Actual Opex INR", R["Q05"].loc["FY25", "actual_opex"], "inr")]),
        ("Slicer: dim_date[MonthStart] = 2026-09-01", [
            ("Opex MoM %", R["Q09"].loc["2026-09-01", "mom_pct"], "num"), ("Opex YoY %", R["Q09"].loc["2026-09-01", "yoy_pct"], "num")]),
        ("Slicer: dim_date[MonthStart] = 2024-10-01", [("Opex MoM %", "BLANK", None), ("Opex YoY %", "BLANK", None)]),
        ("Visual rows: fact_projects[ProjectID] = PRJ016", [
            ("Cost vs Progress Index", R["Q11"].loc["PRJ016", "cost_vs_progress_index"], "num"),
            ("Project Budget Consumed %", R["Q11"].loc["PRJ016", "budget_consumed"], "num"),
            ("Max Days Overdue", R["Q10"].loc["PRJ016", "days_overdue"], "int")]),
    ]
    L = ["# DAX validation checklist (generated)", "",
         "**ALL DATA IS SYNTHETIC.** Generated by `tests/run_phase3_tests.py` from the independent pandas reference "
         "(`tests/kpi_reference.py`). **Status: NOT YET EXECUTED in Power BI.** Every box below is unchecked on purpose.", "",
         "How to use (Power BI Desktop on Windows, or another supported environment):", "",
         "1. Follow `docs/powerquery_setup.md` to load the 7 tables, `param_AsOfDate` and `_Measures`, and create the relationships.",
         "2. Paste `dax/measures.dax` into DAX query view and apply it to the model.",
         "3. Run `qa_row_counts` first: every `Pass` must be `true`.",
         "4. Put the measure in a card or matrix, apply the stated filter, and compare with the expected value. "
         "Tolerance: 0.01 INR for money, 0.0001 for ratios, exact for counts. Tick the box and note any difference.", ""]
    for title, rows in cases:
        L += [f"## {title}", "", "| Done | Measure | Expected (pandas) | Power BI result |", "|---|---|---|---|"]
        for name, val, kind in rows:
            L.append(f"| [ ] | {name} | {val if isinstance(val, str) else fmt(float(val), kind)} | |")
        L.append("")
    (ROOT / "tests" / "dax_validation_checklist.md").write_text("\n".join(L))

    # ---- validation report ---------------------------------------------
    by = defaultdict(list)
    for s, n, ok, d in RESULTS:
        by[s].append((n, ok, d))
    passed = sum(r[2] for r in RESULTS)
    out = ["# Phase 3 Validation Report", "",
           "**ALL DATA IS SYNTHETIC** (invented offices, people and figures; not from any real company).", "",
           f"Generated by `tests/run_phase3_tests.py`. "
           f"SQLite {sqlite3.sqlite_version}, pandas {pd.__version__}, numpy {np.__version__}.", "",
           f"**Result: {passed}/{len(RESULTS)} automated tests passed.**", "",
           "## What was and was not executed", "",
           "| Item | Status |", "|---|---|",
           "| SQLite schema, views, validation checks, business queries | **Executed** (results below) |",
           "| pandas reference KPIs and SQL-vs-pandas comparison | **Executed** (results below) |",
           "| Power Query M (`powerquery/*.m`) | **Written and structurally reviewed only. NOT executed in Power Query / Power BI.** |",
           "| DAX measures (`dax/measures.dax`) | **Written and structurally reviewed only. NOT executed in Power BI / DAX Studio.** |",
           "| DAX results vs expected values | **Pending**: use `tests/dax_validation_checklist.md` on Windows or another supported environment |", "",
           "The structural review (`tests/lint_dax_m.py`) is not a DAX/M engine: it checks brackets, quotes, known function names, "
           "table/column/measure references, circular references and that M type lists match the CSV headers. "
           "The DAX time-comparison logic was only *simulated* in pandas.", ""]
    for s, rows in by.items():
        out += [f"## {s}", "", "| Result | Test | Detail |", "|---|---|---|"]
        for n, ok, d in rows:
            out.append(f"| {'PASS' if ok else '**FAIL**'} | {n} | {str(d).replace('|', '/')} |")
        out.append("")
    (ROOT / "docs" / "phase3_validation_report.md").write_text("\n".join(out))


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
