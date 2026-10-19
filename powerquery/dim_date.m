// ALL DATA IS SYNTHETIC (invented offices, people and figures). Phase 3 Power Query (M).
// Syntax-reviewed on macOS only: NOT executed in Power Query / Power BI yet.
// Query name: dim_date   (source: data/clean/dim_date.csv)
let
    Source = fnLoadCsv("dim_date.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
        {"MonthStart", type date},
        {"Year", Int64.Type},
        {"MonthNumber", Int64.Type},
        {"MonthName", type text},
        {"YearMonth", type text},
        {"Quarter", type text},
        {"FiscalYear", type text},
        {"FiscalQuarter", type text},
        {"FiscalMonthNumber", Int64.Type}
        },
        "en-US"
    )
in
    Typed
