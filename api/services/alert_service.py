"""
api/services/alert_service.py
Creates fraud alerts in Postgres and publishes them to the Kafka alerts topic.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

log = logging.getLogger("api.alerts")

# Alert type thresholds
ALERT_RULES = [
    {"type": "critical_score",    "min_score": 0.80, "severity": "critical",
     "message": "Transaction fraud score exceeds critical threshold ({score:.0%})"},
    {"type": "high_score",        "min_score": 0.55, "severity": "high",
     "message": "High fraud probability detected ({score:.0%})"},
    {"type": "impossible_travel", "min_score": 0.30, "severity": "high",
     "message": "Impossible travel detected — transaction location inconsistent with recent activity"},
    {"type": "velocity_burst",    "min_score": 0.20, "severity": "medium",
     "message": "Unusual transaction velocity on account"},
    {"type": "high_risk_merchant","min_score": 0.25, "severity": "medium",
     "message": "Transaction at high-risk merchant category with elevated fraud score"},
]


def determine_alert_type(fraud_score: float, features: Optional[dict]) -> Optional[dict]:
    """Return the highest-priority matching alert rule, or None."""
    if features:
        if features.get("impossible_travel") and fraud_score >= 0.30:
            return next(r for r in ALERT_RULES if r["type"] == "impossible_travel")
        if features.get("tx_count_1h", 0) > 15 and fraud_score >= 0.20:
            return next(r for r in ALERT_RULES if r["type"] == "velocity_burst")
        if features.get("is_high_risk_merchant") and fraud_score >= 0.25:
            return next(r for r in ALERT_RULES if r["type"] == "high_risk_merchant")

    for rule in ALERT_RULES:
        if fraud_score >= rule["min_score"] and rule["type"] in ("critical_score", "high_score"):
            return rule

    return None


def create_alert(
    *,
    pg_conn,
    kafka_producer,
    kafka_topic: str,
    transaction_id: str,
    fraud_score: float,
    features: Optional[dict] = None,
) -> Optional[dict]:
    """
    Evaluates alert rules against the scoring result.
    If triggered: persists to Postgres + publishes to Kafka.
    Returns the created alert dict or None.
    """
    rule = determine_alert_type(fraud_score, features)
    if rule is None:
        return None

    alert_id = str(uuid.uuid4())
    message  = rule["message"].format(score=fraud_score)
    now      = datetime.utcnow()

    # ── Persist to Postgres ───────────────────────────────────────────────────
    try:
        cur = pg_conn.cursor()
        cur.execute("""
            INSERT INTO fraud_alerts
                (id, transaction_id, alert_type, severity, message,
                 rule_triggered, fraud_score, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s, %s)
        """, (
            alert_id, transaction_id, rule["type"], rule["severity"],
            message, rule["type"], fraud_score, now, now,
        ))
    except Exception as e:
        log.error("Failed to persist alert to Postgres: %s", e)
        return None

    alert = {
        "id":             alert_id,
        "transaction_id": transaction_id,
        "alert_type":     rule["type"],
        "severity":       rule["severity"],
        "message":        message,
        "fraud_score":    fraud_score,
        "status":         "open",
        "created_at":     now.isoformat(),
    }

    # ── Publish to Kafka ──────────────────────────────────────────────────────
    if kafka_producer:
        try:
            kafka_producer.send(
                kafka_topic,
                key=transaction_id,
                value=json.dumps(alert),
            )
        except Exception as e:
            log.warning("Kafka publish failed (alert still saved to DB): %s", e)

    log.info("Alert created: %s [%s] score=%.3f tx=%s",
             rule["type"], rule["severity"], fraud_score, transaction_id)
    return alert
