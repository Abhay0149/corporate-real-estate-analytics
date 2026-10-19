from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard_utils import (
    AS_OF_DATE,
    budget_variance_label,
    calculate_kpis,
    filter_tables,
    load_tables,
    monthly_energy_summary,
    monthly_cost_summary,
    office_kpi_export,
    office_summary,
    overdue_projects,
    portfolio_findings,
    cost_variance_export,
    project_risk_export,
    quality_summary_export,
    recorded_quality_result,
    safe_ratio,
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data' / 'clean'
QUALITY_DIR = ROOT / 'data' / 'quality'

st.set_page_config(
    page_title='Corporate Real Estate Analytics',
    page_icon='🏢',
    layout='wide',
    initial_sidebar_state='expanded',
)
st.markdown(
    '''<style>
.app-title{font-size:2rem;font-weight:650;line-height:1.15;letter-spacing:-.02em;margin:.1rem 0 .2rem;color:#e7eef7}
.app-subtitle{color:#a9bbcf;font-size:1rem;margin:0 0 .7rem}
.synthetic-banner{background:#332b16;color:#ffe6a0;border:1px solid #806829;border-radius:8px;padding:8px 12px;margin:0 0 .45rem;font-weight:600;font-size:.9rem}
</style>''',
    unsafe_allow_html=True,
)
px.defaults.template = 'plotly_dark'
# The supported minimum Streamlit release accepts these container-width flags.
TABLE_WIDTH = {'use_container_width': True}
BUTTON_WIDTH = {'use_container_width': True}


def inr_m(value):
    if pd.isna(value):
        return '—'
    return f'₹{value / 1_000_000:,.1f}M'


def pct(value, signed=False):
    if pd.isna(value):
        return '—'
    return f'{value:+.1%}' if signed else f'{value:.1%}'


def render_chart(fig, key=None):
    """Apply shared chart spacing and render responsively inside a light frame."""
    fig.update_layout(
        autosize=True,
        font=dict(family='sans-serif', size=12, color='#D8E1EC'),
        margin=dict(l=18, r=20, t=28, b=24),
    )
    fig.update_xaxes(automargin=True, gridcolor='rgba(148,163,184,0.16)')
    fig.update_yaxes(automargin=True, gridcolor='rgba(148,163,184,0.16)')
    with st.container(border=True):
        st.plotly_chart(
            fig, use_container_width=True, key=key,
            config={'responsive': True, 'displayModeBar': False},
        )


@st.cache_data(show_spinner='Loading clean datasets…')
def cached_load_all(data_dir, data_signature):
    return load_tables(data_dir)

try:
    csv_signature = tuple(
        (path.name, path.stat().st_mtime_ns, path.stat().st_size)
        for path in sorted(DATA_DIR.glob('*.csv'))
    )
    tables = cached_load_all(str(DATA_DIR), csv_signature)
except (OSError, ValueError, KeyError) as exc:
    st.error(
        f'Could not load the clean CSV datasets from {DATA_DIR}. '
        f'Check that the project ZIP was extracted fully. Details: {exc}'
    )
    st.stop()

locations = tables['dim_location']
regions = sorted(locations.Region.dropna().unique().tolist())
offices = locations.sort_values('OfficeName')
office_ids = offices.LocationID.tolist()
duplicate_cities = set(offices.loc[offices.City.duplicated(keep=False), 'City'])
office_display_names = offices.set_index('LocationID').apply(
    lambda row: row.OfficeName if row.City in duplicate_cities else row.City, axis=1
).to_dict()
categories = tables['dim_cost_category'].sort_values('CategoryName')
category_ids = categories.CategoryID.tolist()
category_names = categories.set_index('CategoryID').CategoryName.to_dict()
min_month = pd.Timestamp(tables['dim_date'].MonthStart.min())
max_month = pd.Timestamp(tables['dim_date'].MonthStart.max())
min_date = min_month.date()
max_date = (max_month + pd.offsets.MonthEnd(0)).date()

with st.sidebar:
    st.header('Portfolio filters')
    if st.button('Reset all filters', **BUTTON_WIDTH):
        st.session_state['filter_regions'] = regions
        st.session_state['filter_offices'] = office_ids
        st.session_state['filter_dates'] = (min_date, max_date)
        st.session_state['filter_categories'] = category_ids
        st.rerun()
    with st.expander('Filters', expanded=False):
        selected_regions = st.multiselect(
            'Region', regions, default=regions, key='filter_regions',
            help='Choose one or more regions. Clear the field to show no regions.',
        )
        selected_offices = st.multiselect(
            'Office', office_ids, format_func=office_display_names.get, default=office_ids,
            key='filter_offices',
            help='Unique city names keep selected tags compact. Choices stay stable when Region changes; selections intersect.',
        )
        date_range = st.date_input(
            'Reporting period', value=(min_date, max_date), min_value=min_date,
            max_value=max_date, key='filter_dates',
            help='Monthly data includes every month touched by the selected start and end dates.',
        )
        selected_categories = st.multiselect(
            'Cost categories', category_ids, format_func=category_names.get,
            default=category_ids, key='filter_categories',
            help='This selection filters operating cost and budget views. Workplace and electricity-use measures do not have a cost-category grain.',
        )
    st.divider()
    st.caption('Project overdue status uses the fixed as-of date: 30 Sep 2026.')
    st.caption('Currency: INR. International offices use a fixed assumed exchange rate; FX movements are not modelled.')

if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date = pd.Timestamp(date_range[0]).replace(day=1)
    end_date = pd.Timestamp(date_range[1])
elif isinstance(date_range, (tuple, list)) and len(date_range) == 1:
    start_date = pd.Timestamp(date_range[0]).replace(day=1)
    end_date = pd.Timestamp(date_range[0])
else:
    start_date, end_date = min_month, max_month

filtered = filter_tables(
    tables,
    selected_regions,
    selected_offices,
    start_date,
    end_date,
    selected_categories,
)
if filtered['dim_location'].empty:
    st.warning('No offices match the selected region and office filters. Select at least one matching office.')
    st.stop()
if filtered['fact_space_usage'].empty:
    st.warning('No monthly usage data matches this reporting period. Choose a period covered by the dataset.')
    st.stop()

kpis = calculate_kpis(filtered)
has_cost_data = not filtered['fact_opex'].empty and not filtered['fact_budget'].empty

st.markdown(
    '<div class="app-title">Corporate Real Estate Intelligence</div>'
    '<div class="app-subtitle">Portfolio, workplace and cost analytics for a fictional multi-office estate</div>'
    '<div class="synthetic-banner">SYNTHETIC DEMO DATA — all offices, people and financial figures are fictional, not company data.</div>',
    unsafe_allow_html=True,
)
scope = (
    f'{start_date:%d %b %Y} – {end_date:%d %b %Y} · '
    f'{kpis["office_count"]} offices across {len(selected_regions)} regions · '
    f'{len(selected_categories)} cost categories'
)
st.caption(f'Current view: {scope} · Project snapshot: 30 Sep 2026')

tab_exec, tab_work, tab_cost, tab_energy, tab_projects, tab_quality = st.tabs(
    ['Executive overview', 'Workplace & space', 'Cost & budget', 'Energy analytics', 'Project portfolio', 'Data quality']
)

with tab_exec:
    st.subheader('Executive overview')
    st.caption('Portfolio snapshot measures count selected offices once; rate measures use office-month totals.')
    kpi_columns = st.columns(3)
    kpi_columns[0].metric('Offices', f'{kpis["office_count"]:,}')
    kpi_columns[1].metric('Gross floor area', f'{kpis["floor_area"]:,.0f} m²')
    kpi_columns[2].metric('Desk utilisation', pct(kpis['desk_utilisation']))
    kpi_columns = st.columns(3)
    kpi_columns[0].metric(
        'Actual operating cost',
        inr_m(kpis['actual_cost']) if has_cost_data else '—',
        help='INR, shown in millions. Cost-category filters apply to this measure.',
    )
    variance_text = budget_variance_label(kpis['variance_pct']) if has_cost_data else 'No cost categories selected'
    variance_color = 'inverse' if kpis['variance'] > 0 else 'normal'
    kpi_columns[1].metric(
        'Budget variance',
        inr_m(kpis['variance']) if has_cost_data else '—',
        variance_text,
        delta_color=variance_color if kpis['variance'] != 0 else 'off',
        help='Absolute variance is actual cost minus budget. Positive means overspend; negative means underspend.',
    )
    kpi_columns[2].metric('Overdue projects', f'{kpis["overdue_projects"]:,}')

    st.markdown('#### Key findings')
    findings = portfolio_findings(filtered)
    if findings:
        for finding in findings[:4]:
            st.info(finding, icon='🔎')
    else:
        st.info('No cost, utilisation, or overdue-project findings are available for this selected scope.')
    st.caption('Findings describe filtered synthetic records; they do not explain causes or represent real-company outcomes.')

    loc = filtered['dim_location']
    category_dim = filtered['dim_cost_category']
    opex = filtered['fact_opex'].merge(
        loc[['LocationID', 'OfficeName', 'Region']], on='LocationID', how='left'
    ).merge(category_dim[['CategoryID', 'CategoryName', 'CostGroup']], on='CategoryID', how='left')
    budget = filtered['fact_budget'].merge(
        loc[['LocationID', 'OfficeName', 'Region']], on='LocationID', how='left'
    ).merge(category_dim[['CategoryID', 'CategoryName', 'CostGroup']], on='CategoryID', how='left')
    usage = filtered['fact_space_usage'].merge(
        loc[['LocationID', 'OfficeName', 'Region', 'City', 'Country', 'FloorAreaM2', 'UsableAreaM2', 'Desks']],
        on='LocationID',
        how='left',
    )
    projects = filtered['fact_projects'].merge(
        loc[['LocationID', 'OfficeName', 'Region']], on='LocationID', how='left'
    )

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown('#### Monthly operating cost vs budget')
        monthly = monthly_cost_summary(filtered)
        if monthly.empty:
            st.info('No cost and budget records match the selected cost categories.')
        else:
            monthly['Month'] = monthly.MonthStart.dt.strftime('%b %Y')
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=monthly.Month,
                    y=monthly.Actual / 1_000_000,
                    name='Actual',
                    mode='lines+markers',
                    line=dict(width=2.5, color='#56b4e9'),
                    hovertemplate='%{x}<br>Actual: ₹%{y:,.1f}M<extra></extra>',
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=monthly.Month,
                    y=monthly.Budget / 1_000_000,
                    name='Budget',
                    mode='lines+markers',
                    line=dict(width=2.5, dash='dash', color='#f0b44d'),
                    hovertemplate='%{x}<br>Budget: ₹%{y:,.1f}M<extra></extra>',
                )
            )
            fig.update_layout(
                height=360,
                yaxis_title='INR (millions)',
                xaxis_title='Month',
                legend=dict(orientation='h', y=1.12),
                margin=dict(l=10, r=10, t=25, b=10),
            )
            render_chart(fig, key='executive_monthly_cost')
    with right:
        st.markdown('#### Cost category spend vs budget')
        if opex.empty and budget.empty:
            st.info('No cost and budget records match the selected cost categories.')
        else:
            by_category = opex.groupby('CategoryName', as_index=False).ActualCostINR.sum()
            by_category = by_category.rename(columns={'ActualCostINR': 'Actual'})
            category_budget = budget.groupby('CategoryName', as_index=False).BudgetINR.sum()
            category_budget = category_budget.rename(columns={'BudgetINR': 'Budget'})
            by_category = by_category.merge(category_budget, on='CategoryName', how='outer')
            by_category = by_category.sort_values('Actual', na_position='first')
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=by_category.Actual / 1_000_000,
                y=by_category.CategoryName,
                name='Actual',
                orientation='h',
                marker_color='#56b4e9',
                hovertemplate='%{y}<br>Actual: ₹%{x:,.1f}M<extra></extra>',
            ))
            fig.add_trace(go.Bar(
                x=by_category.Budget / 1_000_000,
                y=by_category.CategoryName,
                name='Budget',
                orientation='h',
                marker_color='#f0b44d',
                hovertemplate='%{y}<br>Budget: ₹%{x:,.1f}M<extra></extra>',
            ))
            fig.update_layout(
                barmode='group',
                height=360,
                xaxis_title='INR (millions)',
                yaxis_title='',
                legend=dict(orientation='h', y=1.12),
                margin=dict(l=10, r=10, t=25, b=10),
            )
            render_chart(fig, key='executive_category_cost')

    st.markdown('#### Office performance')
    office = office_summary(filtered)
    office_view = office[
        ['OfficeName', 'Region', 'DeskUtilisation', 'ActualCostINR', 'BudgetINR', 'VarianceINR', 'VariancePct', 'OpexPerM2Month']
    ].copy()
    office_view['DeskUtilisation'] = office_view.DeskUtilisation.map(pct)
    office_view['VariancePct'] = office_view.VariancePct.map(lambda value: pct(value, signed=True))
    for column in ['ActualCostINR', 'BudgetINR', 'VarianceINR']:
        office_view[column] = office_view[column].map(inr_m)
    office_view['OpexPerM2Month'] = office_view.OpexPerM2Month.map(
        lambda value: f'₹{value:,.1f}' if pd.notna(value) else '—'
    )
    office_view = office_view.rename(columns={
        'OfficeName': 'Office',
        'DeskUtilisation': 'Desk utilisation',
        'ActualCostINR': 'Actual cost',
        'BudgetINR': 'Budget',
        'VarianceINR': 'Variance (INR)',
        'VariancePct': 'Variance (%)',
        'OpexPerM2Month': 'Opex / m² / month',
    })
    office_export = office_kpi_export(filtered)
    st.download_button(
        'Download office KPI summary (CSV)', office_export.to_csv(index=False),
        file_name='office_kpi_summary.csv', mime='text/csv', key='download_office_kpis',
    )
    st.dataframe(office_view, hide_index=True, **TABLE_WIDTH)
    st.caption('Positive variance is overspend. A missing budget is displayed as unavailable, not as zero.')

with tab_work:
    st.subheader('Workplace and space analytics')
    st.caption(
        'Desk utilisation = average daily occupied desks ÷ available desk-months. '
        'Headcount is assigned employees, not a measurement of people physically present.'
    )
    office = office_summary(filtered).sort_values('DeskUtilisation', na_position='last')
    left, right = st.columns([1.15, 1])
    with left:
        st.markdown('#### Desk utilisation by office')
        office_rates = office.dropna(subset=['DeskUtilisation'])
        if office_rates.empty:
            st.info('No desk-utilisation records are available for this selection.')
        else:
            fig = px.bar(
                office_rates,
                x='DeskUtilisation',
                y='OfficeName',
                color='Region',
                orientation='h',
                labels={'DeskUtilisation': 'Occupied desks / available desk-months', 'OfficeName': 'Office'},
                hover_data={'DeskUtilisation': ':.1%', 'City': True, 'Country': True, 'HeadcountMonths': ':,.0f'},
            )
            fig.update_layout(height=max(360, 34 * len(office_rates)), xaxis_tickformat='.0%')
            render_chart(fig, key='workplace_office_utilisation')
    with right:
        st.markdown('#### Monthly desk utilisation')
        monthly_usage = usage.groupby('MonthStart', as_index=False).agg(
            Occupied=('AvgDailyOccupiedDesks', 'sum'),
            Capacity=('Desks', 'sum'),
        )
        monthly_usage['DeskUtilisation'] = monthly_usage.Occupied / monthly_usage.Capacity.where(monthly_usage.Capacity.ne(0))
        if monthly_usage.empty:
            st.info('No monthly usage records are available for this selection.')
        else:
            fig = px.line(
                monthly_usage,
                x='MonthStart',
                y='DeskUtilisation',
                markers=True,
                labels={'MonthStart': 'Month', 'DeskUtilisation': 'Desk utilisation'},
                hover_data={'DeskUtilisation': ':.1%', 'Occupied': ':,.0f', 'Capacity': ':,.0f'},
            )
            fig.update_layout(height=360, yaxis_tickformat='.0%')
            render_chart(fig, key='workplace_monthly_utilisation')

    st.markdown('#### Assigned headcount vs desk capacity')
    capacity = office.dropna(subset=['UsageMonths']).copy()
    capacity['Average assigned headcount'] = capacity.HeadcountMonths / capacity.UsageMonths
    capacity_long = capacity.melt(
        id_vars=['OfficeName'],
        value_vars=['Average assigned headcount', 'Desks'],
        var_name='Measure',
        value_name='People / desks',
    )
    if capacity_long.empty:
        st.info('No office-month headcount or capacity data is available for this selection.')
    else:
        fig = px.bar(
            capacity_long,
            x='OfficeName',
            y='People / desks',
            color='Measure',
            barmode='group',
            labels={'OfficeName': 'Office', 'People / desks': 'Average people or available desks'},
            color_discrete_map={'Average assigned headcount': '#56b4e9', 'Desks': '#f0b44d'},
        )
        fig.update_layout(height=380, xaxis_tickangle=-35)
        render_chart(fig, key='workplace_capacity')

    st.markdown('#### Space and headcount indicators')
    office_query = st.text_input('Find an office', key='office_search')
    area_per_employee = office[['OfficeName', 'HeadcountMonths', 'UsageMonths', 'UsableAreaM2']].copy()
    area_per_employee['Usable m² per assigned employee'] = (
        area_per_employee.UsableAreaM2 * area_per_employee.UsageMonths
    ) / area_per_employee.HeadcountMonths.where(area_per_employee.HeadcountMonths.ne(0))
    if office_query.strip():
        area_per_employee = area_per_employee[
            area_per_employee.OfficeName.str.contains(office_query.strip(), case=False, na=False)
        ]
    if area_per_employee.empty:
        st.info('No offices match that search.')
    st.dataframe(
        area_per_employee[['OfficeName', 'HeadcountMonths', 'Usable m² per assigned employee']]
        .rename(columns={'OfficeName': 'Office', 'HeadcountMonths': 'Headcount-months'})
        .round(2),
        hide_index=True,
        **TABLE_WIDTH,
    )
    st.caption(
        'Headcount-months sum assigned employees across office-months. '
        'Fixed desk capacity is counted once per office-month; the category filter does not affect these measures.'
    )

with tab_cost:
    st.subheader('Cost and budget')
    if not has_cost_data:
        st.info('No cost categories are selected. Choose at least one category to view cost and budget comparisons.')

    office = office_summary(filtered)
    left, right = st.columns([1.2, 1])
    with left:
        st.markdown('#### Actual cost and budget by office')
        office_cost = office[['OfficeName', 'ActualCostINR', 'BudgetINR']].melt(
            id_vars=['OfficeName'],
            var_name='Measure',
            value_name='INR',
        )
        if office_cost.INR.notna().any():
            office_cost['Measure'] = office_cost.Measure.map({'ActualCostINR': 'Actual', 'BudgetINR': 'Budget'})
            office_cost['INRMillions'] = office_cost.INR / 1_000_000
            office_order = (
                office.sort_values('ActualCostINR', ascending=True, na_position='first').OfficeName.tolist()
            )
            fig = px.bar(
                office_cost,
                x='INRMillions',
                y='OfficeName',
                color='Measure',
                barmode='group',
                orientation='h',
                category_orders={'OfficeName': office_order, 'Measure': ['Actual', 'Budget']},
                labels={'OfficeName': 'Office', 'INRMillions': 'INR (millions)', 'Measure': ''},
                hover_data={'INR': ':,.0f', 'INRMillions': False},
                color_discrete_map={'Actual': '#56b4e9', 'Budget': '#f0b44d'},
            )
            fig.update_traces(
                hovertemplate='%{y}<br>%{fullData.name}: ₹%{customdata[0]:,.0f}<extra></extra>'
            )
            fig.update_layout(height=460, xaxis_title='Cost (INR, millions)')
            fig.update_xaxes(tickprefix='₹', ticksuffix='M')
            render_chart(fig, key='cost_office_actual_budget')
        else:
            st.info('No office cost or budget records match the selected categories.')
    with right:
        st.markdown('#### Budget variance by category')
        actual_category = opex.groupby('CategoryName', as_index=False).ActualCostINR.sum()
        actual_category = actual_category.rename(columns={'ActualCostINR': 'Actual'})
        budget_category = budget.groupby('CategoryName', as_index=False).BudgetINR.sum()
        budget_category = budget_category.rename(columns={'BudgetINR': 'Budget'})
        category_variance = actual_category.merge(budget_category, on='CategoryName', how='outer')
        category_variance['VarianceINR'] = category_variance.Actual - category_variance.Budget
        category_variance['VariancePct'] = category_variance.VarianceINR / category_variance.Budget.where(category_variance.Budget.ne(0))
        category_variance['Budget status'] = category_variance.VarianceINR.map(
            lambda value: 'Above budget' if pd.notna(value) and value > 0
            else ('Below budget' if pd.notna(value) and value < 0
                  else ('On budget' if pd.notna(value) else 'Budget unavailable'))
        )
        if category_variance.empty:
            st.info('No category-level cost or budget records are available.')
        else:
            fig = px.bar(
                category_variance.sort_values('VarianceINR', na_position='first'),
                x='VarianceINR',
                y='CategoryName',
                color='Budget status',
                orientation='h',
                color_discrete_map={
                    'Above budget': '#E9A23B',
                    'Below budget': '#39B7B0',
                    'On budget': '#8492A6',
                    'Budget unavailable': '#64748B',
                },
                labels={'VarianceINR': 'Actual minus budget (INR)', 'CategoryName': ''},
                hover_data={'VariancePct': ':+.1%', 'Actual': ':,.0f', 'Budget': ':,.0f'},
            )
            fig.add_vline(x=0, line_dash='dash', line_color='#E7EEF7', line_width=2)
            fig.update_layout(height=360, legend_title_text='Budget status')
            render_chart(fig, key='cost_category_variance')
            st.caption('Variance = actual minus budget. Positive is above budget (amber); negative is below budget (teal); zero is on budget (slate). Labels and hover values state the status and amounts.')

    st.markdown('#### Office variance: INR and percentage')
    variance_table = office[['OfficeName', 'ActualCostINR', 'BudgetINR', 'VarianceINR', 'VariancePct']].copy()
    variance_table = variance_table.sort_values('VarianceINR', ascending=False, na_position='last')
    variance_table['VariancePct'] = variance_table.VariancePct.map(lambda value: pct(value, signed=True))
    for column in ['ActualCostINR', 'BudgetINR', 'VarianceINR']:
        variance_table[column] = variance_table[column].map(inr_m)
    st.dataframe(
        variance_table.rename(columns={
            'OfficeName': 'Office',
            'ActualCostINR': 'Actual cost',
            'BudgetINR': 'Budget',
            'VarianceINR': 'Variance (INR)',
            'VariancePct': 'Variance (%)',
        }),
        hide_index=True,
        **TABLE_WIDTH,
    )
    cost_export = cost_variance_export(filtered)
    st.download_button(
        'Download office and category variance (CSV)', cost_export.to_csv(index=False),
        file_name='cost_budget_variance.csv', mime='text/csv', key='download_cost_variance',
    )
    st.caption('Variance (INR) is actual minus budget; variance (%) divides that difference by budget. Missing or zero budgets have no percentage.')

with tab_energy:
    st.subheader('Energy analytics')
    st.caption('Metered electricity is aggregated at office-month grain and is independent of cost-category selection.')
    energy_monthly = monthly_energy_summary(filtered)
    monthly_energy = energy_monthly[['MonthStart', 'ElectricityKWh']]
    intensity = office[['OfficeName', 'KWh', 'FloorAreaM2', 'UsageMonths']].copy()
    intensity['kWh per m² per month'] = intensity.KWh / (
        intensity.FloorAreaM2 * intensity.UsageMonths.where(intensity.UsageMonths.ne(0))
    )
    energy_left, energy_right = st.columns(2)
    with energy_left:
        st.markdown('#### Monthly electricity use')
        if monthly_energy.empty:
            st.info('No metered electricity data is available for this period.')
        else:
            fig = px.line(
                monthly_energy,
                x='MonthStart',
                y='ElectricityKWh',
                markers=True,
                labels={'MonthStart': 'Month', 'ElectricityKWh': 'Metered electricity (kWh)'},
                hover_data={'ElectricityKWh': ':,.0f'},
            )
            fig.update_layout(height=360)
            render_chart(fig, key='energy_monthly_consumption')
    with energy_right:
        st.markdown('#### Electricity intensity by office')
        intensity = intensity.dropna(subset=['kWh per m² per month']).sort_values('kWh per m² per month')
        if intensity.empty:
            st.info('No energy-intensity values can be calculated for this selection.')
        else:
            fig = px.bar(
                intensity,
                x='kWh per m² per month',
                y='OfficeName',
                orientation='h',
                labels={'kWh per m² per month': 'Metered kWh / gross area / month', 'OfficeName': 'Office'},
                hover_data={'KWh': ':,.0f', 'UsageMonths': True},
            )
            fig.update_layout(height=max(360, 32 * len(intensity)))
            render_chart(fig, key='energy_office_intensity')
    monthly_intensity = energy_monthly.rename(
        columns={'EnergyIntensityKWhPerM2Month': 'kWh per m² per month'}
    )
    st.markdown('#### Monthly energy intensity')
    if monthly_intensity.empty:
        st.info('No monthly energy-intensity values are available for this selection.')
    else:
        fig = px.line(
            monthly_intensity, x='MonthStart', y='kWh per m² per month', markers=True,
            labels={'MonthStart': 'Month', 'kWh per m² per month': 'Metered kWh / gross floor area / month'},
            hover_data={'ElectricityKWh': ':,.0f', 'GrossFloorAreaM2': ':,.0f'},
        )
        fig.update_layout(height=340)
        render_chart(fig, key='energy_monthly_intensity')
    st.caption(
        'Energy intensity is metered kWh divided by gross floor-area months (kWh/m²/month). '
        'It is a measured-use comparison, not a stand-alone environmental efficiency rating. '
        'Energy use is independent of cost-category selection.'
    )

with tab_projects:
    st.subheader('Improvement project portfolio')
    st.caption(
        'Project status is assessed as of 30 Sep 2026. Projects are filtered by selected offices, '
        'not by the monthly reporting-period or cost-category filters.'
    )
    project_search = st.text_input('Find a project, office or ID', key='project_search')
    if project_search.strip():
        match = projects[['ProjectID', 'ProjectName', 'OfficeName']].astype(str).apply(
            lambda column: column.str.contains(project_search.strip(), case=False, na=False)
        ).any(axis=1)
        projects = projects[match].copy()
    project_overdue = overdue_projects(projects)
    project_columns = st.columns(3)
    project_columns[0].metric('Projects in selected offices', f'{len(projects):,}')
    project_columns[1].metric('High risk', f'{int(projects.RiskLevel.eq("High").sum()):,}')
    project_columns[2].metric('Overdue open projects', f'{len(project_overdue):,}')
    if projects.empty:
        st.info('No projects are assigned to the selected offices.')
    else:
        project_chart = projects.copy()
        project_chart['BudgetConsumed'] = project_chart.apply(
            lambda row: safe_ratio(row.ActualCostINR, row.BudgetINR), axis=1
        )
        left, right = st.columns(2)
        with left:
            st.markdown('#### Project status by recorded risk')
            status = project_chart.groupby(['Status', 'RiskLevel'], as_index=False).size()
            fig = px.bar(
                status,
                x='Status',
                y='size',
                color='RiskLevel',
                barmode='stack',
                category_orders={'RiskLevel': ['Low', 'Medium', 'High']},
                labels={'size': 'Projects', 'Status': 'Project status', 'RiskLevel': 'Recorded risk'},
                color_discrete_map={'Low': '#56b4e9', 'Medium': '#f0b44d', 'High': '#e76f51'},
            )
            fig.update_layout(height=360)
            render_chart(fig, key='project_status_risk')
        with right:
            st.markdown('#### Spend vs completion progress')
            spend_progress = project_chart.dropna(subset=['BudgetConsumed']).copy()
            if spend_progress.empty:
                st.info('No project budget-consumption ratios can be calculated.')
            else:
                spend_progress['Progress'] = spend_progress.PercentComplete / 100
                fig = px.scatter(
                    spend_progress,
                    x='Progress',
                    y='BudgetConsumed',
                    color='RiskLevel',
                    hover_name='ProjectName',
                    hover_data={
                        'Status': True,
                        'RiskLevel': True,
                        'OfficeName': True,
                        'BudgetINR': ':,.0f',
                        'ActualCostINR': ':,.0f',
                        'Progress': ':.0%',
                        'BudgetConsumed': ':.1%',
                        'ProjectID': True,
                    },
                    labels={
                        'Progress': 'Completion',
                        'BudgetConsumed': 'Actual spend / approved budget',
                        'RiskLevel': 'Recorded risk',
                    },
                    color_discrete_map={'Low': '#56b4e9', 'Medium': '#f0b44d', 'High': '#e76f51'},
                )
                fig.add_shape(
                    type='line', x0=0, y0=0, x1=1, y1=1,
                    line=dict(color='#9fb0c3', dash='dot'),
                )
                fig.add_hline(y=1, line_dash='dash', line_color='#e76f51')
                fig.add_annotation(x=0.98, y=1.02, text='Approved budget limit', showarrow=False, xanchor='right')
                fig.update_layout(
                    height=360,
                    xaxis_tickformat='.0%',
                    yaxis_tickformat='.0%',
                    margin=dict(l=10, r=10, t=10, b=10),
                )
                render_chart(fig, key='project_spend_progress')
                st.caption('Colour shows recorded risk; hover shows project status and values. The 100% line is the approved-budget limit; the diagonal is equal budget consumption and completion progress.')

        project_detail = project_chart.copy()
        project_detail['DaysOverdue'] = 0
        project_detail.loc[project_detail.ProjectID.isin(project_overdue.ProjectID), 'DaysOverdue'] = (
            project_detail.ProjectID.map(project_overdue.set_index('ProjectID').DaysOverdue).fillna(0)
        )
        project_detail['CostVsProgressIndex'] = project_detail.apply(
            lambda row: safe_ratio(row.ActualCostINR, row.BudgetINR * row.PercentComplete / 100),
            axis=1,
        )
        project_detail['RiskPriority'] = project_detail.RiskLevel.map({'High': 0, 'Medium': 1, 'Low': 2})
        project_detail['BudgetStatus'] = project_detail.BudgetConsumed.map(
            lambda value: 'Over approved budget' if pd.notna(value) and value > 1
            else ('Within approved budget' if pd.notna(value) else 'Budget unavailable')
        )
        project_detail['ReviewFlags'] = project_detail.apply(
            lambda row: '; '.join(
                ([f'Overdue {int(row.DaysOverdue)} days'] if row.DaysOverdue > 0 else [])
                + (['Recorded high risk'] if row.RiskLevel == 'High' else [])
                + (['Above approved budget'] if pd.notna(row.BudgetConsumed) and row.BudgetConsumed > 1 else [])
                + (
                    ['Spend ahead of progress']
                    if pd.notna(row.CostVsProgressIndex) and row.CostVsProgressIndex > 1
                    else []
                )
            ) or 'No current review flag',
            axis=1,
        )
        project_detail = project_detail.sort_values(
            ['DaysOverdue', 'RiskPriority', 'ProjectName'],
            ascending=[False, True, True],
        )
        st.markdown('#### Project-level review list')
        project_view = project_detail[
            [
                'ProjectID', 'ProjectName', 'OfficeName', 'Status', 'RiskLevel',
                'PercentComplete', 'BudgetINR', 'ActualCostINR', 'BudgetConsumed',
                'CostVsProgressIndex', 'DaysOverdue', 'BudgetStatus', 'ReviewFlags',
            ]
        ].rename(columns={
            'ProjectID': 'ID',
            'ProjectName': 'Project',
            'OfficeName': 'Office',
            'Status': 'Status',
            'RiskLevel': 'Recorded risk',
            'PercentComplete': 'Progress (%)',
            'BudgetINR': 'Approved budget (INR)',
            'ActualCostINR': 'Actual spend (INR)',
            'BudgetConsumed': 'Budget consumed',
            'CostVsProgressIndex': 'Spend / progress index',
            'DaysOverdue': 'Days overdue',
            'BudgetStatus': 'Approved-budget status',
            'ReviewFlags': 'Review flags',
        })
        st.dataframe(
            project_view.style.format({
                'Progress (%)': '{:.0f}%',
                'Approved budget (INR)': '₹{:,.0f}',
                'Actual spend (INR)': '₹{:,.0f}',
                'Budget consumed': '{:.1%}',
                'Spend / progress index': '{:.2f}',
            }, na_rep='—'),
            hide_index=True,
            **TABLE_WIDTH,
        )
        project_export = project_risk_export(filtered)
        if project_search.strip():
            searchable = project_export[['Project ID', 'Project', 'Office']].astype(str).apply(
                lambda column: column.str.contains(project_search.strip(), case=False, na=False)
            ).any(axis=1)
            project_export = project_export[searchable]
        st.download_button(
            'Download project review list (CSV)', project_export.to_csv(index=False),
            file_name='project_risk_review.csv', mime='text/csv', key='download_project_risk',
        )
        st.caption(
            'Budget consumed >100% means approved budget exceeded. Spend / progress index >1 means spending is ahead of completion progress; '
            'the latter does not by itself mean the approved budget was exceeded. Blank index means no progress-based denominator.'
        )
        st.caption('Review-list ordering is a simple triage order: longest overdue first, then recorded risk and project name. It is not an official risk score.')

with tab_quality:
    st.subheader('Data quality and trust')
    st.markdown(
        'The dashboard loads the cleaned synthetic layer. Interpolated monthly values remain flagged; '
        'invalid project records are quarantined instead of being estimated.'
    )
    quality_table = quality_summary_export(filtered)
    quality_table['Imputed share'] = quality_table['Imputed share'].map(pct)

    report_path = ROOT / 'docs' / 'data_quality_report.md'
    report_result = recorded_quality_result(report_path) if report_path.is_file() else None
    quarantine_path = QUALITY_DIR / 'quarantined_rows.csv'
    quarantined = pd.read_csv(quarantine_path) if quarantine_path.is_file() else pd.DataFrame()

    quality_columns = st.columns(3)
    if report_result:
        quality_columns[0].metric(
            'Recorded clean-layer checks',
            f'{report_result["passed"]:,} / {report_result["total"]:,}',
            f'{report_result["status"]} · {report_result["failed"]} failed',
        )
    else:
        quality_columns[0].metric('Recorded clean-layer checks', 'Unavailable')
    quality_columns[1].metric('Quarantined raw rows', f'{len(quarantined):,}' if quarantine_path.is_file() else 'Unavailable')
    quality_columns[2].metric('Imputed rows in current view', f'{quality_table["Imputed rows"].sum():,}')
    st.dataframe(quality_table, hide_index=True, **TABLE_WIDTH)
    st.download_button(
        'Download filtered quality summary (CSV)', quality_summary_export(filtered).to_csv(index=False),
        file_name='filtered_data_quality_summary.csv', mime='text/csv', key='download_quality_summary',
    )
    if report_result:
        st.caption(
            'The pass/fail count is read from the checked-in data-quality report; opening this dashboard does not rerun validation.'
        )
    else:
        st.info('No parseable recorded validation result is available; no validation score is inferred.')

    flags = pd.concat(
        [
            filtered[key][['DataQualityFlag']].assign(Dataset=label)
            for key, label in [
                ('fact_space_usage', 'Space usage'),
                ('fact_opex', 'Operating costs'),
                ('fact_budget', 'Budgets'),
            ]
        ],
        ignore_index=True,
    )
    st.markdown('#### Quality flags in the filtered clean data')
    if flags.empty:
        st.info('No quality-flagged rows are present in this filtered data view.')
    else:
        flag_counts = flags.groupby(['Dataset', 'DataQualityFlag'], as_index=False).size()
        fig = px.bar(
            flag_counts,
            x='Dataset',
            y='size',
            color='DataQualityFlag',
            barmode='stack',
            labels={'size': 'Rows', 'DataQualityFlag': 'Cleaning flag'},
            color_discrete_map={'OK': '#56b4e9', 'Imputed': '#f0b44d'},
        )
        fig.update_layout(height=340)
        render_chart(fig, key='quality_flags')

    issues_path = QUALITY_DIR / 'issues_detected.csv'
    if issues_path.is_file():
        issues = pd.read_csv(issues_path)
        st.markdown('#### Recorded cleaning actions')
        actions = issues.groupby(['Rule', 'Action'], as_index=False).size().sort_values('size', ascending=False)
        st.dataframe(actions, hide_index=True, **TABLE_WIDTH)
    if not quarantined.empty:
        st.markdown('#### Quarantined records')
        st.dataframe(
            quarantined[['Table', 'RecordKey']],
            hide_index=True,
            **TABLE_WIDTH,
        )
    st.caption(
        'Quality counts for flags are filter-aware; the validation report, issue log, and quarantined-row total describe the full cleaning run. '
        'Interpolation is an estimate, not an observed value.'
    )

st.divider()
st.caption(
    'Corporate Real Estate Portfolio Analytics · Fictional portfolio · '
    'Project status as of 30 Sep 2026 · International costs use assumed fixed FX rates'
)
