"""Reusable KPI and filtering helpers for the synthetic CRE dashboard."""
from pathlib import Path
import re
from typing import Dict, List, Optional, Union

import pandas as pd

AS_OF_DATE = pd.Timestamp('2026-09-30')


def safe_ratio(numerator: Optional[Union[int, float]], denominator: Optional[Union[int, float]]) -> float:
    """Return a ratio, or NaN when either input is missing or the denominator is zero."""
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return float('nan')
    return float(numerator / denominator)


def budget_variance_label(variance_pct: Optional[float]) -> str:
    """Describe the signed actual-minus-budget percentage without implying overspend is good."""
    if pd.isna(variance_pct):
        return 'Budget unavailable'
    if variance_pct > 0:
        return f'+{variance_pct:.1%} above budget'
    if variance_pct < 0:
        return f'{variance_pct:.1%} below budget'
    return 'On budget'


def recorded_quality_result(report_path: Union[str, Path]) -> Optional[Dict[str, Union[int, str]]]:
    """Parse the last recorded clean-layer validation result; this does not run checks."""
    report = Path(report_path).read_text(encoding='utf-8')
    match = re.search(
        r'Overall result:\s*\*\*(PASS|FAIL)\*\*\s*\((\d+)/(\d+) checks passed\)',
        report,
    )
    if not match:
        return None
    return {
        'status': match.group(1),
        'passed': int(match.group(2)),
        'total': int(match.group(3)),
        'failed': int(match.group(3)) - int(match.group(2)),
    }


def reporting_period_months(start, end):
    """Return inclusive month-start bounds for a reporting period selected by calendar date."""
    start = pd.Timestamp(start).to_period('M').to_timestamp()
    end = pd.Timestamp(end).to_period('M').to_timestamp()
    return start, end


def load_tables(data_dir):
    data_dir = Path(data_dir)
    names = ['dim_location', 'dim_cost_category', 'dim_date', 'fact_space_usage', 'fact_opex', 'fact_budget', 'fact_projects']
    tables = {name: pd.read_csv(data_dir / f'{name}.csv') for name in names}
    for name, cols in {
        'dim_date': ['MonthStart'],
        'fact_space_usage': ['MonthStart'],
        'fact_opex': ['MonthStart'],
        'fact_budget': ['MonthStart'],
        'fact_projects': ['StartDate', 'DeadlineDate', 'CompletionDate'],
    }.items():
        for col in cols:
            tables[name][col] = pd.to_datetime(tables[name][col], errors='coerce')
    return tables


def filter_tables(t, regions=None, offices=None, start=None, end=None, categories=None):
    """Filter by shared dimensions without joining fact tables at incompatible grains."""
    loc = t['dim_location'].copy()
    # None means "no filter supplied"; an empty selection means "select nothing".
    if regions is not None:
        loc = loc[loc.Region.isin(regions)]
    if offices is not None:
        loc = loc[loc.LocationID.isin(offices)]
    loc_ids = set(loc.LocationID)
    start = start if start is not None else t['dim_date'].MonthStart.min()
    end = end if end is not None else t['dim_date'].MonthStart.max()
    start, end = reporting_period_months(start, end)
    dates = set(t['dim_date'].loc[t['dim_date'].MonthStart.between(start, end), 'MonthStart'])
    cats = set(categories) if categories is not None else set(t['dim_cost_category'].CategoryID)
    out = dict(t)
    out['dim_location'] = loc
    out['fact_space_usage'] = t['fact_space_usage'][t['fact_space_usage'].LocationID.isin(loc_ids) & t['fact_space_usage'].MonthStart.isin(dates)].copy()
    location_date_mask_opex = t['fact_opex'].LocationID.isin(loc_ids) & t['fact_opex'].MonthStart.isin(dates)
    location_date_mask_budget = t['fact_budget'].LocationID.isin(loc_ids) & t['fact_budget'].MonthStart.isin(dates)
    out['fact_opex'] = t['fact_opex'][location_date_mask_opex & t['fact_opex'].CategoryID.isin(cats)].copy()
    out['fact_budget'] = t['fact_budget'][location_date_mask_budget & t['fact_budget'].CategoryID.isin(cats)].copy()
    # Electricity tariff is a dedicated KPI: keep CC01 costs available even if the
    # user excludes CC01 from the general cost-category filter.
    out['fact_electricity_opex'] = t['fact_opex'][location_date_mask_opex & t['fact_opex'].CategoryID.eq('CC01')].copy()
    out['fact_projects'] = t['fact_projects'][t['fact_projects'].LocationID.isin(loc_ids)].copy()
    out['dim_cost_category'] = t['dim_cost_category'][t['dim_cost_category'].CategoryID.isin(cats)].copy()
    out['dim_date'] = t['dim_date'][t['dim_date'].MonthStart.isin(dates)].copy()
    return out


def calculate_kpis(t):
    loc = t['dim_location']
    usage = t['fact_space_usage']
    opex = t['fact_opex']
    budget = t['fact_budget']
    projects = t['fact_projects']
    area_months = usage[['LocationID']].merge(loc[['LocationID','FloorAreaM2']], on='LocationID', how='left').FloorAreaM2.sum()
    desk_months = usage[['LocationID']].merge(loc[['LocationID','Desks']], on='LocationID', how='left').Desks.sum()
    occupied = usage.AvgDailyOccupiedDesks.sum()
    actual = opex.ActualCostINR.sum()
    planned = budget.BudgetINR.sum()
    headcount_months = usage.Headcount.sum()
    overdue = overdue_projects(projects)
    return {
        'office_count': int(loc.LocationID.nunique()),
        'floor_area': float(loc.FloorAreaM2.sum()),
        'usable_area': float(loc.UsableAreaM2.sum()),
        'desk_utilisation': safe_ratio(occupied, desk_months),
        'desk_assignment': safe_ratio(headcount_months, desk_months),
        'actual_cost': float(actual),
        'budget': float(planned),
        'variance': float(actual - planned),
        'variance_pct': safe_ratio(actual - planned, planned),
        'opex_per_m2_month': safe_ratio(actual, area_months),
        'opex_per_employee_month': safe_ratio(actual, headcount_months),
        'electricity_kwh': float(usage.ElectricityKWh.sum()),
        'electricity_cost': float(t.get('fact_electricity_opex', opex[opex.CategoryID == 'CC01']).ActualCostINR.sum()),
        'electricity_tariff': safe_ratio(
            t.get('fact_electricity_opex', opex[opex.CategoryID == 'CC01']).ActualCostINR.sum(),
            usage.ElectricityKWh.sum(),
        ),
        'overdue_projects': int(len(overdue)),
        'high_risk_projects': int((projects.RiskLevel == 'High').sum()),
        'imputed_rows': int(sum((df.DataQualityFlag == 'Imputed').sum() for df in [usage, opex, budget] if 'DataQualityFlag' in df)),
        'quality_rows': int(len(usage) + len(opex) + len(budget)),
        'area_months': float(area_months),
        'desk_months': float(desk_months),
    }


def overdue_projects(projects: pd.DataFrame, as_of: pd.Timestamp = AS_OF_DATE) -> pd.DataFrame:
    """Return open, overdue projects with days overdue at the fixed reporting date."""
    overdue = projects.loc[
        projects.Status.isin(['In Progress', 'On Hold'])
        & projects.DeadlineDate.notna()
        & projects.DeadlineDate.lt(as_of)
    ].copy()
    overdue['DaysOverdue'] = (pd.Timestamp(as_of) - overdue.DeadlineDate).dt.days
    return overdue


def office_summary(t):
    loc=t['dim_location']
    u=t['fact_space_usage'].groupby('LocationID', as_index=False).agg(OccupiedDeskMonths=('AvgDailyOccupiedDesks','sum'), HeadcountMonths=('Headcount','sum'), KWh=('ElectricityKWh','sum'), UsageMonths=('MonthStart','nunique'))
    o=t['fact_opex'].groupby('LocationID', as_index=False).agg(ActualCostINR=('ActualCostINR','sum'))
    b=t['fact_budget'].groupby('LocationID', as_index=False).agg(BudgetINR=('BudgetINR','sum'))
    x=loc.merge(u,on='LocationID',how='left').merge(o,on='LocationID',how='left').merge(b,on='LocationID',how='left')
    x['DeskUtilisation']=x.OccupiedDeskMonths/(x.Desks*x.UsageMonths.where(x.UsageMonths.ne(0)))
    x['VarianceINR']=x.ActualCostINR-x.BudgetINR
    x['VariancePct']=x.VarianceINR/x.BudgetINR.where(x.BudgetINR.ne(0))
    x['OpexPerM2Month']=x.ActualCostINR/(x.FloorAreaM2*x.UsageMonths.where(x.UsageMonths.ne(0)))
    return x


def office_kpi_export(t: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return a filter-scoped, numeric office KPI table suitable for CSV export."""
    columns = {
        'OfficeName': 'Office', 'Region': 'Region', 'FloorAreaM2': 'Gross floor area (m²)',
        'Desks': 'Available desks', 'DeskUtilisation': 'Desk utilisation',
        'ActualCostINR': 'Actual cost (INR)', 'BudgetINR': 'Budget (INR)',
        'VarianceINR': 'Variance (INR)', 'VariancePct': 'Variance (%)',
        'OpexPerM2Month': 'Opex per m² per month (INR)',
    }
    return office_summary(t)[list(columns)].rename(columns=columns)


def cost_variance_export(t: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return filter-scoped office/category actuals, budgets, and actual-minus-budget variance."""
    # Preserve month grain so a missing month's budget cannot disappear into a partial sum.
    keys = ['LocationID', 'CategoryID', 'MonthStart']
    actual = t['fact_opex'].groupby(keys, as_index=False).agg(ActualCostINR=('ActualCostINR', 'sum'))
    budget = t['fact_budget'].groupby(keys, as_index=False).agg(BudgetINR=('BudgetINR', 'sum'))
    result = actual.merge(budget, on=keys, how='outer')
    result = result.merge(t['dim_location'][['LocationID', 'OfficeName', 'Region']], on='LocationID', how='left')
    result = result.merge(t['dim_cost_category'][['CategoryID', 'CategoryName']], on='CategoryID', how='left')
    result['VarianceINR'] = result.ActualCostINR - result.BudgetINR
    result['VariancePct'] = result.VarianceINR / result.BudgetINR.where(result.BudgetINR.ne(0))
    result = result.rename(columns={
        'OfficeName': 'Office', 'CategoryName': 'Cost category',
        'ActualCostINR': 'Actual cost (INR)', 'BudgetINR': 'Budget (INR)',
        'VarianceINR': 'Variance (INR)', 'VariancePct': 'Variance (%)',
    })
    result = result.rename(columns={'MonthStart': 'Month'})
    return result[['Office', 'Region', 'Month', 'Cost category', 'Actual cost (INR)', 'Budget (INR)', 'Variance (INR)', 'Variance (%)']]


def project_risk_export(t: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return filter-scoped project status and risk indicators as of the portfolio snapshot."""
    projects = t['fact_projects'].merge(
        t['dim_location'][['LocationID', 'OfficeName']], on='LocationID', how='inner'
    ).copy()
    if projects.empty:
        return pd.DataFrame(columns=[
            'Project ID', 'Project', 'Office', 'Status', 'Recorded risk', 'Progress (%)',
            'Approved budget (INR)', 'Actual spend (INR)', 'Budget consumed',
            'Spend / progress index', 'Days overdue',
        ])
    overdue = overdue_projects(projects).set_index('ProjectID').DaysOverdue
    projects['BudgetConsumed'] = projects.apply(lambda row: safe_ratio(row.ActualCostINR, row.BudgetINR), axis=1)
    projects['CostVsProgressIndex'] = projects.apply(
        lambda row: safe_ratio(row.ActualCostINR, row.BudgetINR * row.PercentComplete / 100), axis=1
    )
    projects['DaysOverdue'] = projects.ProjectID.map(overdue).fillna(0).astype(int)
    return projects[[
        'ProjectID', 'ProjectName', 'OfficeName', 'Status', 'RiskLevel', 'PercentComplete',
        'BudgetINR', 'ActualCostINR', 'BudgetConsumed', 'CostVsProgressIndex', 'DaysOverdue',
    ]].rename(columns={
        'ProjectID': 'Project ID', 'ProjectName': 'Project', 'OfficeName': 'Office',
        'RiskLevel': 'Recorded risk', 'PercentComplete': 'Progress (%)',
        'BudgetINR': 'Approved budget (INR)', 'ActualCostINR': 'Actual spend (INR)',
        'BudgetConsumed': 'Budget consumed', 'CostVsProgressIndex': 'Spend / progress index',
        'DaysOverdue': 'Days overdue',
    })


def quality_summary_export(t: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Summarize clean-layer row and imputation counts for the active filter scope."""
    rows = []
    for key, label in [
        ('fact_space_usage', 'Space usage'), ('fact_opex', 'Operating costs'), ('fact_budget', 'Budgets'),
    ]:
        frame = t[key]
        imputed = int(frame.DataQualityFlag.eq('Imputed').sum())
        rows.append({
            'Dataset': label, 'Filtered rows': len(frame), 'Imputed rows': imputed,
            'Imputed share': safe_ratio(imputed, len(frame)),
        })
    return pd.DataFrame(rows)


def portfolio_findings(t: Dict[str, pd.DataFrame]) -> List[str]:
    """Build concise observations from the already-filtered tables."""
    findings = []
    categories = t['dim_cost_category'][['CategoryID', 'CategoryName']]
    costs = t['fact_opex'].merge(categories, on='CategoryID', how='inner')
    if not costs.empty:
        category_costs = costs.groupby('CategoryName').ActualCostINR.sum().sort_values(ascending=False)
        category, amount = category_costs.index[0], category_costs.iloc[0]
        findings.append(f'{category} is the largest cost category at ₹{amount:,.0f} actual spend.')

    offices = office_summary(t)
    overspend = offices.loc[offices.VarianceINR.gt(0)].dropna(subset=['VarianceINR'])
    if not overspend.empty:
        row = overspend.sort_values('VarianceINR', ascending=False).iloc[0]
        pct_text = f' ({row.VariancePct:+.1%})' if pd.notna(row.VariancePct) else ''
        findings.append(
            f'{row.OfficeName} has the largest office overspend at ₹{row.VarianceINR:,.0f}{pct_text}.'
        )

    utilisation = offices.dropna(subset=['DeskUtilisation']).sort_values('DeskUtilisation')
    if not utilisation.empty:
        low, high = utilisation.iloc[0], utilisation.iloc[-1]
        findings.append(
            f'Desk utilisation ranges from {low.OfficeName} at {low.DeskUtilisation:.1%} '
            f'to {high.OfficeName} at {high.DeskUtilisation:.1%}.'
        )

    overdue = overdue_projects(t['fact_projects'])
    if not overdue.empty:
        oldest = overdue.sort_values('DaysOverdue', ascending=False).iloc[0]
        findings.append(
            f'{oldest.ProjectName} is the most overdue open project at {int(oldest.DaysOverdue)} days.'
        )
    return findings


def monthly_cost_summary(t):
    a=t['fact_opex'].groupby('MonthStart',as_index=False).ActualCostINR.sum().rename(columns={'ActualCostINR':'Actual'})
    b=t['fact_budget'].groupby('MonthStart',as_index=False).BudgetINR.sum().rename(columns={'BudgetINR':'Budget'})
    x=a.merge(b,on='MonthStart',how='outer').sort_values('MonthStart')
    x['Variance']=x.Actual-x.Budget
    return x


def monthly_energy_summary(t: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Aggregate electricity and gross-area intensity once per office-month, without cost joins."""
    usage = t['fact_space_usage'].merge(
        t['dim_location'][['LocationID', 'FloorAreaM2']],
        on='LocationID', how='left', validate='many_to_one',
    )
    monthly = usage.groupby('MonthStart', as_index=False).agg(
        ElectricityKWh=('ElectricityKWh', 'sum'),
        GrossFloorAreaM2=('FloorAreaM2', 'sum'),
    )
    monthly['EnergyIntensityKWhPerM2Month'] = (
        monthly.ElectricityKWh / monthly.GrossFloorAreaM2.where(monthly.GrossFloorAreaM2.ne(0))
    )
    return monthly
