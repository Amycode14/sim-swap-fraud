"""Seed live API with synthetic scenarios. Requires a demo admin bearer token."""
import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone
import httpx
parser = argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:8000')
parser.add_argument('--token',required=True)
args = parser.parse_args()
client = httpx.Client(base_url=args.url,headers={'Authorization':'Bearer '+args.token},timeout=20,trust_env=False)
now = datetime.now(timezone.utc)
for scenario in ['ordinary-login','legitimate-esim','suspicious-recovery','suspicious-transfer','recycled-number']:
    subscriber = f'demo-{scenario}-{str(uuid.uuid4())[:8]}'
    prefix = str(uuid.uuid4())
    def event(kind,hours,**attributes):
        payload = {'event_id':prefix+'-'+kind+str(hours),'source':'synthetic-demo','subscriber':subscriber,
                   'event_time':(now-timedelta(hours=hours)).isoformat(),'event_type':kind,'attributes':attributes}
        response=client.post('/api/v1/events',json=payload)
        response.raise_for_status()
    event('login',72,device_id='known-device')
    event('transaction',48,amount=200,currency='ETB',beneficiary_id='known-beneficiary')
    if scenario != 'ordinary-login':
        event('sim_change',.1,reason='esim' if scenario=='legitimate-esim' else 'replacement')
    if scenario == 'suspicious-recovery':
        event('recovery',.05)
    if scenario == 'recycled-number':
        event('number_recycle',.01)
    context={'subscriber':subscriber,'action_id':prefix,'action':'login','device_id':'known-device','trusted_device':True}
    if scenario=='suspicious-recovery':
        context.update({'action':'recovery','device_id':'unfamiliar-device','trusted_device':False})
    if scenario=='suspicious-transfer':
        context.update({'action':'transaction','device_id':'unfamiliar-device','amount':5000,'currency':'ETB','beneficiary_id':'new-beneficiary','trusted_device':False})
    response=client.post('/api/v1/assessments',json=context,headers={'Idempotency-Key':str(uuid.uuid4())})
    response.raise_for_status()
    value=response.json()
    print(json.dumps({'scenario':scenario,'risk_score':value['risk_score'],'recommendation':value['recommendation']}))
