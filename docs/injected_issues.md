# Injected Data-Quality Issues (raw dataset only)

These issues were added **deliberately** by `scripts/generate_data.py` into `data/raw/` to test the
validation script. The files in `data/clean/` are produced by `scripts/validate_and_clean.py` and
contain none of them. `dim_cost_category` and `dim_date` are reference tables with no injected issues.

Total injected issues: **19**

| ID | Table | Record | Column | Rule | Description | Expected action |
|---|---|---|---|---|---|---|
| ISS01 | dim_location | LOC04 | City | `text_formatting` | City stored in lower case with stray spaces | Corrected: trim and title-case |
| ISS02 | dim_location | LOC08 | Region | `region_country_mismatch` | Region 'Europe' recorded for an Australian office | Corrected: Region derived from Country |
| ISS03 | fact_space_usage | SU0099 | Headcount | `missing_value` | Headcount left blank | Imputed by interpolation, row flagged |
| ISS04 | fact_space_usage | SU0070 | Headcount | `missing_value` | Headcount left blank | Imputed by interpolation, row flagged |
| ISS05 | fact_space_usage | SU0097 | AvgDailyOccupiedDesks | `occupied_exceeds_desks` | Occupied desks (1389) exceed desks available (1372) | Value rejected, imputed by interpolation, row flagged |
| ISS06 | fact_opex | OC1034 | ActualCostINR | `missing_value` | Actual cost left blank | Imputed by interpolation, row flagged |
| ISS07 | fact_opex | OC0120 | ActualCostINR | `missing_value` | Actual cost left blank | Imputed by interpolation, row flagged |
| ISS08 | fact_opex | OC1368 | ActualCostINR | `negative_value` | Cost recorded as negative | Value rejected, imputed by interpolation, row flagged |
| ISS09 | fact_opex | OC0261 | ActualCostINR | `outlier_vs_budget` | Electricity cost 100x too large (decimal-point error) | Value rejected (actual/budget > 3), imputed, row flagged |
| ISS10 | fact_opex | OC0963 | LocationID | `orphan_foreign_key` | LocationID 'LOC99' does not exist in dim_location | Row quarantined; month/category cell gap-filled and flagged |
| ISS11 | fact_opex | OC0259 | LocationID | `text_formatting` | LocationID in lower case with leading space | Corrected: trim and upper-case |
| ISS12 | fact_opex | OC0788 | MonthStart | `date_not_month_start` | Month recorded as mid-month date | Corrected: normalised to first of month |
| ISS13 | fact_opex | OC0707 | ALL | `duplicate_exact` | Entire row repeated | Removed: first copy kept |
| ISS14 | fact_opex | OC0646 | OpexID | `duplicate_conflict` | Same OpexID appears twice with different costs | Both copies quarantined; cell gap-filled and flagged |
| ISS15 | fact_budget | BD0943 | MonthStart | `invalid_date` | Month '2025-13-01' is not a valid date | Row quarantined; cell gap-filled and flagged |
| ISS16 | fact_budget | BD1193 | ALL | `duplicate_exact` | Entire row repeated | Removed: first copy kept |
| ISS17 | fact_projects | PRJ010 | DeadlineDate | `date_order` | Deadline is before the start date | Row quarantined (cannot infer correct date) |
| ISS18 | fact_projects | PRJ015 | PercentComplete | `status_inconsistency` | Status 'Completed' but PercentComplete is 60 | Row quarantined (status or progress is wrong; cannot tell which) |
| ISS19 | fact_projects | PRJ019 | BudgetINR | `negative_value` | Project budget recorded as negative | Row quarantined |
