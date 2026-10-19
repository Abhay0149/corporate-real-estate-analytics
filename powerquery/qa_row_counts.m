// ALL DATA IS SYNTHETIC (invented offices, people and figures). Phase 3 Power Query (M).
// Syntax-reviewed on macOS only: NOT executed in Power Query / Power BI yet.
// Query name: qa_row_counts   (optional QA table; run it once in Power BI, then you may disable load)
// Row counts and join-key checks. Every row in the result must show Pass = true.
let
    Counts = {
        {"dim_location", Table.RowCount(dim_location), 12},
        {"dim_cost_category", Table.RowCount(dim_cost_category), 5},
        {"dim_date", Table.RowCount(dim_date), 24},
        {"fact_space_usage", Table.RowCount(fact_space_usage), 288},
        {"fact_opex", Table.RowCount(fact_opex), 1440},
        {"fact_budget", Table.RowCount(fact_budget), 1440},
        {"fact_projects", Table.RowCount(fact_projects), 27},
        {"orphans: fact_space_usage -> dim_location",
            Table.RowCount(Table.NestedJoin(fact_space_usage, {"LocationID"}, dim_location, {"LocationID"}, "j", JoinKind.LeftAnti)), 0},
        {"orphans: fact_opex -> dim_location",
            Table.RowCount(Table.NestedJoin(fact_opex, {"LocationID"}, dim_location, {"LocationID"}, "j", JoinKind.LeftAnti)), 0},
        {"orphans: fact_opex -> dim_cost_category",
            Table.RowCount(Table.NestedJoin(fact_opex, {"CategoryID"}, dim_cost_category, {"CategoryID"}, "j", JoinKind.LeftAnti)), 0},
        {"orphans: fact_budget -> dim_date",
            Table.RowCount(Table.NestedJoin(fact_budget, {"MonthStart"}, dim_date, {"MonthStart"}, "j", JoinKind.LeftAnti)), 0},
        {"opex keys without a budget key",
            Table.RowCount(Table.NestedJoin(fact_opex, {"LocationID", "MonthStart", "CategoryID"},
                                            fact_budget, {"LocationID", "MonthStart", "CategoryID"}, "j", JoinKind.LeftAnti)), 0}
    },
    Result = #table(
        type table [Check = text, Actual = Int64.Type, Expected = Int64.Type, Pass = logical],
        List.Transform(Counts, (r) => {r{0}, r{1}, r{2}, r{1} = r{2}})
    )
in
    Result
