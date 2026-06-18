-- ============================================================
-- Fraud Detection Platform — Database Schema
-- Migration: 001_initial_schema.sql
-- Runs automatically on first postgres container start
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- fast text search on names/emails

-- ────────────────────────────────────────────────────────────
-- CUSTOMERS
-- ────────────────────────────────────────────────────────────
CREATE TABLE customers (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id         VARCHAR(64) UNIQUE NOT NULL,          -- bank's customer ref
    full_name           VARCHAR(255) NOT NULL,
    email               VARCHAR(255) UNIQUE NOT NULL,
    phone               VARCHAR(32),
    date_of_birth       DATE,
    country_code        CHAR(2) NOT NULL DEFAULT 'US',
    city                VARCHAR(128),
    risk_tier           VARCHAR(16) NOT NULL DEFAULT 'low'    -- low | medium | high
                            CHECK (risk_tier IN ('low','medium','high')),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_customers_external_id ON customers(external_id);
CREATE INDEX idx_customers_risk_tier   ON customers(risk_tier);

-- ────────────────────────────────────────────────────────────
-- ACCOUNTS
-- ────────────────────────────────────────────────────────────
CREATE TABLE accounts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id         UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    account_number      VARCHAR(32) UNIQUE NOT NULL,
    account_type        VARCHAR(16) NOT NULL DEFAULT 'checking'
                            CHECK (account_type IN ('checking','savings','credit','investment')),
    currency            CHAR(3) NOT NULL DEFAULT 'USD',
    balance             NUMERIC(18,2) NOT NULL DEFAULT 0.00,
    credit_limit        NUMERIC(18,2),
    is_frozen           BOOLEAN NOT NULL DEFAULT FALSE,
    opened_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_accounts_customer_id ON accounts(customer_id);

-- ────────────────────────────────────────────────────────────
-- MERCHANTS
-- ────────────────────────────────────────────────────────────
CREATE TABLE merchants (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    merchant_code       VARCHAR(32) UNIQUE NOT NULL,
    name                VARCHAR(255) NOT NULL,
    category            VARCHAR(64) NOT NULL,                  -- MCC category
    country_code        CHAR(2) NOT NULL,
    city                VARCHAR(128),
    is_high_risk        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_merchants_category    ON merchants(category);
CREATE INDEX idx_merchants_high_risk   ON merchants(is_high_risk);

-- ────────────────────────────────────────────────────────────
-- TRANSACTIONS  (core fact table)
-- ────────────────────────────────────────────────────────────
CREATE TABLE transactions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_tx_id          VARCHAR(64) UNIQUE NOT NULL,       -- bank's tx reference
    account_id              UUID NOT NULL REFERENCES accounts(id),
    merchant_id             UUID REFERENCES merchants(id),

    -- Monetary
    amount                  NUMERIC(18,2) NOT NULL,
    currency                CHAR(3) NOT NULL DEFAULT 'USD',
    amount_usd              NUMERIC(18,2),                     -- normalised for ML

    -- Classification
    transaction_type        VARCHAR(32) NOT NULL
                                CHECK (transaction_type IN (
                                    'purchase','atm_withdrawal','transfer',
                                    'online_purchase','international','refund'
                                )),
    channel                 VARCHAR(16) NOT NULL DEFAULT 'card'
                                CHECK (channel IN ('card','online','atm','wire','mobile')),

    -- Location
    ip_address              INET,
    latitude                NUMERIC(9,6),
    longitude               NUMERIC(9,6),
    country_code            CHAR(2),
    city                    VARCHAR(128),

    -- Fraud labels  (set by analysts / ground truth)
    is_fraud                BOOLEAN,                           -- NULL = unlabelled
    fraud_type              VARCHAR(64),                       -- card_not_present | identity_theft | …
    labelled_at             TIMESTAMPTZ,
    labelled_by             VARCHAR(128),

    -- ML scoring (populated by risk API — Phase 3)
    fraud_score             NUMERIC(5,4),                      -- 0.0000–1.0000
    risk_tier               VARCHAR(16)
                                CHECK (risk_tier IN ('low','medium','high','critical')),
    model_version           VARCHAR(32),
    scored_at               TIMESTAMPTZ,

    -- Status
    status                  VARCHAR(16) NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','approved','declined','flagged','reversed')),

    -- Timestamps
    initiated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes tuned for fraud query patterns
CREATE INDEX idx_tx_account_id        ON transactions(account_id);
CREATE INDEX idx_tx_merchant_id       ON transactions(merchant_id);
CREATE INDEX idx_tx_is_fraud          ON transactions(is_fraud);
CREATE INDEX idx_tx_risk_tier         ON transactions(risk_tier);
CREATE INDEX idx_tx_fraud_score       ON transactions(fraud_score DESC);
CREATE INDEX idx_tx_initiated_at      ON transactions(initiated_at DESC);
CREATE INDEX idx_tx_status            ON transactions(status);
CREATE INDEX idx_tx_country           ON transactions(country_code);
-- Partial index for fast flagged/fraud dashboards
CREATE INDEX idx_tx_flagged           ON transactions(initiated_at DESC)
    WHERE status = 'flagged' OR is_fraud = TRUE;

-- ────────────────────────────────────────────────────────────
-- FRAUD ALERTS
-- ────────────────────────────────────────────────────────────
CREATE TABLE fraud_alerts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transaction_id      UUID NOT NULL REFERENCES transactions(id),
    alert_type          VARCHAR(64) NOT NULL,                  -- velocity | geo_anomaly | amount_spike | …
    severity            VARCHAR(16) NOT NULL DEFAULT 'medium'
                            CHECK (severity IN ('low','medium','high','critical')),
    message             TEXT NOT NULL,
    rule_triggered      VARCHAR(128),
    fraud_score         NUMERIC(5,4),

    -- Resolution
    status              VARCHAR(16) NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open','investigating','resolved','false_positive')),
    resolved_by         VARCHAR(128),
    resolved_at         TIMESTAMPTZ,
    resolution_notes    TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alerts_transaction_id ON fraud_alerts(transaction_id);
CREATE INDEX idx_alerts_status         ON fraud_alerts(status);
CREATE INDEX idx_alerts_severity       ON fraud_alerts(severity);
CREATE INDEX idx_alerts_created_at     ON fraud_alerts(created_at DESC);

-- ────────────────────────────────────────────────────────────
-- TRANSACTION FEATURES  (materialised ML features per tx)
-- ────────────────────────────────────────────────────────────
CREATE TABLE transaction_features (
    transaction_id          UUID PRIMARY KEY REFERENCES transactions(id),

    -- Velocity features (lookback windows)
    tx_count_1h             INT,         -- # txns by this account in past 1 hour
    tx_count_24h            INT,
    tx_count_7d             INT,
    amount_sum_1h           NUMERIC(18,2),
    amount_sum_24h          NUMERIC(18,2),
    amount_sum_7d           NUMERIC(18,2),

    -- Behavioural features
    avg_amount_30d          NUMERIC(18,2),
    std_amount_30d          NUMERIC(18,2),
    amount_zscore           NUMERIC(8,4), -- how many σ from mean
    unique_merchants_7d     INT,
    unique_countries_7d     INT,

    -- Geo anomaly
    geo_distance_km         NUMERIC(10,2), -- distance from last tx location
    time_since_last_tx_min  NUMERIC(10,2), -- minutes since previous tx
    impossible_travel       BOOLEAN DEFAULT FALSE,

    -- Temporal features
    hour_of_day             SMALLINT,    -- 0-23
    day_of_week             SMALLINT,    -- 0 Mon – 6 Sun
    is_weekend              BOOLEAN,
    is_night                BOOLEAN,     -- 22:00–06:00

    -- Merchant risk
    merchant_fraud_rate_30d NUMERIC(5,4),
    is_high_risk_merchant   BOOLEAN DEFAULT FALSE,

    computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- AUDIT LOG
-- ────────────────────────────────────────────────────────────
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    entity_type     VARCHAR(64) NOT NULL,
    entity_id       UUID NOT NULL,
    action          VARCHAR(32) NOT NULL,  -- INSERT | UPDATE | DELETE | LABEL | RESOLVE
    changed_by      VARCHAR(128),
    old_values      JSONB,
    new_values      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);

-- ────────────────────────────────────────────────────────────
-- HELPER: updated_at auto-trigger
-- ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_customers_updated_at
    BEFORE UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_accounts_updated_at
    BEFORE UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_alerts_updated_at
    BEFORE UPDATE ON fraud_alerts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ────────────────────────────────────────────────────────────
-- SEED: merchant categories and a handful of test records
-- ────────────────────────────────────────────────────────────
INSERT INTO merchants (merchant_code, name, category, country_code, city, is_high_risk) VALUES
  ('MCH001', 'Amazon',             'online_retail',      'US', 'Seattle',      FALSE),
  ('MCH002', 'Walmart',            'retail',             'US', 'Bentonville',  FALSE),
  ('MCH003', 'Shell Gas Station',  'fuel',               'US', 'Houston',      FALSE),
  ('MCH004', 'Starbucks',          'food_beverage',      'US', 'Seattle',      FALSE),
  ('MCH005', 'Las Vegas Casino',   'gambling',           'US', 'Las Vegas',    TRUE),
  ('MCH006', 'Crypto Exchange XYZ','cryptocurrency',     'MT', 'Valletta',     TRUE),
  ('MCH007', 'Netflix',            'digital_services',   'US', 'Los Gatos',    FALSE),
  ('MCH008', 'ATM - Chase Bank',   'atm',                'US', 'New York',     FALSE),
  ('MCH009', 'AliExpress',         'online_retail',      'CN', 'Hangzhou',     FALSE),
  ('MCH010', 'Western Union',      'money_transfer',     'US', 'Denver',       TRUE);
