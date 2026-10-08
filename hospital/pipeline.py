import argparse
import csv
import hashlib
import json
from pathlib import Path
from .analytics import daily_metrics, monthly, detect_anomalies
from .assistant import build_payload, rule_summary
from .config import ROOT
from .database import connect, load
from .generate import generate
from .quality import clean


def write_csv(path, rows, fields=None):
    fields = fields or (list(rows[0]) if rows else [])
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(source=None, output=None, backend='sqlite', db_path=None):
    source, output = Path(source or ROOT / 'data/raw'), Path(output or ROOT / 'artifacts')
    cleaned, quarantine, quality = clean(source)
    dates = [row['business_date'] for row in cleaned['registrations']]
    if not dates:
        raise ValueError('没有有效挂号数据，已停止运行。')
    start, end = min(dates), max(dates)
    # Manifest preserves boundary dates with zero events. Custom input must provide coverage explicitly.
    manifest_path = source / 'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        from datetime import date
        start, end = str(date.fromisoformat(manifest['start'])), str(date.fromisoformat(manifest['end']))
        if min(dates) < start or max(dates) > end or start > end:
            raise ValueError('有效数据日期超出 manifest 覆盖区间。')
    db = connect(backend, db_path)
    try:
        load(db, cleaned)
        daily = daily_metrics(db, start, end)
    finally:
        db.close()
    alerts, months = detect_anomalies(daily), monthly(daily)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / 'daily_metrics.csv', daily)
    write_csv(output / 'monthly_metrics.csv', months)
    write_csv(output / 'anomalies.csv', alerts, ['business_date', 'department', 'metric', 'actual', 'baseline', 'threshold', 'direction', 'deviation_pct', 'baseline_samples', 'reason'])
    write_csv(output / 'registration_details.csv', cleaned['registrations'])
    write_csv(output / 'visit_details.csv', cleaned['visits'], ['visit_id', 'registration_id', 'status'])
    write_csv(output / 'charge_details.csv', cleaned['charges'], ['charge_id', 'registration_id', 'kind', 'amount_cents'])
    (output / 'quarantine.json').write_text(json.dumps(quarantine, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'quality.json').write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding='utf-8')
    payload = build_payload(daily, alerts, {'start': start, 'end': end, 'department': '全部', 'period': '全部'})
    (output / 'ai_input.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'summary.md').write_text(rule_summary(payload), encoding='utf-8')
    report = {'source': 'synthetic_demo_or_user_supplied', 'backend': backend, 'start': start, 'end': end,
        'quality': quality, 'metrics': payload['metrics'], 'daily_rows': len(daily), 'anomalies': len(alerts),
        'input_sha256': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(source.glob('*.csv'))}}
    (output / 'run_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description='Synthetic outpatient analytics pipeline')
    parser.add_argument('--generate', action='store_true', help='Generate deterministic synthetic CSV inputs')
    parser.add_argument('--backend', choices=['sqlite', 'mysql'], default='sqlite')
    parser.add_argument('--source', type=Path, default=ROOT / 'data/raw')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts')
    parser.add_argument('--db-path', type=Path)
    args = parser.parse_args()
    if args.generate:
        generate(args.source)
    print(json.dumps(run(args.source, args.output, args.backend, args.db_path), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
