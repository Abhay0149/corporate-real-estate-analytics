// ALL DATA IS SYNTHETIC (invented offices, people and figures). Phase 3 Power Query (M).
// Syntax-reviewed on macOS only: NOT executed in Power Query / Power BI yet.
// Query name: fact_projects   (source: data/clean/fact_projects.csv)
let
    Source = fnLoadCsv("fact_projects.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
        {"ProjectID", type text},
        {"LocationID", type text},
        {"ProjectName", type text},
        {"ProjectType", type text},
        {"OwnerName", type text},
        {"StartDate", type date},
        {"DeadlineDate", type date},
        {"CompletionDate", type date},
        {"BudgetINR", type number},
        {"ActualCostINR", type number},
        {"PercentComplete", Int64.Type},
        {"Status", type text},
        {"RiskLevel", type text}
        },
        "en-US"
    )
in
    Typed
