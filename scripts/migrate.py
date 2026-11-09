import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/api'))
from app.db import connect,migrate
with connect() as c: migrate(c)
print('Migration 001 applied (idempotent).')
