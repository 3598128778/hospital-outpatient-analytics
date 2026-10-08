"""Fixed-seed synthetic events; no real patients or hospital records."""
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path
from .config import DEPARTMENTS, PERIODS

FIELDS = {
    'registrations': ['registration_id', 'business_date', 'department', 'period', 'status'],
    'visits': ['visit_id', 'registration_id', 'status'],
    'charges': ['charge_id', 'registration_id', 'kind', 'amount'],
}


def generate(destination, seed=42, start='2024-12-01', end='2026-06-30'):
    destination = Path(destination)
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError('start must be <= end')
    rng = random.Random(seed)
    rows = {name: [] for name in FIELDS}
    rid = cid = 0
    current = first
    while current <= last:
        for di, department in enumerate(DEPARTMENTS):
            count = round((20 - di * 2) * (0.78 if current.weekday() >= 5 else 1)
                          * (1.08 if current.year == 2026 else 1) * rng.uniform(.85, 1.15))
            if str(current) == '2026-06-15' and department == '儿科':
                count *= 3
            for _ in range(count):
                rid += 1
                key = f'R{rid:07d}'
                period = rng.choices(PERIODS, weights=[55, 38, 7])[0]
                status = 'cancelled' if rng.random() < .06 else 'valid'
                rows['registrations'].append([key, str(current), department, period, status])
                if status == 'cancelled' or rng.random() < .08:
                    continue
                rows['visits'].append([f'V{rid:07d}', key, 'completed'])
                cents = rng.randint(8000, 32000)
                if str(current) == '2026-06-22' and department == '内科':
                    cents *= 4
                # Two charge lines demonstrate why raw fact tables must not be joined directly.
                for amount in (2000, cents - 2000):
                    cid += 1
                    rows['charges'].append([f'C{cid:07d}', key, 'payment', f'{amount / 100:.2f}'])
                if rng.random() < .025:
                    cid += 1
                    rows['charges'].append([f'C{cid:07d}', key, 'refund', '20.00'])
        current += timedelta(days=1)
    # Deliberate quality fixtures are exported and traceable in the quarantine report.
    rows['registrations'].append(rows['registrations'][0][:])
    rows['registrations'].append(['BAD_DATE', '2026-02-30', '内科', '上午', 'valid'])
    rows['registrations'].append(['BAD_DEPT', end, '未知科室', '上午', 'valid'])
    rows['visits'].append(['ORPHAN_VISIT', 'MISSING', 'completed'])
    rows['charges'].append(['BAD_AMOUNT', 'R0000001', 'payment', '-10.00'])
    rows['charges'].append(['ORPHAN_CHARGE', 'MISSING', 'payment', '10.00'])
    destination.mkdir(parents=True, exist_ok=True)
    for name, fields in FIELDS.items():
        with (destination / f'{name}.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            writer.writerows(rows[name])
    manifest = {'source': 'synthetic', 'seed': seed, 'start': start, 'end': end,
                'rows': {name: len(data) for name, data in rows.items()},
                'injected_events': ['2026-06-15 儿科挂号量增加', '2026-06-22 内科收费增加'],
                'quality_fixtures': 6}
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest
