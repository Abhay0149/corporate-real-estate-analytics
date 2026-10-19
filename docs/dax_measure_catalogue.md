# DAX measure catalogue (Phase 3)

> **All data is synthetic.** **Status: syntax-reviewed only; not executed in Power BI.** Source: `dax/measures.dax` (48 measures on table `_Measures`). Definitions follow `docs/data_dictionary.md`; every ratio is a ratio of sums. Positive variance = overspend.

| Group | Measures | Notes |
|---|---|---|
| Space snapshot | Offices, Total Floor Area m2, Total Usable Area m2, Total Desks, Usable Area Ratio, Floor Area per Desk m2 | Read `dim_location` once per office, never summed across months |
| Rate denominators | Area-Months m2, Usable Area-Months m2, Desk-Months, Occupied Desk-Months, Headcount-Months | `SUMX` over `fact_space_usage` with `RELATED(dim_location[...])`; unaffected by cost-category filters |
| Workplace | Desk Utilisation %, Desk Assignment Ratio, Usable Area per Employee m2 | Occupied ÷ desk-months; headcount ÷ desk-months; usable area-months ÷ headcount-months |
| Operating cost | Actual Opex INR, Budget INR, Budget Variance INR, Budget Variance %, Opex per m2 / per Employee / per Occupied Desk per Month INR | Cost ÷ area-months, headcount-months, occupied-desk-months |
| Electricity & utilities | Electricity kWh, Electricity Intensity kWh per m2 per Month, Electricity Cost INR, Electricity Budget INR, Electricity Variance %, Implied Electricity Tariff INR per kWh, Utilities Cost INR, Utilities Share % | kWh is not split by category, so cost-side measures remove category filters and pin CC01 |
| Time | Actual Opex INR Prior Month / Prior Year, Opex MoM %, Opex YoY % | Month-shift with `TREATAS`; BLANK unless every selected month has a prior month (YoY exists only for Oct 2025 – Sep 2026) |
| Projects | As Of Date, Projects, Overdue Projects, High Risk Projects, Project Budget / Actual Cost INR, Project Budget Consumed %, Completed Project Budget Variance INR, Cost vs Progress Index, Avg Days Late Completed, Max Days Overdue, Risk Rule Mismatches | As-of date from `param_AsOfDate`; index = Σ actual ÷ Σ (budget × % complete), Not Started excluded; `Risk Rule Mismatches` recomputes the dictionary rule and should be 0 |
| Data quality | Imputed Rows % Space Usage / Opex / Budget | Share of rows with `DataQualityFlag = "Imputed"` |

**Reading the cost-vs-progress index:** above 1 means spending is ahead of progress. It is not the same as over budget (Pune's HVAC project has index 1.28 yet has used 89.6% of its budget).
