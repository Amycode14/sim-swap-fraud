"""Issue a local demonstration JWT. OIDC tokens are required outside demo."""
import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import jwt
root = Path(__file__).resolve().parents[1]
values = dict(line.split('=', 1) for line in (root / '.env').read_text().splitlines() if '=' in line and not line.startswith('#')) if (root / '.env').exists() else {}
values.update(os.environ)
if values.get('APP_ENV') != 'demo':
    raise SystemExit('Demo token issuer disabled outside APP_ENV=demo')
parser = argparse.ArgumentParser()
parser.add_argument('--role', default='administrator', choices=['administrator','analyst','supervisor','auditor','integration'])
parser.add_argument('--subject', default='demo-admin')
parser.add_argument('--tenant', default='demo')
args = parser.parse_args()
now = datetime.now(timezone.utc)
print(jwt.encode({'sub': args.subject, 'tenant': args.tenant, 'role': args.role,
                  'iss': 'sim-swap-demo', 'aud': 'sim-swap-demo', 'iat': now, 'exp': now + timedelta(hours=2)},
                 values['APP_SECRET'], algorithm='HS256'))
