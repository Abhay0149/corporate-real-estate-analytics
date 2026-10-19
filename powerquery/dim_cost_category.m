// ALL DATA IS SYNTHETIC (invented offices, people and figures). Phase 3 Power Query (M).
// Syntax-reviewed on macOS only: NOT executed in Power Query / Power BI yet.
// Query name: dim_cost_category   (source: data/clean/dim_cost_category.csv)
let
    Source = fnLoadCsv("dim_cost_category.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
        {"CategoryID", type text},
        {"CategoryName", type text},
        {"CostGroup", type text},
        {"Description", type text}
        },
        "en-US"
    )
in
    Typed
