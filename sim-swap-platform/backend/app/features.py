"""Shared point-in-time feature builder; training and API call this exact function."""
from datetime import datetime, timedelta, timezone
import numpy as np

VERSION = 'features-1'
NAMES = ['sim_age_hours', 'sim_changes_24h', 'requests_24h', 'port_recent', 'new_device',
         'recovery_recent', 'new_beneficiary', 'failed_logins_1h', 'transactions_1h',
         'amount_ratio', 'tenure_days', 'signal_missing', 'trusted_device', 'cold_start', 'network_recent']


def dt(value):
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    return value.astimezone(timezone.utc)


def build_features(events, decision_time, context, signal):
    at = dt(decision_time)
    # Both clocks must qualify: late-arriving history cannot leak into old decisions.
    history = sorted([e for e in events if dt(e['event_time']) <= at and dt(e['ingested_at']) <= at],
                     key=lambda e: dt(e['event_time']))
    # Number reassignment severs prior subscriber history.
    recycled = [e for e in history if e['event_type'] == 'number_recycle']
    if recycled:
        history = [e for e in history if dt(e['event_time']) > dt(recycled[-1]['event_time'])]
    day = [e for e in history if dt(e['event_time']) >= at - timedelta(days=1)]
    hour = [e for e in day if dt(e['event_time']) >= at - timedelta(hours=1)]
    swaps = [e for e in history if e['event_type'] == 'sim_change']
    status = signal.get('status', 'unknown')
    observed = dt(signal['observed_at']) if signal.get('observed_at') else at
    signal_missing = status not in {'recent_change', 'no_change_in_window'} or observed > at
    latest = signal.get('latest_change') if not signal_missing else None
    last = dt(latest) if latest else (dt(swaps[-1]['event_time']) if swaps else None)
    if recycled and last and last <= dt(recycled[-1]['event_time']):
        last = None
        status = 'unknown'
        signal_missing = True
    # A past local event is still useful even when a live provider is unavailable.
    age = max(0, (at - last).total_seconds() / 3600) if last and last <= at else 2160.0
    device = context.get('device_id')
    known = {e['attributes'].get('device_id') for e in history if e['attributes'].get('device_id')}
    beneficiary = context.get('beneficiary_id')
    known_beneficiaries = {e['attributes'].get('beneficiary_id') for e in history
                         if e['event_type'] == 'transaction'}
    amounts = [e['attributes']['amount'] for e in history if e['event_type'] == 'transaction'
               and e['attributes'].get('amount') is not None
               and e['attributes'].get('currency', 'ETB') == context.get('currency', 'ETB')]
    median = float(np.median(amounts)) if amounts else 0
    return dict(zip(NAMES, [
        min(age, 2160), sum(e['event_type'] == 'sim_change' for e in day),
        sum(e['event_type'] == 'sim_request' for e in day), int(any(e['event_type'] == 'port' for e in day)),
        int(bool(device) and device not in known), int(any(e['event_type'] == 'recovery' for e in hour)),
        int(bool(beneficiary) and beneficiary not in known_beneficiaries),
        sum(e['event_type'] == 'failed_login' for e in hour), sum(e['event_type'] == 'transaction' for e in hour),
        min(100.0, context.get('amount', 0) / max(median, 1.0)) if amounts else 0.0,
        min(3650.0, max(0, (at - dt(history[0]['event_time'])).total_seconds() / 86400)) if history else 0.0,
        int(signal_missing), int(context.get('trusted_device', False)), int(not history), int(status == 'recent_change' and not signal_missing)
    ]))


def vector(features):
    return np.array([[float(features[name]) for name in NAMES]], dtype=float)
