import sys,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/api'))
from app.db import connect,migrate
from app.seed import seed
p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=20261108);p.add_argument('--count',type=int,default=8000);args=p.parse_args()
with connect() as c:
    migrate(c); print('PG-1 business checksum:',seed(c,args.seed,args.count))
