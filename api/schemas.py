"""
api/schemas.py
Pydantic v2 models for all request bodies and response shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ══════════════════════════════════════════════════════════════════════════════
# Scoring
# ══════════════════════════════════════════════════════════════════════════════

class TransactionScoreRequest(BaseModel):
    """Single transaction submitted for real-time fraud scoring."""

    # Identifiers
    tx_id:       str  = Field(..., description="Unique transaction ID from the bank")
    account_id:  str  = Field(..., description="Internal account UUID")
    merchant_id: Optional[str] = None

    # Monetary
    amount:   float = Field(..., gt=0, description="Transaction amount in base currency")
    currency: str   = Field("USD", min_length=3, max_length=3)

    # Classification
    transaction_type: str = Field(
        ...,
        description="purchase|online_purchase|atm_withdrawal|transfer|international|refund"
    )
    channel: str = Field(
        ...,
        description="card|online|mobile|atm|wire"
    )

    # Location
    ip_address:   Optional[str]   = None
    latitude:     Optional[float] = Field(None, ge=-90,  le=90)
    longitude:    Optional[float] = Field(None, ge=-180, le=180)
    country_code: str             = Field("US", min_length=2, max_length=2)
    city:         Optional[str]   = None

    # Merchant context
    merchant_category: Optional[str] = None

    # Timestamp
    initiated_at: Optional[datetime] = None

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v):
        allowed = {"card", "online", "mobile", "atm", "wire"}
        if v not in allowed:
            raise ValueError(f"channel must be one of {allowed}")
        return v

    @field_validator("transaction_type")
    @classmethod
    def validate_tx_type(cls, v):
        allowed = {"purchase", "online_purchase", "atm_withdrawal", "transfer", "international", "refund"}
        if v not in allowed:
            raise ValueError(f"transaction_type must be one of {allowed}")
        return v


class TransactionScoreResponse(BaseModel):
    """Fraud scoring result returned to the caller."""
    tx_id:         str
    account_id:    str
    fraud_score:   float  = Field(..., ge=0, le=1, description="ML fraud probability 0–1")
    risk_tier:     str    = Field(..., description="low|medium|high|critical")
    is_fraud_pred: bool
    threshold:     float
    model_version: str
    latency_ms:    float
    alert_created: bool   = False
    scored_at:     datetime = Field(default_factory=datetime.utcnow)


class BatchScoreRequest(BaseModel):
    transactions: List[TransactionScoreRequest] = Field(..., min_length=1, max_length=500)


class BatchScoreResponse(BaseModel):
    results:      List[TransactionScoreResponse]
    total:        int
    fraud_count:  int
    latency_ms:   float


# ══════════════════════════════════════════════════════════════════════════════
# Alerts
# ══════════════════════════════════════════════════════════════════════════════

class AlertResponse(BaseModel):
    id:             str
    transaction_id: str
    alert_type:     str
    severity:       str
    message:        str
    fraud_score:    Optional[float]
    status:         str
    created_at:     datetime


class AlertUpdateRequest(BaseModel):
    status:           str = Field(..., description="investigating|resolved|false_positive")
    resolved_by:      Optional[str] = None
    resolution_notes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        allowed = {"investigating", "resolved", "false_positive"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class AlertListResponse(BaseModel):
    alerts: List[AlertResponse]
    total:  int
    page:   int
    size:   int


# ══════════════════════════════════════════════════════════════════════════════
# Transactions
# ══════════════════════════════════════════════════════════════════════════════

class TransactionResponse(BaseModel):
    id:               str
    external_tx_id:   str
    account_id:       str
    amount:           float
    currency:         str
    transaction_type: str
    channel:          str
    country_code:     Optional[str]
    fraud_score:      Optional[float]
    risk_tier:        Optional[str]
    is_fraud:         Optional[bool]
    status:           str
    initiated_at:     datetime


class TransactionListResponse(BaseModel):
    transactions: List[TransactionResponse]
    total:        int
    page:         int
    size:         int


# ══════════════════════════════════════════════════════════════════════════════
# Analytics / Dashboard
# ══════════════════════════════════════════════════════════════════════════════

class FraudSummary(BaseModel):
    period:              str    # e.g. "last_24h", "last_7d"
    total_transactions:  int
    fraud_count:         int
    fraud_rate:          float
    total_amount_usd:    float
    fraud_amount_usd:    float
    avg_fraud_score:     Optional[float]
    critical_alerts:     int
    open_alerts:         int


class FraudByCategory(BaseModel):
    category:    str
    tx_count:    int
    fraud_count: int
    fraud_rate:  float


class FraudTrendPoint(BaseModel):
    timestamp:   datetime
    tx_count:    int
    fraud_count: int
    fraud_rate:  float


class ModelHealthResponse(BaseModel):
    model_version:  str
    threshold:      float
    roc_auc:        Optional[float]
    avg_precision:  Optional[float]
    f1:             Optional[float]
    precision:      Optional[float]
    recall:         Optional[float]
    model_loaded:   bool
    last_checked:   datetime = Field(default_factory=datetime.utcnow)


# ══════════════════════════════════════════════════════════════════════════════
# Auth
# ══════════════════════════════════════════════════════════════════════════════

class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int


# ══════════════════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    status:    str
    version:   str
    services:  dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)
