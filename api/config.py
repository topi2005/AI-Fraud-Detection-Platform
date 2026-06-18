"""
api/config.py
All settings loaded from environment variables / .env file.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_name:    str  = "Fraud Detection API"
    app_version: str  = "1.0.0"
    debug:       bool = False
    environment: str = "development"  # or "production"
    log_level:   str  = "INFO"

    # ── Auth (JWT) ────────────────────────────────────────────────────────────
    secret_key:          str = "CHANGE_ME_IN_PRODUCTION_32chars!!"
    algorithm:           str = "HS256"
    access_token_expire_minutes: int = 60

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    postgres_host:     str = "localhost"
    postgres_port:     int = 5432
    postgres_db:       str = "fraud_detection"
    postgres_user:     str = "fraud_user"
    postgres_password: str = "fraud_secret"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db:   int = 0

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ── Kafka ─────────────────────────────────────────────────────────────────
    kafka_bootstrap_servers:  str = "localhost:9092"
    kafka_topic_transactions: str = "transactions.raw"
    kafka_topic_alerts:       str = "fraud.alerts"
    kafka_topic_scored:       str = "transactions.scored"

    # ── ML model ──────────────────────────────────────────────────────────────
    model_path:     str   = "../ml-engine/models/fraud_model.pkl"
    score_threshold: float = 0.35

    # ── Celery ────────────────────────────────────────────────────────────────
    celery_broker_url:  str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── Rate limiting ─────────────────────────────────────────────────────────
    rate_limit_per_minute: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
