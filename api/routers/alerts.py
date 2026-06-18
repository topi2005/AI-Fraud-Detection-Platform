"""
api/routers/alerts.py

GET  /api/v1/alerts              — list alerts (filterable by status/severity)
GET  /api/v1/alerts/{id}         — single alert detail
PATCH /api/v1/alerts/{id}        — update status (resolve / mark false positive)
GET  /api/v1/alerts/stats        — alert counts by severity + status
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies import get_pg_connection
from middleware.auth import get_current_user, require_admin
from schemas import AlertResponse, AlertUpdateRequest, AlertListResponse

log    = logging.getLogger("api.alerts")
router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])


def _row_to_alert(row: dict) -> AlertResponse:
    return AlertResponse(
        id             = str(row["id"]),
        transaction_id = str(row["transaction_id"]),
        alert_type     = row["alert_type"],
        severity       = row["severity"],
        message        = row["message"],
        fraud_score    = float(row["fraud_score"]) if row["fraud_score"] else None,
        status         = row["status"],
        created_at     = row["created_at"],
    )


@router.get("", response_model=AlertListResponse, summary="List fraud alerts")
async def list_alerts(
    status_filter: Optional[str] = Query(None, alias="status",
                                         description="open|investigating|resolved|false_positive"),
    severity:      Optional[str] = Query(None, description="low|medium|high|critical"),
    page:          int           = Query(1, ge=1),
    size:          int           = Query(20, ge=1, le=100),
    user:          dict          = Depends(get_current_user),
    pg_conn                      = Depends(get_pg_connection),
):
    offset = (page - 1) * size
    filters, params = [], []

    if status_filter:
        filters.append("status = %s");  params.append(status_filter)
    if severity:
        filters.append("severity = %s"); params.append(severity)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    cur = pg_conn.cursor()
    cur.execute(f"SELECT COUNT(*) AS n FROM fraud_alerts {where}", params)
    total = cur.fetchone()["n"]

    cur.execute(f"""
        SELECT id, transaction_id, alert_type, severity, message,
               fraud_score, status, created_at
        FROM fraud_alerts {where}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, [*params, size, offset])

    rows = cur.fetchall()
    return AlertListResponse(
        alerts=[_row_to_alert(r) for r in rows],
        total=total, page=page, size=size,
    )


@router.get("/stats", summary="Alert counts by severity and status")
async def alert_stats(
    user:    dict = Depends(get_current_user),
    pg_conn       = Depends(get_pg_connection),
):
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT
            severity,
            status,
            COUNT(*) AS count
        FROM fraud_alerts
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY severity, status
        ORDER BY severity, status
    """)
    rows = cur.fetchall()

    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'open')         AS open_count,
            COUNT(*) FILTER (WHERE severity = 'critical')   AS critical_count,
            COUNT(*) FILTER (WHERE severity = 'high')       AS high_count,
            COUNT(*) FILTER (WHERE status = 'false_positive') AS false_positives,
            AVG(fraud_score)                                AS avg_score
        FROM fraud_alerts
        WHERE created_at >= NOW() - INTERVAL '24 hours'
    """)
    summary = cur.fetchone()

    return {
        "breakdown":     [dict(r) for r in rows],
        "last_24h": {
            "open_alerts":    summary["open_count"],
            "critical_alerts":summary["critical_count"],
            "high_alerts":    summary["high_count"],
            "false_positives":summary["false_positives"],
            "avg_fraud_score":round(float(summary["avg_score"]), 4) if summary["avg_score"] else None,
        },
    }


@router.get("/{alert_id}", response_model=AlertResponse, summary="Get a single alert")
async def get_alert(
    alert_id: str,
    user:     dict = Depends(get_current_user),
    pg_conn        = Depends(get_pg_connection),
):
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT id, transaction_id, alert_type, severity, message,
               fraud_score, status, created_at
        FROM fraud_alerts WHERE id = %s
    """, (alert_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _row_to_alert(row)


@router.patch("/{alert_id}", response_model=AlertResponse, summary="Update alert status")
async def update_alert(
    alert_id: str,
    body:     AlertUpdateRequest,
    user:     dict = Depends(get_current_user),
    pg_conn        = Depends(get_pg_connection),
):
    cur = pg_conn.cursor()
    cur.execute("""
        UPDATE fraud_alerts
        SET status           = %s,
            resolved_by      = %s,
            resolution_notes = %s,
            resolved_at      = CASE WHEN %s IN ('resolved','false_positive') THEN NOW() ELSE resolved_at END,
            updated_at       = NOW()
        WHERE id = %s
        RETURNING id, transaction_id, alert_type, severity, message,
                  fraud_score, status, created_at
    """, (body.status, body.resolved_by or user["username"],
          body.resolution_notes, body.status, alert_id))

    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    log.info("Alert %s → %s by %s", alert_id, body.status, user["username"])
    return _row_to_alert(row)
