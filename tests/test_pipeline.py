import csv
import json
import os
from datetime import date, timedelta
import pytest
from hospital.generate import generate, FIELDS
from hospital.quality import clean
from hospital.database import connect, load, query
from hospital.analytics import totals, daily_metrics, detect_anomalies, monthly, change
from hospital.pipeline import run
from hospital.assistant import build_payload, rule_summary, llm_summary


def write_inputs(folder, registrations=None, visits=None, charges=None):
    values = {'registrations': registrations or [], 'visits': visits or [], 'charges': charges or []}
    for table, fields in FIELDS.items():
        with (folder / f'{table}.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            writer.writerows(values[table])


def fixture_data():
    return {'registrations': [{'registration_id': 'R1', 'business_date': '2026-06-01', 'department': '内科', 'period': '上午', 'status': 'valid'}],
        'visits': [{'visit_id': 'V1', 'registration_id': 'R1', 'status': 'completed'}],
        'charges': [{'charge_id': 'C1', 'registration_id': 'R1', 'kind': 'payment', 'amount_cents': 10000},
                    {'charge_id': 'C2', 'registration_id': 'R1', 'kind': 'payment', 'amount_cents': 5000},
                    {'charge_id': 'C3', 'registration_id': 'R1', 'kind': 'refund', 'amount_cents': 2000}]}


def test_no_join_fanout_and_refunds():
    db = connect(path=':memory:')
    load(db, fixture_data())
    summary = totals(daily_metrics(db, '2026-06-01', '2026-06-01'))
    assert summary == {'registrations': 1, 'visits': 1, 'gross_cents': 15000, 'refund_cents': 2000,
                       'net_cents': 13000, 'avg_spend': 130.0, 'completion_rate': 1.0}
    db.close()


def test_clean_and_conflicts(tmp_path):
    r1 = ['R1', '2026-06-01', '内科', '上午', 'valid']
    r2 = ['R2', '2026-06-01', '内科', '上午', 'valid']
    write_inputs(tmp_path, [r1, r1, r2, ['R2', '2026-06-02', '内科', '上午', 'valid'],
        ['BAD', '2026-02-30', '内科', '上午', 'valid']],
        [['V1', 'R2', 'completed']], [['C1', 'R1', 'payment', '1.001'], ['C2', 'R1', 'payment', 'NaN']])
    accepted, rejected, stats = clean(tmp_path)
    assert len(accepted['registrations']) == 1
    assert stats['registrations'] == {'input': 5, 'accepted': 1, 'quarantined': 4}
    assert len(rejected) == 7
    assert {row['reason'] for row in rejected} == {'exact_duplicate', 'conflicting_primary_key', 'invalid_date', 'orphan_registration', 'invalid_amount'}


def test_multiple_visits_quarantined(tmp_path):
    write_inputs(tmp_path, [['R1', '2026-06-01', '内科', '上午', 'valid']],
        [['V1', 'R1', 'completed'], ['V2', 'R1', 'pending']])
    accepted, rejected, _ = clean(tmp_path)
    assert accepted['visits'] == []
    assert all(row['reason'] == 'multiple_visits_per_registration' for row in rejected)


def test_empty_denominators():
    assert totals([])['avg_spend'] is None
    assert change(10, 0) is None


def test_anomaly_has_no_future_leakage():
    rows = []
    for i in range(9):
        rows.append({'business_date': str(date(2026, 1, 5) + timedelta(days=i * 7)), 'department': '内科',
            'period': '上午', 'registrations': 100 if i == 8 else 10, 'visits': 8,
            'gross_cents': 8000, 'refund_cents': 0, 'net_cents': 8000})
    assert detect_anomalies(rows[:8]) == []
    alerts = detect_anomalies(rows)
    assert len(alerts) == 1
    assert alerts[0]['actual'] == 100 and alerts[0]['baseline'] == 10
    assert alerts[0]['baseline_samples'] == 8


def test_monthly_missing_history_and_partial_month():
    rows = []
    for start, days, value in [('2025-01-01', 31, 10), ('2026-01-01', 31, 20), ('2026-02-01', 10, 30)]:
        for i in range(days):
            rows.append({'business_date': str(date.fromisoformat(start) + timedelta(days=i)), 'department': '内科',
                'period': '上午', 'registrations': value, 'visits': value, 'gross_cents': value * 100,
                'refund_cents': 0, 'net_cents': value * 100})
    result = monthly(rows)
    assert result[1]['registrations_yoy'] == 1
    assert result[1]['registrations_mom'] is None
    assert result[2]['registrations_mom'] is None


def test_pipeline_determinism_and_conservation(tmp_path):
    source, output = tmp_path / 'raw', tmp_path / 'out'
    generate(source, start='2026-05-01', end='2026-06-30')
    first = run(source, output, db_path=tmp_path / 'hospital.db')
    daily_before = (output / 'daily_metrics.csv').read_bytes()
    second = run(source, output, db_path=tmp_path / 'hospital.db')
    assert first == second
    assert daily_before == (output / 'daily_metrics.csv').read_bytes()
    assert sum(item['quarantined'] for item in first['quality'].values()) == 6
    for item in first['quality'].values():
        assert item['input'] == item['accepted'] + item['quarantined']
    accepted, _, _ = clean(source)
    expected = sum(r['amount_cents'] * (1 if r['kind'] == 'payment' else -1) for r in accepted['charges'])
    assert first['metrics']['net_cents'] == expected


def test_database_load_rolls_back_on_invalid_fk():
    db = connect(path=':memory:')
    load(db, fixture_data())
    bad = fixture_data()
    bad['charges'][0]['registration_id'] = 'MISSING'
    with pytest.raises(Exception):
        load(db, bad)
    assert query(db, 'SELECT COUNT(*) AS n FROM charges')[0]['n'] == 3
    db.close()


def test_ai_contains_only_aggregates(monkeypatch):
    payload = build_payload([], [], {'start': '2026-06-01', 'end': '2026-06-30', 'department': '全部', 'period': '全部'})
    assert 'registration_id' not in json.dumps(payload)
    assert '未调用大模型' in rule_summary(payload)
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    with pytest.raises(ValueError, match='LLM_API_KEY'):
        llm_summary(payload)


def test_ai_http_contract(monkeypatch):
    import io
    import urllib.request
    monkeypatch.setenv('LLM_API_KEY', 'test-not-a-real-key')
    monkeypatch.setenv('LLM_MODEL', 'test-model')
    monkeypatch.setenv('LLM_BASE_URL', 'https://example.invalid/v1')
    def fake_urlopen(request, timeout):
        assert request.full_url.endswith('/v1/chat/completions')
        body = json.loads(request.data)
        assert body['model'] == 'test-model'
        assert timeout == 45
        assert json.loads(body['messages'][1]['content']) == {'metrics': {}}
        return io.BytesIO(json.dumps({'choices': [{'message': {'content': '测试摘要'}}]}).encode())
    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    assert llm_summary({'metrics': {}}) == '测试摘要'


@pytest.mark.skipif(os.getenv('TEST_MYSQL') != '1', reason='Requires configured MySQL test database')
def test_mysql_sqlite_parity():
    sqlite, mysql = connect(path=':memory:'), connect('mysql')
    try:
        for db in (sqlite, mysql):
            load(db, fixture_data())
        assert daily_metrics(sqlite, '2026-06-01', '2026-06-02') == daily_metrics(mysql, '2026-06-01', '2026-06-02')
    finally:
        sqlite.close()
        mysql.close()
