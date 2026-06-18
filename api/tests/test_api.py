"""
api/tests/test_api.py

Integration tests for the fraud detection API.
Uses FastAPI's TestClient — no running server needed.

Run:
    pytest tests/ -v
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Patch heavy dependencies before importing the app
mock_scorer = MagicMock()
mock_scorer.score.return_value = MagicMock(
    tx_id="tx-001",
    account_id="acc-001",
    fraud_score=0.92,
    risk_tier="critical",
    is_fraud_pred=True,
    threshold=0.35,
    model_version="abc12345",
    latency_ms=4.2,
    features={"amount": 8500, "geo_distance_km": 9000},
)
mock_scorer.score_batch.return_value = [mock_scorer.score.return_value]
mock_scorer.meta = {"model_version": "abc12345", "roc_auc": 0.982, "avg_precision": 0.876,
                    "f1": 0.841, "precision": 0.891, "recall": 0.795}
mock_scorer.threshold = 0.35

mock_redis = MagicMock()
mock_redis.ping.return_value = True
mock_redis.get.return_value = None

mock_pg = MagicMock()
mock_pg_cursor = MagicMock()
mock_pg.cursor.return_value = mock_pg_cursor
mock_pg_cursor.fetchone.return_value = {
    "n": 0, "total_transactions": 10, "fraud_count": 1,
    "total_amount": 5000.0, "fraud_amount": 500.0, "avg_score": 0.45,
    "critical": 1, "open_total": 2,
}
mock_pg_cursor.fetchall.return_value = []

mock_kafka = MagicMock()


@pytest.fixture(scope="module")
def client():
    with (
        patch("dependencies.get_scorer", return_value=mock_scorer),
        patch("dependencies.get_redis",  return_value=mock_redis),
        patch("dependencies.get_pg_connection", return_value=iter([mock_pg])),
        patch("dependencies.get_kafka_producer", return_value=mock_kafka),
    ):
        from main import app
        with TestClient(app) as c:
            yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    resp = client.post("/api/v1/auth/token", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# Auth
# ══════════════════════════════════════════════════════════════════════════════

class TestAuth:
    def test_login_success(self, client):
        resp = client.post("/api/v1/auth/token",
                           data={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        resp = client.post("/api/v1/auth/token",
                           data={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    def test_login_unknown_user(self, client):
        resp = client.post("/api/v1/auth/token",
                           data={"username": "ghost", "password": "abc"})
        assert resp.status_code == 401

    def test_me_endpoint(self, client, auth_headers):
        resp = client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"

    def test_protected_without_token(self, client):
        resp = client.post("/api/v1/score", json={})
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Scoring
# ══════════════════════════════════════════════════════════════════════════════

VALID_TX = {
    "tx_id":            "tx-test-001",
    "account_id":       "acc-test-001",
    "amount":           8500.00,
    "currency":         "USD",
    "transaction_type": "transfer",
    "channel":          "wire",
    "country_code":     "RO",
    "ip_address":       "5.2.3.4",
    "latitude":         44.43,
    "longitude":        26.10,
}


class TestScoring:
    def test_score_single_returns_200(self, client, auth_headers):
        with patch("routers.scoring.create_alert", return_value={"id": "alert-1"}):
            resp = client.post("/api/v1/score", json=VALID_TX, headers=auth_headers)
        assert resp.status_code == 200

    def test_score_response_shape(self, client, auth_headers):
        with patch("routers.scoring.create_alert", return_value=None):
            resp = client.post("/api/v1/score", json=VALID_TX, headers=auth_headers)
        body = resp.json()
        assert "fraud_score" in body
        assert "risk_tier" in body
        assert "is_fraud_pred" in body
        assert "model_version" in body
        assert "latency_ms" in body

    def test_score_invalid_channel(self, client, auth_headers):
        bad_tx = {**VALID_TX, "channel": "carrier_pigeon"}
        resp = client.post("/api/v1/score", json=bad_tx, headers=auth_headers)
        assert resp.status_code == 422

    def test_score_invalid_amount(self, client, auth_headers):
        bad_tx = {**VALID_TX, "amount": -50}
        resp = client.post("/api/v1/score", json=bad_tx, headers=auth_headers)
        assert resp.status_code == 422

    def test_score_batch(self, client, auth_headers):
        payload = {"transactions": [VALID_TX, {**VALID_TX, "tx_id": "tx-002"}]}
        resp = client.post("/api/v1/score/batch", json=payload, headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body
        assert "total" in body
        assert "fraud_count" in body

    def test_score_batch_too_large(self, client, auth_headers):
        payload = {"transactions": [VALID_TX] * 501}
        resp = client.post("/api/v1/score/batch", json=payload, headers=auth_headers)
        assert resp.status_code == 422

    def test_model_health(self, client, auth_headers):
        resp = client.get("/api/v1/model/health", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["model_loaded"] is True
        assert "roc_auc" in body
        assert "threshold" in body


# ══════════════════════════════════════════════════════════════════════════════
# Alerts
# ══════════════════════════════════════════════════════════════════════════════

class TestAlerts:
    def test_list_alerts(self, client, auth_headers):
        resp = client.get("/api/v1/alerts", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "alerts" in body
        assert "total" in body

    def test_list_alerts_filter_status(self, client, auth_headers):
        resp = client.get("/api/v1/alerts?status=open", headers=auth_headers)
        assert resp.status_code == 200

    def test_list_alerts_pagination(self, client, auth_headers):
        resp = client.get("/api/v1/alerts?page=1&size=10", headers=auth_headers)
        assert resp.status_code == 200

    def test_alert_stats(self, client, auth_headers):
        resp = client.get("/api/v1/alerts/stats", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "breakdown" in body
        assert "last_24h" in body

    def test_get_nonexistent_alert(self, client, auth_headers):
        mock_pg_cursor.fetchone.return_value = None
        resp = client.get("/api/v1/alerts/does-not-exist", headers=auth_headers)
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# Analytics
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalytics:
    def test_summary_default(self, client, auth_headers):
        mock_pg_cursor.fetchone.return_value = {
            "total_transactions": 1000, "fraud_count": 25,
            "total_amount": 500_000.0, "fraud_amount": 12_500.0,
            "avg_score": 0.42, "critical": 5, "open_total": 12,
        }
        resp = client.get("/api/v1/analytics/summary", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "total_transactions" in body
        assert "fraud_rate" in body

    def test_summary_periods(self, client, auth_headers):
        for period in ["1h", "24h", "7d", "30d"]:
            resp = client.get(f"/api/v1/analytics/summary?period={period}", headers=auth_headers)
            assert resp.status_code == 200

    def test_trend(self, client, auth_headers):
        mock_pg_cursor.fetchall.return_value = []
        resp = client.get("/api/v1/analytics/trend", headers=auth_headers)
        assert resp.status_code == 200
        assert "points" in resp.json()

    def test_by_category(self, client, auth_headers):
        resp = client.get("/api/v1/analytics/by-category", headers=auth_headers)
        assert resp.status_code == 200

    def test_by_country(self, client, auth_headers):
        resp = client.get("/api/v1/analytics/by-country", headers=auth_headers)
        assert resp.status_code == 200

    def test_transactions_list(self, client, auth_headers):
        mock_pg_cursor.fetchone.return_value = {"n": 0}
        mock_pg_cursor.fetchall.return_value = []
        resp = client.get("/api/v1/analytics/transactions", headers=auth_headers)
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# System
# ══════════════════════════════════════════════════════════════════════════════

class TestSystem:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "services" in body

    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "docs" in resp.json()

    def test_timing_header(self, client):
        resp = client.get("/health")
        assert "X-Process-Time-Ms" in resp.headers

    def test_docs_available(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200
