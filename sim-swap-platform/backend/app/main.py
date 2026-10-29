import hashlib
import json
import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from .config import Settings
from .db import Base, Tenant, canonical, now, iso, make_engine, session_factory, lock_tenant, find, records, put, audit, verify_audit
from .security import Auth, require, pseudonym
from .schemas import EventIn, AssessmentIn, CasePatch, PolicyIn, DecisionValidation, OverrideIn
from .features import build_features, dt, VERSION
from .decisions import DEFAULT_POLICY, rules
from .provider import Provider
from .model_runtime import ModelRuntime


def create_app(settings=None):
    settings = settings or Settings()
    settings.validate()
    Path('data').mkdir(exist_ok=True)
    engine = make_engine(settings.database_url)
    Session = session_factory(engine)
    auth = Auth(settings)
    provider = Provider(settings)
    def runtime_for(tenant):
        root = Path(settings.artifact_dir)
        return ModelRuntime(root if settings.environment == 'demo' else root / tenant)
    mutex = asyncio.Lock()  # SQLite demo serializes writes; PostgreSQL also uses per-tenant row lock.
    registry = CollectorRegistry()
    assessments_counter = Counter('sim_assessments_total', 'Assessments', ['recommendation'], registry=registry)
    latency = Histogram('sim_assessment_seconds', 'Complete assessment latency including provider', registry=registry)

    @asynccontextmanager
    async def lifespan(app):
        if settings.environment == 'demo':
            Base.metadata.create_all(engine)
            with Session.begin() as db:
                if db.get(Tenant, 'demo') is None:
                    db.add(Tenant(id='demo'))
        # Production schema changes must be deployed explicitly via Alembic.
        yield
        engine.dispose()

    app = FastAPI(title='SIM Shield', version='0.1.0', lifespan=lifespan,
                  description='Fraud risk recommendations. Synthetic models are shadow-only. No external enforcement.')
    app.state.settings = settings
    app.state.Session = Session
    app.state.provider = provider
    app.state.engine = engine
    app.state.auth = auth

    async def connection(principal=Depends(auth.authenticate)):
        async with mutex:
            with Session.begin() as db:
                try:
                    lock_tenant(db, principal.tenant)
                except ValueError:
                    raise HTTPException(403, 'Tenant not provisioned') from None
                yield db

    def get_row(db, principal, kind, key):
        row = find(db, principal.tenant, kind, key)
        if row is None:
            raise HTTPException(404, 'Record not found')
        return row

    def active_policy(db, tenant):
        row = find(db, tenant, 'setting', 'active_policy')
        return dict(row.data) if row else dict(DEFAULT_POLICY)

    def history(db, tenant, subscriber):
        # Reference implementation uses JSON records. High-volume deployment needs indexed typed event tables.
        return [row.data for row in records(db, tenant, 'event') if row.data['subscriber'] == subscriber]

    def normalized_context(payload, principal):
        value = payload.model_dump(mode='json')
        value['subscriber'] = pseudonym(value['subscriber'], principal.tenant, settings.pseudonym_key)
        for field in ('device_id', 'beneficiary_id'):
            if value.get(field):
                value[field] = pseudonym(value[field], principal.tenant, settings.pseudonym_key)
        return value

    @app.middleware('http')
    async def harden(request, call_next):
        # Size rejection before body consumption; reverse proxy must also cap chunked uploads.
        try:
            if int(request.headers.get('content-length', '0')) > 1024 * 1024:
                return Response('Request too large', status_code=413)
        except ValueError:
            return Response('Invalid Content-Length', status_code=400)
        try:
            response = await call_next(request)
        except SQLAlchemyError:
            response = Response('Database unavailable; no decision issued', status_code=503)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        return response

    @app.get('/health/live')
    def live():
        return {'status': 'alive', 'environment': settings.environment}

    @app.get('/health/ready')
    def ready():
        try:
            with engine.connect() as db:
                db.execute(text('SELECT 1'))
            if auth.redis:
                auth.redis.ping()
        except Exception:
            raise HTTPException(503, 'Dependency unavailable') from None
        return {'status': 'ready', 'provider_mode': settings.provider,
                'production_approved': False}

    @app.get('/metrics')
    def metrics(principal=Depends(auth.authenticate)):
        require(principal, 'audit')
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.get('/api/v1/me')
    def me(principal=Depends(auth.authenticate)):
        return {'tenant': principal.tenant, 'subject': principal.subject, 'scopes': sorted(principal.scopes),
                'environment': settings.environment}

    def ingest_one(payload, principal, db):
        current = now()
        if payload.event_time > current + timedelta(seconds=60):
            raise HTTPException(422, 'Event time exceeds allowed clock skew')
        if payload.event_time < current - timedelta(days=settings.max_age_days):
            raise HTTPException(422, 'Event is outside retention window')
        body = payload.model_dump(mode='json')
        body['subscriber'] = pseudonym(body['subscriber'], principal.tenant, settings.pseudonym_key)
        if body.get('account'):
            body['account'] = pseudonym(body['account'], principal.tenant, settings.pseudonym_key)
        for field in ('device_id', 'beneficiary_id', 'agent_id'):
            if body['attributes'].get(field):
                body['attributes'][field] = pseudonym(body['attributes'][field], principal.tenant, settings.pseudonym_key)
        digest = hashlib.sha256(canonical(body).encode()).hexdigest()
        existing = find(db, principal.tenant, 'event', body['event_id'])
        if existing:
            if existing.data['payload_hash'] != digest:
                raise HTTPException(409, 'Event ID reused with different payload')
            return {'event_id': body['event_id'], 'duplicate': True}
        body.update({'ingested_at': iso(current), 'payload_hash': digest,
                     'quality': 'late' if (current - payload.event_time).total_seconds() > 300 else 'timely'})
        put(db, principal.tenant, 'event', body['event_id'], body)
        audit(db, principal.tenant, principal.subject, 'event_ingested', body['event_id'], settings.secret,
              {'event_type': body['event_type'], 'source': body['source']})
        return {'event_id': body['event_id'], 'duplicate': False, 'quality': body['quality']}

    @app.post('/api/v1/events', status_code=201)
    def ingest(payload: EventIn, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'ingest')
        return ingest_one(payload, principal, db)

    @app.post('/api/v1/events/batch', status_code=201)
    def ingest_batch(payload: list[EventIn], principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'ingest')
        if not 1 <= len(payload) <= 200:
            raise HTTPException(422, 'Batch must contain 1 to 200 events')
        return {'results': [ingest_one(item, principal, db) for item in payload], 'atomic': True}

    @app.get('/api/v1/events')
    def events(subscriber: str, limit: int = Query(100, ge=1, le=500), principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'read')
        key = pseudonym(subscriber, principal.tenant, settings.pseudonym_key)
        return {'items': history(db, principal.tenant, key)[-limit:]}

    @app.post('/api/v1/assessments', status_code=201)
    def assess(payload: AssessmentIn, idempotency_key: str = Header(min_length=8, max_length=100),
               principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'assess')
        if (payload.mode == 'pre_replacement') != (payload.action == 'sim_replacement'):
            raise HTTPException(422, 'Pre-replacement mode must assess sim_replacement; other actions use post-replacement')
        context = normalized_context(payload, principal)
        digest = hashlib.sha256(canonical(context).encode()).hexdigest()
        key = hashlib.sha256(idempotency_key.encode()).hexdigest()
        existing = find(db, principal.tenant, 'idempotency', key)
        if existing:
            if existing.data['payload_hash'] != digest:
                raise HTTPException(409, 'Idempotency key reused with different action')
            # Replays return the original snapshot, including original expiry, never a fresh approval.
            return get_row(db, principal, 'assessment', existing.data['assessment_id']).data
        start = time.perf_counter()
        signal = provider.check(payload.subscriber)
        at = now()
        all_events = history(db, principal.tenant, context['subscriber'])
        if settings.provider == 'mock':
            recycled = [e for e in all_events if e['event_type'] == 'number_recycle']
            cutoff = max([dt(e['event_time']) for e in recycled], default=dt('1970-01-01T00:00:00+00:00'))
            swaps = [e for e in all_events if e['event_type'] == 'sim_change' and dt(e['event_time']) <= at and dt(e['ingested_at']) <= at and dt(e['event_time']) > cutoff]
            swaps.sort(key=lambda e: dt(e['event_time']))
            if swaps:
                signal = {'status': 'recent_change' if (at - dt(swaps[-1]['event_time'])).total_seconds() < 86400 else 'stale',
                          'latest_change': swaps[-1]['event_time'], 'observed_at': swaps[-1]['ingested_at'],
                          'source': 'synthetic-ingested-sim-event', 'demo': True}
        if signal.get('observed_at') and (at - dt(signal['observed_at'])).total_seconds() > settings.signal_ttl and signal['status'] in {'recent_change', 'no_change_in_window'}:
            signal['status'] = 'stale'
        features = build_features(all_events, at, context, signal)
        policy = active_policy(db, principal.tenant)
        result = rules(features, context, policy)
        model = find(db, principal.tenant, 'setting', 'shadow_model')
        ml_score = None
        model_error = None
        if model:
            try:
                ml_score, manifest = runtime_for(principal.tenant).score(model.data['model_id'], features)
            except Exception:
                model_error = 'Model unavailable or incompatible; rules remain authoritative'
        assessment_id = str(uuid.uuid4())
        result.update({'assessment_id': assessment_id, 'subscriber': context['subscriber'],
                       'context': context, 'assessed_at': iso(at),
                       'expires_at': iso(at + timedelta(seconds=policy['assessment_ttl'])),
                       'policy_version': policy['version'], 'feature_version': VERSION,
                       'model_version': model.data['model_id'] if model else None,
                       'fraud_probability': None, 'shadow_model_score': ml_score,
                       'shadow_score_meaning': 'Synthetic/unvalidated model output; not used to authorize or block',
                       'fallback_used': not model or bool(model_error), 'model_error': model_error,
                       'signal': signal, 'features': features, 'demo': settings.environment == 'demo',
                       'recommendation_only': True, 'version': 1,
                       'event_watermark': max([e['ingested_at'] for e in all_events], default='')})
        put(db, principal.tenant, 'assessment', assessment_id, result)
        put(db, principal.tenant, 'idempotency', key, {'payload_hash': digest, 'assessment_id': assessment_id})
        if result['recommendation'] in {'REVIEW', 'TEMPORARY_HOLD', 'BLOCK_RECOMMENDATION'}:
            case_id = str(uuid.uuid4())
            put(db, principal.tenant, 'case', case_id, {'case_id': case_id, 'assessment_id': assessment_id,
                'status': 'open', 'assigned_to': None, 'notes': [], 'created_at': iso(at), 'version': 1,
                'label': None, 'label_provenance': None, 'label_history': []})
        audit(db, principal.tenant, principal.subject, 'assessment_created', assessment_id, settings.secret,
              {'recommendation': result['recommendation'], 'policy_version': policy['version']})
        put(db, principal.tenant, 'outbox', assessment_id, {'event_id': assessment_id, 'type': 'assessment.created',
            'payload': {'assessment_id': assessment_id, 'recommendation': result['recommendation'], 'expires_at': result['expires_at']},
            'status': 'pending' if settings.webhook_url else 'disabled', 'attempts': 0, 'next_attempt': iso()})
        assessments_counter.labels(result['recommendation']).inc()
        latency.observe(time.perf_counter() - start)
        return result

    @app.get('/api/v1/assessments')
    def list_assessments(offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
                         recommendation: str | None = None, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'read')
        items = [row.data for row in reversed(records(db, principal.tenant, 'assessment'))]
        if recommendation:
            items = [item for item in items if item['recommendation'] == recommendation]
        return {'items': items[offset:offset + limit], 'total': len(items)}

    @app.get('/api/v1/assessments/{assessment_id}')
    def assessment(assessment_id: str, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'read')
        return get_row(db, principal, 'assessment', assessment_id).data

    @app.post('/api/v1/assessments/{assessment_id}/validate')
    def validate(assessment_id: str, payload: DecisionValidation, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'assess')
        result = get_row(db, principal, 'assessment', assessment_id).data
        reasons = []
        if payload.action_id != result['context']['action_id'] or payload.action != result['context']['action']:
            reasons.append('ACTION_MISMATCH')
        if now() >= dt(result['expires_at']):
            reasons.append('EXPIRED')
        watermark = max([e['ingested_at'] for e in history(db, principal.tenant, result['subscriber'])], default='')
        if watermark != result['event_watermark']:
            reasons.append('NEW_EVENTS_REQUIRE_REASSESSMENT')
        return {'valid': not reasons, 'reasons': reasons, 'recommendation': result['recommendation'],
                'enforcement_performed': False}

    @app.post('/api/v1/assessments/{assessment_id}/override')
    def override(assessment_id: str, payload: OverrideIn, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'supervise')
        row = get_row(db, principal, 'assessment', assessment_id)
        if row.version != payload.expected_version:
            raise HTTPException(409, 'Version conflict')
        result = row.data
        if now() >= dt(result['expires_at']):
            raise HTTPException(409, 'Expired assessment must be reassessed')
        result['override'] = {'actor': principal.subject, 'time': iso(), **payload.model_dump()}
        result['recommendation'] = payload.recommendation
        result['version'] = row.version + 1
        row.update(result)
        audit(db, principal.tenant, principal.subject, 'assessment_overridden', assessment_id, settings.secret,
              {'recommendation': payload.recommendation, 'verification_reference': payload.independent_verification_reference})
        return result

    @app.get('/api/v1/cases')
    def cases(status: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
              principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'read')
        items = [row.data for row in reversed(records(db, principal.tenant, 'case'))]
        if status:
            items = [item for item in items if item['status'] == status]
        return {'items': items[offset:offset + limit], 'total': len(items)}

    @app.patch('/api/v1/cases/{case_id}')
    def update_case(case_id: str, payload: CasePatch, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'investigate')
        row = get_row(db, principal, 'case', case_id)
        if payload.expected_version != row.version:
            raise HTTPException(409, 'Case changed; refresh before editing')
        terminal = payload.status in {'resolved_fraud', 'resolved_legitimate', 'disputed'}
        if terminal:
            require(principal, 'supervise')
        if payload.status.startswith('resolved') and not payload.evidence:
            raise HTTPException(422, 'Adjudication requires an evidence reference')
        body = row.data
        if body['status'].startswith('resolved') and not terminal:
            require(principal, 'supervise')
        body.update({'status': payload.status, 'assigned_to': payload.assigned_to, 'version': row.version + 1})
        body['notes'].append({'actor': principal.subject, 'time': iso(), 'note': payload.note, 'evidence': payload.evidence})
        if terminal or body['label']:
            previous = body['label']
            body['label'] = {'resolved_fraud': 1, 'resolved_legitimate': 0}.get(payload.status)
            body['label_provenance'] = {'actor': principal.subject, 'time': iso(), 'evidence': payload.evidence}
            body['label_history'].append({'previous': previous, 'new': body['label'], **body['label_provenance']})
        row.update(body)
        audit(db, principal.tenant, principal.subject, 'case_updated', case_id, settings.secret,
              {'status': payload.status, 'version': body['version']})
        return body

    @app.get('/api/v1/policies')
    def policies(principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'read')
        return {'active': active_policy(db, principal.tenant), 'proposals': [row.data for row in records(db, principal.tenant, 'policy')]}

    @app.post('/api/v1/policies/simulate')
    def simulate(payload: PolicyIn, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'policy')
        if not payload.step_up < payload.review < payload.hold:
            raise HTTPException(422, 'Thresholds must strictly increase')
        policy = payload.model_dump()
        distribution = {}
        changes = 0
        for row in records(db, principal.tenant, 'assessment'):
            result = rules(row.data['features'], row.data['context'], policy)
            action = result['recommendation']
            distribution[action] = distribution.get(action, 0) + 1
            changes += action != row.data['recommendation']
        return {'distribution': distribution, 'changed_decisions': changes, 'offline_only': True}

    @app.post('/api/v1/policies', status_code=201)
    def propose(payload: PolicyIn, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'policy')
        if not payload.step_up < payload.review < payload.hold:
            raise HTTPException(422, 'Thresholds must strictly increase')
        key = str(uuid.uuid4())
        body = {**payload.model_dump(), 'version': key, 'proposed_by': principal.subject, 'approved_by': None}
        put(db, principal.tenant, 'policy', key, body)
        audit(db, principal.tenant, principal.subject, 'policy_proposed', key, settings.secret)
        return body

    @app.post('/api/v1/policies/{policy_id}/approve')
    def approve(policy_id: str, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'supervise')
        body = get_row(db, principal, 'policy', policy_id).data
        if body['proposed_by'] == principal.subject:
            raise HTTPException(403, 'A different supervisor must approve this policy')
        body['approved_by'] = principal.subject
        row = find(db, principal.tenant, 'setting', 'active_policy')
        if row:
            row.update(body)
        else:
            put(db, principal.tenant, 'setting', 'active_policy', body)
        audit(db, principal.tenant, principal.subject, 'policy_activated', policy_id, settings.secret)
        return body

    @app.get('/api/v1/models')
    def models(principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'read')
        manifests = []
        root = runtime_for(principal.tenant).root
        for folder in root.iterdir() if root.exists() else []:
            try:
                manifest, _ = runtime_for(principal.tenant).manifest(folder.name)
                manifests.append({'model_id': folder.name, **manifest})
            except Exception:
                continue
        active = find(db, principal.tenant, 'setting', 'shadow_model')
        return {'items': manifests, 'shadow_model': active.data if active else None, 'active_ml_enforcement': False}

    @app.post('/api/v1/models/{model_id}/shadow')
    def shadow(model_id: str, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'model')
        try:
            runtime_for(principal.tenant).manifest(model_id)
        except Exception:
            raise HTTPException(422, 'Model artifact missing, invalid, or incompatible') from None
        row = find(db, principal.tenant, 'setting', 'shadow_model')
        value = {'model_id': model_id, 'activated_by': principal.subject, 'time': iso()}
        if row:
            row.update(value)
        else:
            put(db, principal.tenant, 'setting', 'shadow_model', value)
        audit(db, principal.tenant, principal.subject, 'shadow_model_changed', model_id, settings.secret)
        return value

    @app.delete('/api/v1/models/shadow')
    def disable_shadow(principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'model')
        row = find(db, principal.tenant, 'setting', 'shadow_model')
        if row:
            db.delete(row)
        audit(db, principal.tenant, principal.subject, 'shadow_model_disabled', 'shadow', settings.secret)
        return {'mode': 'rules_only'}

    @app.get('/api/v1/monitoring')
    def monitoring(principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'read')
        data = [row.data for row in records(db, principal.tenant, 'assessment')]
        distribution = {}
        for item in data:
            action = item['recommendation']
            distribution[action] = distribution.get(action, 0) + 1
        recent = data[-100:]
        missing = sum(item['features']['signal_missing'] for item in recent) / max(1, len(recent))
        return {'total_assessments': len(data), 'decision_distribution': distribution,
                'recent_signal_missing_rate': missing, 'recent_average_score': sum(i['risk_score'] for i in recent) / max(1, len(recent)),
                'open_cases': sum(row.data['status'] in {'open', 'investigating'} for row in records(db, principal.tenant, 'case')),
                'data_quality_alert': missing > 0.2, 'window_size': len(recent),
                'automated_enforcement': False, 'demo': settings.environment == 'demo'}

    @app.get('/api/v1/audit')
    def audit_list(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                   principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'audit')
        rows = records(db, principal.tenant, 'audit')
        return {'items': [r.data for r in rows[offset:offset + limit]], 'total': len(rows),
                'chain_valid': verify_audit(rows, settings.secret)}

    @app.get('/api/v1/outbox')
    def outbox(principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'audit')
        return {'items': [row.data for row in records(db, principal.tenant, 'outbox')]}

    @app.post('/api/v1/outbox/{event_id}/replay')
    def replay(event_id: str, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'supervise')
        if not settings.webhook_url:
            raise HTTPException(409, 'No webhook destination configured')
        row = get_row(db, principal, 'outbox', event_id)
        value = row.data
        if value['status'] != 'dead_letter':
            raise HTTPException(409, 'Only dead-letter events may be replayed')
        value.update({'status': 'pending', 'attempts': 0, 'next_attempt': iso()})
        row.update(value)
        audit(db, principal.tenant, principal.subject, 'webhook_replayed', event_id, settings.secret)
        return value

    @app.delete('/api/v1/subscribers/{subscriber}/data')
    def purge(subscriber: str, principal=Depends(auth.authenticate), db=Depends(connection)):
        require(principal, 'purge')
        key = pseudonym(subscriber, principal.tenant, settings.pseudonym_key)
        assessment_ids = {r.key for r in records(db, principal.tenant, 'assessment') if r.data['subscriber'] == key}
        deleted = 0
        for kind in ['event', 'assessment', 'case', 'idempotency', 'outbox']:
            for row in records(db, principal.tenant, kind):
                value = row.data
                if value.get('subscriber') == key or value.get('assessment_id') in assessment_ids or (kind == 'outbox' and row.key in assessment_ids):
                    db.delete(row)
                    deleted += 1
        audit(db, principal.tenant, principal.subject, 'subscriber_operational_data_purged', 'redacted', settings.secret,
              {'records': deleted, 'training_artifact_erasure_pending': True})
        return {'deleted_records': deleted, 'training_artifact_erasure_pending': True,
                'audit_retention': 'Separate approved retention policy required; audit chain retained'}

    frontend = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
    if frontend.exists():
        app.mount('/', StaticFiles(directory=frontend, html=True), name='dashboard')
    if __import__('os').getenv('OTEL_ENABLED', 'false').lower() == 'true':
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        tracing = TracerProvider()
        tracing.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tracing)
        # Exclude URL/query capture endpoints that can contain subscriber identifiers.
        FastAPIInstrumentor.instrument_app(app, excluded_urls='/api/v1/events,/api/v1/subscribers.*,/health.*')
    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(create_app(), host='127.0.0.1', port=8000)
