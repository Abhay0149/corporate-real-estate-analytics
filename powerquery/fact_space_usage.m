// ALL DATA IS SYNTHETIC (invented offices, people and figures). Phase 3 Power Query (M).
// Syntax-reviewed on macOS only: NOT executed in Power Query / Power BI yet.
// Query name: fact_space_usage   (source: data/clean/fact_space_usage.csv)
let
    Source = fnLoadCsv("fact_space_usage.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
        {"UsageID", type text},
        {"LocationID", type text},
        {"MonthStart", type date},
        {"Headcount", Int64.Type},
        {"AvgDailyOccupiedDesks", Int64.Type},
        {"ElectricityKWh", type number},
        {"DataQualityFlag", type text}
        },
        "en-US"
    )
in
    Typed
