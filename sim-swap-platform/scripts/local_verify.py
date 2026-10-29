"""Launch a real local server, run HTTP examples/benchmark/UI tests, then stop it."""
import json
import os
import subprocess
import sys
import time
import tempfile
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1]
os.chdir(root)
values=dict(line.split('=',1) for line in Path('.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
temporary=tempfile.TemporaryDirectory(prefix='simshield-verify-')
environment={**os.environ,**values,'DATABASE_URL':'sqlite:///'+str(Path(temporary.name)/'verify.db'),'RATE_LIMIT_PER_MINUTE':'10000','PORT':'8011'}
log=Path('reports/server.log').open('w')
server=subprocess.Popen([sys.executable,'scripts/run.py'],env=environment,stdout=log,stderr=log)
try:
    client=httpx.Client(base_url='http://127.0.0.1:8011',trust_env=False)
    for _ in range(200):
        if server.poll() is not None:
            raise RuntimeError(Path('reports/server.log').read_text())
        try:
            if client.get('/health/ready').status_code==200:break
        except httpx.HTTPError:pass
        time.sleep(.1)
    else:raise RuntimeError('Server failed readiness')
    access=subprocess.check_output([sys.executable,'scripts/issue_demo_token.py'],text=True).strip()
    subprocess.run([sys.executable,'scripts/seed_demo.py','--url','http://127.0.0.1:8011','--token',access],check=True)
    subprocess.run([sys.executable,'scripts/benchmark.py','--url','http://127.0.0.1:8011','--token',access,'--count','150','--concurrency','8'],check=True)
    schema=client.get('/openapi.json').json()
    Path('docs/openapi.json').write_text(json.dumps(schema,indent=2))
    if os.getenv('RUN_BROWSER_TESTS')=='true':
        subprocess.run(['node','scripts/browser_test.cjs'],env={**os.environ,'TEST_TOKEN':access,'TEST_URL':'http://127.0.0.1:8011'},check=True)
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill();server.wait()
    log.close()
    temporary.cleanup()
