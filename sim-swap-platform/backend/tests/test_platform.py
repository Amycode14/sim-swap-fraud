import copy
from datetime import datetime, timedelta, timezone
import pytest
from backend.app.db import find, records, verify_audit
from backend.app.security import pseudonym, sign_webhook, verify_webhook
from backend.app.features import build_features
from backend.app.config import Settings
from .conftest import headers,event,assessment,token


def post_assessment(client,**kwargs):
    return client.post('/api/v1/assessments',json=assessment(**kwargs),headers=headers())


def test_health_and_unauthenticated(client):
    assert client.get('/health/ready').status_code==200
    assert client.get('/api/v1/assessments').status_code in [401,403]


def test_tampered_token(client):
    assert client.get('/api/v1/me',headers={'Authorization':'Bearer '+token(secret='wrong'*10)}).status_code==401


def test_unknown_tenant(client):
    assert client.get('/api/v1/assessments',headers=headers(tenant='unknown')).status_code==403


def test_ingestion_duplicate_payload_conflict(client):
    item=event()
    first=client.post('/api/v1/events',json=item,headers=headers())
    assert first.status_code==201
    assert client.post('/api/v1/events',json=item,headers=headers()).json()['duplicate'] is True
    item['event_type']='port'
    assert client.post('/api/v1/events',json=item,headers=headers()).status_code==409


def test_pseudonym_and_no_raw_identifier_stored(client,app):
    client.post('/api/v1/events',json=event(device_id='secret-device'),headers=headers())
    with app.state.Session() as db:
        row=records(db,'demo','event')[0]
        assert '0911223344' not in row.body
        assert 'secret-device' not in row.body
    assert pseudonym('0911223344','demo','b'*64)==pseudonym('+251911223344','demo','b'*64)
    assert pseudonym('0911223344','demo','b'*64)!=pseudonym('0911223344','other','b'*64)


def test_swap_transfer_case_created(client):
    client.post('/api/v1/events',json=event(),headers=headers())
    result=post_assessment(client)
    assert result.status_code==201,result.text
    value=result.json()
    assert value['recommendation']=='REVIEW'
    assert value['fraud_probability'] is None
    assert 'NEW_BENEFICIARY_AFTER_CHANGE' in value['reason_codes']
    assert client.get('/api/v1/cases',headers=headers()).json()['total']==1


def test_legitimate_replacement_not_automatically_blocked(client):
    client.post('/api/v1/events',json=event('login','known-login',hours=24,device_id='known'),headers=headers())
    client.post('/api/v1/events',json=event(reason='esim'),headers=headers())
    value=post_assessment(client,action='login',device_id='known',beneficiary_id=None,amount=0).json()
    assert value['recommendation']=='ALLOW'
    assert value['risk_score']==25


def test_recovery_high_risk(client):
    client.post('/api/v1/events',json=event(),headers=headers())
    value=post_assessment(client,action='recovery').json()
    assert value['risk_score']>=85
    assert value['recommendation']=='TEMPORARY_HOLD'
    assert 'sms' not in value['step_up_options']


def test_unknown_signal_requires_independent_step_up(client):
    value=post_assessment(client,device_id=None,beneficiary_id=None).json()
    assert value['signal']['status']=='unknown'
    assert value['recommendation']=='STEP_UP'
    assert value['features']['signal_missing']==1


@pytest.mark.parametrize('status',['unsupported','timeout','outage','stale','unknown'])
def test_provider_degraded_states_never_become_clean(client,app,status):
    app.state.provider.check=lambda _: {'status':status,'observed_at':datetime.now(timezone.utc).isoformat(),'source':'test'}
    value=post_assessment(client,device_id=None,beneficiary_id=None).json()
    assert value['recommendation']=='STEP_UP'
    assert value['signal']['status']==status


def test_recent_window_only_signal_is_risky(client,app):
    app.state.provider.check=lambda _: {'status':'recent_change','observed_at':datetime.now(timezone.utc).isoformat(),'source':'test','recency_window_only':True}
    value=post_assessment(client).json()
    assert 'RECENT_SIM_OR_PORT_CHANGE' in value['reason_codes']


def test_idempotent_assessment_conflicting_replay(client):
    first=post_assessment(client).json()
    second=post_assessment(client).json()
    assert first['assessment_id']==second['assessment_id']
    assert first['expires_at']==second['expires_at']
    assert post_assessment(client,amount=9999).status_code==409


def test_tenant_isolation(client):
    value=post_assessment(client).json()
    assert client.get('/api/v1/assessments/'+value['assessment_id'],headers=headers(tenant='other')).status_code==404
    assert client.get('/api/v1/assessments',headers=headers(tenant='other')).json()['total']==0


def test_role_denials(client):
    assert client.post('/api/v1/events',json=event(),headers=headers('analyst')).status_code==403
    assert client.post('/api/v1/assessments',json=assessment(),headers=headers('auditor')).status_code==403
    assert client.get('/api/v1/audit',headers=headers('analyst')).status_code==403
    assert client.get('/api/v1/assessments',headers=headers('integration')).status_code==403


def test_action_binding_expiry_and_new_event(client,app):
    value=post_assessment(client).json()
    url='/api/v1/assessments/'+value['assessment_id']+'/validate'
    body={'action_id':'tx-1','action':'transaction'}
    assert client.post(url,json=body,headers=headers()).json()['valid']
    assert not client.post(url,json={**body,'action_id':'other'},headers=headers()).json()['valid']
    client.post('/api/v1/events',json=event(),headers=headers())
    assert 'NEW_EVENTS_REQUIRE_REASSESSMENT' in client.post(url,json=body,headers=headers()).json()['reasons']
    with app.state.Session.begin() as db:
        row=find(db,'demo','assessment',value['assessment_id']);data=row.data
        data['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat();row.update(data)
    assert 'EXPIRED' in client.post(url,json=body,headers=headers()).json()['reasons']


def test_case_adjudication_and_label_correction(client):
    client.post('/api/v1/events',json=event(),headers=headers())
    post_assessment(client)
    case=client.get('/api/v1/cases',headers=headers()).json()['items'][0]
    url='/api/v1/cases/'+case['case_id']
    body={'expected_version':1,'status':'resolved_fraud','note':'Verified customer denial','evidence':'ticket-123'}
    assert client.patch(url,json=body,headers=headers('analyst')).status_code==403
    resolved=client.patch(url,json=body,headers=headers('supervisor')).json()
    assert resolved['label']==1
    assert client.patch(url,json=body,headers=headers()).status_code==409
    body.update({'expected_version':2,'status':'resolved_legitimate'})
    corrected=client.patch(url,json=body,headers=headers()).json()
    assert corrected['label']==0
    assert len(corrected['label_history'])==2


def test_policy_two_person_approval_and_rollback(client):
    body={'name':'reviewed','step_up':25,'review':55,'hold':85}
    proposal=client.post('/api/v1/policies',json=body,headers=headers()).json()
    url='/api/v1/policies/'+proposal['version']+'/approve'
    assert client.post(url,headers=headers()).status_code==403
    assert client.post(url,headers=headers('supervisor',subject='reviewer')).status_code==200
    policy=client.get('/api/v1/policies',headers=headers()).json()['active']
    assert policy['step_up']==25
    bad={**body,'review':20}
    assert client.post('/api/v1/policies',json=bad,headers=headers()).status_code==422


def test_audit_detects_tampering(client,app):
    post_assessment(client)
    assert client.get('/api/v1/audit',headers=headers()).json()['chain_valid']
    with app.state.Session.begin() as db:
        row=records(db,'demo','audit')[0];data=row.data;data['actor']='tampered';row.update(data)
    assert not client.get('/api/v1/audit',headers=headers()).json()['chain_valid']


def test_schema_prohibits_secrets_and_future_events(client):
    item=event();item['attributes']['otp']='123456'
    assert client.post('/api/v1/events',json=item,headers=headers()).status_code==422
    item=event(hours=-2)
    assert client.post('/api/v1/events',json=item,headers=headers()).status_code==422
    item=event(hours=24*91)
    assert client.post('/api/v1/events',json=item,headers=headers()).status_code==422
    item=event();item['event_time']='2026-01-01T00:00:00'
    assert client.post('/api/v1/events',json=item,headers=headers()).status_code==422


def test_atomic_batch_rolls_back_on_conflict(client):
    assert client.post('/api/v1/events/batch',json=[event(event_id='atomic'),event('port',event_id='atomic')],headers=headers()).status_code==409
    assert client.get('/api/v1/events?subscriber=0911223344',headers=headers()).json()['items']==[]


def test_feature_point_in_time_and_ingestion_clock():
    at=datetime.now(timezone.utc)
    context={'action':'login','device_id':'new','amount':0,'currency':'ETB'}
    def row(event_at,ingestion):
        return {'event_time':event_at.isoformat(),'ingested_at':ingestion.isoformat(),'event_type':'sim_change','attributes':{}}
    signal={'status':'unknown','observed_at':at.isoformat()}
    events=[row(at+timedelta(hours=1),at),row(at-timedelta(hours=1),at+timedelta(seconds=1))]
    assert build_features(events,at,context,signal)['sim_changes_24h']==0
    events.append(row(at-timedelta(hours=2),at-timedelta(hours=1)))
    assert build_features(events,at,context,signal)['sim_changes_24h']==1


def test_number_recycling_severs_history():
    at=datetime.now(timezone.utc)
    events=[{'event_time':(at-timedelta(hours=h)).isoformat(),'ingested_at':(at-timedelta(hours=h)).isoformat(),
             'event_type':kind,'attributes':{}} for kind,h in [('sim_change',2),('number_recycle',1)]]
    f=build_features(events,at,{'action':'login'},{'status':'unknown','observed_at':at.isoformat()})
    assert f['cold_start']==1 and f['sim_changes_24h']==0


def test_signed_webhook_timestamp_and_body():
    body=b'{"event_id":"e1"}';ts='1000';sig=sign_webhook(body,ts,'secret')
    assert verify_webhook(body,ts,sig,'secret',current=1001)
    assert not verify_webhook(body+b'x',ts,sig,'secret',current=1001)
    assert not verify_webhook(body,ts,sig,'secret',current=2000)


def test_pre_replacement_mode(client):
    assert post_assessment(client,action='sim_replacement',mode='pre_replacement').status_code==201
    assert post_assessment(client,mode='pre_replacement').status_code==422


def test_production_rejects_demo_configuration():
    with pytest.raises(RuntimeError):
        Settings(environment='production',secret='a'*64,pseudonym_key='b'*64).validate()


def test_operational_data_purge(client):
    client.post('/api/v1/events',json=event(),headers=headers())
    post_assessment(client)
    response=client.delete('/api/v1/subscribers/0911223344/data',headers=headers())
    assert response.json()['deleted_records']>=3
    assert client.get('/api/v1/assessments',headers=headers()).json()['total']==0
    assert client.get('/api/v1/audit',headers=headers()).json()['chain_valid']


def test_rate_limit_enforced(client,app):
    app.state.settings.rate_limit=1
    assert client.get('/api/v1/me',headers=headers()).status_code==200
    assert client.get('/api/v1/me',headers=headers()).status_code==429


def test_absent_shadow_model_falls_back(client):
    value=post_assessment(client).json()
    assert value['fallback_used'] is True
    assert client.post('/api/v1/models/nonexistent/shadow',headers=headers()).status_code==422
