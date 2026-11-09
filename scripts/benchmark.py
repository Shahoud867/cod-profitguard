"""Reproducible local acceptance benchmark on an isolated 10,000-order database."""
import sys,tempfile,time,json,statistics,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/api'))
from app.db import connect,migrate,rows,row
from app.seed import seed,checksum
from app.optimization import optimize
with tempfile.TemporaryDirectory() as tmp:
    path=str(Path(tmp)/'benchmark.db')
    with connect(path) as c:
        migrate(c);t=time.perf_counter();seed(c,total=10000);seed_s=time.perf_counter()-t
        samples=[]
        for i in range(21):
            t=time.perf_counter()
            result=rows(c,'SELECT o.external_id,o.status,cu.name FROM orders o JOIN customers cu ON cu.id=o.customer_id AND cu.tenant_id=o.tenant_id WHERE o.tenant_id=? AND (o.external_id LIKE ? OR cu.name LIKE ?) ORDER BY o.created_at DESC,o.id LIMIT 1000',('t1','%PG%','%Demo%'))
            if i:samples.append((time.perf_counter()-t)*1000)
        t=time.perf_counter();proposal=optimize(c,'t1',limit=100);opt_s=time.perf_counter()-t
        assert not rows(c,'PRAGMA foreign_key_check')
        print(json.dumps({'orders':10000,'seed_seconds':round(seed_s,3),'query_rows':len(result),'query_median_ms':round(statistics.median(samples),3),'query_max_ms':round(max(samples),3),'optimization_100_seconds':round(opt_s,3),'optimization_assigned':proposal['assigned'],'checksum':checksum(c),'note':'This executor only; API/network/browser latency excluded from SQL query benchmark.'},indent=2))
    c.close()
