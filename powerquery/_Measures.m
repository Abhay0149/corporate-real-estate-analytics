// ALL DATA IS SYNTHETIC (invented offices, people and figures). Phase 3 Power Query (M).
// Syntax-reviewed on macOS only: NOT executed in Power Query / Power BI yet.
// Query name: _Measures   (load to model; unrelated; hosts all DAX measures from dax/measures.dax)
// Hide the Placeholder column after loading.
let
    Source = #table(type table [Placeholder = text], {})
in
    Source
