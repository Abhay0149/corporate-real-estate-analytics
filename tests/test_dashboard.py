"""Core dashboard KPI tests using the shipped clean synthetic CSVs."""
import unittest
from pathlib import Path
import sys
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dashboard_utils import (
    load_tables, calculate_kpis, filter_tables, office_summary,
    budget_variance_label, reporting_period_months, safe_ratio,
    overdue_projects, portfolio_findings, recorded_quality_result,
    office_kpi_export, cost_variance_export, project_risk_export, quality_summary_export,
    monthly_energy_summary,
)

class DashboardKpiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = load_tables(ROOT / 'data' / 'clean')

    def test_clean_table_row_counts(self):
        expected = {'dim_location':12,'dim_cost_category':5,'dim_date':24,'fact_space_usage':288,'fact_opex':1440,'fact_budget':1440,'fact_projects':27}
        self.assertEqual({k:len(self.tables[k]) for k in expected}, expected)

    def test_portfolio_scenarios(self):
        k = calculate_kpis(self.tables)
        self.assertEqual(k['office_count'], 12)
        self.assertAlmostEqual(k['desk_utilisation'], 0.0 + self.tables['fact_space_usage'].AvgDailyOccupiedDesks.sum() / sum(self.tables['dim_location'].set_index('LocationID').loc[x,'Desks'] for x in self.tables['fact_space_usage'].LocationID), places=12)
        self.assertAlmostEqual(k['actual_cost'] / k['budget'] - 1, 0.0289, delta=0.001)
        self.assertEqual(k['overdue_projects'], 5)
        self.assertEqual(k['high_risk_projects'], 9)

    def test_region_office_date_category_filters(self):
        t = filter_tables(self.tables, regions=['India'], offices=None, start='2025-10-01', end='2025-12-01', categories=['CC01'])
        self.assertTrue(set(t['dim_location'].Region) <= {'India'})
        self.assertEqual(t['fact_opex'].CategoryID.nunique(), 1)
        self.assertTrue(t['fact_opex'].MonthStart.between('2025-10-01','2025-12-01').all())
        self.assertEqual(len(t['fact_space_usage']), len(t['dim_location'])*3)

    def test_reporting_period_includes_all_of_final_selected_month(self):
        start, end = reporting_period_months('2024-10-01', '2026-09-30')
        self.assertEqual(start, pd.Timestamp('2024-10-01'))
        self.assertEqual(end, pd.Timestamp('2026-09-01'))
        t = filter_tables(self.tables, start='2024-10-01', end='2026-09-30')
        self.assertEqual(t['dim_date'].MonthStart.max(), pd.Timestamp('2026-09-01'))
        self.assertTrue((t['fact_space_usage'].MonthStart == pd.Timestamp('2026-09-01')).any())

    def test_budget_variance_labels(self):
        self.assertEqual(budget_variance_label(0.0289), '+2.9% above budget')
        self.assertEqual(budget_variance_label(-0.0289), '-2.9% below budget')
        self.assertEqual(budget_variance_label(0.0), 'On budget')
        self.assertEqual(budget_variance_label(float('nan')), 'Budget unavailable')

    def test_undefined_ratios_remain_undefined(self):
        self.assertTrue(pd.isna(safe_ratio(10, 0)))
        self.assertTrue(pd.isna(safe_ratio(None, 10)))
        t = filter_tables(self.tables, categories=[])
        k = calculate_kpis(t)
        self.assertTrue(pd.isna(k['variance_pct']))
        self.assertEqual(budget_variance_label(k['variance_pct']), 'Budget unavailable')

    def test_overdue_projects_use_open_statuses_and_strict_as_of_date(self):
        projects = pd.DataFrame({
            'ProjectID': ['open', 'on_hold', 'completed', 'not_started', 'today'],
            'ProjectName': ['Open', 'On hold', 'Completed', 'Not started', 'Due today'],
            'Status': ['In Progress', 'On Hold', 'Completed', 'Not Started', 'In Progress'],
            'DeadlineDate': pd.to_datetime([
                '2026-09-29', '2026-09-01', '2026-09-01', '2026-09-01', '2026-09-30',
            ]),
        })
        result = overdue_projects(projects)
        self.assertEqual(result.ProjectID.tolist(), ['open', 'on_hold'])
        self.assertEqual(result.DaysOverdue.tolist(), [1, 29])

    def test_portfolio_findings_follow_filtered_scope(self):
        t = filter_tables(
            self.tables, regions=['India'], offices=['LOC05'],
            start='2024-10-01', end='2026-09-30',
        )
        findings = portfolio_findings(t)
        self.assertTrue(findings)
        self.assertTrue(any('Chennai Service Office' in finding for finding in findings))
        self.assertFalse(any('Pune Operations Campus' in finding for finding in findings))

    def test_recorded_quality_result_is_explicitly_read_from_report(self):
        result = recorded_quality_result(ROOT / 'docs' / 'data_quality_report.md')
        self.assertEqual(result, {'status': 'PASS', 'passed': 36, 'total': 36, 'failed': 0})

    def test_csv_export_helpers_respect_current_filter_scope(self):
        scoped = filter_tables(
            self.tables, regions=['India'], offices=['LOC05'],
            start='2025-10-01', end='2026-09-30', categories=['CC02'],
        )
        office_export = office_kpi_export(scoped)
        self.assertEqual(office_export.Office.tolist(), ['Chennai Service Office'])
        cost_export = cost_variance_export(scoped)
        self.assertEqual(cost_export.Office.unique().tolist(), ['Chennai Service Office'])
        self.assertEqual(cost_export['Cost category'].unique().tolist(), ['Water & Other Utilities'])
        project_export = project_risk_export(scoped)
        self.assertTrue(set(project_export.Office) <= {'Chennai Service Office'})
        quality_export = quality_summary_export(scoped).set_index('Dataset')
        self.assertEqual(quality_export.loc['Space usage', 'Filtered rows'], 12)
        self.assertEqual(quality_export.loc['Operating costs', 'Filtered rows'], 12)

    def test_cost_export_keeps_missing_budget_distinct_from_zero(self):
        scoped = filter_tables(self.tables)
        one_actual_key = scoped['fact_opex'][['LocationID', 'CategoryID', 'MonthStart']].iloc[0]
        mask = ~(
            scoped['fact_budget'].LocationID.eq(one_actual_key.LocationID)
            & scoped['fact_budget'].CategoryID.eq(one_actual_key.CategoryID)
            & scoped['fact_budget'].MonthStart.eq(one_actual_key.MonthStart)
        )
        scoped['fact_budget'] = scoped['fact_budget'].loc[mask].copy()
        result = cost_variance_export(scoped)
        row = result[
            result.Office.eq(scoped['dim_location'].set_index('LocationID').loc[one_actual_key.LocationID, 'OfficeName'])
            & result['Cost category'].eq(scoped['dim_cost_category'].set_index('CategoryID').loc[one_actual_key.CategoryID, 'CategoryName'])
            & result.Month.eq(one_actual_key.MonthStart)
        ].iloc[0]
        self.assertTrue(pd.notna(row['Actual cost (INR)']))
        self.assertTrue(pd.isna(row['Budget (INR)']))
        self.assertTrue(pd.isna(row['Variance (INR)']))

    def test_no_cost_category_fanout_in_office_summary(self):
        x=office_summary(self.tables)
        self.assertEqual(len(x),12)
        self.assertAlmostEqual(x.ActualCostINR.sum(), self.tables['fact_opex'].ActualCostINR.sum(), places=2)
        self.assertTrue(x.DeskUtilisation.between(0,1).all())

    def test_electricity_tariff_filters_cc01(self):
        k=calculate_kpis(self.tables)
        cc01=self.tables['fact_opex'].query("CategoryID == 'CC01'").ActualCostINR.sum()
        kwh=self.tables['fact_space_usage'].ElectricityKWh.sum()
        self.assertAlmostEqual(k['electricity_tariff'],cc01/kwh,places=10)

    def test_empty_region_selection_means_no_results(self):
        t = filter_tables(self.tables, regions=[], offices=None)
        self.assertEqual(len(t['dim_location']), 0)
        self.assertEqual(len(t['fact_space_usage']), 0)
        self.assertEqual(len(t['fact_opex']), 0)

    def test_empty_office_selection_means_no_results(self):
        t = filter_tables(self.tables, regions=['India'], offices=[])
        self.assertEqual(len(t['dim_location']), 0)
        self.assertEqual(len(t['fact_space_usage']), 0)

    def test_empty_category_selection_means_no_costs(self):
        t = filter_tables(self.tables, categories=[])
        self.assertEqual(len(t['fact_opex']), 0)
        self.assertEqual(len(t['fact_budget']), 0)
        self.assertEqual(len(t['fact_electricity_opex']), 288)

    def test_electricity_tariff_ignores_general_category_filter(self):
        t = filter_tables(self.tables, categories=['CC02'])
        k = calculate_kpis(t)
        cc01 = self.tables['fact_opex'].query("CategoryID == 'CC01'").ActualCostINR.sum()
        kwh = self.tables['fact_space_usage'].ElectricityKWh.sum()
        self.assertAlmostEqual(k['electricity_tariff'], cc01 / kwh, places=10)

    def test_monthly_energy_uses_office_month_grain_and_ignores_cost_category_filter(self):
        monthly = monthly_energy_summary(self.tables)
        self.assertEqual(len(monthly), 24)
        first_month = self.tables['fact_space_usage'].MonthStart.min()
        monthly_row = monthly.set_index('MonthStart').loc[first_month]
        first_usage = self.tables['fact_space_usage'].query('MonthStart == @first_month')
        self.assertAlmostEqual(monthly_row.ElectricityKWh, first_usage.ElectricityKWh.sum())
        expected_area = self.tables['dim_location'].FloorAreaM2.sum()
        self.assertAlmostEqual(monthly_row.GrossFloorAreaM2, expected_area)
        self.assertAlmostEqual(monthly_row.EnergyIntensityKWhPerM2Month, first_usage.ElectricityKWh.sum() / expected_area)
        no_categories = filter_tables(self.tables, categories=[])
        self.assertTrue(monthly_energy_summary(no_categories).equals(monthly))

if __name__ == '__main__':
    unittest.main(verbosity=2)
