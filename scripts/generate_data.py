#!/usr/bin/env python3
"""
Generate the SYNTHETIC raw datasets for the
Corporate Real Estate Portfolio & Workplace Performance Analytics project.

* Entirely fictional data: office names, owners and numbers are invented.
  Nothing here is real company data.
* Reproducible: a fixed random seed means every run gives identical files.
* Output goes to data/raw/ and contains a small number of DELIBERATE data
  quality issues. Every one is recorded in data/raw/injected_issues_log.csv
  and docs/injected_issues.md. The clean dataset is produced separately by
  scripts/validate_and_clean.py.

Run from the project root:   python scripts/generate_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DOCS = ROOT / "docs"

START = "2024-10-01"          # first month  (FY25 starts in Oct, assumption)
N_MONTHS = 24                 # Oct 2024 - Sep 2026
AS_OF = pd.Timestamp("2026-09-30")   # reporting "as of" date for project status

rng = np.random.default_rng(SEED)
months = pd.date_range(START, periods=N_MONTHS, freq="MS")

# --------------------------------------------------------------------------
# Reference tables
# --------------------------------------------------------------------------
# id, office, city, country, region, ownership, gross m2, usable ratio,
# m2 per desk, headcount/desk ratio, base attendance, kWh/m2/month, tariff INR/kWh
LOCATIONS = [
    ("LOC01", "Gurugram Regional Office",   "Gurugram",  "India",          "India", "Leased", 16500, .79,  9.5, 1.05, .62, 11.0,  9.2),
    ("LOC02", "Mumbai Business Hub",        "Mumbai",    "India",          "India", "Leased", 12800, .76,  9.0, 1.10, .60, 11.0, 11.5),
    ("LOC03", "Bengaluru Technology Centre","Bengaluru", "India",          "India", "Owned",  24000, .80,  9.8, 0.98, .66, 10.5,  8.4),
    ("LOC04", "Pune Operations Campus",     "Pune",      "India",          "India", "Owned",  21000, .82, 10.2, 0.92, .55, 11.0,  8.8),
    ("LOC05", "Chennai Service Office",     "Chennai",   "India",          "India", "Leased",  7200, .74,  9.2, 0.80, .42, 11.5,  8.0),
    ("LOC06", "Singapore Regional Office",  "Singapore", "Singapore",      "APAC",  "Leased",  5200, .77,  8.8, 1.15, .58,  9.5, 22.0),
    ("LOC07", "Shanghai Engineering Office","Shanghai",  "China",          "APAC",  "Leased",  9800, .78,  9.4, 1.00, .57,  9.5,  9.8),
    ("LOC08", "Sydney Sales Office",        "Sydney",    "Australia",      "APAC",  "Leased",  3400, .75,  9.0, 0.95, .52,  9.0, 24.0),
    ("LOC09", "Erlangen Technology Centre", "Erlangen",  "Germany",        "Europe","Owned",  28000, .81, 10.5, 0.90, .54,  8.5, 20.5),
    ("LOC10", "Berlin Project Office",      "Berlin",    "Germany",        "Europe","Leased",  8800, .77,  9.6, 1.00, .50,  8.0, 23.0),
    ("LOC11", "Warsaw Shared Services",     "Warsaw",    "Poland",         "Europe","Leased",  6400, .76,  8.6, 1.20, .64,  8.5, 17.5),
    ("LOC12", "London Commercial Office",   "London",    "United Kingdom", "Europe","Leased",  4600, .74,  9.0, 0.85, .48,  8.0, 25.0),
]
# Designed scenarios (documented, so later insights are not "discovered by magic"):
#   LOC04 Pune  : older HVAC -> electricity ~31% above plan; HVAC project late, spend ahead of progress
#   LOC05 Chennai: deliberately low desk utilisation (~35%)
#   LOC11 Warsaw : facility-management cost ~8.5% above budget (10% bias before noise)
ENERGY_FACTOR = {"LOC04": 1.30}
COST_BIAS = {("LOC11", "CC04"): 1.10}

CATEGORIES = [
    ("CC01", "Electricity",            "Utilities",         "Metered electricity consumption"),
    ("CC02", "Water & Other Utilities","Utilities",         "Water, sewage and other metered utilities"),
    ("CC03", "Maintenance",            "Maintenance",       "Planned and reactive building maintenance"),
    ("CC04", "Facility Management",    "Facility Services", "Cleaning, reception, helpdesk and soft services"),
    ("CC05", "Security",               "Facility Services", "Guarding, CCTV monitoring and access control"),
]
# Base cost rates, INR per gross m2 per month (assumed constant FX; synthetic)
RATES = {  # region: (water, maintenance, FM services, security)
    "India":  (9, 42, 85, 30),
    "APAC":   (17, 105, 210, 70),
    "Europe": (22, 120, 260, 85),
}
CAT_IDS = ["CC02", "CC03", "CC04", "CC05"]

loc_df = pd.DataFrame(
    [(l[0], l[1], l[2], l[3], l[4], l[5], l[6], round(l[6] * l[7])) for l in LOCATIONS],
    columns=["LocationID", "OfficeName", "City", "Country", "Region",
             "OwnershipType", "FloorAreaM2", "UsableAreaM2"],
)
loc_df["Desks"] = [round(l[6] * l[7] / l[8]) for l in LOCATIONS]

cat_df = pd.DataFrame(CATEGORIES, columns=["CategoryID", "CategoryName", "CostGroup", "Description"])

fy = np.where(months.month >= 10, months.year + 1, months.year)
fm = (months.month - 10) % 12 + 1
date_df = pd.DataFrame({
    "MonthStart": months.strftime("%Y-%m-%d"),
    "Year": months.year,
    "MonthNumber": months.month,
    "MonthName": months.strftime("%b"),
    "YearMonth": months.strftime("%Y-%m"),
    "Quarter": ["Q" + str((m - 1) // 3 + 1) for m in months.month],
    "FiscalYear": ["FY" + str(y)[-2:] for y in fy],
    "FiscalQuarter": ["FQ" + str((m - 1) // 3 + 1) for m in fm],
    "FiscalMonthNumber": fm,
})

# --------------------------------------------------------------------------
# Monthly fact tables
# --------------------------------------------------------------------------
def elec_season(region, m):
    if region == "India":
        return 1 + 0.22 * np.cos(2 * np.pi * (m - 5) / 12)    # summer cooling peak
    if region == "Europe":
        return 1 + 0.12 * np.cos(2 * np.pi * (m - 1) / 12)    # winter peak
    return 1 + 0.10 * np.cos(2 * np.pi * (m - 7) / 12)


def attendance_season(m):
    return {12: 0.88, 8: 0.94, 1: 0.96, 10: 0.97}.get(m, 1.0)


loc_eff = {l[0]: ENERGY_FACTOR.get(l[0], round(rng.uniform(0.97, 1.07), 3)) for l in LOCATIONS}
loc_mult = {(l[0], c): round(rng.uniform(0.90, 1.10), 3) for l in LOCATIONS for c in CAT_IDS}

usage_rows, opex_rows, budget_rows = [], [], []
for l, d in zip(LOCATIONS, loc_df.itertuples()):
    lid, region = l[0], l[4]
    gross, desks = l[6], d.Desks
    base_hc = desks * l[9]
    for t, ms in enumerate(months):
        m = ms.month
        hc = int(round(base_hc * (1 + 0.0015 * t) * (1 + rng.normal(0, 0.008))))
        att = float(np.clip(l[10] * (1 + 0.002 * t) * attendance_season(m) + rng.normal(0, 0.02), 0.2, 0.9))
        occ = min(int(round(hc * att)), desks)
        util = occ / desks
        season = elec_season(region, m)
        esc = 1.04 ** (t / 12)                                   # 4% p.a. cost escalation
        kwh = gross * l[11] * season * loc_eff[lid] * (0.88 + 0.24 * util) * rng.lognormal(0, 0.025)
        kwh_plan = gross * l[11] * season * rng.uniform(0.97, 1.03)
        tariff = l[12] * esc
        usage_rows.append((lid, ms, hc, occ, round(kwh, 1)))
        opex_rows.append((lid, ms, "CC01", round(kwh * tariff * (1 + rng.normal(0, 0.02)), 2)))
        budget_rows.append((lid, ms, "CC01", round(kwh_plan * tariff, 2)))
        for cid, rate in zip(CAT_IDS, RATES[region]):
            season_c = (1 + 0.10 * np.cos(2 * np.pi * (m - 5) / 12)) if (cid == "CC02" and region == "India") else 1.0
            expected = gross * rate * loc_mult[(lid, cid)] * esc * season_c
            bias = COST_BIAS.get((lid, cid), 1.01)
            opex_rows.append((lid, ms, cid, round(expected * bias * (1 + rng.normal(0, 0.04)), 2)))
            budget_rows.append((lid, ms, cid, round(expected * rng.uniform(0.97, 1.03), 2)))


def finish(rows, cols, prefix):
    df = pd.DataFrame(rows, columns=cols)
    df["MonthStart"] = df["MonthStart"].dt.strftime("%Y-%m-%d")
    df = df.sort_values(["MonthStart", "LocationID"] + (["CategoryID"] if "CategoryID" in cols else []),
                        kind="stable").reset_index(drop=True)
    df.insert(0, prefix[0], [f"{prefix[1]}{i + 1:04d}" for i in range(len(df))])
    return df


usage_df = finish(usage_rows, ["LocationID", "MonthStart", "Headcount", "AvgDailyOccupiedDesks", "ElectricityKWh"],
                  ("UsageID", "SU"))
opex_df = finish(opex_rows, ["LocationID", "MonthStart", "CategoryID", "ActualCostINR"], ("OpexID", "OC"))
budget_df = finish(budget_rows, ["LocationID", "MonthStart", "CategoryID", "BudgetINR"], ("BudgetID", "BD"))
usage_df["Headcount"] = usage_df["Headcount"].astype("Int64")
usage_df["AvgDailyOccupiedDesks"] = usage_df["AvgDailyOccupiedDesks"].astype("Int64")

# --------------------------------------------------------------------------
# Improvement projects (30)
# --------------------------------------------------------------------------
PROJECT_TYPES = {  # type: (min budget, max budget) in INR for an India office
    "LED Lighting Retrofit": (2_500_000, 8_000_000),
    "HVAC Upgrade": (12_000_000, 35_000_000),
    "Space Reconfiguration": (5_000_000, 15_000_000),
    "Smart Metering": (1_500_000, 4_000_000),
    "Meeting Room Refresh": (2_000_000, 6_000_000),
    "Fire Safety Compliance": (3_000_000, 9_000_000),
    "Access Control Upgrade": (2_000_000, 5_000_000),
    "Pantry Refurbishment": (1_000_000, 3_000_000),
}
OWNERS = {  # fictional names
    "India": ["Ananya Rao", "Rohan Iyer", "Meera Nair", "Karan Malhotra"],
    "APAC": ["Wei Lin", "Priya Menon", "Daniel Foster"],
    "Europe": ["Lena Fischer", "Tomasz Nowak", "Clara Jensen"],
}
city_of = dict(zip(loc_df.LocationID, loc_df.City))
region_of = dict(zip(loc_df.LocationID, loc_df.Region))

specs = []
for _ in range(29):
    lid = str(rng.choice(loc_df.LocationID))
    ptype = str(rng.choice(list(PROJECT_TYPES)))
    start = pd.Timestamp("2024-10-01") + pd.Timedelta(days=int(rng.integers(0, 760)))
    specs.append((lid, ptype, start, int(rng.integers(90, 300))))
# forced scenario: Pune HVAC upgrade, past deadline and spending ahead of progress (still under total budget)
specs.append(("LOC04", "HVAC Upgrade", pd.Timestamp("2025-12-01"), 210))
specs.sort(key=lambda s: s[2])

proj_rows, seen_names = [], {}
for i, (lid, ptype, start, dur) in enumerate(specs, start=1):
    lo, hi = PROJECT_TYPES[ptype]
    budget = round(rng.uniform(lo, hi) * (1.0 if region_of[lid] == "India" else 1.5), -4)
    deadline = start + pd.Timedelta(days=dur)
    forced = (lid == "LOC04" and ptype == "HVAC Upgrade" and start == pd.Timestamp("2025-12-01"))
    if forced:
        status, pct, actual = "In Progress", 70, round(budget * 0.70 * 1.28, -3)
        completion = None
    elif start > AS_OF:
        status, pct, actual, completion = "Not Started", 0, 0.0, None
    else:
        if deadline < AS_OF:
            status = str(rng.choice(["Completed", "In Progress", "On Hold"], p=[.82, .12, .06]))
        else:
            status = str(rng.choice(["In Progress", "On Hold"], p=[.92, .08]))
        if status == "Completed":
            pct = 100
            completion = min(deadline + pd.Timedelta(days=int(rng.integers(-15, 46))), AS_OF)
            completion = max(completion, start + pd.Timedelta(days=30))
            actual = round(budget * rng.uniform(0.90, 1.25), -3)
        else:
            completion = None
            if deadline < AS_OF:
                pct = int(rng.integers(60, 91))
            else:
                elapsed = (AS_OF - start).days / max((deadline - start).days, 1)
                pct = int(np.clip(round(elapsed * 100 + rng.normal(-8, 10)), 5, 95))
            actual = round(budget * pct / 100 * rng.uniform(0.90, 1.30), -3)
    overdue = status in ("In Progress", "On Hold") and deadline < AS_OF
    base_pct = max(pct, 1) / 100 if status != "Completed" else 1.0
    ratio = (actual / (budget * base_pct)) if status != "Not Started" else 0.0
    risk = "High" if (overdue or ratio > 1.15) else ("Medium" if (ratio > 1.05 or status == "On Hold") else "Low")
    name = f"{ptype} - {city_of[lid]}"
    seen_names[name] = seen_names.get(name, 0) + 1
    if seen_names[name] > 1:
        name += f" (Phase {seen_names[name]})"
    proj_rows.append((f"PRJ{i:03d}", lid, name, ptype, str(rng.choice(OWNERS[region_of[lid]])),
                      start.strftime("%Y-%m-%d"), deadline.strftime("%Y-%m-%d"),
                      completion.strftime("%Y-%m-%d") if completion is not None else None,
                      budget, actual, pct, status, risk))
proj_df = pd.DataFrame(proj_rows, columns=[
    "ProjectID", "LocationID", "ProjectName", "ProjectType", "OwnerName", "StartDate", "DeadlineDate",
    "CompletionDate", "BudgetINR", "ActualCostINR", "PercentComplete", "Status", "RiskLevel"])

# --------------------------------------------------------------------------
# Deliberate data-quality issues -> RAW copies only
# --------------------------------------------------------------------------
issues = []
used = {k: set() for k in ["dim_location", "fact_space_usage", "fact_opex", "fact_budget", "fact_projects"]}


def pick(table, df, n=1, where=None):
    pool = [i for i in (df.index if where is None else df.index[where]) if i not in used[table]]
    chosen = [int(i) for i in rng.choice(pool, size=n, replace=False)]
    used[table].update(chosen)
    return chosen


def log(table, key, col, rule, kind, desc, orig, new, action):
    issues.append(dict(IssueID=f"ISS{len(issues) + 1:02d}", Table=table, RecordKey=key, Column=col,
                       ExpectedRule=rule, IssueType=kind, Description=desc,
                       OriginalValue=orig, InjectedValue=new, ExpectedAction=action))


# Keep the designed Pune HVAC scenario project clean so it survives into the clean dataset
used["fact_projects"].update(int(i) for i in proj_df.index[
    (proj_df.LocationID == "LOC04") & (proj_df.ProjectType == "HVAC Upgrade") & (proj_df.StartDate == "2025-12-01")])

raw_loc, raw_usage = loc_df.copy(), usage_df.copy()
raw_opex, raw_budget, raw_proj = opex_df.copy(), budget_df.copy(), proj_df.copy()

# --- dim_location --------------------------------------------------------
i = raw_loc.index[raw_loc.LocationID == "LOC04"][0]; used["dim_location"].add(i)
log("dim_location", "LOC04", "City", "text_formatting", "Inconsistent text",
    "City stored in lower case with stray spaces", "Pune", " pune ", "Corrected: trim and title-case")
raw_loc.at[i, "City"] = " pune "
i = raw_loc.index[raw_loc.LocationID == "LOC08"][0]; used["dim_location"].add(i)
log("dim_location", "LOC08", "Region", "region_country_mismatch", "Inconsistent relationship",
    "Region 'Europe' recorded for an Australian office", "APAC", "Europe", "Corrected: Region derived from Country")
raw_loc.at[i, "Region"] = "Europe"

# --- fact_space_usage ----------------------------------------------------
for i in pick("fact_space_usage", raw_usage, 2):
    k = raw_usage.at[i, "UsageID"]
    log("fact_space_usage", k, "Headcount", "missing_value", "Missing value", "Headcount left blank",
        str(raw_usage.at[i, "Headcount"]), "", "Imputed by interpolation, row flagged")
    raw_usage.at[i, "Headcount"] = pd.NA
i = pick("fact_space_usage", raw_usage)[0]
desks = int(loc_df.set_index("LocationID").at[raw_usage.at[i, "LocationID"], "Desks"])
new = desks + int(rng.integers(5, 40))
log("fact_space_usage", raw_usage.at[i, "UsageID"], "AvgDailyOccupiedDesks", "occupied_exceeds_desks",
    "Inconsistent relationship", f"Occupied desks ({new}) exceed desks available ({desks})",
    str(raw_usage.at[i, "AvgDailyOccupiedDesks"]), str(new), "Value rejected, imputed by interpolation, row flagged")
raw_usage.at[i, "AvgDailyOccupiedDesks"] = new

# --- fact_opex -----------------------------------------------------------
for i in pick("fact_opex", raw_opex, 2):
    log("fact_opex", raw_opex.at[i, "OpexID"], "ActualCostINR", "missing_value", "Missing value",
        "Actual cost left blank", str(raw_opex.at[i, "ActualCostINR"]), "", "Imputed by interpolation, row flagged")
    raw_opex.at[i, "ActualCostINR"] = np.nan
i = pick("fact_opex", raw_opex)[0]
v = raw_opex.at[i, "ActualCostINR"]
log("fact_opex", raw_opex.at[i, "OpexID"], "ActualCostINR", "negative_value", "Negative cost",
    "Cost recorded as negative", str(v), str(-v), "Value rejected, imputed by interpolation, row flagged")
raw_opex.at[i, "ActualCostINR"] = -v
i = pick("fact_opex", raw_opex, where=(raw_opex.CategoryID == "CC01"))[0]
v = raw_opex.at[i, "ActualCostINR"]
log("fact_opex", raw_opex.at[i, "OpexID"], "ActualCostINR", "outlier_vs_budget", "Outlier (decimal shift)",
    "Electricity cost 100x too large (decimal-point error)", str(v), str(round(v * 100, 2)),
    "Value rejected (actual/budget > 3), imputed, row flagged")
raw_opex.at[i, "ActualCostINR"] = round(v * 100, 2)
i = pick("fact_opex", raw_opex)[0]
log("fact_opex", raw_opex.at[i, "OpexID"], "LocationID", "orphan_foreign_key", "Invalid ID",
    "LocationID 'LOC99' does not exist in dim_location", raw_opex.at[i, "LocationID"], "LOC99",
    "Row quarantined; month/category cell gap-filled and flagged")
raw_opex.at[i, "LocationID"] = "LOC99"
i = pick("fact_opex", raw_opex)[0]
orig = raw_opex.at[i, "LocationID"]
log("fact_opex", raw_opex.at[i, "OpexID"], "LocationID", "text_formatting", "Inconsistent ID format",
    "LocationID in lower case with leading space", orig, " " + orig.lower(), "Corrected: trim and upper-case")
raw_opex.at[i, "LocationID"] = " " + orig.lower()
i = pick("fact_opex", raw_opex)[0]
orig = raw_opex.at[i, "MonthStart"]
log("fact_opex", raw_opex.at[i, "OpexID"], "MonthStart", "date_not_month_start", "Date not first of month",
    "Month recorded as mid-month date", orig, orig[:8] + "15", "Corrected: normalised to first of month")
raw_opex.at[i, "MonthStart"] = orig[:8] + "15"
i = pick("fact_opex", raw_opex)[0]                         # exact duplicate row
log("fact_opex", raw_opex.at[i, "OpexID"], "ALL", "duplicate_exact", "Exact duplicate row",
    "Entire row repeated", "1 row", "2 identical rows", "Removed: first copy kept")
dup_exact = raw_opex.loc[[i]]
i = pick("fact_opex", raw_opex)[0]                         # conflicting duplicate key
dup_conf = raw_opex.loc[[i]].copy()
dup_conf["ActualCostINR"] = round(dup_conf["ActualCostINR"] * 1.15, 2)
log("fact_opex", raw_opex.at[i, "OpexID"], "OpexID", "duplicate_conflict", "Duplicate key, conflicting values",
    "Same OpexID appears twice with different costs", str(raw_opex.at[i, "ActualCostINR"]),
    str(dup_conf["ActualCostINR"].iloc[0]), "Both copies quarantined; cell gap-filled and flagged")
raw_opex = pd.concat([raw_opex, dup_exact, dup_conf], ignore_index=True)

# --- fact_budget ---------------------------------------------------------
i = pick("fact_budget", raw_budget)[0]
log("fact_budget", raw_budget.at[i, "BudgetID"], "MonthStart", "invalid_date", "Invalid date",
    "Month '2025-13-01' is not a valid date", raw_budget.at[i, "MonthStart"], "2025-13-01",
    "Row quarantined; cell gap-filled and flagged")
raw_budget.at[i, "MonthStart"] = "2025-13-01"
i = pick("fact_budget", raw_budget)[0]
log("fact_budget", raw_budget.at[i, "BudgetID"], "ALL", "duplicate_exact", "Exact duplicate row",
    "Entire row repeated", "1 row", "2 identical rows", "Removed: first copy kept")
raw_budget = pd.concat([raw_budget, raw_budget.loc[[i]]], ignore_index=True)

# --- fact_projects -------------------------------------------------------
i = pick("fact_projects", raw_proj)[0]
s = pd.Timestamp(raw_proj.at[i, "StartDate"])
new = (s - pd.Timedelta(days=20)).strftime("%Y-%m-%d")
log("fact_projects", raw_proj.at[i, "ProjectID"], "DeadlineDate", "date_order", "Inconsistent dates",
    "Deadline is before the start date", raw_proj.at[i, "DeadlineDate"], new, "Row quarantined (cannot infer correct date)")
raw_proj.at[i, "DeadlineDate"] = new
i = pick("fact_projects", raw_proj, where=(raw_proj.Status == "Completed"))[0]
log("fact_projects", raw_proj.at[i, "ProjectID"], "PercentComplete", "status_inconsistency", "Inconsistent status",
    "Status 'Completed' but PercentComplete is 60", str(raw_proj.at[i, "PercentComplete"]), "60",
    "Row quarantined (status or progress is wrong; cannot tell which)")
raw_proj.at[i, "PercentComplete"] = 60
i = pick("fact_projects", raw_proj, where=(raw_proj.Status == "In Progress"))[0]
v = raw_proj.at[i, "BudgetINR"]
log("fact_projects", raw_proj.at[i, "ProjectID"], "BudgetINR", "negative_value", "Negative budget",
    "Project budget recorded as negative", str(v), str(-v), "Row quarantined")
raw_proj.at[i, "BudgetINR"] = -v

# --------------------------------------------------------------------------
# Write files
# --------------------------------------------------------------------------
RAW.mkdir(parents=True, exist_ok=True)
for name, df in [("dim_location", raw_loc), ("dim_cost_category", cat_df), ("dim_date", date_df),
                 ("fact_space_usage", raw_usage), ("fact_opex", raw_opex), ("fact_budget", raw_budget),
                 ("fact_projects", raw_proj)]:
    df.to_csv(RAW / f"{name}.csv", index=False)
issue_df = pd.DataFrame(issues)
issue_df.to_csv(RAW / "injected_issues_log.csv", index=False)

md = ["# Injected Data-Quality Issues (raw dataset only)", "",
      "These issues were added **deliberately** by `scripts/generate_data.py` into `data/raw/` to test the",
      "validation script. The files in `data/clean/` are produced by `scripts/validate_and_clean.py` and",
      "contain none of them. `dim_cost_category` and `dim_date` are reference tables with no injected issues.", "",
      f"Total injected issues: **{len(issue_df)}**", "",
      "| ID | Table | Record | Column | Rule | Description | Expected action |",
      "|---|---|---|---|---|---|---|"]
for r in issue_df.itertuples():
    md.append(f"| {r.IssueID} | {r.Table} | {r.RecordKey} | {r.Column} | `{r.ExpectedRule}` | "
              f"{r.Description} | {r.ExpectedAction} |")
DOCS.mkdir(exist_ok=True)
(DOCS / "injected_issues.md").write_text("\n".join(md) + "\n")

print(f"Raw data written to {RAW}")
for name, df in [("dim_location", raw_loc), ("fact_space_usage", raw_usage), ("fact_opex", raw_opex),
                 ("fact_budget", raw_budget), ("fact_projects", raw_proj)]:
    print(f"  {name:18s} {len(df):5d} rows")
print(f"  injected issues    {len(issue_df):5d}")
