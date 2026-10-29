"""Synthetic educational scenarios only. These distributions do not represent any operator."""
import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.features import build_features


def generate(count=6000, seed=42):
    rng = random.Random(seed)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scenarios = ['normal', 'replacement', 'esim', 'upgrade', 'travel', 'recycle', 'recovery', 'fraud']
    rows = []
    for index in range(count):
        at = start + timedelta(seconds=index * 3600)
        scenario = rng.choices(scenarios, weights=[63, 9, 6, 6, 5, 3, 5, 3])[0]
        fraud = scenario == 'fraud'
        subscriber = f'synthetic-{index}'
        device = f'device-{index}'
        context = {'action': rng.choice(['login','transaction','recovery']), 'action_id': f'action-{index}',
                   'subscriber': subscriber, 'device_id': device, 'amount': rng.uniform(50,500),
                   'currency': 'ETB', 'beneficiary_id': None, 'trusted_device': not fraud and rng.random() < 0.75,
                   'mode': 'post_replacement'}
        events = []
        def add(kind, ago, **attrs):
            timestamp = (at - timedelta(hours=ago)).isoformat()
            events.append({'event_id': f'{index}-{len(events)}', 'event_type': kind,
                           'subscriber': subscriber, 'event_time': timestamp, 'ingested_at': timestamp,
                           'attributes': {'currency': 'ETB', **attrs}})
        if scenario != 'recycle':
            add('login', rng.uniform(48, 1500), device_id=device)
            for j in range(rng.randint(2, 10)):
                add('transaction', rng.uniform(24, 500), amount=rng.uniform(50, 500), beneficiary_id='known')
        else:
            add('number_recycle', 2)
        recent_swap = scenario in {'replacement','esim','upgrade','fraud'} or rng.random() < 0.08
        signal = {'status': 'no_change_in_window', 'observed_at': at.isoformat()}
        if recent_swap:
            hours = rng.uniform(0.02, 23)
            add('sim_change', hours)
            signal = {'status':'recent_change', 'observed_at':at.isoformat(), 'latest_change':(at - timedelta(hours=hours)).isoformat()}
        if fraud or scenario == 'upgrade':
            context['device_id'] = f'new-{index}'
        if fraud and rng.random() < 0.75 or scenario == 'recovery':
            add('recovery', rng.uniform(0.01, 0.8))
        if fraud and rng.random() < 0.8 or rng.random() < 0.1:
            context.update({'beneficiary_id': f'new-beneficiary-{index}', 'action': 'transaction'})
        if fraud:
            context['amount'] *= rng.uniform(3, 20)
            for j in range(rng.randint(0, 7)):
                add('failed_login', rng.uniform(0.01, 0.8))
            if rng.random() < 0.3:
                add('sim_request', 2)
                add('sim_request', 1)
                add('sim_request', 0.5)
        if rng.random() < 0.12:
            signal = {'status': rng.choice(['unknown','timeout','unsupported','stale']), 'observed_at': at.isoformat()}
        # Small label noise avoids an unrealistically perfect demonstration boundary.
        label = int(fraud)
        if rng.random() < 0.005:
            label = 1 - label
        features = build_features(events, at, context, signal)
        rows.append({'decision_time':at.isoformat(), 'subscriber':subscriber, 'campaign_id':f'campaign-{index}',
                     'operator':rng.choice(['synthetic-A','synthetic-B']), 'scenario':scenario,
                     'context':context, 'signal':signal, 'events':events, 'features':features,
                     'label':label, 'label_time':(at + timedelta(days=7)).isoformat(), 'synthetic':True})
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='data/synthetic.jsonl')
    parser.add_argument('--count', type=int, default=6000)
    args = parser.parse_args()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(row) for row in generate(args.count)) + '\n')
    print(f'Generated {args.count} synthetic observations at {path}')
