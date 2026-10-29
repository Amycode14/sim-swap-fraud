from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

EventType = Literal['sim_request', 'sim_change', 'port', 'login', 'failed_login', 'recovery',
                    'beneficiary', 'transaction', 'device_change', 'legitimate_replacement', 'number_recycle']
SignalStatus = Literal['recent_change', 'no_change_in_window', 'unknown', 'unsupported', 'stale', 'timeout', 'outage']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Attributes(Strict):
    device_id: str | None = Field(None, max_length=120)
    beneficiary_id: str | None = Field(None, max_length=120)
    agent_id: str | None = Field(None, max_length=120)
    amount: float | None = Field(None, ge=0, le=1e12, allow_inf_nan=False)
    currency: str = Field('ETB', pattern='^[A-Z]{3}$')
    country: str | None = Field(None, pattern='^[A-Z]{2}$')
    trusted_device: bool = False
    reason: Literal['replacement', 'esim', 'upgrade', 'travel', 'recycle'] | None = None


class EventIn(Strict):
    event_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')
    schema_version: Literal['1'] = '1'
    source: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    subscriber: str = Field(min_length=1, max_length=160)
    account: str | None = Field(None, max_length=160)
    event_time: datetime
    event_type: EventType
    attributes: Attributes = Field(default_factory=Attributes)

    @field_validator('event_time')
    @classmethod
    def utc(cls, value):
        if value.tzinfo is None:
            raise ValueError('Timezone is required')
        return value.astimezone(timezone.utc)


class AssessmentIn(Strict):
    subscriber: str = Field(min_length=1, max_length=160)
    action_id: str = Field(min_length=1, max_length=100)
    action: Literal['sim_replacement', 'login', 'recovery', 'beneficiary_change', 'transaction']
    mode: Literal['pre_replacement', 'post_replacement'] = 'post_replacement'
    device_id: str | None = Field(None, max_length=120)
    amount: float = Field(0, ge=0, le=1e12, allow_inf_nan=False)
    currency: str = Field('ETB', pattern='^[A-Z]{3}$')
    beneficiary_id: str | None = Field(None, max_length=120)
    trusted_device: bool = False


class CasePatch(Strict):
    expected_version: int = Field(ge=1)
    status: Literal['open', 'investigating', 'resolved_fraud', 'resolved_legitimate', 'unresolved', 'disputed']
    note: str = Field(min_length=1, max_length=2000)
    assigned_to: str | None = Field(None, max_length=120)
    evidence: str | None = Field(None, max_length=500)


class PolicyIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    step_up: int = Field(30, ge=1, le=98)
    review: int = Field(60, ge=2, le=99)
    hold: int = Field(85, ge=3, le=100)
    unknown_sensitive_action: Literal['STEP_UP', 'REVIEW'] = 'STEP_UP'
    assessment_ttl: int = Field(120, ge=10, le=600)


class DecisionValidation(Strict):
    action_id: str
    action: str


class OverrideIn(Strict):
    expected_version: int = Field(ge=1)
    recommendation: Literal['ALLOW', 'STEP_UP', 'REVIEW', 'TEMPORARY_HOLD', 'BLOCK_RECOMMENDATION']
    reason: str = Field(min_length=10, max_length=2000)
    independent_verification_reference: str = Field(min_length=3, max_length=200)
