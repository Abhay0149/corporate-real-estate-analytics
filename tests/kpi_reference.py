"""Independent pandas reference for every Phase 3 KPI.  ALL DATA IS SYNTHETIC.

Computes KPIs straight from data/clean/*.csv with pandas (no SQL, no SQLite),
following docs/data_dictionary.md. The test runner compares SQL results and the
expected-value file for the DAX checklist against this module.

Each reference_Qxx() returns a DataFrame whose first column is Slice and whose
other column names match the SQL query of the same id in sql/03_business_queries.sql.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "clean"
AS_OF = pd.Timestamp("2026-09-30")


def load():
    t = {n: pd.read_csv(CLEAN / f"{n}.csv") for n in
         ["dim_location", "dim_cost_category", "dim_date", "fact_space_usage",
          "fact_opex", "fact_budget", "fact_projects"]}
    for c in ("StartDate", "DeadlineDate", "CompletionDate"):
        t["fact_projects"][c] = pd.to_datetime(t["fact_projects"][c])
    return t


def _om(t):
    """Office-month frame: one row per fact_space_usage row with static attributes attached."""
    om = (t["fact_space_usage"]
          .merge(t["dim_location"], on="LocationID", validate="m:1")
          .merge(t["dim_date"][["MonthStart", "FiscalYear"]], on="MonthStart", validate="m:1"))
    assert len(om) == 288
    return om


def _cost(t):
    """Opex + budget at location x month x category grain, with category attributes."""
    c = (t["fact_opex"].merge(t["fact_budget"], on=["LocationID", "MonthStart", "CategoryID"],
                              validate="1:1", suffixes=("", "_b"))
         .merge(t["dim_cost_category"], on="CategoryID", validate="m:1")
         .merge(t["dim_date"][["MonthStart", "FiscalYear"]], on="MonthStart", validate="m:1"))
    assert len(c) == 1440
    return c


def _with_portfolio(df, key="LocationID"):
    """Append a PORTFOLIO row = sum of the numeric columns (so ratios stay ratio-of-sums)."""
    tot = df.drop(columns=key).sum()
    tot[key] = "PORTFOLIO"
    return pd.concat([df, tot.to_frame().T], ignore_index=True).rename(columns={key: "Slice"})


def reference_Q01(t):
    d = t["dim_location"]
    x = pd.DataFrame({"LocationID": d.LocationID, "f": d.FloorAreaM2, "u": d.UsableAreaM2, "d": d.Desks})
    x = _with_portfolio(x)
    return pd.DataFrame({"Slice": x.Slice, "total_floor_area": x.f.astype(float), "total_desks": x.d.astype(float),
                         "usable_area_ratio": x.u / x.f, "floor_area_per_desk": x.f / x.d})


def reference_Q02(t):
    om = _om(t)
    g = om.groupby("LocationID").agg(desk_m=("Desks", "sum"), occ_m=("AvgDailyOccupiedDesks", "sum"),
                                     hc_m=("Headcount", "sum"), usable_m=("UsableAreaM2", "sum")).reset_index()
    x = _with_portfolio(g)
    return pd.DataFrame({"Slice": x.Slice, "desk_utilisation": x.occ_m / x.desk_m,
                         "desk_assignment_ratio": x.hc_m / x.desk_m, "usable_area_per_employee": x.usable_m / x.hc_m})


def reference_Q03(t):
    c = _cost(t)
    g = c.groupby("LocationID").agg(a=("ActualCostINR", "sum"), b=("BudgetINR", "sum")).reset_index()
    x = _with_portfolio(g)
    return pd.DataFrame({"Slice": x.Slice, "actual_opex": x.a, "budget": x.b,
                         "budget_variance": x.a - x.b, "budget_variance_pct": (x.a - x.b) / x.b})


def reference_Q04(t):
    c = _cost(t)
    area_m = _om(t).FloorAreaM2.sum()  # category filter must NOT change the denominator
    g = c.groupby("CategoryID").agg(a=("ActualCostINR", "sum"), b=("BudgetINR", "sum")).reset_index()
    g = pd.concat([g, pd.DataFrame({"CategoryID": ["ALL"], "a": [g.a.sum()], "b": [g.b.sum()]})], ignore_index=True)
    return pd.DataFrame({"Slice": g.CategoryID, "actual_opex": g.a, "budget": g.b, "budget_variance": g.a - g.b,
                         "budget_variance_pct": (g.a - g.b) / g.b, "opex_per_m2_month": g.a / area_m})


def reference_Q05(t):
    c, om = _cost(t), _om(t)
    g = c.groupby("FiscalYear").agg(a=("ActualCostINR", "sum"), b=("BudgetINR", "sum"))
    g["area_m"] = om.groupby("FiscalYear").FloorAreaM2.sum()
    g = g.sort_index().reset_index()
    prior = g.a.shift(1)
    return pd.DataFrame({"Slice": g.FiscalYear, "actual_opex": g.a, "budget": g.b, "budget_variance": g.a - g.b,
                         "budget_variance_pct": (g.a - g.b) / g.b, "opex_per_m2_month": g.a / g.area_m,
                         "yoy_pct": (g.a - prior) / prior})


def reference_Q06(t):
    om, c = _om(t), _cost(t)
    g = om.groupby("LocationID").agg(area_m=("FloorAreaM2", "sum"), hc_m=("Headcount", "sum"),
                                     occ_m=("AvgDailyOccupiedDesks", "sum"))
    g["a"] = c.groupby("LocationID").ActualCostINR.sum()
    x = _with_portfolio(g.reset_index())
    return pd.DataFrame({"Slice": x.Slice, "opex_per_m2_month": x.a / x.area_m,
                         "opex_per_employee_month": x.a / x.hc_m, "opex_per_occupied_desk_month": x.a / x.occ_m})


def reference_Q07(t):
    om, c = _om(t), _cost(t)
    e = c[c.CategoryID == "CC01"].groupby("LocationID").agg(ec=("ActualCostINR", "sum"), eb=("BudgetINR", "sum"))
    g = om.groupby("LocationID").agg(area_m=("FloorAreaM2", "sum"), kwh=("ElectricityKWh", "sum")).join(e)
    x = _with_portfolio(g.reset_index())
    return pd.DataFrame({"Slice": x.Slice, "electricity_kwh_per_m2_month": x.kwh / x.area_m,
                         "implied_tariff_inr_per_kwh": x.ec / x.kwh, "electricity_variance_pct": (x.ec - x.eb) / x.eb})


def reference_Q08(t):
    c = _cost(t)
    g = pd.DataFrame({"u": c[c.CostGroup == "Utilities"].groupby("LocationID").ActualCostINR.sum(),
                      "a": c.groupby("LocationID").ActualCostINR.sum()})
    x = _with_portfolio(g.reset_index())
    return pd.DataFrame({"Slice": x.Slice, "utilities_share": x.u / x.a})


def reference_Q09(t):
    c = _cost(t)
    m = c.groupby("MonthStart").agg(a=("ActualCostINR", "sum"), b=("BudgetINR", "sum")).sort_index().reset_index()
    p1, p12 = m.a.shift(1), m.a.shift(12)
    return pd.DataFrame({"Slice": m.MonthStart, "actual_opex": m.a, "budget": m.b,
                         "budget_variance_pct": (m.a - m.b) / m.b, "mom_pct": (m.a - p1) / p1, "yoy_pct": (m.a - p12) / p12})


def _proj(t):
    p = t["fact_projects"].copy()
    p["overdue"] = p.Status.isin(["In Progress", "On Hold"]) & (p.DeadlineDate < AS_OF)
    return p


def reference_Q10(t):
    p = _proj(t)
    o = p[p.overdue].copy()
    o["days_overdue"] = (AS_OF - o.DeadlineDate).dt.days
    o = o.sort_values(["days_overdue", "ProjectID"], ascending=[False, True])
    return pd.DataFrame({"Slice": o.ProjectID.values, "days_overdue": o.days_overdue.astype(float).values,
                         "PercentComplete": o.PercentComplete.astype(float).values})


def reference_Q11(t):
    p = _proj(t)
    p = p[p.Status != "Not Started"]
    earned = p.BudgetINR * p.PercentComplete / 100
    rows = pd.DataFrame({"Slice": p.ProjectID, "budget_consumed": p.ActualCostINR / p.BudgetINR,
                         "cost_vs_progress_index": p.ActualCostINR / earned})
    port = pd.DataFrame({"Slice": ["PORTFOLIO"], "budget_consumed": [p.ActualCostINR.sum() / p.BudgetINR.sum()],
                         "cost_vs_progress_index": [p.ActualCostINR.sum() / earned.sum()]})
    return pd.concat([rows, port], ignore_index=True).sort_values("Slice").reset_index(drop=True)


def reference_Q12(t):
    p = _proj(t)
    g = p.groupby("LocationID").agg(projects=("ProjectID", "count"), overdue_projects=("overdue", "sum"),
                                    high_risk_projects=("RiskLevel", lambda s: (s == "High").sum())).astype(float)
    g.loc["PORTFOLIO"] = g.sum()
    g = g.reset_index().rename(columns={"LocationID": "Slice", "index": "Slice"})
    comp = p[p.Status == "Completed"]
    g["avg_days_late_completed"] = np.nan
    g["max_days_overdue"] = np.nan
    g.loc[g.Slice == "PORTFOLIO", "avg_days_late_completed"] = (comp.CompletionDate - comp.DeadlineDate).dt.days.mean()
    g.loc[g.Slice == "PORTFOLIO", "max_days_overdue"] = float((AS_OF - p[p.overdue].DeadlineDate).dt.days.max())
    return g.sort_values("Slice").reset_index(drop=True)


def reference_Q13(t):
    rows = [(n, (t[n].DataQualityFlag == "Imputed").mean()) for n in ["fact_budget", "fact_opex", "fact_space_usage"]]
    return pd.DataFrame(rows, columns=["Slice", "imputed_row_pct"])


def reference_Q15(t):
    c = _cost(t)
    g = c.groupby(["FiscalYear", "CostGroup"]).agg(a=("ActualCostINR", "sum"), b=("BudgetINR", "sum")).reset_index()
    g["share_of_fy_opex"] = g.a / g.groupby("FiscalYear").a.transform("sum")
    g["Slice"] = g.FiscalYear + " " + g.CostGroup
    g = g.sort_values("Slice")
    return pd.DataFrame({"Slice": g.Slice, "actual_opex": g.a, "budget": g.b,
                         "budget_variance_pct": (g.a - g.b) / g.b, "share_of_fy_opex": g.share_of_fy_opex}).reset_index(drop=True)


def reference_Q14(t):
    c, om, p = _cost(t), _om(t), _proj(t)
    e = c[c.CategoryID == "CC01"].groupby("LocationID")[["ActualCostINR", "BudgetINR"]].sum()
    v = lambda d: (d.ActualCostINR.sum() - d.BudgetINR.sum()) / d.BudgetINR.sum()
    u = om.groupby("LocationID").apply(lambda d: d.AvgDailyOccupiedDesks.sum() / d.Desks.sum(), include_groups=False)
    w = c[c.LocationID == "LOC11"]
    r = p[p.ProjectID == "PRJ016"].iloc[0]
    rows = [
        ("S1 Pune electricity variance pct", v(e.loc[["LOC04"]])),
        ("S1 other offices pooled electricity variance pct", v(e.drop("LOC04"))),
        ("S1 PRJ016 days overdue", float((AS_OF - r.DeadlineDate).days)),
        ("S1 PRJ016 cost-vs-progress index", r.ActualCostINR / r.BudgetINR / (r.PercentComplete / 100)),
        ("S1 PRJ016 budget consumed", r.ActualCostINR / r.BudgetINR),
        ("S2 Chennai desk utilisation", u["LOC05"]),
        ("S2 other offices min utilisation", u.drop("LOC05").min()),
        ("S2 other offices max utilisation", u.drop("LOC05").max()),
        ("S3 Warsaw facility-management variance pct", v(w[w.CategoryID == "CC04"])),
        ("S3 Warsaw other categories pooled variance pct", v(w[w.CategoryID != "CC04"])),
    ]
    return pd.DataFrame(rows, columns=["Slice", "value"])


REFERENCES = {f"Q{n:02d}": globals()[f"reference_Q{n:02d}"] for n in range(1, 16) if f"reference_Q{n:02d}" in globals()}


def risk_rule_mismatches(t):
    """Recompute RiskLevel from the dictionary rule; return number of stored values that disagree."""
    p = _proj(t)

    def idx(r):
        if r.Status == "Completed":
            return r.ActualCostINR / r.BudgetINR
        return r.ActualCostINR / r.BudgetINR / (r.PercentComplete / 100) if r.PercentComplete > 0 else 0.0

    def rule(r):
        i = idx(r)
        return "High" if r.overdue or i > 1.15 else "Medium" if i > 1.05 or r.Status == "On Hold" else "Low"

    return int((p.apply(rule, axis=1) != p.RiskLevel).sum())


def expected_values_long(t):
    """All reference KPIs in one long table (for tests/kpi_expected_values.csv)."""
    out = []
    for qid, fn in REFERENCES.items():
        df = fn(t)
        for col in df.columns[1:]:
            for s, v in zip(df.Slice, df[col]):
                if pd.notna(v):
                    out.append((qid, str(s), col, float(v)))
    extra = [("RISK", "PORTFOLIO", "risk_rule_mismatches", float(risk_rule_mismatches(t)))]
    return pd.DataFrame(out + extra, columns=["Query", "Slice", "KPI", "ExpectedValue"])


if __name__ == "__main__":
    print(expected_values_long(load()).head(20).to_string())
