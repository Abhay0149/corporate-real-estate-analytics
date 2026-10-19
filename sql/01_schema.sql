-- =====================================================================
-- Corporate Real Estate Portfolio & Workplace Performance Analytics
-- Phase 3 | SQLite schema (portable to PostgreSQL with minor type edits)
-- ALL DATA IS SYNTHETIC. Offices, people and figures are invented.
-- Loads the CLEAN layer (data/clean/). Dates are ISO text 'YYYY-MM-DD'.
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------- Dimensions ------------------------------------------------
CREATE TABLE dim_location (
    LocationID     TEXT PRIMARY KEY CHECK (LocationID GLOB 'LOC[0-9][0-9]'),
    OfficeName     TEXT NOT NULL,
    City           TEXT NOT NULL,
    Country        TEXT NOT NULL,
    Region         TEXT NOT NULL CHECK (Region IN ('India','APAC','Europe')),
    OwnershipType  TEXT NOT NULL CHECK (OwnershipType IN ('Owned','Leased')),
    FloorAreaM2    INTEGER NOT NULL CHECK (FloorAreaM2 > 0),
    UsableAreaM2   INTEGER NOT NULL CHECK (UsableAreaM2 > 0),
    Desks          INTEGER NOT NULL CHECK (Desks > 0),
    CHECK (UsableAreaM2 <= FloorAreaM2)
);

CREATE TABLE dim_cost_category (
    CategoryID    TEXT PRIMARY KEY CHECK (CategoryID GLOB 'CC[0-9][0-9]'),
    CategoryName  TEXT NOT NULL UNIQUE,
    CostGroup     TEXT NOT NULL CHECK (CostGroup IN ('Utilities','Maintenance','Facility Services')),
    Description   TEXT
);

CREATE TABLE dim_date (
    MonthStart         TEXT PRIMARY KEY CHECK (MonthStart GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-01'),
    Year               INTEGER NOT NULL,
    MonthNumber        INTEGER NOT NULL CHECK (MonthNumber BETWEEN 1 AND 12),
    MonthName          TEXT NOT NULL,
    YearMonth          TEXT NOT NULL UNIQUE,
    Quarter            TEXT NOT NULL CHECK (Quarter IN ('Q1','Q2','Q3','Q4')),
    FiscalYear         TEXT NOT NULL,
    FiscalQuarter      TEXT NOT NULL CHECK (FiscalQuarter IN ('FQ1','FQ2','FQ3','FQ4')),
    FiscalMonthNumber  INTEGER NOT NULL CHECK (FiscalMonthNumber BETWEEN 1 AND 12)
);

-- One-row parameter table: the as-of date is a constant, never "today".
CREATE TABLE param_as_of (
    AsOfDate TEXT NOT NULL CHECK (AsOfDate GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]')
);
INSERT INTO param_as_of VALUES ('2026-09-30');

-- ---------- Facts -----------------------------------------------------
-- Grain: location x month
CREATE TABLE fact_space_usage (
    UsageID                TEXT PRIMARY KEY,
    LocationID             TEXT NOT NULL REFERENCES dim_location(LocationID),
    MonthStart             TEXT NOT NULL REFERENCES dim_date(MonthStart),
    Headcount              INTEGER NOT NULL CHECK (Headcount >= 0),
    AvgDailyOccupiedDesks  INTEGER NOT NULL CHECK (AvgDailyOccupiedDesks >= 0),
    ElectricityKWh         REAL    NOT NULL CHECK (ElectricityKWh >= 0),
    DataQualityFlag        TEXT    NOT NULL CHECK (DataQualityFlag IN ('OK','Imputed')),
    UNIQUE (LocationID, MonthStart)
);

-- Grain: location x month x category (opex and budget share this grain)
CREATE TABLE fact_opex (
    OpexID           TEXT PRIMARY KEY,
    LocationID       TEXT NOT NULL REFERENCES dim_location(LocationID),
    MonthStart       TEXT NOT NULL REFERENCES dim_date(MonthStart),
    CategoryID       TEXT NOT NULL REFERENCES dim_cost_category(CategoryID),
    ActualCostINR    REAL NOT NULL CHECK (ActualCostINR >= 0),
    DataQualityFlag  TEXT NOT NULL CHECK (DataQualityFlag IN ('OK','Imputed')),
    UNIQUE (LocationID, MonthStart, CategoryID)
);

CREATE TABLE fact_budget (
    BudgetID         TEXT PRIMARY KEY,
    LocationID       TEXT NOT NULL REFERENCES dim_location(LocationID),
    MonthStart       TEXT NOT NULL REFERENCES dim_date(MonthStart),
    CategoryID       TEXT NOT NULL REFERENCES dim_cost_category(CategoryID),
    BudgetINR        REAL NOT NULL CHECK (BudgetINR >= 0),
    DataQualityFlag  TEXT NOT NULL CHECK (DataQualityFlag IN ('OK','Imputed')),
    UNIQUE (LocationID, MonthStart, CategoryID)
);

-- Grain: one row per project. Project dates are daily and are NOT linked to dim_date.
CREATE TABLE fact_projects (
    ProjectID        TEXT PRIMARY KEY CHECK (ProjectID GLOB 'PRJ[0-9][0-9][0-9]'),
    LocationID       TEXT NOT NULL REFERENCES dim_location(LocationID),
    ProjectName      TEXT NOT NULL,
    ProjectType      TEXT NOT NULL,
    OwnerName        TEXT NOT NULL,
    StartDate        TEXT NOT NULL,
    DeadlineDate     TEXT NOT NULL,
    CompletionDate   TEXT,               -- NULL unless Completed
    BudgetINR        REAL NOT NULL CHECK (BudgetINR >= 0),
    ActualCostINR    REAL NOT NULL CHECK (ActualCostINR >= 0),
    PercentComplete  INTEGER NOT NULL CHECK (PercentComplete BETWEEN 0 AND 100),
    Status           TEXT NOT NULL CHECK (Status IN ('Not Started','In Progress','On Hold','Completed')),
    RiskLevel        TEXT NOT NULL CHECK (RiskLevel IN ('Low','Medium','High')),
    CHECK (DeadlineDate >= StartDate),
    CHECK ((Status = 'Completed' AND PercentComplete = 100 AND CompletionDate IS NOT NULL)
        OR (Status <> 'Completed' AND CompletionDate IS NULL)),
    CHECK (Status <> 'Not Started' OR PercentComplete = 0)
);

-- ---------- Indexes on foreign keys ----------------------------------
CREATE INDEX ix_space_loc    ON fact_space_usage(LocationID);
CREATE INDEX ix_space_month  ON fact_space_usage(MonthStart);
CREATE INDEX ix_opex_loc     ON fact_opex(LocationID);
CREATE INDEX ix_opex_month   ON fact_opex(MonthStart);
CREATE INDEX ix_opex_cat     ON fact_opex(CategoryID);
CREATE INDEX ix_budget_loc   ON fact_budget(LocationID);
CREATE INDEX ix_budget_month ON fact_budget(MonthStart);
CREATE INDEX ix_budget_cat   ON fact_budget(CategoryID);
CREATE INDEX ix_proj_loc     ON fact_projects(LocationID);

-- ---------- Views -----------------------------------------------------
-- Opex and budget joined at their shared grain (location x month x category).
-- Fan-out safe: both sides have exactly one row per key (enforced by UNIQUE).
CREATE VIEW vw_cost_actual_budget AS
SELECT o.LocationID, o.MonthStart, o.CategoryID, c.CostGroup,
       o.ActualCostINR, b.BudgetINR
FROM fact_opex o
JOIN fact_budget b ON b.LocationID = o.LocationID
                  AND b.MonthStart = o.MonthStart
                  AND b.CategoryID = o.CategoryID
JOIN dim_cost_category c ON c.CategoryID = o.CategoryID;

-- One row per office-month. Costs are collapsed to office-month BEFORE joining
-- to space usage, so area, desks and headcount are never multiplied by 5 categories.
CREATE VIEW vw_office_month AS
SELECT s.LocationID, s.MonthStart, d.FiscalYear,
       l.FloorAreaM2, l.UsableAreaM2, l.Desks,
       s.Headcount, s.AvgDailyOccupiedDesks, s.ElectricityKWh,
       k.ActualCostINR, k.BudgetINR, k.ElectricityCostINR, k.UtilitiesCostINR
FROM fact_space_usage s
JOIN dim_location l ON l.LocationID = s.LocationID
JOIN dim_date d     ON d.MonthStart = s.MonthStart
JOIN (SELECT LocationID, MonthStart,
             SUM(ActualCostINR) AS ActualCostINR,
             SUM(BudgetINR)     AS BudgetINR,
             SUM(CASE WHEN CategoryID = 'CC01' THEN ActualCostINR ELSE 0 END) AS ElectricityCostINR,
             SUM(CASE WHEN CostGroup = 'Utilities' THEN ActualCostINR ELSE 0 END) AS UtilitiesCostINR
      FROM vw_cost_actual_budget
      GROUP BY LocationID, MonthStart) k
  ON k.LocationID = s.LocationID AND k.MonthStart = s.MonthStart;

-- Per-project derived fields (as-of date comes from param_as_of).
CREATE VIEW vw_project_status AS
SELECT p.*,
       a.AsOfDate,
       CASE WHEN p.Status IN ('In Progress','On Hold') AND p.DeadlineDate < a.AsOfDate
            THEN 1 ELSE 0 END                                   AS IsOverdue,
       p.ActualCostINR / p.BudgetINR                            AS BudgetConsumed,
       CASE WHEN p.Status = 'Not Started' THEN NULL
            ELSE p.ActualCostINR / (p.BudgetINR * p.PercentComplete / 100.0) END AS CostVsProgressIndex,
       CASE WHEN p.Status = 'Completed'
            THEN CAST(julianday(p.CompletionDate) - julianday(p.DeadlineDate) AS INTEGER) END AS DaysLate,
       CASE WHEN p.Status IN ('In Progress','On Hold') AND p.DeadlineDate < a.AsOfDate
            THEN CAST(julianday(a.AsOfDate) - julianday(p.DeadlineDate) AS INTEGER) END AS DaysOverdue
FROM fact_projects p CROSS JOIN param_as_of a;
