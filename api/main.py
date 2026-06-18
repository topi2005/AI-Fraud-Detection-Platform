"""
api/main.py

FastAPI application entry point.

Startup order:
  1. Validate settings
  2. Warm up Redis connection
  3. Load FraudScorer (lazy — won't crash if model missing)
  4. Register all routers
  5. Mount Prometheus metrics at /metrics

Run (dev):
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Run (prod):
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
"""

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from dependencies import get_redis, get_scorer, get_kafka_producer
from routers import scoring, alerts, analytics, auth
from schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("api")

settings = get_settings()


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("━" * 55)
    log.info("  %s v%s  [%s]", settings.app_name, settings.app_version, settings.environment)
    log.info("━" * 55)

    # Warm up Redis
    try:
        r = get_redis()
        r.ping()
        log.info("Redis         ✅  %s:%s", settings.redis_host, settings.redis_port)
    except Exception as e:
        log.warning("Redis         ⚠️  unavailable: %s", e)

    # Warm up ML scorer
    scorer = get_scorer()
    if scorer:
        log.info("FraudScorer   ✅  version=%s", scorer.meta.get("model_version", "?"))
    else:
        log.warning("FraudScorer   ⚠️  model not loaded — run train.py first")

    # Warm up Kafka producer
    kafka = get_kafka_producer()
    if kafka:
        log.info("Kafka         ✅  %s", settings.kafka_bootstrap_servers)
    else:
        log.warning("Kafka         ⚠️  producer unavailable")

    log.info("API ready → http://0.0.0.0:8000")
    log.info("Docs      → http://0.0.0.0:8000/docs")

    yield  # ← app is running

    log.info("Shutting down…")
    if kafka:
        kafka.flush()
        kafka.close()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = settings.app_name,
    version     = settings.app_version,
    description = """
## Fraud Detection API

Real-time transaction risk scoring powered by a Random Forest + XGBoost ensemble.

### Key endpoints
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/score` | Score a single transaction |
| `POST` | `/api/v1/score/batch` | Score up to 500 transactions |
| `GET`  | `/api/v1/alerts` | List fraud alerts |
| `GET`  | `/api/v1/analytics/summary` | KPI dashboard data |
| `GET`  | `/api/v1/model/health` | Model version & metrics |

### Auth
All endpoints require a JWT Bearer token.  
Get one at `POST /api/v1/auth/token` with `admin / admin123`.
    """,
    lifespan    = lifespan,
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)


# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:3000", "http://localhost:5173"],  # React dev servers
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ── Request timing middleware ─────────────────────────────────────────────────

@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - t0) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed:.2f}"
    return response


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled exception on %s %s: %s", request.method, request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "path": str(request.url)},
    )


# ── Prometheus metrics ────────────────────────────────────────────────────────

try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    log.info("Prometheus metrics → /metrics")
except ImportError:
    log.info("prometheus_fastapi_instrumentator not installed — /metrics disabled")


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(scoring.router)
app.include_router(alerts.router)
app.include_router(analytics.router)


# ── Health & root ─────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    services = {"api": "ok"}

    try:
        r = get_redis()
        r.ping()
        services["redis"] = "ok"
    except Exception:
        services["redis"] = "unavailable"

    try:
        import psycopg2
        conn = psycopg2.connect(host=settings.postgres_host, port=settings.postgres_port,
                                dbname=settings.postgres_db, user=settings.postgres_user,
                                password=settings.postgres_password, connect_timeout=2)
        conn.close()
        services["postgres"] = "ok"
    except Exception:
        services["postgres"] = "unavailable"

    scorer = get_scorer()
    services["ml_model"] = "loaded" if scorer else "not_loaded"

    overall = "healthy" if all(v in ("ok", "loaded") for v in services.values()) else "degraded"

    return HealthResponse(
        status    = overall,
        version   = settings.app_version,
        services  = services,
        timestamp = datetime.utcnow(),
    )


@app.get("/", include_in_schema=False)
async def root():
    return {
        "name":    settings.app_name,
        "version": settings.app_version,
        "docs":    "/docs",
        "health":  "/health",
    }
