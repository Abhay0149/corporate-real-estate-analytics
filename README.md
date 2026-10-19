# Corporate Real Estate Intelligence

A local Streamlit portfolio demonstration for exploring workplace capacity and utilisation, operating costs and budgets, metered electricity use, improvement projects, and data quality across a fictional 12-office portfolio.

> **Synthetic data disclaimer:** all offices, people, projects, and financial and energy figures are fictional. This project is not an internal Siemens Energy system and does not use or describe Siemens Energy data.

## Business questions

- How many offices and how much floor area are in the selected portfolio?
- How does average daily desk use compare with available desk capacity, and how does that change by month?
- Which cost categories and offices contribute most to operating cost or unfavourable budget variance?
- How does metered electricity use and kWh per square metre vary across offices and months?
- Which projects are overdue or recorded as high risk, and is spending ahead of completion progress or above the approved budget?
- Which clean-layer values were interpolated, and what cleaning checks and quarantined records are documented?

## Dashboard

The six tabs share filters for region, office, reporting period, and cost category:

1. **Executive overview** — portfolio KPIs, filter-aware key findings, monthly actual cost versus budget, category spend comparisons, and an office-level performance table.
2. **Workplace & space** — office desk-utilisation comparisons, monthly utilisation trend, assigned headcount versus desk capacity, and usable-area/headcount indicators.
3. **Cost & budget** — office and category actual-versus-budget comparisons, absolute and percentage variance, with missing budgets kept unavailable.
4. **Energy analytics** — monthly metered electricity, office electricity intensity, and monthly energy-intensity trend.
5. **Project portfolio** — project status and recorded risk, budget consumed versus completion progress, overdue days, and project-level review details.
6. **Data quality** — filter-aware imputed-row counts and flags, plus the recorded cleaning-check result, issue actions, and quarantined raw rows.

The sidebar's **Reset all filters** action restores the full reporting scope. Region and office selections intersect; office choices remain available when the region selection changes. A cost-category filter does not change workplace or measured electricity-use figures. Project records are an office-filtered snapshot and are not filtered by the monthly reporting period.

Office KPI, monthly office/category cost variance, project review, and filtered data-quality summaries can be downloaded as CSV files from their respective tabs. Numeric values remain numeric and unavailable values remain blank; cost variance preserves month grain so a missing month's budget remains visible.

Key findings are generated from the current filtered tables. They describe observed values in the synthetic data and do not assert causes or real-world outcomes.

## Data model and KPI definitions

The model is a star schema with dimensions for location, cost category, and month, and facts for space usage, operating cost, budget, and projects. Table grain, columns, relationships, and cleaning policy are documented in [docs/data_dictionary.md](./docs/data_dictionary.md).

- **Desk utilisation** = sum of average daily occupied desks ÷ sum of available desks across office-months. It is not a measure of all people physically present.
- **Assigned headcount** is not physical attendance. Headcount-versus-desk-capacity compares average assigned employees with fixed available desks.
- **Budget variance** = actual operating cost − budget. Positive is above budget (overspend); negative is below budget (underspend). Percentage variance divides this absolute difference by budget; it is unavailable when the denominator is missing or zero.
- **Energy intensity** = metered electricity kWh ÷ gross floor-area months, in kWh/m²/month. It is a comparative use metric, not an environmental-efficiency rating.
- **Project budget consumed** = actual project spend ÷ approved project budget. **Spend / progress index** = actual spend ÷ (approved budget × completion fraction). An index above 1 indicates spending ahead of completion progress; it does not by itself mean the approved budget was exceeded.
- **Overdue projects** are `In Progress` or `On Hold` with a deadline before the fixed as-of date, 30 September 2026.
- Snapshot floor area and desk counts are summed once per office; rate denominators use office-months from the space-usage fact to avoid multiplying capacity by cost-category rows.
- International-office costs use fixed assumed exchange rates into INR; FX movements are not modelled.

The cleaned layer preserves `DataQualityFlag = Imputed`. Imputed values are estimates produced by the documented cleaning workflow, not observed measurements. The full synthetic dataset includes deliberate raw-data issues; see [docs/data_quality_report.md](./docs/data_quality_report.md).

## Technology

- Python, pandas, NumPy
- Streamlit
- Plotly
- SQLite for the documented SQL model and reconciliation checks
- Power Query M and DAX deliverables for a separate Power BI setup

No database service, cloud account, external API, or authentication is required to run the dashboard.

## Run locally on macOS

From the project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run dashboard.py
```

Open the local URL printed by Streamlit (normally `http://localhost:8501`).

## Tests and validation

Activate the project environment, then run:

```bash
python -m unittest tests/test_dashboard.py -v
python tests/run_phase3_tests.py
python -m py_compile dashboard.py dashboard_utils.py tests/test_dashboard.py
python scripts/validate_and_clean.py
```

The dashboard unit tests cover KPI/filter behavior, inclusive final-month filtering, budget variance labels, unavailable ratios, overdue-project rules, filtered findings, office-month energy aggregation, missing-budget handling, and filter-scoped CSV export helpers. The Phase 3 runner executes SQLite validations and business queries, checks SQL/pandas agreement, reconciles the clean CSV totals, and structurally reviews the Power Query and DAX files.

The dashboard reads the last recorded result from `docs/data_quality_report.md`; opening the app does not execute the raw-data cleaning checks. Run `python scripts/validate_and_clean.py` to regenerate the clean data and its quality report. Run `python scripts/generate_data.py` first only when intentionally recreating the synthetic raw input.

**Current verification:** dashboard unit tests, the Phase 3 SQLite/pandas/reconciliation suite, Python syntax compilation, the clean-data validation script, and a Streamlit AppTest run. The local app health endpoint was also checked. **Not tested in a browser or in Power BI:** the M and DAX files are documented and structurally reviewed only; they have not been executed in Power BI or DAX Studio. No deployed environment is part of this project.

## Screenshots

Screenshots have not been added. Capture genuine screenshots from the locally running application if you choose to publish them; do not treat synthetic portfolio results as company data.

## Known limitations

- All source records and project scenarios are synthetic; the deliberately designed patterns illustrate analysis methods, not actual business findings.
- Desk use is an average daily occupied-desk measure. It should not be interpreted as a complete physical-occupancy or attendance count.
- Electricity intensity is measured use per gross floor-area month; the dataset does not provide weather, operating-hour, or occupancy-normalized comparisons.
- Project status is a fixed snapshot as of 30 September 2026. Project history and progress-over-time measures are unavailable.
- International cost conversion uses assumed fixed FX rates; currency movements are omitted.
- Power Query M and DAX require validation in a supported Power BI environment.

## Project contents

```text
dashboard.py               Streamlit application
dashboard_utils.py         Data loading, filtering, and reusable calculations
data/raw/                  Synthetic input with deliberate data-quality issues
data/clean/                Validated dashboard source tables
data/quality/              Detected issues and quarantined records
scripts/                   Seeded generator and cleaning/validation workflow
sql/                       SQLite schema, checks, and business queries
powerquery/                Power Query M definitions
dax/                       DAX measures
tests/                     Dashboard, SQL/pandas reconciliation, and structural checks
docs/                       Data dictionary, setup, and recorded validation documentation
```
