-- =====================================================================
-- Phase 3 | Business queries (SQLite). ALL DATA IS SYNTHETIC.
-- Rules from docs/data_dictionary.md applied throughout:
--   * ratio of sums, never an average of ratios
--   * snapshot KPIs (area, desks) count each office ONCE (dim_location)
--   * rate KPIs use area-months / desk-months from fact_space_usage
--     (vw_office_month = one row per office-month), never from fact_opex
--   * a cost-category filter changes the numerator only
-- Every block starts with "-- @query <id> <name>"; first column is Slice
-- (office / category / fiscal year / project / 'PORTFOLIO').
-- Positive variance = overspend.
-- =====================================================================

-- @query Q01 space_snapshot
-- Snapshot KPIs: each office counted once, not once per month.
WITH s AS (
  SELECT LocationID AS Slice, FloorAreaM2 AS f, UsableAreaM2 AS u, Desks AS d FROM dim_location),
t AS (
  SELECT * FROM s
  UNION ALL SELECT 'PORTFOLIO', SUM(f), SUM(u), SUM(d) FROM s)
SELECT Slice, f AS total_floor_area, d AS total_desks,
       1.0 * u / f AS usable_area_ratio,
       1.0 * f / d AS floor_area_per_desk
FROM t ORDER BY Slice;

-- @query Q02 workplace_utilisation
-- Desk utilisation, desk assignment ratio, usable area per employee (office-month denominators).
WITH s AS (
  SELECT LocationID AS Slice,
         SUM(Desks) AS desk_m, SUM(AvgDailyOccupiedDesks) AS occ_m,
         SUM(Headcount) AS hc_m, SUM(UsableAreaM2) AS usable_m
  FROM vw_office_month GROUP BY LocationID),
t AS (
  SELECT * FROM s
  UNION ALL SELECT 'PORTFOLIO', SUM(desk_m), SUM(occ_m), SUM(hc_m), SUM(usable_m) FROM s)
SELECT Slice,
       1.0 * occ_m / desk_m    AS desk_utilisation,
       1.0 * hc_m / desk_m     AS desk_assignment_ratio,
       1.0 * usable_m / hc_m   AS usable_area_per_employee
FROM t ORDER BY Slice;

-- @query Q03 budget_vs_actual_by_office
WITH s AS (
  SELECT LocationID AS Slice, SUM(ActualCostINR) AS a, SUM(BudgetINR) AS b
  FROM vw_cost_actual_budget GROUP BY LocationID),
t AS (
  SELECT * FROM s UNION ALL SELECT 'PORTFOLIO', SUM(a), SUM(b) FROM s)
SELECT Slice, a AS actual_opex, b AS budget, a - b AS budget_variance,
       (a - b) / b AS budget_variance_pct
FROM t ORDER BY Slice;

-- @query Q04 budget_vs_actual_by_category
-- Category changes the numerator only: opex per m2 keeps the SAME area-months denominator.
WITH am AS (SELECT SUM(FloorAreaM2) AS area_m FROM vw_office_month),
s AS (
  SELECT CategoryID AS Slice, SUM(ActualCostINR) AS a, SUM(BudgetINR) AS b
  FROM vw_cost_actual_budget GROUP BY CategoryID),
t AS (
  SELECT * FROM s UNION ALL SELECT 'ALL', SUM(a), SUM(b) FROM s)
SELECT Slice, a AS actual_opex, b AS budget, a - b AS budget_variance,
       (a - b) / b AS budget_variance_pct,
       a / (SELECT area_m FROM am) AS opex_per_m2_month
FROM t ORDER BY Slice;

-- @query Q05 fiscal_year_summary
-- Portfolio by fiscal year, with YoY (FY26 vs FY25 total; FY25 has no prior year).
WITH f AS (
  SELECT FiscalYear AS Slice, SUM(ActualCostINR) AS a, SUM(BudgetINR) AS b, SUM(FloorAreaM2) AS area_m
  FROM vw_office_month GROUP BY FiscalYear)
SELECT Slice, a AS actual_opex, b AS budget, a - b AS budget_variance,
       (a - b) / b AS budget_variance_pct,
       a / area_m AS opex_per_m2_month,
       (a - LAG(a) OVER (ORDER BY Slice)) / LAG(a) OVER (ORDER BY Slice) AS yoy_pct
FROM f ORDER BY Slice;

-- @query Q06 unit_costs_by_office
-- Opex per m2 / per employee / per occupied desk, per month.
WITH s AS (
  SELECT LocationID AS Slice, SUM(ActualCostINR) AS a, SUM(FloorAreaM2) AS area_m,
         SUM(Headcount) AS hc_m, SUM(AvgDailyOccupiedDesks) AS occ_m
  FROM vw_office_month GROUP BY LocationID),
t AS (
  SELECT * FROM s UNION ALL SELECT 'PORTFOLIO', SUM(a), SUM(area_m), SUM(hc_m), SUM(occ_m) FROM s)
SELECT Slice, a / area_m AS opex_per_m2_month, a / hc_m AS opex_per_employee_month,
       a / occ_m AS opex_per_occupied_desk_month
FROM t ORDER BY Slice;

-- @query Q07 electricity_by_office
-- kWh is not split by category, so the tariff numerator is filtered to CC01.
WITH sp AS (
  SELECT LocationID AS Slice, SUM(FloorAreaM2) AS area_m, SUM(ElectricityKWh) AS kwh,
         SUM(ElectricityCostINR) AS ec
  FROM vw_office_month GROUP BY LocationID),
eb AS (
  SELECT LocationID AS Slice, SUM(BudgetINR) AS eb
  FROM vw_cost_actual_budget WHERE CategoryID = 'CC01' GROUP BY LocationID),
s AS (SELECT sp.Slice, area_m, kwh, ec, eb FROM sp JOIN eb USING (Slice)),
t AS (SELECT * FROM s UNION ALL SELECT 'PORTFOLIO', SUM(area_m), SUM(kwh), SUM(ec), SUM(eb) FROM s)
SELECT Slice, kwh / area_m AS electricity_kwh_per_m2_month,
       ec / kwh AS implied_tariff_inr_per_kwh,
       (ec - eb) / eb AS electricity_variance_pct
FROM t ORDER BY Slice;

-- @query Q08 utilities_share_by_office
WITH s AS (
  SELECT LocationID AS Slice, SUM(UtilitiesCostINR) AS u, SUM(ActualCostINR) AS a
  FROM vw_office_month GROUP BY LocationID),
t AS (SELECT * FROM s UNION ALL SELECT 'PORTFOLIO', SUM(u), SUM(a) FROM s)
SELECT Slice, u / a AS utilities_share FROM t ORDER BY Slice;

-- @query Q09 monthly_trend_mom_yoy
-- MoM needs a prior month; YoY is only comparable for Oct 2025 - Sep 2026.
WITH m AS (
  SELECT MonthStart AS Slice, SUM(ActualCostINR) AS a, SUM(BudgetINR) AS b
  FROM vw_cost_actual_budget GROUP BY MonthStart)
SELECT Slice, a AS actual_opex, b AS budget, (a - b) / b AS budget_variance_pct,
       (a - LAG(a, 1)  OVER w) / LAG(a, 1)  OVER w AS mom_pct,
       (a - LAG(a, 12) OVER w) / LAG(a, 12) OVER w AS yoy_pct
FROM m WINDOW w AS (ORDER BY Slice) ORDER BY Slice;

-- @query Q10 overdue_projects
-- Overdue = In Progress / On Hold and DeadlineDate < as-of date (30 Sep 2026).
SELECT ProjectID AS Slice, LocationID, ProjectType, Status, DeadlineDate,
       PercentComplete, DaysOverdue AS days_overdue, RiskLevel
FROM vw_project_status WHERE IsOverdue = 1
ORDER BY DaysOverdue DESC, ProjectID;

-- @query Q11 project_cost_vs_progress
-- Per-project index; PORTFOLIO = sum(actual) / sum(budget x pct), Not Started excluded,
-- never an average of project indices.
WITH a AS (SELECT * FROM vw_project_status WHERE Status <> 'Not Started'),
s AS (
  SELECT ProjectID AS Slice, ActualCostINR AS spent, BudgetINR * PercentComplete / 100.0 AS earned,
         BudgetINR AS bud, Status FROM a),
t AS (
  SELECT Slice, spent, earned, bud FROM s
  UNION ALL SELECT 'PORTFOLIO', SUM(spent), SUM(earned), SUM(bud) FROM s)
SELECT Slice, spent / bud AS budget_consumed, spent / earned AS cost_vs_progress_index
FROM t ORDER BY Slice;

-- @query Q12 project_risk_summary
-- Counts per office plus portfolio. Days late / overdue are portfolio-level.
WITH s AS (
  SELECT LocationID AS Slice, COUNT(*) AS projects, SUM(IsOverdue) AS overdue,
         SUM(CASE WHEN RiskLevel = 'High' THEN 1 ELSE 0 END) AS high_risk
  FROM vw_project_status GROUP BY LocationID),
t AS (SELECT * FROM s UNION ALL SELECT 'PORTFOLIO', SUM(projects), SUM(overdue), SUM(high_risk) FROM s)
SELECT Slice, projects, overdue AS overdue_projects, high_risk AS high_risk_projects,
       CASE WHEN Slice = 'PORTFOLIO'
            THEN (SELECT AVG(DaysLate) FROM vw_project_status WHERE Status = 'Completed') END AS avg_days_late_completed,
       CASE WHEN Slice = 'PORTFOLIO'
            THEN (SELECT MAX(DaysOverdue) FROM vw_project_status) END AS max_days_overdue
FROM t ORDER BY Slice;

-- @query Q13 imputed_row_share
SELECT 'fact_space_usage' AS Slice, 1.0 * SUM(DataQualityFlag = 'Imputed') / COUNT(*) AS imputed_row_pct FROM fact_space_usage
UNION ALL SELECT 'fact_opex',   1.0 * SUM(DataQualityFlag = 'Imputed') / COUNT(*) FROM fact_opex
UNION ALL SELECT 'fact_budget', 1.0 * SUM(DataQualityFlag = 'Imputed') / COUNT(*) FROM fact_budget
ORDER BY Slice;

-- @query Q14 designed_scenarios
-- The three scenarios the generator builds in on purpose (see data_dictionary.md).
WITH ev AS (
  SELECT LocationID, SUM(ActualCostINR) a, SUM(BudgetINR) b FROM vw_cost_actual_budget
  WHERE CategoryID = 'CC01' GROUP BY LocationID),
ut AS (
  SELECT LocationID, 1.0 * SUM(AvgDailyOccupiedDesks) / SUM(Desks) AS u FROM vw_office_month GROUP BY LocationID),
fm AS (
  SELECT CategoryID = 'CC04' AS is_fm, SUM(ActualCostINR) a, SUM(BudgetINR) b
  FROM vw_cost_actual_budget WHERE LocationID = 'LOC11' GROUP BY CategoryID = 'CC04')
SELECT 'S1 Pune electricity variance pct' AS Slice, (SELECT (a - b) / b FROM ev WHERE LocationID = 'LOC04') AS value
UNION ALL SELECT 'S1 other offices pooled electricity variance pct',
       (SELECT (SUM(a) - SUM(b)) / SUM(b) FROM ev WHERE LocationID <> 'LOC04')
UNION ALL SELECT 'S1 PRJ016 days overdue', (SELECT DaysOverdue FROM vw_project_status WHERE ProjectID = 'PRJ016')
UNION ALL SELECT 'S1 PRJ016 cost-vs-progress index', (SELECT CostVsProgressIndex FROM vw_project_status WHERE ProjectID = 'PRJ016')
UNION ALL SELECT 'S1 PRJ016 budget consumed', (SELECT BudgetConsumed FROM vw_project_status WHERE ProjectID = 'PRJ016')
UNION ALL SELECT 'S2 Chennai desk utilisation', (SELECT u FROM ut WHERE LocationID = 'LOC05')
UNION ALL SELECT 'S2 other offices min utilisation', (SELECT MIN(u) FROM ut WHERE LocationID <> 'LOC05')
UNION ALL SELECT 'S2 other offices max utilisation', (SELECT MAX(u) FROM ut WHERE LocationID <> 'LOC05')
UNION ALL SELECT 'S3 Warsaw facility-management variance pct', (SELECT (a - b) / b FROM fm WHERE is_fm = 1)
UNION ALL SELECT 'S3 Warsaw other categories pooled variance pct', (SELECT (a - b) / b FROM fm WHERE is_fm = 0);

-- @query Q15 cost_group_by_fiscal_year
-- Share of actual opex by cost group within each fiscal year.
WITH g AS (
  SELECT d.FiscalYear || ' ' || v.CostGroup AS Slice, d.FiscalYear AS fy,
         SUM(v.ActualCostINR) AS a, SUM(v.BudgetINR) AS b
  FROM vw_cost_actual_budget v JOIN dim_date d USING (MonthStart)
  GROUP BY d.FiscalYear, v.CostGroup)
SELECT Slice, a AS actual_opex, b AS budget, (a - b) / b AS budget_variance_pct,
       a / SUM(a) OVER (PARTITION BY fy) AS share_of_fy_opex
FROM g ORDER BY Slice;
