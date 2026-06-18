"""
api/dependencies.py
FastAPI dependency-injection providers for all shared resources.
Each resource is created once at startup and reused across requests.
"""

import sys
import os
import logging
from functools import lru_cache
from typing import Generator

import psycopg2
import psycopg2.extras
import redis

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../ml-engine"))

from config import get_settings

log = logging.getLogger("api.deps")


# ── PostgreSQL ────────────────────────────────────────────────────────────────

_pg_pool = None

def get_pg_connection():
    """
    Yield a Postgres connection from the module-level pool.
    Commits on success, rolls back on exception, always returns connection.
    """
    settings = get_settings()
    conn = psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=5,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Redis ─────────────────────────────────────────────────────────────────────

_redis_client: redis.Redis | None = None

def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _redis_client


# ── ML Scorer ─────────────────────────────────────────────────────────────────

_scorer = None

def get_scorer():
    """
    Lazy-load the FraudScorer singleton.
    Falls back gracefully if model file is missing (returns None).
    """
    global _scorer
    if _scorer is None:
        try:
            from inference import FraudScorer
            settings = get_settings()
            _scorer = FraudScorer(model_path=settings.model_path)
            log.info("FraudScorer loaded ✅")
        except FileNotFoundError as e:
            log.warning("Model not found — scoring will be unavailable: %s", e)
        except Exception as e:
            log.error("Failed to load FraudScorer: %s", e)
    return _scorer


# ── Kafka producer ────────────────────────────────────────────────────────────

_kafka_producer = None

def get_kafka_producer():
    global _kafka_producer
    if _kafka_producer is None:
        try:
            from kafka import KafkaProducer
            settings = get_settings()
            _kafka_producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                value_serializer=lambda v: v.encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8"),
                acks=1,
                linger_ms=10,
            )
            log.info("Kafka producer connected ✅")
        except Exception as e:
            log.warning("Kafka unavailable — alerts will not be published: %s", e)
    return _kafka_producer
