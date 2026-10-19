// ALL DATA IS SYNTHETIC (invented offices, people and figures). Phase 3 Power Query (M).
// Syntax-reviewed on macOS only: NOT executed in Power Query / Power BI yet.
// Query name: param_AsOfDate   (load to model; leave UNRELATED to every other table)
// One-row table so DAX can read the as-of date: [As Of Date] = MAX(param_AsOfDate[AsOfDate]).
let
    Source = #table(type table [AsOfDate = date], {{AsOfDate}})
in
    Source
