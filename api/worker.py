"""
api/worker.py

Kafka consumer that:
  1. Reads raw transactions from `transactions.raw`
  2. Scores each one via FraudScorer
  3. Persists the score to Postgres
  4. Creates fraud alerts for high/critical scores
  5. Publishes scored events to `transactions.scored`

Run alongside the API:
    python worker.py

Can also be run as a Celery task for horizontal scaling.
"""

import json
import logging
import os
import sys
import signal
import time
import uuid
from datetime import datetime

import psycopg2
import psycopg2.extras
import redis
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../ml-engine"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("worker")

# ── Config ────────────────────────────────────────────────────────────────────
KAFKA_SERVERS  = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_RAW      = os.getenv("KAFKA_TOPIC_TRANSACTIONS", "transactions.raw")
TOPIC_SCORED   = os.getenv("KAFKA_TOPIC_SCORED",       "transactions.scored")
TOPIC_ALERTS   = os.getenv("KAFKA_TOPIC_ALERTS",       "fraud.alerts")
MODEL_PATH     = os.getenv("MODEL_PATH", "../ml-engine/models/fraud_model.pkl")
ALERT_THRESHOLD = float(os.getenv("ALERT_SCORE_THRESHOLD", "0.55"))

PG = dict(
    host    = os.getenv("POSTGRES_HOST", "localhost"),
    port    = int(os.getenv("POSTGRES_PORT", "5432")),
    dbname  = os.getenv("POSTGRES_DB", "fraud_detection"),
    user    = os.getenv("POSTGRES_USER", "fraud_user"),
    password= os.getenv("POSTGRES_PASSWORD", "fraud_secret"),
)
REDIS = dict(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=int(os.getenv("REDIS_DB", "0")),
)

_running = True


def handle_signal(sig, frame):
    global _running
    log.info("Shutdown signal received — draining…")
    _running = False


signal.signal(signal.SIGINT,  handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ── Helpers ───────────────────────────────────────────────────────────────────

def connect_kafka_consumer(retries=12) -> KafkaConsumer:
    for attempt in range(1, retries + 1):
        try:
            consumer = KafkaConsumer(
                TOPIC_RAW,
                bootstrap_servers=KAFKA_SERVERS,
                group_id="fraud-scoring-worker",
                auto_offset_reset="latest",
                enable_auto_commit=False,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                max_poll_records=50,
                session_timeout_ms=30_000,
                heartbeat_interval_ms=10_000,
            )
            log.info("Kafka consumer connected ✅  topic=%s", TOPIC_RAW)
            return consumer
        except NoBrokersAvailable:
            log.warning("Kafka not ready (%d/%d) — retry in 5s", attempt, retries)
            time.sleep(5)
    raise RuntimeError("Cannot connect to Kafka")


def connect_kafka_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else b"",
        acks=1,
        linger_ms=20,
    )


def persist_transaction(pg_conn, tx: dict, result):
    """Upsert transaction + score into Postgres."""
    try:
        cur = pg_conn.cursor()
        cur.execute("""
            INSERT INTO transactions (
                id, external_tx_id, account_id,
                amount, currency, transaction_type, channel,
                ip_address, latitude, longitude, country_code,
                fraud_score, risk_tier, model_version, scored_at,
                status, initiated_at, created_at
            )
            SELECT
                %s, %s,
                a.id,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s,
                %s::timestamptz,
                NOW()
            FROM accounts a
            WHERE a.id::text = %s
            ON CONFLICT (external_tx_id) DO UPDATE SET
                fraud_score   = EXCLUDED.fraud_score,
                risk_tier     = EXCLUDED.risk_tier,
                model_version = EXCLUDED.model_version,
                scored_at     = EXCLUDED.scored_at,
                status        = CASE
                    WHEN EXCLUDED.risk_tier IN ('high','critical') THEN 'flagged'
                    ELSE transactions.status
                END
        """, (
            str(uuid.uuid4()),
            tx.get("external_tx_id") or tx.get("tx_id", str(uuid.uuid4())),
            float(tx.get("amount", 0)),
            tx.get("currency", "USD"),
            tx.get("transaction_type", "purchase"),
            tx.get("channel", "card"),
            tx.get("ip_address"),
            tx.get("latitude"),
            tx.get("longitude"),
            tx.get("country_code", "US"),
            result.fraud_score,
            result.risk_tier,
            result.model_version,
            datetime.utcnow(),
            "flagged" if result.risk_tier in ("high", "critical") else "pending",
            tx.get("initiated_at", datetime.utcnow().isoformat()),
            tx.get("account_id", ""),
        ))
        pg_conn.commit()
    except Exception as e:
        pg_conn.rollback()
        log.warning("DB persist failed (non-fatal): %s", e)


def maybe_create_alert(pg_conn, producer, tx: dict, result):
    """Create alert for high/critical transactions."""
    if result.fraud_score < ALERT_THRESHOLD:
        return

    alert_type = "critical_score" if result.fraud_score >= 0.80 else "high_score"
    severity   = "critical" if result.fraud_score >= 0.80 else "high"
    tx_ref     = tx.get("external_tx_id") or tx.get("tx_id", "unknown")
    message    = f"{alert_type.replace('_', ' ').title()}: fraud probability {result.fraud_score:.0%}"
    alert_id   = str(uuid.uuid4())
    now        = datetime.utcnow()

    try:
        cur = pg_conn.cursor()
        # Look up the real transaction UUID
        cur.execute("""
            SELECT id FROM transactions
            WHERE external_tx_id = %s OR id::text = %s
            LIMIT 1
        """, (tx_ref, tx_ref))
        row = cur.fetchone()
        if not row:
            return

        cur.execute("""
            INSERT INTO fraud_alerts
                (id, transaction_id, alert_type, severity, message,
                 rule_triggered, fraud_score, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s, %s)
            ON CONFLICT DO NOTHING
        """, (alert_id, row["id"], alert_type, severity, message,
              alert_type, result.fraud_score, now, now))
        pg_conn.commit()

        # Publish to alerts topic
        producer.send(TOPIC_ALERTS, key=tx_ref, value={
            "id":             alert_id,
            "transaction_id": str(row["id"]),
            "alert_type":     alert_type,
            "severity":       severity,
            "message":        message,
            "fraud_score":    result.fraud_score,
            "created_at":     now.isoformat(),
        })
        log.warning("🚨 ALERT [%s] tx=%s score=%.3f", severity.upper(), tx_ref, result.fraud_score)

    except Exception as e:
        pg_conn.rollback()
        log.error("Alert creation failed: %s", e)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    log.info("Starting scoring worker…")

    # Load model
    try:
        from inference import FraudScorer
        scorer = FraudScorer(model_path=MODEL_PATH)
    except FileNotFoundError:
        log.error("Model not found at %s — run `python train.py` in ml-engine/ first", MODEL_PATH)
        sys.exit(1)

    # Connect dependencies
    pg_conn = psycopg2.connect(**PG, cursor_factory=psycopg2.extras.RealDictCursor)
    r       = redis.Redis(**REDIS, decode_responses=True)
    r.ping()

    consumer = connect_kafka_consumer()
    producer = connect_kafka_producer()

    processed = 0
    fraud_count = 0
    t_start = time.monotonic()

    log.info("━" * 55)
    log.info("  Consuming from : %s", TOPIC_RAW)
    log.info("  Publishing to  : %s  |  %s", TOPIC_SCORED, TOPIC_ALERTS)
    log.info("  Alert threshold: %.2f", ALERT_THRESHOLD)
    log.info("━" * 55)

    while _running:
        try:
            batch = consumer.poll(timeout_ms=500, max_records=50)
        except Exception as e:
            log.error("Poll error: %s", e)
            time.sleep(2)
            continue

        for tp, messages in batch.items():
            for msg in messages:
                try:
                    tx = msg.value
                    result = scorer.score(tx, redis_client=r)

                    persist_transaction(pg_conn, tx, result)
                    maybe_create_alert(pg_conn, producer, tx, result)

                    # Publish scored event
                    producer.send(TOPIC_SCORED, key=tx.get("account_id", ""), value={
                        **tx,
                        "fraud_score":   result.fraud_score,
                        "risk_tier":     result.risk_tier,
                        "is_fraud_pred": result.is_fraud_pred,
                        "model_version": result.model_version,
                        "scored_at":     datetime.utcnow().isoformat(),
                    })

                    processed += 1
                    if result.is_fraud_pred:
                        fraud_count += 1

                except Exception as e:
                    log.error("Failed to process message: %s", e)
                    continue

            consumer.commit()

        # Heartbeat every 500 messages
        if processed > 0 and processed % 500 == 0:
            elapsed = time.monotonic() - t_start
            tps = processed / elapsed
            log.info("📊 Processed: %d | Fraud: %d (%.1f%%) | TPS: %.1f",
                     processed, fraud_count, fraud_count / processed * 100, tps)

    log.info("Shutting down worker… processed=%d fraud=%d", processed, fraud_count)
    consumer.close()
    producer.flush()
    producer.close()
    pg_conn.close()


if __name__ == "__main__":
    run()
