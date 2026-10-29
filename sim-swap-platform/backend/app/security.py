import hashlib
import hmac
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
import jwt
import redis
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer = HTTPBearer()
ROLE_SCOPES = {
    'administrator': {'read', 'ingest', 'assess', 'investigate', 'supervise', 'policy', 'model', 'audit', 'purge'},
    'supervisor': {'read', 'assess', 'investigate', 'supervise', 'policy', 'model', 'audit'},
    'analyst': {'read', 'assess', 'investigate'},
    'auditor': {'read', 'audit'},
    'integration': {'ingest', 'assess'},
}


@dataclass
class Principal:
    tenant: str
    subject: str
    scopes: set


class Auth:
    def __init__(self, settings):
        self.settings = settings
        self.jwks = jwt.PyJWKClient(settings.oidc_jwks, timeout=3) if settings.oidc_jwks else None
        self.redis = redis.Redis.from_url(settings.redis_url, socket_timeout=1) if settings.redis_url else None
        self.windows = defaultdict(deque)

    def authenticate(self, request: Request, credentials: HTTPAuthorizationCredentials = Depends(bearer)):
        try:
            if self.settings.environment == 'demo':
                claims = jwt.decode(credentials.credentials, self.settings.secret, algorithms=['HS256'],
                                    audience='sim-swap-demo', issuer='sim-swap-demo',
                                    options={'require': ['exp', 'iat', 'sub', 'tenant', 'role']})
            else:
                if not self.jwks:
                    raise ValueError('OIDC not configured')
                key = self.jwks.get_signing_key_from_jwt(credentials.credentials).key
                claims = jwt.decode(credentials.credentials, key, algorithms=['RS256'],
                                    audience=self.settings.oidc_audience, issuer=self.settings.oidc_issuer,
                                    options={'require': ['exp', 'iat', 'sub', 'tenant', 'role']})
                if claims['role'] != 'integration' and not set(claims.get('amr', [])).intersection({'mfa', 'hwk'}):
                    raise ValueError('MFA claim required for human users')
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', claims['tenant']):
                raise ValueError('Invalid tenant')
            scopes = ROLE_SCOPES.get(claims['role'], set())
            if not scopes:
                raise ValueError('Unknown role')
            principal = Principal(claims['tenant'], claims['sub'], scopes)
        except Exception:
            raise HTTPException(401, 'Invalid or expired access token') from None
        self.limit(principal)
        request.state.principal = principal
        return principal

    def limit(self, principal):
        key = f'rate:{principal.tenant}:{hashlib.sha256(principal.subject.encode()).hexdigest()}:{int(time.time() // 60)}'
        if self.redis:
            try:
                count = self.redis.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],120) end; return n", 1, key)
            except redis.RedisError:
                raise HTTPException(503, 'Rate limiter unavailable; retry later') from None
        else:
            window = self.windows[(principal.tenant, principal.subject)]
            current = time.monotonic()
            while window and window[0] < current - 60:
                window.popleft()
            window.append(current)
            count = len(window)
        if count > self.settings.rate_limit:
            raise HTTPException(429, 'Rate limit exceeded', headers={'Retry-After': '60'})


def require(principal, scope):
    if scope not in principal.scopes:
        raise HTTPException(403, 'Insufficient permission')


def pseudonym(value, tenant, key):
    if value.startswith('p_') and re.fullmatch(r'p_[a-f0-9]{64}', value):
        return value
    # Normalize only values that resemble phone numbers. Other account IDs remain opaque.
    cleaned = re.sub(r'[\s()-]', '', value)
    if cleaned.startswith('09') and len(cleaned) == 10 and cleaned.isdigit():
        cleaned = '+251' + cleaned[1:]
    elif cleaned.startswith('00251'):
        cleaned = '+' + cleaned[2:]
    digest = hmac.new(key.encode(), f'{tenant}\x00{cleaned}'.encode(), hashlib.sha256).hexdigest()
    return 'p_' + digest


def sign_webhook(body, timestamp, secret):
    return hmac.new(secret.encode(), f'{timestamp}.'.encode() + body, hashlib.sha256).hexdigest()


def verify_webhook(body, timestamp, signature, secret, current=None):
    try:
        if abs((current or time.time()) - int(timestamp)) > 300:
            return False
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(sign_webhook(body, timestamp, secret), signature)
