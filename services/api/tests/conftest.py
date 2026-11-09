import os,sys,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['AUTO_SEED']='false'
import pytest
from fastapi.testclient import TestClient
from app import db as storage
from app.seed import seed
from app.main import app,attempts

@pytest.fixture(scope='session')
def template(tmp_path_factory):
    p=tmp_path_factory.mktemp('seed')/'base.db'
    with storage.connect(str(p)) as c:
        storage.migrate(c); seed(c,total=240); c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    c.close()
    return p
@pytest.fixture
def env(template,tmp_path,monkeypatch):
    path=tmp_path/'test.db';shutil.copy(template,path);monkeypatch.setattr(storage,'DB_PATH',str(path));attempts.clear()
    with TestClient(app) as client: yield client,path
@pytest.fixture
def api(env):
    client,path=env;r=client.post('/api/v1/auth/login',json={'email':'owner@profitguard.example','password':'DemoProfit2026!'});assert r.status_code==200
    csrf=r.json()['csrf']
    class API:
        c=client
        db=path
        def get(self,p): return client.get('/api/v1'+p)
        def post(self,p,data=None,key=None,headers=None):
            from uuid import uuid4
            h={'X-CSRF-Token':csrf,'Idempotency-Key':key or str(uuid4())};h.update(headers or {})
            return client.post('/api/v1'+p,json=data or {},headers=h)
        def put(self,p,data):
            from uuid import uuid4
            return client.put('/api/v1'+p,json=data,headers={'X-CSRF-Token':csrf,'Idempotency-Key':str(uuid4())})
        def login(self,role):
            r=client.post('/api/v1/auth/login',json={'email':role+'@profitguard.example','password':'DemoProfit2026!'})
            assert r.status_code==200
            nonlocal csrf;csrf=r.json()['csrf'];return r
    return API()
