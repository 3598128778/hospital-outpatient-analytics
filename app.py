from pathlib import Path
import calendar
import json
from datetime import date, timedelta
import pandas as pd
import plotly.express as px
import streamlit as st
from hospital.analytics import totals, change
from hospital.assistant import build_payload, rule_summary, llm_summary
from hospital.config import ROOT

st.set_page_config(page_title='门诊运营分析台', page_icon='🏥', layout='wide')
st.markdown('''<style>
.stApp {background:#f4f7fb;color:#172c43}
[data-testid="stMetric"] {background:white;border:1px solid #dde5ed;border-radius:12px;padding:20px}
[data-testid="stMetricValue"] {color:#087f8c}
h1,h2,h3 {letter-spacing:-.02em}
</style>''', unsafe_allow_html=True)
st.caption('OUTPATIENT INTELLIGENCE / 门诊运营分析台')
st.title('从运营指标，到可核查的线索')
st.caption('模拟数据演示 · 统一口径 · 同比环比 · 科室与时段下钻 · AI 辅助解读')
folder = ROOT / 'artifacts'
if not (folder / 'run_report.json').exists():
    st.info('请先运行 python -m hospital.pipeline --generate，生成演示数据。')
    st.stop()


@st.cache_data
def read_artifacts(version):
    return (pd.read_csv(folder / 'daily_metrics.csv'), pd.read_csv(folder / 'anomalies.csv'),
            pd.read_csv(folder / 'registration_details.csv'), pd.read_csv(folder / 'charge_details.csv'),
            pd.read_csv(folder / 'visit_details.csv'))


daily, alerts, details, charges, visits = read_artifacts((folder / 'run_report.json').stat().st_mtime_ns)
earliest, latest = date.fromisoformat(daily.business_date.min()), date.fromisoformat(daily.business_date.max())
with st.sidebar:
    st.header('分析范围')
    selected = st.date_input('日期区间', value=(max(earliest, latest.replace(day=1)), latest), min_value=earliest, max_value=latest)
    department = st.selectbox('科室', ['全部'] + sorted(daily.department.unique().tolist()))
    period = st.selectbox('挂号时段', ['全部', '上午', '下午', '晚间'])
    st.divider()
    st.caption('门诊量＝有效挂号人次\n\n就诊量＝完成就诊人次\n\n净收费＝支付－退款\n\n客单价＝净收费÷就诊人次')
    st.caption('所有收费归属挂号日期与科室，属于队列口径，不等于财务现金流水。')
if len(selected) != 2:
    st.info('请选择开始日期和结束日期。')
    st.stop()
start, end = selected
dimension = daily.copy()
if department != '全部':
    dimension = dimension[dimension.department == department]
if period != '全部':
    dimension = dimension[dimension.period == period]
filtered = dimension[dimension.business_date.between(str(start), str(end))]
records = filtered.to_dict('records')
metric = totals(records)


def shift_year(day):
    return day.replace(year=day.year - 1, day=min(day.day, calendar.monthrange(day.year - 1, day.month)[1]))


def comparable(a, b):
    if a < earliest or b > latest or (b - a).days != (end - start).days:
        return None
    return totals(dimension[dimension.business_date.between(str(a), str(b))].to_dict('records'))


length = end - start + timedelta(days=1)
previous = comparable(start - length, start - timedelta(days=1))
year_ago = comparable(shift_year(start), shift_year(end))
cards = st.columns(4)
for col, label, key, value in zip(cards, ['门诊量 / 有效挂号', '完成就诊', '净收费金额', '客单价 / 就诊人次'],
        ['registrations', 'visits', 'net_cents', 'avg_spend'],
        [f"{metric['registrations']:,}", f"{metric['visits']:,}", f"¥{metric['net_cents']/100:,.2f}",
         '—' if metric['avg_spend'] is None else f"¥{metric['avg_spend']:,.2f}"]):
    col.metric(label, value)
    comparisons = []
    for name, base in [('前等长期间', previous), ('去年同期', year_ago)]:
        delta = change(metric[key], base[key]) if base and metric[key] is not None else None
        comparisons.append(f'{name}：' + ('不可比' if delta is None else f'{delta:+.1%}'))
    col.caption(' · '.join(comparisons))

overview, drill, quality, assistant = st.tabs(['运营总览', '异常与明细', '数据质量', 'AI 分析助手'])
with overview:
    st.subheader('门诊趋势')
    trend = filtered.groupby('business_date', as_index=False)[['registrations', 'visits', 'net_cents']].sum()
    trend = trend.rename(columns={'registrations': '有效挂号', 'visits': '完成就诊'})
    fig = px.line(trend, x='business_date', y=['有效挂号', '完成就诊'],
                  color_discrete_sequence=['#087f8c', '#ec9a46'], labels={'value': '人次', 'business_date': '日期', 'variable': '指标'})
    fig.update_layout(legend_title_text='', margin=dict(t=15, b=15), paper_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)
    left, right = st.columns(2)
    by_department = filtered.groupby('department', as_index=False)[['visits', 'net_cents']].sum()
    by_department['净收费（元）'] = by_department.net_cents / 100
    left.plotly_chart(px.bar(by_department, x='department', y='净收费（元）', color_discrete_sequence=['#087f8c'],
                           title='科室净收费', labels={'department': '科室'}), use_container_width=True)
    heat = filtered.pivot_table(index='department', columns='period', values='visits', aggfunc='sum', fill_value=0)
    heat = heat.reindex(columns=[p for p in ['上午', '下午', '晚间'] if p in heat.columns])
    right.plotly_chart(px.imshow(heat, text_auto=True, color_continuous_scale='Teal', title='科室 × 时段 · 就诊人次',
                                labels={'x': '时段', 'y': '科室', 'color': '人次'}), use_container_width=True)
    st.subheader('完整自然月：同比与环比')
    monthly_raw = pd.read_csv(folder / 'monthly_metrics.csv')
    if department != '全部':
        monthly_raw = monthly_raw[monthly_raw.department == department]
    if period != '全部':
        monthly_raw = monthly_raw[monthly_raw.period == period]
    # Aggregate before calculating ratios; never average department-level percentages.
    months = monthly_raw.groupby('month')[['registrations', 'visits', 'net_cents']].sum()
    complete = monthly_raw.groupby('month').complete_month.all()
    months['净收费（元）'] = months.net_cents / 100
    for label, offset in [('环比', 1), ('同比', 12)]:
        months[label] = None
        for month in months.index:
            reference = str(pd.Period(month, freq='M') - offset)
            if reference in months.index and complete[month] and complete[reference]:
                value = change(int(months.loc[month, 'net_cents']), int(months.loc[reference, 'net_cents']))
                months.loc[month, label] = '不可比' if value is None else f'{value:+.1%}'
    st.caption('按当前科室和时段聚合；展示与所选日期相交的整月，不截取局部月份。环比/同比针对净收费。')
    st.dataframe(months.loc[str(start)[:7]:str(end)[:7]].drop(columns='net_cents').rename(
        columns={'registrations': '有效挂号', 'visits': '完成就诊'}), use_container_width=True)
    st.download_button('下载当前日粒度指标', filtered.to_csv(index=False).encode('utf-8-sig'), 'filtered_metrics.csv', 'text/csv')

scope_alerts = alerts[alerts.business_date.between(str(start), str(end))]
if department != '全部':
    scope_alerts = scope_alerts[scope_alerts.department == department]
with drill:
    st.subheader('异常线索')
    st.caption('异常按科室全天计算，不受时段筛选影响。基线为过去8个同星期日，至少4个样本；金额字段单位为分。')
    st.dataframe(scope_alerts, use_container_width=True, hide_index=True)
    st.subheader('挂号 → 就诊 → 收费明细')
    st.caption('按左侧日期、科室、时段缩小范围，再选择挂号单查看关联明细。')
    selected_details = details[details.business_date.between(str(start), str(end))]
    if department != '全部':
        selected_details = selected_details[selected_details.department == department]
    if period != '全部':
        selected_details = selected_details[selected_details.period == period]
    st.dataframe(selected_details.head(500), use_container_width=True, hide_index=True)
    st.caption(f'共 {len(selected_details):,} 条挂号，表格显示前500条；下载包含完整筛选结果。')
    st.download_button('下载筛选挂号明细', selected_details.to_csv(index=False).encode('utf-8-sig'), 'registrations.csv')
    if not selected_details.empty:
        rid = st.selectbox('选择挂号单号', selected_details.registration_id.tolist())
        st.dataframe(visits[visits.registration_id == rid], hide_index=True, use_container_width=True)
        st.dataframe(charges[charges.registration_id == rid], hide_index=True, use_container_width=True)
with quality:
    report = json.loads((folder / 'quality.json').read_text(encoding='utf-8'))
    st.subheader('输入、接收、隔离守恒')
    st.dataframe(pd.DataFrame(report).T, use_container_width=True)
    quarantine = json.loads((folder / 'quarantine.json').read_text(encoding='utf-8'))
    st.json(quarantine, expanded=False)
    st.caption('完全重复保留一条；同主键内容冲突整组隔离；非法日期、非法金额、孤立外键均保留来源行号。')
with assistant:
    st.subheader('让结论有数据依据')
    st.caption('仅发送下方聚合 JSON，不发送挂号单号与收费明细。大模型回答需对照原始指标核验。')
    payload = build_payload(records, scope_alerts.to_dict('records'),
        {'start': str(start), 'end': str(end), 'department': department, 'period': period})
    with st.expander('查看本次输入给助手的结构化数据'):
        st.json(payload)
    mode = st.radio('生成方式', ['规则摘要（离线可用）', '大模型 API'], horizontal=True)
    signature = json.dumps(payload, ensure_ascii=False, sort_keys=True) + mode
    if st.button('生成运营解读', type='primary'):
        try:
            with st.spinner('正在生成解读…'):
                answer = rule_summary(payload) if mode.startswith('规则') else llm_summary(payload)
            st.session_state['answer'] = (signature, answer)
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
    if st.session_state.get('answer', (None,))[0] == signature:
        answer = st.session_state['answer'][1]
        st.markdown(answer)
        st.download_button('下载解读报告', answer, 'operations_summary.md')
