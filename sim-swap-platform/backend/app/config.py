"""Configuration: demonstration defaults are deliberately refused in production."""
import os
from dataclasses import dataclass


@dataclass
class Settings:
    environment: str = os.getenv('APP_ENV', 'demo')
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./data/platform.db')
    secret: str = os.getenv('APP_SECRET', '')
    pseudonym_key: str = os.getenv('PSEUDONYM_KEY', '')
    provider: str = os.getenv('PROVIDER_MODE', 'mock')
    provider_url: str = os.getenv('PROVIDER_URL', '')
    provider_contract: str = os.getenv('PROVIDER_CONTRACT_VERSION', '2.1.0')
    provider_token: str = os.getenv('PROVIDER_TOKEN', '')
    oidc_issuer: str = os.getenv('OIDC_ISSUER', '')
    oidc_audience: str = os.getenv('OIDC_AUDIENCE', '')
    oidc_jwks: str = os.getenv('OIDC_JWKS_URL', '')
    redis_url: str = os.getenv('REDIS_URL', '')
    webhook_url: str = os.getenv('WEBHOOK_URL', '')
    webhook_secret: str = os.getenv('WEBHOOK_SECRET', '')
    artifact_dir: str = os.getenv('ARTIFACT_DIR', './artifacts')
    max_age_days: int = int(os.getenv('MAX_EVENT_AGE_DAYS', '90'))
    signal_ttl: int = int(os.getenv('SIGNAL_TTL_SECONDS', '300'))
    assessment_ttl: int = int(os.getenv('ASSESSMENT_TTL_SECONDS', '120'))
    rate_limit: int = int(os.getenv('RATE_LIMIT_PER_MINUTE', '300'))

    def validate(self):
        if len(self.secret) < 32 or len(self.pseudonym_key) < 32 or any(value.startswith('GENERATE') for value in [self.secret, self.pseudonym_key]):
            raise RuntimeError('Run python scripts/init_demo.py; two independent 32+ character secrets required')
        if self.secret == self.pseudonym_key:
            raise RuntimeError('Use separate authentication and pseudonymization keys')
        if self.webhook_url and (len(self.webhook_secret) < 32 or
                                (self.environment != 'demo' and not self.webhook_url.startswith('https://'))):
            raise RuntimeError('Webhook requires signing secret and HTTPS outside demo')
        if self.provider == 'camara' and self.provider_contract != '2.1.0':
            raise RuntimeError('This adapter targets CAMARA SIM Swap 2.1.0; approve and test changes explicitly')
        if self.environment == 'production':
            required = [self.oidc_issuer, self.oidc_audience, self.oidc_jwks, self.redis_url,
                        self.provider_url, self.provider_token]
            if self.provider != 'camara' or not all(required):
                raise RuntimeError('Production requires real provider, OIDC, and Redis configuration')
            if not self.database_url.startswith('postgresql+psycopg://'):
                raise RuntimeError('Production requires PostgreSQL')
            if any(not v.startswith('https://') for v in [self.oidc_issuer, self.oidc_jwks, self.provider_url]):
                raise RuntimeError('Production identity and provider endpoints require HTTPS')
