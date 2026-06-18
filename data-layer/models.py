"""
data-layer/models.py
Shared transaction schema (dataclass) used by simulator and Kafka consumer.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
import json
import uuid


@dataclass
class TransactionEvent:
    """
    Represents a single banking transaction flowing through Kafka.
    This is the canonical event schema for the transactions.raw topic.
    """
    # Identifiers
    tx_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    external_tx_id: str = field(default_factory=lambda: f"EXT-{uuid.uuid4().hex[:12].upper()}")
    account_id: str = ""
    customer_id: str = ""
    merchant_id: str = ""

    # Monetary
    amount: float = 0.0
    currency: str = "USD"
    amount_usd: float = 0.0

    # Classification
    transaction_type: str = "purchase"   # purchase|atm_withdrawal|transfer|online_purchase|international|refund
    channel: str = "card"                # card|online|atm|wire|mobile

    # Location
    ip_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    country_code: str = "US"
    city: str = ""

    # Ground truth (only set for labelled / simulated fraud)
    is_fraud: Optional[bool] = None
    fraud_type: Optional[str] = None     # card_not_present|identity_theft|account_takeover|synthetic_id

    # Timestamp
    initiated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: bytes | str) -> "TransactionEvent":
        data = json.loads(raw)
        return cls(**data)


@dataclass
class CustomerProfile:
    """Lightweight customer record cached in Redis for fast feature lookup."""
    customer_id: str
    account_id: str
    account_number: str
    country_code: str
    city: str
    risk_tier: str              # low | medium | high
    avg_monthly_spend: float
    home_lat: float
    home_lon: float
    last_tx_lat: Optional[float] = None
    last_tx_lon: Optional[float] = None
    last_tx_at: Optional[str] = None
    last_tx_amount: Optional[float] = None
    tx_count_today: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "CustomerProfile":
        return cls(**json.loads(raw))
