// ALL DATA IS SYNTHETIC (invented offices, people and figures). Phase 3 Power Query (M).
// Syntax-reviewed on macOS only: NOT executed in Power Query / Power BI yet.
// Query name: dim_location   (source: data/clean/dim_location.csv)
let
    Source = fnLoadCsv("dim_location.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
        {"LocationID", type text},
        {"OfficeName", type text},
        {"City", type text},
        {"Country", type text},
        {"Region", type text},
        {"OwnershipType", type text},
        {"FloorAreaM2", Int64.Type},
        {"UsableAreaM2", Int64.Type},
        {"Desks", Int64.Type}
        },
        "en-US"
    )
in
    Typed
