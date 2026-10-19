# Data Dictionary

**Project:** Corporate Real Estate Portfolio & Workplace Performance Analytics Dashboard
**Data:** 100% synthetic. Office names, owners and all figures are invented. It is not data from any real company.

## Global assumptions

| Item | Assumption |
|---|---|
| Currency | INR. Offices outside India are expressed in INR at an assumed constant exchange rate (no FX effects modelled). |
| Area | Square metres (m²). `FloorAreaM2` is gross floor area; `UsableAreaM2` is net usable area. |
| Period | 24 months, Oct 2024 – Sep 2026, grain = calendar month (`MonthStart` = first day). |
| Fiscal year | Oct–Sep, labelled by end year (Oct 2024 – Sep 2025 = FY25). Assumption for this project. |
| As-of date | **30 Sep 2026**. Used for overdue-project logic (constant, not "today"). |
| Static attributes | Floor area, usable area and desks are fixed per office over the 24 months (no refurbishments modelled). |
| Seed | `42` in `scripts/generate_data.py`. Re-running gives identical raw files. |

## Layers

| Folder | Meaning |
|---|---|
| `data/raw/` | Synthetic export **with deliberate errors** (19, listed in `injected_issues_log.csv`). |
| `data/clean/` | Validated, cleaned tables. **This is what Excel / Power BI should load.** |
| `data/quality/` | `issues_detected.csv` (all findings), `quarantined_rows.csv` (raw rows removed). |

## Tables (clean layer)

Type notation: `text`, `int`, `decimal`, `date` (ISO `YYYY-MM-DD`). **PK** = primary key, **FK** = foreign key.

### dim_location (12 rows) – one row per office
| Column | Type | Rules / meaning |
|---|---|---|
| LocationID | text, PK | `LOC` + 2 digits |
| OfficeName | text | Fictional office name |
| City | text | Title case |
| Country | text | One of 7 countries |
| Region | text | `India`, `APAC` or `Europe`; must match Country |
| OwnershipType | text | `Owned` or `Leased` |
| FloorAreaM2 | int | Gross floor area, > 0 |
| UsableAreaM2 | int | Net usable area, > 0 and ≤ FloorAreaM2 |
| Desks | int | Desks available, > 0 |

### dim_cost_category (5 rows)
| Column | Type | Rules / meaning |
|---|---|---|
| CategoryID | text, PK | `CC01`–`CC05` |
| CategoryName | text | Electricity; Water & Other Utilities; Maintenance; Facility Management; Security |
| CostGroup | text | `Utilities`, `Maintenance` or `Facility Services` |
| Description | text | Free text |

### dim_date (24 rows) – monthly calendar
| Column | Type | Rules / meaning |
|---|---|---|
| MonthStart | date, PK | First day of month |
| Year, MonthNumber | int | Calendar year and month number |
| MonthName | text | `Jan`…`Dec` |
| YearMonth | text | `YYYY-MM` (sorts correctly) |
| Quarter | text | Calendar quarter `Q1`–`Q4` |
| FiscalYear | text | `FY25`, `FY26` |
| FiscalQuarter | text | `FQ1`–`FQ4` |
| FiscalMonthNumber | int | 1 = October … 12 = September |

### fact_space_usage (288 rows) – grain: location × month
| Column | Type | Rules / meaning |
|---|---|---|
| UsageID | text, PK | `SU` + 4 digits (surrogate, reissued during cleaning) |
| LocationID | text, FK → dim_location | |
| MonthStart | date, FK → dim_date | |
| Headcount | int | Employees assigned to the office |
| AvgDailyOccupiedDesks | int | Average desks in use per working day; ≤ Desks |
| ElectricityKWh | decimal | Metered electricity for the month, ≥ 0 |
| DataQualityFlag | text | `OK` or `Imputed` (any value estimated during cleaning) |

### fact_opex (1,440 rows) – grain: location × month × category
| Column | Type | Rules / meaning |
|---|---|---|
| OpexID | text, PK | `OC` + 4 digits (surrogate) |
| LocationID | text, FK → dim_location | |
| MonthStart | date, FK → dim_date | |
| CategoryID | text, FK → dim_cost_category | |
| ActualCostINR | decimal | Actual spend, ≥ 0 |
| DataQualityFlag | text | `OK` or `Imputed` |

### fact_budget (1,440 rows) – grain: location × month × category
Same shape as fact_opex; `BudgetID` (`BD` + 4 digits) and `BudgetINR` (planned spend, ≥ 0).

### fact_projects (27 rows) – one row per facility-improvement project
| Column | Type | Rules / meaning |
|---|---|---|
| ProjectID | text, PK | `PRJ` + 3 digits (**not** reissued; gaps = quarantined rows) |
| LocationID | text, FK → dim_location | |
| ProjectName, ProjectType | text | 8 project types (LED retrofit, HVAC upgrade, …) |
| OwnerName | text | Fictional project owner |
| StartDate, DeadlineDate | date | Deadline ≥ Start |
| CompletionDate | date, nullable | Required when Completed; blank otherwise |
| BudgetINR | decimal | Approved budget, ≥ 0 |
| ActualCostINR | decimal | Spend to date (or final cost if Completed), ≥ 0 |
| PercentComplete | int | 0–100; Completed ⇒ 100; Not Started ⇒ 0 |
| Status | text | `Not Started`, `In Progress`, `On Hold`, `Completed` |
| RiskLevel | text | `Low`, `Medium`, `High` (rule-based rating stored in the data. Let *index* = cost-vs-progress index, or for Completed projects ActualCostINR ÷ BudgetINR. **High** if overdue or index > 1.15; **Medium** if index > 1.05 or On Hold; otherwise **Low**) |

Project dates are not linked to dim_date (daily dates vs monthly calendar); they are used directly.

## Relationships (star schema)

| From (many) | To (one) | Key | Cardinality |
|---|---|---|---|
| fact_space_usage | dim_location | LocationID | many-to-one |
| fact_opex | dim_location | LocationID | many-to-one |
| fact_budget | dim_location | LocationID | many-to-one |
| fact_projects | dim_location | LocationID | many-to-one |
| fact_space_usage | dim_date | MonthStart | many-to-one |
| fact_opex | dim_date | MonthStart | many-to-one |
| fact_budget | dim_date | MonthStart | many-to-one |
| fact_opex | dim_cost_category | CategoryID | many-to-one |
| fact_budget | dim_cost_category | CategoryID | many-to-one |

fact_opex and fact_budget share the same grain (location × month × category), so budget-vs-actual compares like for like through the shared dimensions. Natural keys are (LocationID, MonthStart[, CategoryID]); the IDs are surrogate.

## KPI definitions

### Aggregation rules (read first)

An **office-month** is one office in one month, which is exactly one row of `fact_space_usage`.

1. **Ratio of sums, never an average of ratios.** Add up numerator and denominator over the filter, then divide.
2. **Fixed attributes are not summed across fact rows.** `FloorAreaM2`, `UsableAreaM2` and `Desks` live once per office in `dim_location`.
   - *Snapshot* KPIs (total area, desk count) sum them over **distinct offices**, once.
   - *Rate* KPIs (per month) use **area-months** = Σ over office-months of `FloorAreaM2`, which equals Σ office `FloorAreaM2` × months selected. Likewise **desk-months** = Σ `Desks` × months selected.
3. **Take denominators from `fact_space_usage`** (one row per office-month). Never total `FloorAreaM2`, `Desks` or `Headcount` by iterating over `fact_opex` or `fact_budget`: they hold 5 rows per office-month (one per cost category), which would count each area, desk or employee 5 times.
4. **A cost-category filter changes the numerator only.** Area-months, desk-months and headcount stay the same.

Worked example: an office with 100 desks and 10,000 m² over 12 months has 1,200 desk-months and 120,000 m²-months, not 100 desks or 10,000 m² × 5 categories × 12.

### Space and workplace
| KPI | Formula | Notes |
|---|---|---|
| Total floor area (m²) | Σ FloorAreaM2 over distinct selected offices | Snapshot: each office counted once, **not** once per month |
| Total desks | Σ Desks over distinct selected offices | Snapshot, counted once |
| Usable area ratio | Σ UsableAreaM2 ÷ Σ FloorAreaM2 over distinct offices | |
| Desk utilisation % | Σ AvgDailyOccupiedDesks ÷ Σ Desks, both over office-months | Denominator = desk-months. Measures real use of desks |
| Desk assignment ratio | Σ Headcount ÷ Σ Desks, both over office-months | > 1.0 means more people assigned than desks (hybrid working) |
| Usable area per employee (m²) | Σ UsableAreaM2 ÷ Σ Headcount, both over office-months | Single office-month: UsableAreaM2 ÷ Headcount |
| Floor area per desk (m²) | Σ FloorAreaM2 ÷ Σ Desks over distinct offices | Months cancel out, so no month weighting is needed |

### Operating cost
| KPI | Formula | Notes |
|---|---|---|
| Actual opex (INR) | Σ ActualCostINR | |
| Budget (INR) | Σ BudgetINR | |
| Budget variance (INR) | Σ ActualCostINR − Σ BudgetINR over the same filter | Positive = overspend. Both facts share the same grain, so slices line up |
| Budget variance % | (Σ ActualCostINR − Σ BudgetINR) ÷ Σ BudgetINR | Ratio of sums, not the average of row-level variances |
| Opex per m² per month | Σ ActualCostINR ÷ area-months | Area-months from `fact_space_usage` (rule 3). Allows comparison between offices |
| Opex per employee per month | Σ ActualCostINR ÷ Σ Headcount over office-months | Cost per employee-month |
| Opex per occupied desk per month | Σ ActualCostINR ÷ Σ AvgDailyOccupiedDesks over office-months | Cost per occupied-desk-month. Exposes under-used space |
| Electricity intensity (kWh/m²/month) | Σ ElectricityKWh ÷ area-months | Both terms come from `fact_space_usage` |
| Implied electricity tariff (INR/kWh) | Σ ActualCostINR (CategoryID = CC01) ÷ Σ ElectricityKWh, same offices and months | kWh is not split by category, so the cost side must be filtered to CC01 |
| Utilities share % | Utilities cost ÷ total actual opex | CostGroup = Utilities |
| MoM % / YoY % | (Current − Prior period) ÷ Prior period | YoY only comparable for Oct 2025 – Sep 2026 |

### Projects (as-of date = 30 Sep 2026)
| KPI | Formula |
|---|---|
| Overdue project | Status ∈ {In Progress, On Hold} **and** DeadlineDate < as-of date |
| Overdue count | Count of overdue projects |
| Project budget variance (INR) | ActualCostINR − BudgetINR (meaningful for Completed projects) |
| Budget consumed % | ActualCostINR ÷ BudgetINR |
| Cost-vs-progress index | (ActualCostINR ÷ BudgetINR) ÷ (PercentComplete ÷ 100); > 1 means spending ahead of progress. This is **not** an overspend: a project can have an index above 1 and still be under budget |
| Portfolio cost-vs-progress index | Σ ActualCostINR ÷ Σ (BudgetINR × PercentComplete ÷ 100) | Weighted by budget; never the average of project indices. Exclude Not Started projects |
| Days late (Completed) | CompletionDate − DeadlineDate |
| High-risk count | Count where RiskLevel = High |

### Data quality
| KPI | Formula |
|---|---|
| Imputed-row % | Rows with DataQualityFlag = Imputed ÷ total rows, per fact table |
| Quarantined rows | Row count of `quarantined_rows.csv` |
| Checks passed | Passed ÷ total tests in `data_quality_report.md` |

KPIs are defined here once; Phase 3 will implement the same definitions in SQL and DAX.

## Designed scenarios in the synthetic data

So findings are not mistaken for real-world discoveries, the generator deliberately builds in three patterns:

1. **Pune (LOC04):** electricity about 31% above budget over the 24 months. The other 11 offices pooled together are about 3.4% above budget; individually they range from about -7% to +10%, so "about 3%" describes the pooled figure only, not each office. Pune's HVAC Upgrade project (PRJ016) is **past its deadline** (93 days at the 30 Sep 2026 as-of date) and **spending ahead of progress**: ₹22.73M of a ₹25.37M approved budget used (89.6%) at 70% complete, a cost-vs-progress index of 1.28. Spending is still below the approved budget, so it is *not* recorded as over budget.
2. **Chennai (LOC05):** low desk utilisation, about 34% over the 24 months (other offices: 42–78%).
3. **Warsaw (LOC11):** facility-management cost about 8.5% above budget over the 24 months (its other categories: about 3%).

All other variation is random noise and seasonality. Insights drawn from this data illustrate analysis technique, not real savings.
