import csv
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from .config import DEPARTMENTS, PERIODS
from .generate import FIELDS


def clean(source):
    """Keep one exact duplicate; quarantine every row of a conflicting primary key."""
    cleaned, rejected, stats = {}, [], {}
    valid_registrations = {}
    for table, fields in FIELDS.items():
        with (source / f'{table}.csv').open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != fields:
                raise ValueError(f'{table}: expected columns {fields}')
            records = list(reader)
        grouped = defaultdict(list)
        for line, row in enumerate(records, 2):
            grouped[row.get(fields[0])].append((line, row))
        accepted = []
        for key, versions in grouped.items():
            fingerprints = {tuple(row.get(c) for c in fields) for _, row in versions}
            conflict = len(fingerprints) > 1
            for index, (line, row) in enumerate(versions):
                reason = None
                converted = dict(row)
                if conflict:
                    reason = 'conflicting_primary_key'
                elif index:
                    reason = 'exact_duplicate'
                elif None in row or any(row.get(c) is None or not row[c].strip() for c in fields):
                    reason = 'missing_or_extra_fields'
                elif any(len(row[c]) > 40 for c in fields):
                    reason = 'field_too_long'
                elif table == 'registrations':
                    try:
                        parsed = date.fromisoformat(row['business_date'])
                        if str(parsed) != row['business_date']:
                            raise ValueError()
                    except ValueError:
                        reason = 'invalid_date'
                    if not reason and (row['department'] not in DEPARTMENTS or row['period'] not in PERIODS
                            or row['status'] not in ('valid', 'cancelled')):
                        reason = 'invalid_dimension_or_status'
                elif table == 'visits':
                    if row['registration_id'] not in valid_registrations:
                        reason = 'orphan_registration'
                    elif valid_registrations[row['registration_id']]['status'] != 'valid':
                        reason = 'visit_for_cancelled_registration'
                    elif row['status'] not in ('completed', 'pending'):
                        reason = 'invalid_status'
                elif table == 'charges':
                    try:
                        value = Decimal(row['amount'])
                        if not value.is_finite() or value <= 0 or value > 1000000 or value * 100 != (value * 100).to_integral_value():
                            raise ValueError()
                        converted = {c: row[c] for c in fields if c != 'amount'}
                        converted['amount_cents'] = int(value * 100)
                    except (InvalidOperation, ValueError):
                        reason = 'invalid_amount'
                    if not reason and row['registration_id'] not in valid_registrations:
                        reason = 'orphan_registration'
                    if not reason and row['kind'] not in ('payment', 'refund'):
                        reason = 'invalid_charge_kind'
                if reason:
                    rejected.append({'table': table, 'line': line, 'reason': reason, 'row': row})
                else:
                    accepted.append((line, row, converted))
        if table == 'visits':
            # A registration is one encounter. Ambiguous multiple visits are all quarantined.
            counts = Counter(item[2]['registration_id'] for item in accepted)
            unique = []
            for line, row, converted in accepted:
                if counts[converted['registration_id']] > 1:
                    rejected.append({'table': table, 'line': line, 'reason': 'multiple_visits_per_registration', 'row': row})
                else:
                    unique.append((line, row, converted))
            accepted = unique
        cleaned[table] = [item[2] for item in accepted]
        if table == 'registrations':
            valid_registrations = {row['registration_id']: row for row in cleaned[table]}
        stats[table] = {'input': len(records), 'accepted': len(accepted), 'quarantined': len(records) - len(accepted)}
    return cleaned, rejected, stats
