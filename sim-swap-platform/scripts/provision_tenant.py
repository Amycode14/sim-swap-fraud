import argparse
import os
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.db import Tenant, make_engine, session_factory
parser=argparse.ArgumentParser()
parser.add_argument('tenant')
args=parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',args.tenant):
    raise SystemExit('Invalid tenant identifier')
Session=session_factory(make_engine(os.environ['DATABASE_URL']))
with Session.begin() as db:
    if not db.get(Tenant,args.tenant):
        db.add(Tenant(id=args.tenant))
print('Tenant provisioned; bind tenant claim only through trusted identity administration.')
