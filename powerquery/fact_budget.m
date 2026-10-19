// ALL DATA IS SYNTHETIC (invented offices, people and figures). Phase 3 Power Query (M).
// Syntax-reviewed on macOS only: NOT executed in Power Query / Power BI yet.
// Query name: fact_budget   (source: data/clean/fact_budget.csv)
let
    Source = fnLoadCsv("fact_budget.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
        {"BudgetID", type text},
        {"LocationID", type text},
        {"MonthStart", type date},
        {"CategoryID", type text},
        {"BudgetINR", type number},
        {"DataQualityFlag", type text}
        },
        "en-US"
    )
in
    Typed
