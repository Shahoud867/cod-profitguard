"""SQLite unit-of-work boundary. Amounts are integer paisa; dates are UTC ISO-8601."""
import os, sqlite3, json, uuid
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[3]
DB_PATH = os.environ.get('PROFITGUARD_DB', str(ROOT / 'data' / 'profitguard.db'))
def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return str(uuid.uuid4())
def stable(value): return str(uuid.uuid5(uuid.NAMESPACE_URL, 'profitguard:' + value))
def js(value): return json.dumps(value, separators=(',', ':'), sort_keys=True)
def connect(path=None):
    p = path or DB_PATH
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA busy_timeout=30000')
    return c

def migrate(c):
    c.executescript((ROOT / 'services/api/migrations/001_initial.sql').read_text())
    c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(1,?)', (now(),))
    c.commit()

def insert(c, table, **values):
    keys = list(values)
    c.execute(f'INSERT INTO {table} ({",".join(keys)}) VALUES ({",".join("?" for _ in keys)})', tuple(values[k] for k in keys))
    return values

def row(c, sql, args=()):
    r = c.execute(sql, args).fetchone()
    return dict(r) if r else None

def rows(c, sql, args=()): return [dict(r) for r in c.execute(sql, args)]
