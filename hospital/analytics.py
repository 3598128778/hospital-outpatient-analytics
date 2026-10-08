import calendar
import statistics
from collections import defaultdict
from datetime import date, timedelta
from .config import DEPARTMENTS, PERIODS, ROOT
from .database import query

METRICS = ('registrations', 'visits', 'gross_cents', 'refund_cents', 'net_cents')


def daily_metrics(db, start, end):
    raw = query(db, (ROOT / 'sql/daily_metrics.sql').read_text(encoding='utf-8'))
    lookup = {(r['business_date'], r['department'], r['period']): r for r in raw}
    rows = []
    current, last = date.fromisoformat(start), date.fromisoformat(end)
    while current <= last:
        for department in DEPARTMENTS:
            for period in PERIODS:
                key = (str(current), department, period)
                row = dict(lookup.get(key, dict(zip(('business_date', 'department', 'period'), key))))
                row.update({m: int(row.get(m, 0)) for m in METRICS})
                row['avg_spend'] = round(row['net_cents'] / 100 / row['visits'], 2) if row['visits'] else None
                rows.append(row)
        current += timedelta(days=1)
    return rows


def totals(rows):
    result = {m: sum(int(r[m]) for r in rows) for m in METRICS}
    result['avg_spend'] = round(result['net_cents'] / 100 / result['visits'], 2) if result['visits'] else None
    result['completion_rate'] = round(result['visits'] / result['registrations'], 4) if result['registrations'] else None
    return result


def change(current, previous):
    return round((current - previous) / abs(previous), 4) if previous else None


def monthly(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row['business_date'][:7], row['department'], row['period'])].append(row)
    lookup = {}
    for key, group in sorted(groups.items()):
        month, department, period = key
        y, m = map(int, month.split('-'))
        lookup[key] = {'month': month, 'department': department, 'period': period,
            **totals(group), 'complete_month': len(group) == calendar.monthrange(y, m)[1]}
    result = []
    for key, row in lookup.items():
        y, m = map(int, row['month'].split('-'))
        previous = f'{y - 1}-12' if m == 1 else f'{y}-{m - 1:02d}'
        year_ago = f'{y - 1}-{m:02d}'
        for label, period in [('mom', previous), ('yoy', year_ago)]:
            prior = lookup.get((period, key[1], key[2]))
            for metric in ('registrations', 'visits', 'net_cents', 'avg_spend'):
                row[f'{metric}_{label}'] = change(row[metric], prior[metric]) if (
                    prior and prior['complete_month'] and row['complete_month'] and row[metric] is not None) else None
        result.append(row)
    return result


def detect_anomalies(rows):
    """Compare against prior eight matching weekdays, without future leakage."""
    groups = defaultdict(list)
    for row in rows:
        groups[(row['business_date'], row['department'])].append(row)
    history = defaultdict(list)
    alerts = []
    for (day, department), group in sorted(groups.items()):
        aggregate = totals(group)
        weekday = date.fromisoformat(day).weekday()
        for metric in ('registrations', 'net_cents'):
            key = (department, weekday, metric)
            baseline = history[key][-8:]
            current = aggregate[metric]
            if len(baseline) >= 4:
                mean = statistics.mean(baseline)
                std = statistics.pstdev(baseline)
                threshold = max(3 * std, abs(mean) * .30, 5 if metric == 'registrations' else 5000)
                if abs(current - mean) > threshold:
                    alerts.append({'business_date': day, 'department': department, 'metric': metric,
                        'actual': current, 'baseline': round(mean, 2), 'threshold': round(threshold, 2),
                        'direction': '上升' if current > mean else '下降',
                        'deviation_pct': change(current, mean), 'baseline_samples': len(baseline),
                        'reason': '偏离历史同星期基线；需核查排班、活动、收费明细，不能据此认定原因'})
            history[key].append(current)
    return alerts
