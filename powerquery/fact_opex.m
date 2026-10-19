// ALL DATA IS SYNTHETIC (invented offices, people and figures). Phase 3 Power Query (M).
// Syntax-reviewed on macOS only: NOT executed in Power Query / Power BI yet.
// Query name: fact_opex   (source: data/clean/fact_opex.csv)
let
    Source = fnLoadCsv("fact_opex.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
        {"OpexID", type text},
        {"LocationID", type text},
        {"MonthStart", type date},
        {"CategoryID", type text},
        {"ActualCostINR", type number},
        {"DataQualityFlag", type text}
        },
        "en-US"
    )
in
    Typed
