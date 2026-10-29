import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import patch
import httpx
import pytest
from backend.app.provider import Provider
from backend.app.config import Settings
from backend.app.model_runtime import ModelRuntime
from backend.app.features import NAMES, VERSION, build_features
from backend.app.db import find, records
from backend.app.worker import deliver
from .conftest import headers,assessment


def provider():
    return Provider(Settings(provider='camara',provider_url='https://operator.example/sim-swap/v1',provider_token='token'))


def test_camara_missing_boolean_is_outage():
    adapter=provider()
    response=httpx.Response(200,json={'swapped':None},request=httpx.Request('POST','https://operator.example'))
    with patch('httpx.post',return_value=response):
        assert adapter.check('+251911223344')['status']=='outage'


def test_camara_window_not_exact_timestamp():
    adapter=provider()
    response=httpx.Response(200,json={'swapped':True},request=httpx.Request('POST','https://operator.example'))
    with patch('httpx.post',return_value=response):
        value=adapter.check('+251911223344')
    assert value['status']=='recent_change' and 'latest_change' not in value


def test_camara_timeout_circuit_breaker():
    adapter=provider()
    with patch('httpx.post',side_effect=httpx.ReadTimeout('timeout')) as call:
        for _ in range(3):
            assert adapter.check('+251911223344')['status']=='timeout'
        assert adapter.check('+251911223344')['status']=='outage'
        assert call.call_count==3


def test_model_native_integrity_and_path_protection(tmp_path):
    folder=tmp_path/'test-model';folder.mkdir()
    artifact=folder/'model.json'
    artifact.write_text(json.dumps({'mean':[0]*len(NAMES),'scale':[1]*len(NAMES),'coefficients':[0]*len(NAMES),'intercept':0}))
    manifest={'algorithm':'logistic','feature_version':VERSION,'feature_names':NAMES,
              'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()}
    (folder/'manifest.json').write_text(json.dumps(manifest))
    runtime=ModelRuntime(tmp_path)
    assert runtime.score('test-model',dict(zip(NAMES,[0]*len(NAMES))))[0]==.5
    artifact.write_text('{}')
    with pytest.raises(ValueError):runtime.manifest('test-model')
    with pytest.raises(ValueError):runtime.manifest('../test-model')


def test_shadow_artifact_failure_rules_fallback(client,app,tmp_path):
    from backend.app.db import put
    with app.state.Session.begin() as db:
        put(db,'demo','setting','shadow_model',{'model_id':'absent'})
    response=client.post('/api/v1/assessments',json=assessment(),headers=headers())
    assert response.status_code==201
    assert response.json()['fallback_used'] and response.json()['model_error']


def test_outbox_delivery_signature_and_dead_letter(client,app):
    app.state.settings.webhook_url='https://receiver.example/events'
    app.state.settings.webhook_secret='c'*64
    result=client.post('/api/v1/assessments',json=assessment(),headers=headers()).json()
    response=httpx.Response(200,request=httpx.Request('POST','https://receiver.example/events'))
    with patch('httpx.post',return_value=response) as send:
        assert deliver(app.state.settings,app.state.Session)==1
        assert 'X-Signature' in send.call_args.kwargs['headers']
    with app.state.Session() as db:
        assert find(db,'demo','outbox',result['assessment_id']).data['status']=='delivered'


def test_outbox_failure_preserves_pending_then_dead_letters(client,app):
    app.state.settings.webhook_url='https://receiver.example/events'
    app.state.settings.webhook_secret='c'*64
    result=client.post('/api/v1/assessments',json=assessment(),headers=headers()).json()
    with app.state.Session.begin() as db:
        row=find(db,'demo','outbox',result['assessment_id']);value=row.data;value['attempts']=7;row.update(value)
    with patch('httpx.post',side_effect=httpx.ReadTimeout('timeout')):
        assert deliver(app.state.settings,app.state.Session)==0
    with app.state.Session() as db:
        value=find(db,'demo','outbox',result['assessment_id']).data
        assert value['status']=='dead_letter' and value['attempts']==8
    assert client.post('/api/v1/outbox/'+result['assessment_id']+'/replay',headers=headers()).status_code==200


def test_readiness_database_failure(client,app):
    with patch.object(app.state.engine,'connect',side_effect=RuntimeError('down')):
        assert client.get('/health/ready').status_code==503


def test_redis_outage_is_explicit_503(client,app):
    import redis
    class BrokenRedis:
        def eval(self,*args):raise redis.RedisError('down')
    app.state.auth.redis=BrokenRedis()
    assert client.get('/api/v1/me',headers=headers()).status_code==503
