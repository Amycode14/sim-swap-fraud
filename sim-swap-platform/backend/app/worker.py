"""Single outbox worker per deployment. Delivery is at least once; receivers deduplicate event_id."""
import random
import time
from datetime import timedelta
import httpx
from sqlalchemy import select
from .config import Settings
from .db import Tenant, make_engine, session_factory, lock_tenant, records, canonical, now, iso
from .features import dt
from .security import sign_webhook


def deliver(settings, Session):
    completed = 0
    with Session() as db:
        tenants = list(db.scalars(select(Tenant.id)))
    for tenant in tenants:
        with Session.begin() as db:
            lock_tenant(db, tenant)
            due = [r for r in records(db, tenant, 'outbox')
                   if r.data['status'] == 'pending' and dt(r.data['next_attempt']) <= now()][:50]
            for row in due:
                value = row.data
                body = canonical({'tenant': tenant, 'event_id': value['event_id'], 'type': value['type'], 'payload': value['payload']}).encode()
                timestamp = str(int(time.time()))
                try:
                    response = httpx.post(settings.webhook_url, content=body,
                        headers={'Content-Type': 'application/json', 'X-Event-ID': value['event_id'],
                                 'X-Signature-Timestamp': timestamp,
                                 'X-Signature': sign_webhook(body, timestamp, settings.webhook_secret)},
                        timeout=3, follow_redirects=False)
                    response.raise_for_status()
                    value.update({'status': 'delivered', 'delivered_at': iso()})
                    completed += 1
                except httpx.HTTPError:
                    value['attempts'] += 1
                    value['status'] = 'dead_letter' if value['attempts'] >= 8 else 'pending'
                    value['next_attempt'] = iso(now() + timedelta(seconds=min(300, 2 ** value['attempts']) + random.random()))
                    value['last_error'] = 'Delivery failed; destination response redacted'
                row.update(value)
    return completed


def main():
    settings = Settings()
    settings.validate()
    if not settings.webhook_url:
        raise SystemExit('Configure WEBHOOK_URL and WEBHOOK_SECRET before starting worker')
    Session = session_factory(make_engine(settings.database_url))
    while True:
        try:
            deliver(settings, Session)
        except Exception:
            print('Outbox iteration failed; pending records retained', flush=True)
        time.sleep(2)


if __name__ == '__main__':
    main()
