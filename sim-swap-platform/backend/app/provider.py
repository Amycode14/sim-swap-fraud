"""Provider boundary. CAMARA /check only: no invented operator-specific endpoints."""
import time
from urllib.parse import urlparse
import httpx
from .db import iso


class Provider:
    def __init__(self, settings):
        self.settings = settings
        self.failures = 0
        self.open_until = 0.0

    def check(self, phone):
        if self.settings.provider == 'mock':
            return {'status': 'unknown', 'observed_at': iso(), 'source': 'mock-no-network-data',
                    'demo': True, 'monitoring_hours': None}
        if self.settings.provider != 'camara':
            return {'status': 'unsupported', 'observed_at': iso(), 'source': 'disabled'}
        if time.monotonic() < self.open_until:
            return {'status': 'outage', 'observed_at': iso(), 'source': 'camara-circuit-open'}
        if phone.startswith('p_'):
            return {'status': 'unknown', 'observed_at': iso(), 'source': 'camara-phone-not-provided'}
        if urlparse(self.settings.provider_url).scheme != 'https':
            return {'status': 'unsupported', 'observed_at': iso(), 'source': 'camara-invalid-configuration'}
        try:
            response = httpx.post(self.settings.provider_url.rstrip('/') + '/check',
                                  headers={'Authorization': 'Bearer ' + self.settings.provider_token},
                                  json={'phoneNumber': phone, 'maxAge': 24}, timeout=2, follow_redirects=False)
            if response.status_code in {404, 501}:
                return {'status': 'unsupported', 'observed_at': iso(), 'source': 'camara'}
            response.raise_for_status()
            data = response.json()
            if type(data.get('swapped')) is not bool:
                raise ValueError('Provider returned no boolean swapped signal')
            self.failures = 0
            return {'status': 'recent_change' if data['swapped'] else 'no_change_in_window',
                    'monitoring_hours': 24, 'observed_at': iso(), 'source': 'camara',
                    # /check supplies a window, never invent an exact swap timestamp.
                    'recency_window_only': True}
        except httpx.TimeoutException:
            status = 'timeout'
        except (httpx.HTTPError, ValueError):
            status = 'outage'
        self.failures += 1
        if self.failures >= 3:
            self.open_until = time.monotonic() + 30
        return {'status': status, 'observed_at': iso(), 'source': 'camara'}
