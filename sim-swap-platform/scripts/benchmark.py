"""Actual HTTP benchmark of local reference API, not a production SLA."""
import argparse
import concurrent.futures
import json
import platform
import time
import uuid
from pathlib import Path
import httpx
import numpy as np
parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:8000')
parser.add_argument('--token',required=True)
parser.add_argument('--count',type=int,default=150)
parser.add_argument('--concurrency',type=int,default=8)
args=parser.parse_args()

def one(index):
    started=time.perf_counter()
    with httpx.Client(base_url=args.url,timeout=30,trust_env=False) as client:
        response=client.post('/api/v1/assessments',headers={'Authorization':'Bearer '+args.token,'Idempotency-Key':str(uuid.uuid4())},
             json={'subscriber':f'benchmark-{index}','action':'login','action_id':str(uuid.uuid4()),'device_id':'new'})
    return {'seconds':time.perf_counter()-started,'status':response.status_code}

start=time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
    results=list(pool.map(one,range(args.count)))
elapsed=time.perf_counter()-start
latencies=[item['seconds']*1000 for item in results]
report={'description':'Local HTTP assessment benchmark, synthetic provider, SQLite, rules-only',
        'environment':{'python':platform.python_version(),'os':platform.system(),'cpu':platform.machine()},
        'requests':args.count,'concurrency':args.concurrency,'elapsed_seconds':elapsed,
        'requests_per_second':args.count/elapsed,'latency_ms':dict(zip(['p50','p95','p99'],np.percentile(latencies,[50,95,99]).tolist())),
        'status_counts':{str(status):sum(item['status']==status for item in results) for status in {i['status'] for i in results}},
        'scope':'Includes creating an HTTP client per request. Not a sustained production, PostgreSQL, operator, or broker benchmark.'}
Path('reports/benchmark.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
