# Power Query and model setup (Phase 3)

> **All data is synthetic.** Offices, people and figures are invented.

**Status: written and structurally reviewed on macOS only. Not executed in Power Query or Power BI.** Power BI Desktop does not run natively on macOS; do the steps below on Windows (or a Windows VM / another supported environment). Treat the first load as the real test.

## 1. Create parameters (Home → Manage Parameters → New Parameter)

| Name | Type | Value |
|---|---|---|
| `DataFolder` | Text | absolute path of `data/clean` on that machine (see `powerquery/p_DataFolder.m`) |
| `AsOfDate` | Date | `2026-09-30` (see `powerquery/p_AsOfDate.m`) |

## 2. Create queries (New Source → Blank Query → Advanced Editor → paste the file)

Create in this order; each file's first lines name the query it must be called.

| Order | File | Query name | Load to model? |
|---|---|---|---|
| 1 | `fnLoadCsv.m` | `fnLoadCsv` | No (function) |
| 2 | `dim_location.m`, `dim_cost_category.m`, `dim_date.m` | same as file | Yes |
| 3 | `fact_space_usage.m`, `fact_opex.m`, `fact_budget.m`, `fact_projects.m` | same as file | Yes |
| 4 | `param_AsOfDate.m` | `param_AsOfDate` | Yes, **no relationships** |
| 5 | `_Measures.m` | `_Measures` | Yes, no relationships; hide `Placeholder` |
| 6 | `qa_row_counts.m` | `qa_row_counts` | Optional; every `Pass` must be `true` |

Transformations: only column typing (culture `en-US`, so ISO dates parse) and blank→null for `CompletionDate`. The clean layer is already a star schema, so no merges or pivots are needed. `DataQualityFlag` is kept so visuals can show or exclude imputed rows.

## 3. Relationships (Model view)

Create these as **many-to-one, single direction** (dimension filters fact):

`dim_location[LocationID]` → `fact_space_usage`, `fact_opex`, `fact_budget`, `fact_projects`
`dim_date[MonthStart]` → `fact_space_usage`, `fact_opex`, `fact_budget`
`dim_cost_category[CategoryID]` → `fact_opex`, `fact_budget`

Do **not** relate `fact_space_usage` to `dim_cost_category` (it has no category), and do not relate `fact_projects` to `dim_date`. This is what makes a category filter change only the cost numerator.

## 4. Measures

Paste `dax/measures.dax` into DAX query view and apply it; then run `tests/dax_validation_checklist.md`.
