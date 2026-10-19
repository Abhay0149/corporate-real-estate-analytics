# Phase 3 overview: SQL, Power Query, DAX and KPI validation

> **All data is synthetic.** Offices, people and figures are invented; nothing here is data from, or a claim about, any real company. Phase 3 adds files only; Phase 2 data, scripts and reports are unchanged (the one documented exception is a wording fix in `docs/data_dictionary.md`).

## What is in Phase 3

| Folder / file | Purpose | Verified how |
|---|---|---|
| `sql/01_schema.sql`, `02_validation.sql`, `03_business_queries.sql` | SQLite model, 38 checks, 15 business queries | **Executed**, compared with pandas |
| `tests/build_database.py` | builds `sql/cre_synthetic.sqlite` from `data/clean/` (generated file, can be deleted) | Executed |
| `tests/kpi_reference.py` | independent pandas implementation of every KPI | Executed |
| `tests/run_phase3_tests.py` | runs everything, writes the report, expected values and checklist | Executed |
| `powerquery/*.m` | parameters, CSV loader, 7 typed table queries, QA query | **Structurally reviewed only; not executed** |
| `dax/measures.dax` | 48 measures | **Structurally reviewed only; not executed** |
| `tests/lint_dax_m.py` | structural review of the M and DAX files (not an engine) | Executed, with self-test |
| `tests/kpi_expected_values.csv` | pandas reference values (long format) | Generated |
| `tests/dax_validation_checklist.md` | expected values to compare in Power BI | **Pending execution on Windows** |
| `docs/sql_model.md`, `powerquery_setup.md`, `dax_measure_catalogue.md`, `phase3_validation_report.md` | documentation and actual test results | |

## Run it (macOS)

```bash
cd corporate-real-estate-analytics
source .venv/bin/activate          # created in Phase 2; needs pandas and numpy only
python tests/run_phase3_tests.py   # builds the DB, runs all tests, rewrites the report
```

SQLite ships with Python, so nothing else needs installing.

## Still requires Power BI (Windows or another supported environment)

1. Load the Power Query files and confirm `qa_row_counts` shows `Pass = true` throughout.
2. Create the relationships in `docs/powerquery_setup.md`.
3. Apply `dax/measures.dax` and fix anything the DAX engine rejects.
4. Compare results with `tests/dax_validation_checklist.md`.

Not started: the dashboard (Phase 4). Nothing has been published or pushed to GitHub.
