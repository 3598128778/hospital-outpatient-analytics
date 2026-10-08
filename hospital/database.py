import os
import sqlite3
from .config import ROOT


def connect(backend='sqlite', path=None):
    if backend == 'sqlite':
        path = path or ROOT / 'data' / 'hospital.db'
        if str(path) != ':memory:':
            path = __import__('pathlib').Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(path))
        db.execute('PRAGMA foreign_keys=ON')
        return db
    if backend != 'mysql':
        raise ValueError('Unsupported backend')
    import pymysql
    return pymysql.connect(host=os.getenv('MYSQL_HOST', '127.0.0.1'),
        port=int(os.getenv('MYSQL_PORT', '3306')), user=os.getenv('MYSQL_USER', 'hospital'),
        password=os.environ['MYSQL_PASSWORD'], database=os.getenv('MYSQL_DATABASE', 'hospital_demo'),
        charset='utf8mb4', autocommit=False)


def query(db, sql, params=()):
    with_cursor = db.cursor()
    try:
        with_cursor.execute(sql, params)
        names = [d[0] for d in with_cursor.description]
        return [dict(zip(names, row)) for row in with_cursor.fetchall()]
    finally:
        with_cursor.close()


def load(db, cleaned):
    cursor = db.cursor()
    try:
        for statement in (ROOT / 'sql/schema.sql').read_text(encoding='utf-8').split(';'):
            if statement.strip():
                cursor.execute(statement)
        for table in ('charges', 'visits', 'registrations'):
            cursor.execute(f'DELETE FROM {table}')
        placeholder = '?' if isinstance(db, sqlite3.Connection) else '%s'
        for table, rows in cleaned.items():
            if rows:
                columns = list(rows[0])
                sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join([placeholder] * len(columns))})"
                cursor.executemany(sql, [tuple(row[c] for c in columns) for row in rows])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()
