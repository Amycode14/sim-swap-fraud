"""Tenant-scoped storage. Tenant row locks serialize transactional audit and outbox writes."""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, Text, select, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def now():
    return datetime.now(timezone.utc)


def iso(value=None):
    return (value or now()).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = 'tenants'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)


class Record(Base):
    __tablename__ = 'records'
    __table_args__ = (UniqueConstraint('tenant', 'kind', 'key'), Index('record_lookup', 'tenant', 'kind', 'created'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(30))
    key: Mapped[str] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created: Mapped[str] = mapped_column(String(40), default=iso)
    body: Mapped[str] = mapped_column(Text)

    @property
    def data(self):
        return json.loads(self.body)

    def update(self, value):
        self.body = canonical(value)
        self.version += 1


def make_engine(url):
    kwargs = {'pool_pre_ping': True}
    if url.startswith('sqlite'):
        kwargs['connect_args'] = {'check_same_thread': False, 'timeout': 30}
        if ':memory:' in url:
            kwargs['poolclass'] = StaticPool
    return create_engine(url, **kwargs)


def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


def lock_tenant(db, tenant):
    # Tenants must be provisioned by an operator, never accepted from request bodies.
    row = db.scalar(select(Tenant).where(Tenant.id == tenant).with_for_update())
    if row is None:
        raise ValueError('Tenant is not provisioned')


def find(db, tenant, kind, key):
    return db.scalar(select(Record).where(Record.tenant == tenant, Record.kind == kind, Record.key == key))


def records(db, tenant, kind):
    return list(db.scalars(select(Record).where(Record.tenant == tenant, Record.kind == kind).order_by(Record.key if kind == 'audit' else Record.created)))


def put(db, tenant, kind, key, body):
    row = Record(tenant=tenant, kind=kind, key=key, body=canonical(body))
    db.add(row)
    db.flush()
    return row


def audit(db, tenant, actor, action, target, secret, detail=None):
    latest = db.scalar(select(Record).where(Record.tenant == tenant, Record.kind == 'audit').order_by(Record.key.desc()).limit(1))
    previous = latest.data['hash'] if latest else '0' * 64
    sequence = latest.data['sequence'] + 1 if latest else 1
    payload = {'sequence': sequence, 'timestamp': iso(), 'actor': actor, 'action': action,
               'target': target, 'detail': detail or {}, 'previous_hash': previous}
    payload['hash'] = hmac.new(secret.encode(), canonical(payload).encode(), hashlib.sha256).hexdigest()
    put(db, tenant, 'audit', f'{sequence:020d}', payload)


def verify_audit(rows, secret):
    previous = '0' * 64
    for sequence, row in enumerate(rows, 1):
        value = dict(row.data)
        signature = value.pop('hash')
        expected = hmac.new(secret.encode(), canonical(value).encode(), hashlib.sha256).hexdigest()
        if value['sequence'] != sequence or value['previous_hash'] != previous or not hmac.compare_digest(signature, expected):
            return False
        previous = signature
    return True
