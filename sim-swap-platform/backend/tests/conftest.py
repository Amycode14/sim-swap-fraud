from datetime import datetime, timedelta, timezone
import pytest
import jwt
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.config import Settings
from backend.app.db import Tenant


@pytest.fixture
def app(tmp_path):
    settings = Settings(environment='demo',database_url='sqlite:///:memory:',secret='a'*64,
                        pseudonym_key='b'*64,provider='mock',artifact_dir=str(tmp_path),redis_url='',rate_limit=10000)
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        with app.state.Session.begin() as db:
            db.add(Tenant(id='other'))
        yield client


def token(role='administrator',tenant='demo',subject='admin',secret='a'*64):
    at=datetime.now(timezone.utc)
    return jwt.encode({'iss':'sim-swap-demo','aud':'sim-swap-demo','sub':subject,'tenant':tenant,'role':role,
                       'iat':at,'exp':at+timedelta(hours=1)},secret,algorithm='HS256')


def headers(role='administrator',tenant='demo',subject='admin'):
    return {'Authorization':'Bearer '+token(role,tenant,subject),'Idempotency-Key':'assessment-idempotency-1'}


def event(kind='sim_change',event_id='event-1',subscriber='0911223344',hours=.1,**attrs):
    return {'event_id':event_id,'source':'test','subscriber':subscriber,
            'event_type':kind,'event_time':(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat(),
            'attributes':attrs}


def assessment(**kwargs):
    return {'subscriber':'0911223344','action':'transaction','action_id':'tx-1','device_id':'unknown',
            'amount':5000,'beneficiary_id':'new',**kwargs}
