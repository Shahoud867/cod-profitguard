import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/api'))
from app.db import connect,rows,row
from app.seed import checksum
from app.domain import realized
with connect() as c:
    assert not rows(c,'PRAGMA foreign_key_check')
    for table in ['orders','customers','couriers','events','order_items','agent_runs','statements']:
        print(table,row(c,f'SELECT count(*) n FROM {table}')['n'])
    assert row(c,'SELECT count(*) n FROM orders')['n']==8000
    assert row(c,'SELECT count(*) n FROM orders o JOIN customers cu ON cu.id=o.customer_id WHERE o.tenant_id!=cu.tenant_id')['n']==0
    assert row(c,'SELECT count(*) n FROM statements s JOIN orders o ON o.id=s.order_id WHERE s.expected!=o.revenue-o.actual_cost')['n']==0
    assert row(c,'SELECT count(*) n FROM orders o WHERE o.status="delivered" AND o.revenue!=o.cod')['n']==0
    assert row(c,'SELECT count(*) n FROM orders o WHERE o.status="returned" AND o.revenue!=0')['n']==0
    print('Integrity OK. PG-1 checksum:',checksum(c))
