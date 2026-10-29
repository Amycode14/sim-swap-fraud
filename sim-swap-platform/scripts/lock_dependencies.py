"""Freeze the installed transitive dependency closure used to validate this release."""
from importlib.metadata import distribution, version
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
roots=['fastapi','uvicorn','SQLAlchemy','psycopg','psycopg-binary','redis','httpx','PyJWT','cryptography',
       'prometheus-client','pytest','xgboost','scikit-learn','numpy','pandas','joblib','alembic','ruff','pydantic',
       'boto3','confluent-kafka','opentelemetry-sdk','opentelemetry-instrumentation-fastapi',
       'opentelemetry-exporter-otlp-proto-http','pip-audit']
seen={}
def visit(name):
    key=canonicalize_name(name)
    if key in seen:return
    package=distribution(name)
    seen[key]=package.version
    for item in package.requires or []:
        requirement=Requirement(item)
        if requirement.marker and not requirement.marker.evaluate({'extra':''}):continue
        visit(requirement.name)
for name in roots:visit(name)
Path('requirements-lock.txt').write_text('# Validated on CPython 3.12 Linux; generated from installed dependency closure.\n'+
 '\n'.join(f'{name}=={value}' for name,value in sorted(seen.items()))+'\n')
Path('requirements-integrations.txt').write_text('\n'.join(f'{name}=={version(name)}' for name in roots[18:])+'\n')
print(f'Pinned {len(seen)} direct/transitive distributions')
