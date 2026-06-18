"""
data-layer/simulator/producer.py

Kafka transaction producer that simulates realistic banking activity,
including several fraud patterns found in real datasets:

  • card_not_present  — online txn far from home location
  • velocity_abuse    — many small txns in rapid succession
  • amount_spike      — single unusually large txn
  • geo_anomaly       — impossible travel (two distant txns minutes apart)
  • account_takeover  — sudden change in channel + country

Run:
    python simulator/producer.py

Env vars are loaded from ../.env via python-dotenv.
"""

import os
import sys
import time
import random
import uuid
import json
import logging
import math
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from faker import Faker
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
import psycopg2
import psycopg2.extras
import redis

# ── project models ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models import TransactionEvent, CustomerProfile

# ── config ────────────────────────────────────────────────────────────────────
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("simulator")

fake = Faker()
Faker.seed(42)
random.seed(42)

# ── constants ─────────────────────────────────────────────────────────────────
TPS              = int(os.getenv("SIMULATOR_TPS", "10"))
FRAUD_RATE       = float(os.getenv("SIMULATOR_FRAUD_RATE", "0.02"))
NUM_CUSTOMERS    = int(os.getenv("SIMULATOR_NUM_CUSTOMERS", "500"))
BURST_ENABLED    = os.getenv("SIMULATOR_BURST_ENABLED", "true").lower() == "true"

KAFKA_SERVERS    = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_TX         = os.getenv("KAFKA_TOPIC_TRANSACTIONS", "transactions.raw")

PG_HOST          = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT          = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB            = os.getenv("POSTGRES_DB", "fraud_detection")
PG_USER          = os.getenv("POSTGRES_USER", "fraud_user")
PG_PASS          = os.getenv("POSTGRES_PASSWORD", "fraud_secret")

REDIS_HOST       = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT       = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB         = int(os.getenv("REDIS_DB", "0"))

# Merchant pool (must match seeded merchants in migration 001)
MERCHANT_POOL = [
    {"id": "MCH001", "name": "Amazon",            "category": "online_retail",    "country": "US", "lat": 47.61, "lon": -122.33, "high_risk": False},
    {"id": "MCH002", "name": "Walmart",            "category": "retail",           "country": "US", "lat": 36.36, "lon": -94.21, "high_risk": False},
    {"id": "MCH003", "name": "Shell Gas Station",  "category": "fuel",             "country": "US", "lat": 29.76, "lon": -95.37, "high_risk": False},
    {"id": "MCH004", "name": "Starbucks",          "category": "food_beverage",    "country": "US", "lat": 47.61, "lon": -122.33, "high_risk": False},
    {"id": "MCH005", "name": "Las Vegas Casino",   "category": "gambling",         "country": "US", "lat": 36.17, "lon": -115.14, "high_risk": True},
    {"id": "MCH006", "name": "Crypto Exchange XYZ","category": "cryptocurrency",   "country": "MT", "lat": 35.90, "lon": 14.51,  "high_risk": True},
    {"id": "MCH007", "name": "Netflix",            "category": "digital_services", "country": "US", "lat": 37.34, "lon": -121.96, "high_risk": False},
    {"id": "MCH008", "name": "ATM - Chase Bank",   "category": "atm",              "country": "US", "lat": 40.71, "lon": -74.01, "high_risk": False},
    {"id": "MCH009", "name": "AliExpress",         "category": "online_retail",    "country": "CN", "lat": 30.27, "lon": 120.15, "high_risk": False},
    {"id": "MCH010", "name": "Western Union",      "category": "money_transfer",   "country": "US", "lat": 39.74, "lon": -104.98, "high_risk": True},
]

FRAUD_TYPES = ["card_not_present", "identity_theft", "account_takeover", "synthetic_id", "velocity_abuse"]


# ══════════════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════════════

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two GPS coords in kilometres."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def random_ip(country: str = "US") -> str:
    """Return a plausible IPv4 (not truly geo-accurate, just realistic-looking)."""
    return fake.ipv4_public()


def jitter(lat: float, lon: float, max_km: float = 50) -> tuple[float, float]:
    """Slightly shift a GPS coordinate by up to max_km."""
    delta = max_km / 111  # rough degrees per km
    return (
        round(lat + random.uniform(-delta, delta), 6),
        round(lon + random.uniform(-delta, delta), 6),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Customer pool (created in memory and persisted to Postgres + Redis)
# ══════════════════════════════════════════════════════════════════════════════

def generate_customer_pool(n: int) -> list[CustomerProfile]:
    """Build a synthetic pool of n customers with home locations."""
    cities = [
        ("New York",      40.71, -74.01, "US"),
        ("Los Angeles",   34.05, -118.24, "US"),
        ("Chicago",       41.88, -87.63, "US"),
        ("Houston",       29.76, -95.37, "US"),
        ("Phoenix",       33.45, -112.07, "US"),
        ("Philadelphia",  39.95, -75.17, "US"),
        ("San Antonio",   29.42, -98.49, "US"),
        ("London",        51.51, -0.13,  "GB"),
        ("Toronto",       43.65, -79.38, "CA"),
        ("Sydney",       -33.87, 151.21, "AU"),
    ]
    pool = []
    for i in range(n):
        city_name, lat, lon, country = random.choice(cities)
        hlat, hlon = jitter(lat, lon, 30)
        profile = CustomerProfile(
            customer_id=str(uuid.uuid4()),
            account_id=str(uuid.uuid4()),
            account_number=f"ACC{i:08d}",
            country_code=country,
            city=city_name,
            risk_tier=random.choices(["low", "medium", "high"], weights=[0.75, 0.20, 0.05])[0],
            avg_monthly_spend=round(random.uniform(500, 8000), 2),
            home_lat=hlat,
            home_lon=hlon,
        )
        pool.append(profile)
    log.info("Generated %d synthetic customers", n)
    return pool


def seed_postgres(pool: list[CustomerProfile], pg_conn) -> dict[str, str]:
    """
    Upsert customers and accounts into Postgres.
    Returns mapping customer_id -> merchant_id (UUID from merchants table).
    """
    cur = pg_conn.cursor()

    # Fetch seeded merchant UUIDs
    cur.execute("SELECT merchant_code, id::text FROM merchants")
    merchant_map: dict[str, str] = {row["merchant_code"]: row["id"] for row in cur.fetchall()}

    for p in pool:
        # customers
        cur.execute("""
            INSERT INTO customers (id, external_id, full_name, email, country_code, city, risk_tier)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (external_id) DO NOTHING
        """, (p.customer_id, p.account_number, fake.name(), fake.unique.email(),
              p.country_code, p.city, p.risk_tier))

        # accounts
        cur.execute("""
            INSERT INTO accounts (id, customer_id, account_number, account_type, currency, balance)
            VALUES (%s, %s, %s, 'checking', 'USD', %s)
            ON CONFLICT (account_number) DO NOTHING
        """, (p.account_id, p.customer_id, p.account_number,
              round(random.uniform(100, 50000), 2)))

    pg_conn.commit()
    cur.close()
    log.info("Seeded %d customers/accounts into Postgres", len(pool))
    return merchant_map


def cache_profiles(pool: list[CustomerProfile], r: redis.Redis):
    """Store all customer profiles in Redis for fast feature lookup."""
    pipe = r.pipeline()
    for p in pool:
        pipe.set(f"customer:{p.account_id}", p.to_json(), ex=86400)
    pipe.execute()
    log.info("Cached %d profiles in Redis", len(pool))


# ══════════════════════════════════════════════════════════════════════════════
# Transaction generators
# ══════════════════════════════════════════════════════════════════════════════

def make_normal_tx(profile: CustomerProfile, merchant_map: dict[str, str]) -> TransactionEvent:
    """Generate a plausible legitimate transaction."""
    merchant = random.choice([m for m in MERCHANT_POOL if not m["high_risk"]])
    merchant_db_id = merchant_map.get(merchant["id"], merchant["id"])

    # Stay near home
    lat, lon = jitter(profile.home_lat, profile.home_lon, 20)
    amount = round(random.lognormvariate(
        math.log(max(profile.avg_monthly_spend / 30, 10)), 0.6
    ), 2)

    channel = random.choices(
        ["card", "online", "mobile", "atm"],
        weights=[0.50, 0.30, 0.15, 0.05]
    )[0]

    tx_type_map = {
        "card":   random.choice(["purchase", "purchase", "atm_withdrawal"]),
        "online": "online_purchase",
        "mobile": "purchase",
        "atm":    "atm_withdrawal",
    }

    return TransactionEvent(
        account_id=profile.account_id,
        customer_id=profile.customer_id,
        merchant_id=merchant_db_id,
        amount=amount,
        amount_usd=amount,
        transaction_type=tx_type_map[channel],
        channel=channel,
        ip_address=random_ip(profile.country_code),
        latitude=lat,
        longitude=lon,
        country_code=profile.country_code,
        city=profile.city,
        is_fraud=False,
    )


def make_fraud_tx(
    profile: CustomerProfile,
    merchant_map: dict[str, str],
    fraud_type: Optional[str] = None,
) -> TransactionEvent:
    """Generate a fraudulent transaction based on one of several known patterns."""
    if fraud_type is None:
        fraud_type = random.choice(FRAUD_TYPES)

    base = make_normal_tx(profile, merchant_map)
    base.is_fraud = True
    base.fraud_type = fraud_type

    if fraud_type == "card_not_present":
        # Online purchase from a foreign IP / location
        foreign_country = random.choice(["RO", "NG", "RU", "UA", "CN", "BR"])
        base.channel = "online"
        base.transaction_type = "online_purchase"
        base.ip_address = random_ip(foreign_country)
        base.country_code = foreign_country
        base.latitude = round(random.uniform(-60, 70), 6)
        base.longitude = round(random.uniform(-170, 170), 6)
        base.amount = round(random.uniform(200, 2000), 2)
        # Use a high-risk merchant
        high_risk = random.choice([m for m in MERCHANT_POOL if m["high_risk"]])
        base.merchant_id = merchant_map.get(high_risk["id"], high_risk["id"])

    elif fraud_type == "velocity_abuse":
        # Small rapid transactions — this event is just one of many (simulator will burst)
        base.amount = round(random.uniform(1, 50), 2)
        base.amount_usd = base.amount
        base.channel = random.choice(["online", "card"])
        base.transaction_type = "purchase"

    elif fraud_type == "amount_spike":
        # Sudden large transaction far above normal spend
        spike_multiplier = random.uniform(10, 50)
        base.amount = round(profile.avg_monthly_spend * spike_multiplier / 30, 2)
        base.amount_usd = base.amount
        base.channel = random.choice(["wire", "online"])
        base.transaction_type = "transfer"

    elif fraud_type == "geo_anomaly":
        # Transaction from a location impossible to reach since last tx
        base.latitude = round(random.uniform(-60, 70), 6)
        base.longitude = round(random.uniform(-170, 170), 6)
        base.country_code = random.choice(["DE", "JP", "AU", "ZA", "BR"])
        base.channel = "card"
        base.transaction_type = "purchase"

    elif fraud_type == "account_takeover":
        # New device/IP, large transfer to external account
        base.ip_address = fake.ipv4_public()
        base.channel = "wire"
        base.transaction_type = "transfer"
        base.amount = round(random.uniform(1000, 15000), 2)
        base.amount_usd = base.amount
        base.country_code = random.choice(["CY", "MT", "PA", "VG"])

    elif fraud_type == "synthetic_id":
        # Looks mostly normal but uses a slightly different lat/lon each time
        lat, lon = jitter(profile.home_lat, profile.home_lon, 200)
        base.latitude = lat
        base.longitude = lon

    base.amount_usd = base.amount  # simplified; real system applies FX
    return base


# ══════════════════════════════════════════════════════════════════════════════
# Kafka helpers
# ══════════════════════════════════════════════════════════════════════════════

def build_producer() -> KafkaProducer:
    retries = 0
    while retries < 10:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_SERVERS,
                value_serializer=lambda v: v.encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8"),
                acks="all",
                retries=3,
                linger_ms=5,
                batch_size=16384,
            )
            log.info("Connected to Kafka at %s", KAFKA_SERVERS)
            return producer
        except NoBrokersAvailable:
            retries += 1
            log.warning("Kafka not ready, retrying in 5s… (%d/10)", retries)
            time.sleep(5)
    raise RuntimeError("Could not connect to Kafka after 10 attempts")


def send_tx(producer: KafkaProducer, tx: TransactionEvent):
    producer.send(
        TOPIC_TX,
        key=tx.account_id,      # partition by account for ordering
        value=tx.to_json(),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Main simulation loop
# ══════════════════════════════════════════════════════════════════════════════

def run():
    log.info("Starting fraud transaction simulator (TPS=%d, fraud_rate=%.1f%%)", TPS, FRAUD_RATE * 100)

    # ── Connect to dependencies ───────────────────────────────────────────────
    log.info("Connecting to PostgreSQL…")
    pg = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASS,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )

    log.info("Connecting to Redis…")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    r.ping()

    log.info("Connecting to Kafka…")
    producer = build_producer()

    # ── Seed data ─────────────────────────────────────────────────────────────
    pool = generate_customer_pool(NUM_CUSTOMERS)
    merchant_map = seed_postgres(pool, pg)
    cache_profiles(pool, r)

    # ── Simulation state ──────────────────────────────────────────────────────
    total_sent   = 0
    total_fraud  = 0
    burst_active = False
    burst_target : Optional[CustomerProfile] = None
    burst_remaining = 0

    log.info("━" * 60)
    log.info("🚀 Producing to topic: %s", TOPIC_TX)
    log.info("   Press Ctrl+C to stop")
    log.info("━" * 60)

    interval = 1.0 / TPS  # seconds between transactions

    try:
        while True:
            loop_start = time.monotonic()

            # ── Fraud burst: inject velocity_abuse pattern ────────────────────
            if BURST_ENABLED and not burst_active and random.random() < 0.001:
                burst_active    = True
                burst_target    = random.choice(pool)
                burst_remaining = random.randint(15, 40)
                log.warning("🔥 FRAUD BURST: account %s — %d rapid txns incoming",
                            burst_target.account_number, burst_remaining)

            if burst_active and burst_remaining > 0:
                tx = make_fraud_tx(burst_target, merchant_map, fraud_type="velocity_abuse")
                burst_remaining -= 1
                if burst_remaining == 0:
                    burst_active = False
                    log.info("   Burst ended")
            else:
                profile = random.choice(pool)
                if random.random() < FRAUD_RATE:
                    tx = make_fraud_tx(profile, merchant_map)
                    total_fraud += 1
                else:
                    tx = make_normal_tx(profile, merchant_map)

            send_tx(producer, tx)
            total_sent += 1

            # ── Console heartbeat every 100 txns ─────────────────────────────
            if total_sent % 100 == 0:
                fraud_pct = (total_fraud / total_sent) * 100
                log.info("📊 Sent: %6d | Fraud: %5d (%.2f%%) | Topic: %s",
                         total_sent, total_fraud, fraud_pct, TOPIC_TX)

            # ── Maintain target TPS ───────────────────────────────────────────
            elapsed = time.monotonic() - loop_start
            sleep_for = max(0, interval - elapsed)
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        log.info("Stopping simulator…")
    finally:
        producer.flush()
        producer.close()
        pg.close()
        log.info("✅ Done. Total sent: %d | Fraud: %d", total_sent, total_fraud)


if __name__ == "__main__":
    run()
