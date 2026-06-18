"""
api/routers/analytics.py

GET /api/v1/analytics/summary          — fraud KPIs for a time window
GET /api/v1/analytics/trend            — fraud rate over time (hourly/daily)
GET /api/v1/analytics/by-category      — fraud breakdown by merchant category
GET /api/v1/analytics/by-country       — fraud breakdown by country
GET /api/v1/analytics/transactions     — paginated transaction history
GET /api/v1/analytics/transactions/{id} — single transaction detail
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from dependencies import get_pg_connection
from middleware.auth import get_current_user
from schemas import (
    FraudSummary, FraudByCategory, FraudTrendPoint,
    TransactionResponse, TransactionListResponse,
)

log    = logging.getLogger("api.analytics")
router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


def _period_to_interval(period: str) -> str:
    return {
        "1h":  "1 hour",
        "24h": "24 hours",
        "7d":  "7 days",
        "30d": "30 days",
    }.get(period, "24 hours")


@router.get("/summary", response_model=FraudSummary, summary="Fraud KPI summary")
async def get_summary(
    period:  str  = Query("24h", description="1h|24h|7d|30d"),
    user:    dict = Depends(get_current_user),
    pg_conn        = Depends(get_pg_connection),
):
    interval = _period_to_interval(period)
    cur = pg_conn.cursor()
    cur.execute(f"""
        SELECT
            COUNT(*)                                           AS total_transactions,
            COUNT(*) FILTER (WHERE is_fraud = TRUE)           AS fraud_count,
            COALESCE(SUM(amount_usd), SUM(amount))            AS total_amount,
            COALESCE(SUM(amount_usd) FILTER (WHERE is_fraud), 0) AS fraud_amount,
            AVG(fraud_score) FILTER (WHERE fraud_score IS NOT NULL) AS avg_score
        FROM transactions
        WHERE initiated_at >= NOW() - INTERVAL '{interval}'
    """)
    row = cur.fetchone()

    cur.execute(f"""
        SELECT
            COUNT(*) FILTER (WHERE severity = 'critical' AND status = 'open') AS critical,
            COUNT(*) FILTER (WHERE status = 'open')                            AS open_total
        FROM fraud_alerts
        WHERE created_at >= NOW() - INTERVAL '{interval}'
    """)
    alert_row = cur.fetchone()

    total = int(row["total_transactions"] or 0)
    fraud = int(row["fraud_count"] or 0)

    return FraudSummary(
        period             = period,
        total_transactions = total,
        fraud_count        = fraud,
        fraud_rate         = round(fraud / total, 4) if total else 0.0,
        total_amount_usd   = round(float(row["total_amount"] or 0), 2),
        fraud_amount_usd   = round(float(row["fraud_amount"] or 0), 2),
        avg_fraud_score    = round(float(row["avg_score"]), 4) if row["avg_score"] else None,
        critical_alerts    = int(alert_row["critical"] or 0),
        open_alerts        = int(alert_row["open_total"] or 0),
    )


@router.get("/trend", summary="Fraud rate over time")
async def get_trend(
    period:      str = Query("24h", description="24h|7d|30d"),
    granularity: str = Query("hour", description="hour|day"),
    user:        dict = Depends(get_current_user),
    pg_conn           = Depends(get_pg_connection),
):
    interval = _period_to_interval(period)
    trunc    = "hour" if granularity == "hour" else "day"

    cur = pg_conn.cursor()
    cur.execute(f"""
        SELECT
            DATE_TRUNC('{trunc}', initiated_at)          AS bucket,
            COUNT(*)                                      AS tx_count,
            COUNT(*) FILTER (WHERE is_fraud = TRUE)      AS fraud_count
        FROM transactions
        WHERE initiated_at >= NOW() - INTERVAL '{interval}'
        GROUP BY bucket
        ORDER BY bucket
    """)
    rows = cur.fetchall()

    return {
        "period":      period,
        "granularity": granularity,
        "points": [
            {
                "timestamp":   row["bucket"].isoformat(),
                "tx_count":    int(row["tx_count"]),
                "fraud_count": int(row["fraud_count"]),
                "fraud_rate":  round(int(row["fraud_count"]) / max(int(row["tx_count"]), 1), 4),
            }
            for row in rows
        ],
    }


@router.get("/by-category", summary="Fraud breakdown by merchant category")
async def get_by_category(
    period:  str  = Query("7d"),
    user:    dict = Depends(get_current_user),
    pg_conn        = Depends(get_pg_connection),
):
    interval = _period_to_interval(period)
    cur = pg_conn.cursor()
    cur.execute(f"""
        SELECT
            m.category,
            COUNT(t.id)                                  AS tx_count,
            COUNT(t.id) FILTER (WHERE t.is_fraud = TRUE) AS fraud_count
        FROM transactions t
        LEFT JOIN merchants m ON t.merchant_id = m.id
        WHERE t.initiated_at >= NOW() - INTERVAL '{interval}'
        GROUP BY m.category
        HAVING COUNT(t.id) > 5
        ORDER BY fraud_count DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    return [
        FraudByCategory(
            category   = row["category"] or "unknown",
            tx_count   = int(row["tx_count"]),
            fraud_count= int(row["fraud_count"]),
            fraud_rate = round(int(row["fraud_count"]) / max(int(row["tx_count"]), 1), 4),
        )
        for row in rows
    ]


@router.get("/by-country", summary="Fraud breakdown by country")
async def get_by_country(
    period:  str  = Query("7d"),
    user:    dict = Depends(get_current_user),
    pg_conn        = Depends(get_pg_connection),
):
    interval = _period_to_interval(period)
    cur = pg_conn.cursor()
    cur.execute(f"""
        SELECT
            country_code,
            COUNT(*)                                     AS tx_count,
            COUNT(*) FILTER (WHERE is_fraud = TRUE)      AS fraud_count,
            AVG(fraud_score)                             AS avg_score
        FROM transactions
        WHERE initiated_at >= NOW() - INTERVAL '{interval}'
          AND country_code IS NOT NULL
        GROUP BY country_code
        HAVING COUNT(*) > 3
        ORDER BY fraud_count DESC
        LIMIT 30
    """)
    rows = cur.fetchall()
    return [
        {
            "country_code": row["country_code"],
            "tx_count":     int(row["tx_count"]),
            "fraud_count":  int(row["fraud_count"]),
            "fraud_rate":   round(int(row["fraud_count"]) / max(int(row["tx_count"]), 1), 4),
            "avg_score":    round(float(row["avg_score"]), 4) if row["avg_score"] else None,
        }
        for row in rows
    ]


@router.get("/transactions", response_model=TransactionListResponse,
            summary="Paginated transaction history")
async def list_transactions(
    page:         int            = Query(1, ge=1),
    size:         int            = Query(20, ge=1, le=100),
    is_fraud:     Optional[bool] = Query(None),
    risk_tier:    Optional[str]  = Query(None, description="low|medium|high|critical"),
    min_score:    Optional[float]= Query(None, ge=0, le=1),
    account_id:   Optional[str]  = Query(None),
    user:         dict           = Depends(get_current_user),
    pg_conn                       = Depends(get_pg_connection),
):
    offset  = (page - 1) * size
    filters, params = [], []

    if is_fraud is not None:
        filters.append("is_fraud = %s");        params.append(is_fraud)
    if risk_tier:
        filters.append("risk_tier = %s");       params.append(risk_tier)
    if min_score is not None:
        filters.append("fraud_score >= %s");    params.append(min_score)
    if account_id:
        filters.append("account_id::text = %s");params.append(account_id)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    cur = pg_conn.cursor()
    cur.execute(f"SELECT COUNT(*) AS n FROM transactions {where}", params)
    total = cur.fetchone()["n"]

    cur.execute(f"""
        SELECT id, external_tx_id, account_id::text, amount,
               currency, transaction_type, channel, country_code,
               fraud_score, risk_tier, is_fraud, status, initiated_at
        FROM transactions {where}
        ORDER BY initiated_at DESC
        LIMIT %s OFFSET %s
    """, [*params, size, offset])

    rows = cur.fetchall()
    txns = [
        TransactionResponse(
            id               = str(r["id"]),
            external_tx_id   = r["external_tx_id"],
            account_id       = str(r["account_id"]),
            amount           = float(r["amount"]),
            currency         = r["currency"],
            transaction_type = r["transaction_type"],
            channel          = r["channel"],
            country_code     = r["country_code"],
            fraud_score      = float(r["fraud_score"]) if r["fraud_score"] else None,
            risk_tier        = r["risk_tier"],
            is_fraud         = r["is_fraud"],
            status           = r["status"],
            initiated_at     = r["initiated_at"],
        )
        for r in rows
    ]
    return TransactionListResponse(transactions=txns, total=total, page=page, size=size)


@router.get("/transactions/{tx_id}", response_model=TransactionResponse,
            summary="Single transaction detail")
async def get_transaction(
    tx_id:   str,
    user:    dict = Depends(get_current_user),
    pg_conn        = Depends(get_pg_connection),
):
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT id, external_tx_id, account_id::text, amount,
               currency, transaction_type, channel, country_code,
               fraud_score, risk_tier, is_fraud, status, initiated_at
        FROM transactions
        WHERE id::text = %s OR external_tx_id = %s
    """, (tx_id, tx_id))
    row = cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Transaction not found")

    return TransactionResponse(
        id               = str(row["id"]),
        external_tx_id   = row["external_tx_id"],
        account_id       = str(row["account_id"]),
        amount           = float(row["amount"]),
        currency         = row["currency"],
        transaction_type = row["transaction_type"],
        channel          = row["channel"],
        country_code     = row["country_code"],
        fraud_score      = float(row["fraud_score"]) if row["fraud_score"] else None,
        risk_tier        = row["risk_tier"],
        is_fraud         = row["is_fraud"],
        status           = row["status"],
        initiated_at     = row["initiated_at"],
    )
