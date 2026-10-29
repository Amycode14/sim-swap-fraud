"""Generate independent local-only secrets. Never ship generated .env or tokens."""
import json
import os
import secrets
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.db import Base, Tenant, make_engine, session_factory

root = Path(__file__).resolve().parents[1]
config = root / '.env'
if not config.exists():
    values = {'APP_ENV': 'demo', 'APP_SECRET': secrets.token_hex(32), 'PSEUDONYM_KEY': secrets.token_hex(32),
              'PROVIDER_MODE': 'mock', 'DATABASE_URL': 'sqlite:///./data/platform.db',
              'POSTGRES_PASSWORD': secrets.token_hex(24), 'REDIS_PASSWORD': secrets.token_hex(24),
              'RATE_LIMIT_PER_MINUTE': '300', 'ARTIFACT_DIR': './artifacts'}
    config.write_text('\n'.join(f'{k}={v}' for k,v in values.items()) + '\n')
    config.chmod(0o600)
(root / 'data').mkdir(exist_ok=True)
(root / 'artifacts').mkdir(exist_ok=True)
print('Local demonstration configuration ready. Start the application with scripts/run.py.')
