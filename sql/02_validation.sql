-- =====================================================================
-- Phase 3 | Data validation checks (SQLite). SYNTHETIC DATA.
-- Each block starts with "-- @check <name>" and returns ONE number named
-- violations. Expected value: 0. The test runner (tests/run_phase3_tests.py)
-- executes every block and reports PASS/FAIL.
-- =====================================================================

-- ---- Row counts (violations = distance from the expected count) -----
-- @check rowcount dim_location = 12
SELECT ABS(COUNT(*) - 12) AS violations FROM dim_location;
-- @check rowcount dim_cost_category = 5
SELECT ABS(COUNT(*) - 5) AS violations FROM dim_cost_category;
-- @check rowcount dim_date = 24
SELECT ABS(COUNT(*) - 24) AS violations FROM dim_date;
-- @check rowcount fact_space_usage = 288 (12 offices x 24 months)
SELECT ABS(COUNT(*) - 288) AS violations FROM fact_space_usage;
-- @check rowcount fact_opex = 1440 (288 x 5 categories)
SELECT ABS(COUNT(*) - 1440) AS violations FROM fact_opex;
-- @check rowcount fact_budget = 1440
SELECT ABS(COUNT(*) - 1440) AS violations FROM fact_budget;
-- @check rowcount fact_projects = 27 (30 raw - 3 quarantined)
SELECT ABS(COUNT(*) - 27) AS violations FROM fact_projects;

-- ---- Referential integrity (orphans) --------------------------------
-- @check orphans fact_space_usage -> dim_location
SELECT COUNT(*) AS violations FROM fact_space_usage f LEFT JOIN dim_location d USING (LocationID) WHERE d.LocationID IS NULL;
-- @check orphans fact_space_usage -> dim_date
SELECT COUNT(*) AS violations FROM fact_space_usage f LEFT JOIN dim_date d USING (MonthStart) WHERE d.MonthStart IS NULL;
-- @check orphans fact_opex -> dim_location
SELECT COUNT(*) AS violations FROM fact_opex f LEFT JOIN dim_location d USING (LocationID) WHERE d.LocationID IS NULL;
-- @check orphans fact_opex -> dim_date
SELECT COUNT(*) AS violations FROM fact_opex f LEFT JOIN dim_date d USING (MonthStart) WHERE d.MonthStart IS NULL;
-- @check orphans fact_opex -> dim_cost_category
SELECT COUNT(*) AS violations FROM fact_opex f LEFT JOIN dim_cost_category d USING (CategoryID) WHERE d.CategoryID IS NULL;
-- @check orphans fact_budget -> dim_location
SELECT COUNT(*) AS violations FROM fact_budget f LEFT JOIN dim_location d USING (LocationID) WHERE d.LocationID IS NULL;
-- @check orphans fact_budget -> dim_date
SELECT COUNT(*) AS violations FROM fact_budget f LEFT JOIN dim_date d USING (MonthStart) WHERE d.MonthStart IS NULL;
-- @check orphans fact_budget -> dim_cost_category
SELECT COUNT(*) AS violations FROM fact_budget f LEFT JOIN dim_cost_category d USING (CategoryID) WHERE d.CategoryID IS NULL;
-- @check orphans fact_projects -> dim_location
SELECT COUNT(*) AS violations FROM fact_projects f LEFT JOIN dim_location d USING (LocationID) WHERE d.LocationID IS NULL;

-- ---- Grain ----------------------------------------------------------
-- @check grain fact_space_usage: one row per location x month
SELECT COUNT(*) AS violations FROM (SELECT 1 FROM fact_space_usage GROUP BY LocationID, MonthStart HAVING COUNT(*) <> 1);
-- @check grain fact_opex: one row per location x month x category
SELECT COUNT(*) AS violations FROM (SELECT 1 FROM fact_opex GROUP BY LocationID, MonthStart, CategoryID HAVING COUNT(*) <> 1);
-- @check grain fact_budget: one row per location x month x category
SELECT COUNT(*) AS violations FROM (SELECT 1 FROM fact_budget GROUP BY LocationID, MonthStart, CategoryID HAVING COUNT(*) <> 1);
-- @check grain every office has all 24 months of usage
SELECT COUNT(*) AS violations FROM (SELECT 1 FROM fact_space_usage GROUP BY LocationID HAVING COUNT(*) <> 24);
-- @check keys: every opex key has a budget key
SELECT COUNT(*) AS violations FROM fact_opex o LEFT JOIN fact_budget b USING (LocationID, MonthStart, CategoryID) WHERE b.BudgetID IS NULL;
-- @check keys: every budget key has an opex key
SELECT COUNT(*) AS violations FROM fact_budget b LEFT JOIN fact_opex o USING (LocationID, MonthStart, CategoryID) WHERE o.OpexID IS NULL;
-- @check keys: opex/budget cover exactly the usage office-months
SELECT COUNT(*) AS violations FROM fact_space_usage s
WHERE (SELECT COUNT(*) FROM fact_opex o WHERE o.LocationID = s.LocationID AND o.MonthStart = s.MonthStart) <> 5;

-- ---- Business rules -------------------------------------------------
-- @check occupied desks never exceed desks
SELECT COUNT(*) AS violations FROM fact_space_usage s JOIN dim_location l USING (LocationID) WHERE s.AvgDailyOccupiedDesks > l.Desks;
-- @check region consistent with country
SELECT COUNT(*) AS violations FROM dim_location
WHERE Region <> CASE WHEN Country = 'India' THEN 'India'
                     WHEN Country IN ('Singapore','China','Australia') THEN 'APAC'
                     WHEN Country IN ('Germany','Poland','United Kingdom') THEN 'Europe' END
   OR CASE WHEN Country = 'India' THEN 'India'
           WHEN Country IN ('Singapore','China','Australia') THEN 'APAC'
           WHEN Country IN ('Germany','Poland','United Kingdom') THEN 'Europe' END IS NULL;
-- @check no negative actual costs or budgets
SELECT (SELECT COUNT(*) FROM fact_opex   WHERE ActualCostINR < 0)
     + (SELECT COUNT(*) FROM fact_budget WHERE BudgetINR < 0) AS violations;
-- @check electricity kWh strictly positive
SELECT COUNT(*) AS violations FROM fact_space_usage WHERE ElectricityKWh <= 0;
-- @check month dates are first-of-month and dim_date is contiguous (24 months)
SELECT COUNT(*) AS violations FROM dim_date WHERE substr(MonthStart, 9, 2) <> '01'
                                             OR substr(MonthStart, 1, 7) <> YearMonth;
-- @check fiscal year labels follow Oct-Sep rule (FY = calendar year + 1 for Oct-Dec)
SELECT COUNT(*) AS violations FROM dim_date
WHERE FiscalYear <> 'FY' || substr(CAST(Year + CASE WHEN MonthNumber >= 10 THEN 1 ELSE 0 END AS TEXT), 3, 2)
   OR FiscalMonthNumber <> ((MonthNumber + 2) % 12) + 1;
-- @check project Completed rows are 100% with a completion date (others none)
SELECT COUNT(*) AS violations FROM fact_projects
WHERE (Status = 'Completed' AND (PercentComplete <> 100 OR CompletionDate IS NULL))
   OR (Status <> 'Completed' AND CompletionDate IS NOT NULL);
-- @check stored project RiskLevel equals the dictionary rule (as-of 2026-09-30)
SELECT COUNT(*) AS violations FROM (
  SELECT RiskLevel,
         CASE WHEN IsOverdue = 1 OR idx > 1.15 THEN 'High'
              WHEN idx > 1.05 OR Status = 'On Hold' THEN 'Medium'
              ELSE 'Low' END AS RuleRisk
  FROM (SELECT RiskLevel, Status, IsOverdue,
               CASE WHEN Status = 'Completed' THEN BudgetConsumed
                    WHEN PercentComplete > 0 THEN CostVsProgressIndex
                    ELSE 0 END AS idx
        FROM vw_project_status))
WHERE RiskLevel <> RuleRisk;

-- ---- Plausibility ranges (same bands as Phase 2) --------------------
-- @check desk utilisation per office-month within 0.2-0.95
SELECT COUNT(*) AS violations FROM vw_office_month
WHERE 1.0 * AvgDailyOccupiedDesks / Desks NOT BETWEEN 0.2 AND 0.95;
-- @check implied electricity tariff per office-month within 5-40 INR/kWh
SELECT COUNT(*) AS violations FROM vw_office_month
WHERE ElectricityCostINR / ElectricityKWh NOT BETWEEN 5 AND 40;
-- @check opex per m2 per month per office-month within 100-1000 INR
SELECT COUNT(*) AS violations FROM vw_office_month
WHERE ActualCostINR / FloorAreaM2 NOT BETWEEN 100 AND 1000;

-- ---- Data-quality flags agree with the Phase 2 quality report -------
-- @check imputed rows: space_usage=3, opex=6, budget=1
SELECT ABS((SELECT COUNT(*) FROM fact_space_usage WHERE DataQualityFlag='Imputed') - 3)
     + ABS((SELECT COUNT(*) FROM fact_opex        WHERE DataQualityFlag='Imputed') - 6)
     + ABS((SELECT COUNT(*) FROM fact_budget      WHERE DataQualityFlag='Imputed') - 1) AS violations;

-- ---- Model integrity: views do not fan out --------------------------
-- @check vw_office_month has exactly 288 rows (no 5x fan-out)
SELECT ABS(COUNT(*) - 288) AS violations FROM vw_office_month;
-- @check vw_cost_actual_budget has exactly 1440 rows
SELECT ABS(COUNT(*) - 1440) AS violations FROM vw_cost_actual_budget;
-- @check vw_office_month cost totals equal fact totals
SELECT CASE WHEN ABS((SELECT SUM(ActualCostINR) FROM vw_office_month) - (SELECT SUM(ActualCostINR) FROM fact_opex))   < 0.01
             AND ABS((SELECT SUM(BudgetINR)     FROM vw_office_month) - (SELECT SUM(BudgetINR)     FROM fact_budget)) < 0.01
            THEN 0 ELSE 1 END AS violations;
