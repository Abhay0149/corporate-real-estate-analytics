#!/usr/bin/env python3
"""
Validate the RAW synthetic data, clean it, and write a data-quality report.

Input : data/raw/*.csv
Output: data/clean/*.csv             clean tables (what Power BI will load)
        data/quality/issues_detected.csv   every finding, with the action taken
        data/quality/quarantined_rows.csv  raw rows removed and why
        docs/data_quality_report.md        human-readable report

Cleaning policy (see the report for details):
  1. Safe formatting problems are CORRECTED (trim / case / month-start date).
  2. Exact duplicate rows are REMOVED; conflicting duplicates are QUARANTINED.
  3. Rows with invalid keys, dates or relationships are QUARANTINED, never guessed.
  4. Invalid VALUES in monthly fact tables (blank, negative, outlier) are set to
     missing and IMPUTED by linear interpolation within the same
     location (+category) series. Every such row gets DataQualityFlag = 'Imputed'.
  5. Project rows that fail checks are quarantined and NOT imputed.

Run from the project root:   python scripts/validate_and_clean.py
Exit code 0 = all integrity checks passed, 1 = something failed.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, CLEAN, QUAL, DOCS = (ROOT / "data" / "raw", ROOT / "data" / "clean",
                          ROOT / "data" / "quality", ROOT / "docs")
for p in (CLEAN, QUAL, DOCS):
    p.mkdir(parents=True, exist_ok=True)

COUNTRY_REGION = {"India": "India", "Singapore": "APAC", "China": "APAC", "Australia": "APAC",
                  "Germany": "Europe", "Poland": "Europe", "United Kingdom": "Europe"}
STATUSES = {"Not Started", "In Progress", "On Hold", "Completed"}
RISKS = {"Low", "Medium", "High"}
OUTLIER_HI, OUTLIER_LO = 3.0, 0.25        # actual / budget plausibility band
findings, quarantine, stats = [], [], {}


# ---------------------------------------------------------------- helpers
def add(table, key, col, rule, detail, action, severity="Error"):
    findings.append(dict(Table=table, RecordKey=key, Column=col, Rule=rule,
                         Severity=severity, Detail=detail, Action=action))


def quar(table, row, key):
    d = {k: (None if pd.isna(v) else str(v)) for k, v in row.items()}
    quarantine.append(dict(Table=table, RecordKey=d.get(key), RawRow=json.dumps(d)))


def reject(df, mask, table, key, col, rule, detail):
    """Quarantine rows where mask is True and return the remaining rows."""
    for i in df.index[mask]:
        add(table, df.at[i, key], col, rule, detail(df.loc[i]) if callable(detail) else detail, "Quarantined")
        quar(table, df.loc[i], key)
    return df[~mask].copy()


def read(name):
    df = pd.read_csv(RAW / f"{name}.csv", dtype=str, keep_default_na=False)
    return df.replace("", np.nan)


def tidy_text(df, table, key, col, mode):
    s = df[col]
    f = s.str.strip().str.replace(r"\s+", " ", regex=True)
    f = f.str.upper() if mode == "id" else f.str.title()
    changed = s.notna() & (s != f)
    for i in df.index[changed]:
        add(table, df.at[i, key], col, "text_formatting", f"'{s[i]}' -> '{f[i]}'", "Corrected")
    df[col] = f
    return df


def check_id(df, table, key, col, pattern):
    bad = df[col].notna() & ~df[col].fillna("").str.fullmatch(pattern)
    return reject(df, bad, table, key, col, "invalid_id_format", lambda r: f"'{r[col]}' does not match {pattern}")


def check_required(df, table, key, cols):
    for c in cols:
        df = reject(df, df[c].isna(), table, key, c, "missing_value", f"Required field {c} is blank")
    return df


def check_numeric(df, table, key, col, quarantine_rows=False):
    """Coerce to number; flag non-numeric / negative. Bad values -> NaN (or quarantine)."""
    v = pd.to_numeric(df[col], errors="coerce")
    nonnum = df[col].notna() & v.isna()
    neg = v < 0
    action = "Quarantined" if quarantine_rows else "Value rejected (imputed later)"
    for i in df.index[nonnum]:
        add(table, df.at[i, key], col, "non_numeric", f"'{df.at[i, col]}' is not a number", action)
    for i in df.index[neg]:
        add(table, df.at[i, key], col, "negative_value", f"{col} = {v[i]:,.2f} is negative", action)
    df[col] = v
    if quarantine_rows:
        return reject_silent(df, nonnum | neg, table, key)
    df.loc[nonnum | neg, col] = np.nan
    for i in df.index[df[col].isna() & ~(nonnum | neg)]:
        add(table, df.at[i, key], col, "missing_value", f"{col} is blank", "Value missing (imputed later)")
    return df


def reject_silent(df, mask, table, key):
    for i in df.index[mask]:
        quar(table, df.loc[i], key)
    return df[~mask].copy()


def dedupe(df, table, key):
    ex = df.duplicated(keep="first")
    for i in df.index[ex]:
        add(table, df.at[i, key], "ALL", "duplicate_exact", "Identical row repeated", "Removed")
    df = df[~ex].copy()
    conf = df.duplicated(subset=[key], keep=False) & df[key].notna()
    for k in df.loc[conf, key].unique():
        add(table, k, key, "duplicate_conflict", "Same key, different values", "Quarantined (all copies)")
    return reject_silent(df, conf, table, key)


def parse_month(df, table, key, valid_months):
    d = pd.to_datetime(df["MonthStart"], format="%Y-%m-%d", errors="coerce")
    df = df.copy()
    bad = d.isna()
    df = reject(df, bad, table, key, "MonthStart", "invalid_date", lambda r: f"'{r['MonthStart']}' is not a valid date")
    d = d[~bad]
    notfirst = d.dt.day != 1
    for i in df.index[notfirst]:
        add(table, df.at[i, key], "MonthStart", "date_not_month_start",
            f"{df.at[i, 'MonthStart']} -> first of month", "Corrected")
    df["MonthStart"] = d.dt.to_period("M").dt.to_timestamp()
    return reject(df, ~df["MonthStart"].isin(valid_months), table, key, "MonthStart", "date_out_of_range",
                  "Month outside the 24-month reporting window")


def prep_fact(name, key, id_pat, loc_ids, cat_ids, valid_months):
    raw = read(name)
    stats[name] = {"raw": len(raw)}
    df = dedupe(raw, name, key)
    df = check_required(df, name, key, [key, "LocationID", "MonthStart"] + (["CategoryID"] if cat_ids is not None else []))
    df = tidy_text(df, name, key, "LocationID", "id")
    if cat_ids is not None:
        df = tidy_text(df, name, key, "CategoryID", "id")
    df = check_id(df, name, key, key, id_pat)
    df = reject(df, ~df["LocationID"].isin(loc_ids), name, key, "LocationID", "orphan_foreign_key",
                lambda r: f"LocationID '{r['LocationID']}' not in dim_location")
    if cat_ids is not None:
        df = reject(df, ~df["CategoryID"].isin(cat_ids), name, key, "CategoryID", "orphan_foreign_key",
                    lambda r: f"CategoryID '{r['CategoryID']}' not in dim_cost_category")
    return parse_month(df, name, key, valid_months)


def gap_fill(df, name, id_prefix, id_col, loc_ids, months, cat_ids, value_cols, int_cols=()):
    """Rebuild the full location x month (x category) grid, interpolate missing values, flag them."""
    nat = ["LocationID", "MonthStart"] + (["CategoryID"] if cat_ids is not None else [])
    before = len(df)
    nk = df.duplicated(subset=nat, keep="first")
    for i in df.index[nk]:
        add(name, df.at[i, id_col], "+".join(nat), "duplicate_natural_key", "Same location/month/category twice", "Removed")
    df = df[~nk]
    parts = [loc_ids, months] + ([cat_ids] if cat_ids is not None else [])
    grid = pd.MultiIndex.from_product(parts, names=nat).to_frame(index=False)
    out = grid.merge(df.drop(columns=[id_col]), on=nat, how="left")
    out["DataQualityFlag"] = np.where(out[value_cols].isna().any(axis=1), "Imputed", "OK")
    group = [c for c in nat if c != "MonthStart"]
    out = out.sort_values(group + ["MonthStart"]).reset_index(drop=True)
    for c in value_cols:
        out[c] = out.groupby(group)[c].transform(lambda s: s.interpolate(limit=2, limit_direction="both"))
    if out[value_cols].isna().any().any():
        raise SystemExit(f"{name}: gaps longer than 2 consecutive months cannot be imputed")
    for c in int_cols:
        out[c] = out[c].round().astype(int)
    for c in value_cols:
        if c not in int_cols:
            out[c] = out[c].round(2 if "INR" in c else 1)
    out = out.sort_values(["MonthStart", "LocationID"] + (["CategoryID"] if cat_ids is not None else []))
    out.insert(0, id_col, [f"{id_prefix}{i + 1:04d}" for i in range(len(out))])
    stats[name].update(after_dedupe=before, grid_cells=len(grid), rows_added=len(grid) - len(df),
                       imputed=int((out["DataQualityFlag"] == "Imputed").sum()), clean=len(out))
    return out.reset_index(drop=True)


# ---------------------------------------------------------------- dimensions
dloc = read("dim_location"); stats["dim_location"] = {"raw": len(dloc)}
dloc = dedupe(dloc, "dim_location", "LocationID")
dloc = check_required(dloc, "dim_location", "LocationID",
                      ["LocationID", "OfficeName", "City", "Country", "Region", "OwnershipType",
                       "FloorAreaM2", "UsableAreaM2", "Desks"])
dloc = tidy_text(dloc, "dim_location", "LocationID", "LocationID", "id")
dloc = tidy_text(dloc, "dim_location", "LocationID", "City", "title")
dloc = check_id(dloc, "dim_location", "LocationID", "LocationID", r"LOC\d{2}")
for c in ["FloorAreaM2", "UsableAreaM2", "Desks"]:
    dloc = check_numeric(dloc, "dim_location", "LocationID", c, quarantine_rows=True)
    dloc = reject(dloc, dloc[c] <= 0, "dim_location", "LocationID", c, "negative_value", f"{c} must be > 0")
dloc = reject(dloc, dloc["UsableAreaM2"] > dloc["FloorAreaM2"], "dim_location", "LocationID", "UsableAreaM2",
              "area_inconsistency", "Usable area exceeds floor area")
exp_region = dloc["Country"].map(COUNTRY_REGION)
mism = dloc["Region"] != exp_region
for i in dloc.index[mism]:
    add("dim_location", dloc.at[i, "LocationID"], "Region", "region_country_mismatch",
        f"{dloc.at[i, 'Country']}: '{dloc.at[i, 'Region']}' -> '{exp_region[i]}'", "Corrected")
dloc["Region"] = exp_region
for c in ["FloorAreaM2", "UsableAreaM2", "Desks"]:
    dloc[c] = dloc[c].astype(int)
dloc = dloc.sort_values("LocationID").reset_index(drop=True)
stats["dim_location"]["clean"] = len(dloc)

dcat = read("dim_cost_category"); stats["dim_cost_category"] = {"raw": len(dcat), "clean": len(dcat)}
ddate = read("dim_date"); stats["dim_date"] = {"raw": len(ddate), "clean": len(ddate)}
for c in ["Year", "MonthNumber", "FiscalMonthNumber"]:
    ddate[c] = ddate[c].astype(int)
months = pd.to_datetime(ddate["MonthStart"])
loc_ids, cat_ids = list(dloc["LocationID"]), list(dcat["CategoryID"])
desks_of = dict(zip(dloc["LocationID"], dloc["Desks"]))

# ---------------------------------------------------------------- budget (first: used to test actuals)
bud = prep_fact("fact_budget", "BudgetID", r"BD\d{4}", loc_ids, cat_ids, set(months))
bud = check_numeric(bud, "fact_budget", "BudgetID", "BudgetINR")
bud = gap_fill(bud, "fact_budget", "BD", "BudgetID", loc_ids, months, cat_ids, ["BudgetINR"])

# ---------------------------------------------------------------- space usage
use = prep_fact("fact_space_usage", "UsageID", r"SU\d{4}", loc_ids, None, set(months))
for c in ["Headcount", "AvgDailyOccupiedDesks", "ElectricityKWh"]:
    use = check_numeric(use, "fact_space_usage", "UsageID", c)
over = use["AvgDailyOccupiedDesks"] > use["LocationID"].map(desks_of)
for i in use.index[over]:
    add("fact_space_usage", use.at[i, "UsageID"], "AvgDailyOccupiedDesks", "occupied_exceeds_desks",
        f"{use.at[i, 'AvgDailyOccupiedDesks']:.0f} occupied > {desks_of[use.at[i, 'LocationID']]} desks",
        "Value rejected (imputed later)")
use.loc[over, "AvgDailyOccupiedDesks"] = np.nan
use = gap_fill(use, "fact_space_usage", "SU", "UsageID", loc_ids, months, None,
               ["Headcount", "AvgDailyOccupiedDesks", "ElectricityKWh"], int_cols=("Headcount", "AvgDailyOccupiedDesks"))

# ---------------------------------------------------------------- operating cost actuals
opx = prep_fact("fact_opex", "OpexID", r"OC\d{4}", loc_ids, cat_ids, set(months))
opx = check_numeric(opx, "fact_opex", "OpexID", "ActualCostINR")
ratio = opx.merge(bud[["LocationID", "MonthStart", "CategoryID", "BudgetINR"]],
                  on=["LocationID", "MonthStart", "CategoryID"], how="left")
r = (ratio["ActualCostINR"] / ratio["BudgetINR"]).values
bad = (r > OUTLIER_HI) | (r < OUTLIER_LO)
for i in np.where(bad)[0]:
    add("fact_opex", opx.iloc[i]["OpexID"], "ActualCostINR", "outlier_vs_budget",
        f"Actual {opx.iloc[i]['ActualCostINR']:,.0f} is {r[i]:.1f}x budget (allowed {OUTLIER_LO}-{OUTLIER_HI}x)",
        "Value rejected (imputed later)")
opx.loc[opx.index[bad], "ActualCostINR"] = np.nan
opx = gap_fill(opx, "fact_opex", "OC", "OpexID", loc_ids, months, cat_ids, ["ActualCostINR"])

# ---------------------------------------------------------------- projects
T = "fact_projects"
prj = read(T); stats[T] = {"raw": len(prj)}
prj = dedupe(prj, T, "ProjectID")
prj = check_required(prj, T, "ProjectID", ["ProjectID", "LocationID", "ProjectName", "ProjectType", "OwnerName",
                                           "StartDate", "DeadlineDate", "BudgetINR", "ActualCostINR",
                                           "PercentComplete", "Status", "RiskLevel"])
prj = tidy_text(prj, T, "ProjectID", "LocationID", "id")
prj = check_id(prj, T, "ProjectID", "ProjectID", r"PRJ\d{3}")
prj = reject(prj, ~prj["LocationID"].isin(loc_ids), T, "ProjectID", "LocationID", "orphan_foreign_key",
             lambda r: f"LocationID '{r['LocationID']}' not in dim_location")
for c in ["StartDate", "DeadlineDate", "CompletionDate"]:
    d = pd.to_datetime(prj[c], format="%Y-%m-%d", errors="coerce")
    prj = reject(prj, prj[c].notna() & d.isna(), T, "ProjectID", c, "invalid_date", lambda r, c=c: f"'{r[c]}' invalid")
    prj[c] = pd.to_datetime(prj[c], format="%Y-%m-%d", errors="coerce")
for c in ["BudgetINR", "ActualCostINR", "PercentComplete"]:
    prj = check_numeric(prj, T, "ProjectID", c, quarantine_rows=True)
prj = reject(prj, prj["DeadlineDate"] < prj["StartDate"], T, "ProjectID", "DeadlineDate", "date_order",
             "Deadline is before start date")
prj = reject(prj, ~prj["Status"].isin(STATUSES) | ~prj["RiskLevel"].isin(RISKS), T, "ProjectID", "Status",
             "invalid_category_value", "Status or RiskLevel not in allowed list")
inconsistent = (
    ~prj["PercentComplete"].between(0, 100)
    | ((prj["Status"] == "Completed") & ((prj["PercentComplete"] != 100) | prj["CompletionDate"].isna()))
    | ((prj["Status"] != "Completed") & prj["CompletionDate"].notna())
    | ((prj["Status"] == "Not Started") & (prj["PercentComplete"] > 0))
)
prj = reject(prj, inconsistent, T, "ProjectID", "Status", "status_inconsistency",
             lambda r: f"Status '{r['Status']}' conflicts with PercentComplete/CompletionDate")
prj["PercentComplete"] = prj["PercentComplete"].astype(int)
prj = prj.sort_values("ProjectID").reset_index(drop=True)
stats[T]["clean"] = len(prj)

# ---------------------------------------------------------------- plausibility warnings (not errors)
el = opx[opx.CategoryID == "CC01"].merge(use[["LocationID", "MonthStart", "ElectricityKWh"]],
                                         on=["LocationID", "MonthStart"])
el["tariff"] = el["ActualCostINR"] / el["ElectricityKWh"]
for r_ in el[(el.tariff < 5) | (el.tariff > 40)].itertuples():
    add("fact_opex", r_.OpexID, "ActualCostINR", "implausible_tariff",
        f"Implied tariff {r_.tariff:.1f} INR/kWh outside 5-40", "Flagged only", "Warning")

# ---------------------------------------------------------------- write clean tables
def out(df, name, dates=()):
    df = df.copy()
    for c in dates:
        df[c] = pd.to_datetime(df[c]).dt.strftime("%Y-%m-%d")
    df.to_csv(CLEAN / f"{name}.csv", index=False)


out(dloc, "dim_location"); out(dcat, "dim_cost_category"); out(ddate, "dim_date")
out(use, "fact_space_usage", ["MonthStart"]); out(opx, "fact_opex", ["MonthStart"])
out(bud, "fact_budget", ["MonthStart"])
out(prj, "fact_projects", ["StartDate", "DeadlineDate", "CompletionDate"])

fdf = pd.DataFrame(findings)
fdf.to_csv(QUAL / "issues_detected.csv", index=False)
pd.DataFrame(quarantine).to_csv(QUAL / "quarantined_rows.csv", index=False)

# ---------------------------------------------------------------- integrity tests on CLEAN output
checks = []


def test(name, ok):
    checks.append((name, bool(ok)))


tables = {"dim_location": dloc, "fact_space_usage": use, "fact_opex": opx, "fact_budget": bud, "fact_projects": prj}
keys = {"dim_location": "LocationID", "fact_space_usage": "UsageID", "fact_opex": "OpexID",
        "fact_budget": "BudgetID", "fact_projects": "ProjectID"}
for n, df in tables.items():
    test(f"{n}: primary key unique", df[keys[n]].is_unique)
    req = [c for c in df.columns if c != "CompletionDate"]
    test(f"{n}: no blank required fields", not df[req].isna().any().any())
for n in ["fact_space_usage", "fact_opex", "fact_budget", "fact_projects"]:
    test(f"{n}: every LocationID exists in dim_location", tables[n]["LocationID"].isin(loc_ids).all())
for n in ["fact_opex", "fact_budget"]:
    test(f"{n}: every CategoryID exists in dim_cost_category", tables[n]["CategoryID"].isin(cat_ids).all())
    test(f"{n}: every MonthStart exists in dim_date", tables[n]["MonthStart"].isin(months).all())
    test(f"{n}: one row per location x month x category",
         len(tables[n]) == len(loc_ids) * len(months) * len(cat_ids)
         and not tables[n].duplicated(["LocationID", "MonthStart", "CategoryID"]).any())
test("fact_space_usage: one row per location x month",
     len(use) == len(loc_ids) * len(months) and not use.duplicated(["LocationID", "MonthStart"]).any())
test("No negative costs or budgets", (opx.ActualCostINR >= 0).all() and (bud.BudgetINR >= 0).all()
     and (prj.BudgetINR >= 0).all() and (prj.ActualCostINR >= 0).all())
test("Occupied desks never exceed desks", (use.AvgDailyOccupiedDesks <= use.LocationID.map(desks_of)).all())
test("Usable area <= floor area for every office", (dloc.UsableAreaM2 <= dloc.FloorAreaM2).all())
test("Region consistent with Country", (dloc.Region == dloc.Country.map(COUNTRY_REGION)).all())
test("Project deadline >= start date", (prj.DeadlineDate >= prj.StartDate).all())
done = prj.Status == "Completed"
test("Completed projects are 100% with a completion date; others have none",
     (prj.loc[done, "PercentComplete"] == 100).all() and prj.loc[done, "CompletionDate"].notna().all()
     and prj.loc[~done, "CompletionDate"].isna().all())

# ---------------------------------------------------------------- injected-issue detection test
injected = pd.read_csv(RAW / "injected_issues_log.csv", dtype=str, keep_default_na=False)
seen = set(zip(fdf.Table, fdf.RecordKey, fdf.Rule))
injected["Detected"] = [(t, k, r) in seen for t, k, r in zip(injected.Table, injected.RecordKey, injected.ExpectedRule)]
test(f"All {len(injected)} injected issues were detected", injected["Detected"].all())
expected_set = set(zip(injected.Table, injected.RecordKey, injected.ExpectedRule))
extra = fdf[(fdf.Severity == "Error") & ~pd.Series(list(zip(fdf.Table, fdf.RecordKey, fdf.Rule))).isin(expected_set).values]
test("No unexpected error findings (no false positives)", extra.empty)

# ---------------------------------------------------------------- plausibility ranges on CLEAN data
u = use.merge(dloc, on="LocationID")
u["util"] = u.AvgDailyOccupiedDesks / u.Desks
u["kwh_m2"] = u.ElectricityKWh / u.FloorAreaM2
c = opx.merge(dloc[["LocationID", "FloorAreaM2", "Region"]], on="LocationID")
opex_m2 = c.groupby(["LocationID", "MonthStart", "Region"], as_index=False).agg(cost=("ActualCostINR", "sum"), a=("FloorAreaM2", "first"))
opex_m2["per_m2"] = opex_m2.cost / opex_m2.a
ab = (opx.ActualCostINR / bud.BudgetINR)
ranges = [
    ("Desk utilisation (occupied / desks)", u.util.min(), u.util.max(), 0.2, 0.95),
    ("Headcount per desk", (u.Headcount / u.Desks).min(), (u.Headcount / u.Desks).max(), 0.5, 1.5),
    ("Floor area per desk (m2)", (u.FloorAreaM2 / u.Desks).min(), (u.FloorAreaM2 / u.Desks).max(), 8, 20),
    ("Electricity kWh per m2 per month", u.kwh_m2.min(), u.kwh_m2.max(), 3, 25),
    ("Implied electricity tariff (INR/kWh)", el.tariff.min(), el.tariff.max(), 5, 40),
    ("Total opex INR per m2 per month", opex_m2.per_m2.min(), opex_m2.per_m2.max(), 100, 1000),
    ("Actual / budget ratio (row level)", ab.min(), ab.max(), 0.7, 1.5),
]
for label, lo, hi, a, b in ranges:
    test(f"Plausible range: {label} within {a}-{b}", a <= lo and hi <= b)

passed = all(ok for _, ok in checks)


# ---------------------------------------------------------------- report
def md_table(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(x).replace("|", "/") for x in row) + " |")
    return "\n".join(lines)


summ = pd.DataFrame([
    dict(Table=n, RawRows=s.get("raw", ""), CleanRows=s.get("clean", ""),
         ImputedRows=s.get("imputed", 0), RowsRebuiltByGridFill=s.get("rows_added", 0))
    for n, s in stats.items()])
qcount = pd.DataFrame(quarantine)
by_rule = fdf.groupby(["Table", "Rule", "Severity", "Action"]).size().reset_index(name="Count")
rep = [
    "# Data Quality Report", "",
    "Generated by `scripts/validate_and_clean.py` from `data/raw/` (synthetic data with deliberately injected issues).",
    f"Overall result: **{'PASS' if passed else 'FAIL'}** ({sum(ok for _, ok in checks)}/{len(checks)} checks passed).", "",
    "## 1. Row counts", "", md_table(summ), "",
    f"Quarantined raw rows: **{len(qcount)}** (see `data/quality/quarantined_rows.csv`). "
    "*RowsRebuiltByGridFill* = location/month/category cells with no valid raw row, recreated by interpolation and flagged `Imputed`.", "",
    "## 2. Findings by rule", "", md_table(by_rule), "",
    "## 3. Every finding", "", md_table(fdf[["Table", "RecordKey", "Column", "Rule", "Severity", "Detail", "Action"]]), "",
    "## 4. Injected issues vs. detected", "",
    md_table(injected[["IssueID", "Table", "RecordKey", "ExpectedRule", "Detected"]]), "",
    "## 5. Cleaning decisions", "",
    "| Situation | Decision | Why |", "|---|---|---|",
    "| Spaces / case in IDs or city names | Corrected | Meaning is unambiguous |",
    "| Mid-month date in a monthly table | Normalised to first of month | Tables are monthly grain |",
    "| Region contradicts Country | Region derived from Country | Country is the more specific fact |",
    "| Exact duplicate row | First copy kept | No information lost |",
    "| Same key, different values | All copies quarantined | Cannot know which is right |",
    "| Unknown LocationID / invalid date | Row quarantined | Cannot be linked to a valid location/month |",
    "| Blank, negative or outlier monthly value | Set to missing, linearly interpolated within the location (+category) series, row flagged `Imputed` | Keeps month totals complete; interpolation is a transparent estimate, not an actual |",
    f"| Actual > {OUTLIER_HI}x or < {OUTLIER_LO}x budget | Treated as outlier (likely decimal error) | Band chosen for this synthetic data; real thresholds need business input |",
    "| Occupied desks > desks available | Value rejected and imputed | Physically impossible |",
    "| Project row failing any check | Quarantined, not imputed | Project facts cannot be estimated safely |", "",
    "Imputed rows keep `DataQualityFlag = 'Imputed'` so reports can exclude or highlight them. "
    "Primary keys in the clean fact tables are re-issued sequentially after cleaning.", "",
    "## 6. Integrity and plausibility tests on the CLEAN data", "",
    md_table(pd.DataFrame([(n, "PASS" if ok else "FAIL") for n, ok in checks], columns=["Test", "Result"])), "",
    "## 7. Limitations", "",
    "- Data is synthetic; ranges are plausible but not benchmarked against real portfolios.",
    "- Interpolation can hide genuine spikes; in real work missing values would be chased with the source owner.",
    "- Validation rules cover the issue types listed above, not every conceivable error.",
]
(DOCS / "data_quality_report.md").write_text("\n".join(rep) + "\n")

print(summ.to_string(index=False))
print(f"\nFindings: {len(fdf)}  | Quarantined rows: {len(qcount)}")
for n, ok in checks:
    print(("PASS  " if ok else "FAIL  ") + n)
print("\nRESULT:", "ALL CHECKS PASSED" if passed else "SOME CHECKS FAILED")
sys.exit(0 if passed else 1)
