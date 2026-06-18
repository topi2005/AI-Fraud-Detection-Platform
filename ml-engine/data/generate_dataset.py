"""
ml-engine/data/generate_dataset.py

Generates a synthetic, labelled fraud dataset and saves it as
ml-engine/data/transactions.csv  (used for model training).

Features mirror the transaction_features table from the DB schema
so the same pipeline works for both offline training and online inference.

Run:
    python data/generate_dataset.py --rows 100000 --fraud-rate 0.025
"""

import argparse
import math
import random
import uuid
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

SEED = 42
rng  = np.random.default_rng(SEED)
random.seed(SEED)

FRAUD_TYPES = [
    "card_not_present",
    "velocity_abuse",
    "amount_spike",
    "geo_anomaly",
    "account_takeover",
    "synthetic_id",
]

MERCHANT_CATEGORIES = [
    "retail", "online_retail", "food_beverage", "fuel",
    "digital_services", "atm", "gambling", "cryptocurrency",
    "money_transfer", "travel", "healthcare", "education",
]

HIGH_RISK_CATEGORIES = {"gambling", "cryptocurrency", "money_transfer"}

CHANNELS = ["card", "online", "mobile", "atm", "wire"]
TX_TYPES  = ["purchase", "online_purchase", "atm_withdrawal", "transfer", "international"]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(max(0, a)))


def random_home():
    """Return (lat, lon) near a major city."""
    cities = [
        (40.71, -74.01), (34.05, -118.24), (41.88, -87.63),
        (51.51, -0.13),  (48.85, 2.35),    (35.68, 139.69),
        (-33.87, 151.21),(43.65, -79.38),  (19.43, -99.13),
        (-26.20, 28.04),
    ]
    lat, lon = random.choice(cities)
    return (
        lat + rng.uniform(-0.5, 0.5),
        lon + rng.uniform(-0.5, 0.5),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Row generators
# ──────────────────────────────────────────────────────────────────────────────

def make_normal_row(account_id, home_lat, home_lon, avg_spend, base_time):
    category = random.choice([c for c in MERCHANT_CATEGORIES if c not in HIGH_RISK_CATEGORIES])
    hour = int(rng.integers(7, 22))         # daytime-ish
    dow  = int(rng.integers(0, 7))
    amount = float(np.clip(rng.lognormal(math.log(max(avg_spend / 30, 5)), 0.55), 1, avg_spend * 3))
    tx_lat = home_lat + rng.uniform(-0.3, 0.3)
    tx_lon = home_lon + rng.uniform(-0.3, 0.3)
    geo_dist = haversine_km(home_lat, home_lon, tx_lat, tx_lon)
    last_amount = float(np.clip(rng.lognormal(math.log(max(avg_spend / 30, 5)), 0.5), 1, avg_spend * 2))
    time_since  = float(rng.exponential(300))   # minutes since last tx

    return {
        "tx_id":                  str(uuid.uuid4()),
        "account_id":             account_id,
        "amount":                 round(amount, 2),
        "hour_of_day":            hour,
        "day_of_week":            dow,
        "is_weekend":             int(dow >= 5),
        "is_night":               int(hour < 6 or hour >= 22),
        "channel":                random.choices(CHANNELS, weights=[0.5, 0.25, 0.15, 0.08, 0.02])[0],
        "transaction_type":       random.choice(["purchase", "online_purchase", "purchase"]),
        "merchant_category":      category,
        "is_high_risk_merchant":  0,
        "tx_count_1h":            int(rng.poisson(1.2)),
        "tx_count_24h":           int(rng.poisson(4)),
        "tx_count_7d":            int(rng.poisson(18)),
        "amount_sum_1h":          round(float(rng.uniform(0, avg_spend * 0.2)), 2),
        "amount_sum_24h":         round(float(rng.uniform(0, avg_spend * 0.8)), 2),
        "amount_sum_7d":          round(float(rng.uniform(avg_spend * 0.5, avg_spend * 3)), 2),
        "avg_amount_30d":         round(avg_spend / 30, 2),
        "std_amount_30d":         round(avg_spend / 30 * 0.4, 2),
        "amount_zscore":          round((amount - avg_spend / 30) / max(avg_spend / 30 * 0.4, 1), 4),
        "unique_merchants_7d":    int(rng.integers(2, 12)),
        "unique_countries_7d":    1,
        "geo_distance_km":        round(geo_dist, 2),
        "time_since_last_tx_min": round(time_since, 2),
        "impossible_travel":      0,
        "last_tx_amount":         round(last_amount, 2),
        "merchant_fraud_rate_30d":round(float(rng.uniform(0, 0.01)), 4),
        "is_fraud":               0,
        "fraud_type":             None,
    }


def make_fraud_row(account_id, home_lat, home_lon, avg_spend, base_time, fraud_type=None):
    if fraud_type is None:
        fraud_type = random.choice(FRAUD_TYPES)

    row = make_normal_row(account_id, home_lat, home_lon, avg_spend, base_time)
    row["is_fraud"]    = 1
    row["fraud_type"]  = fraud_type

    if fraud_type == "card_not_present":
        row["channel"]               = "online"
        row["transaction_type"]      = "online_purchase"
        row["geo_distance_km"]       = round(float(rng.uniform(2000, 12000)), 2)
        row["unique_countries_7d"]   = int(rng.integers(2, 5))
        row["amount"]                = round(float(rng.uniform(200, 3000)), 2)
        row["is_high_risk_merchant"] = int(rng.random() > 0.4)
        row["merchant_fraud_rate_30d"] = round(float(rng.uniform(0.05, 0.3)), 4)

    elif fraud_type == "velocity_abuse":
        row["tx_count_1h"]    = int(rng.integers(20, 60))
        row["tx_count_24h"]   = int(rng.integers(50, 200))
        row["amount"]         = round(float(rng.uniform(1, 80)), 2)
        row["amount_sum_1h"]  = round(row["tx_count_1h"] * row["amount"] * 0.8, 2)
        row["amount_zscore"]  = round(float(rng.uniform(-1, 0.5)), 4)

    elif fraud_type == "amount_spike":
        spike = float(rng.uniform(15, 60))
        row["amount"]         = round(avg_spend / 30 * spike, 2)
        row["amount_zscore"]  = round(spike * 0.8, 4)
        row["channel"]        = random.choice(["wire", "online"])
        row["transaction_type"] = "transfer"

    elif fraud_type == "geo_anomaly":
        row["geo_distance_km"]       = round(float(rng.uniform(5000, 15000)), 2)
        row["time_since_last_tx_min"]= round(float(rng.uniform(5, 120)), 2)
        row["impossible_travel"]     = 1
        row["unique_countries_7d"]   = int(rng.integers(3, 7))

    elif fraud_type == "account_takeover":
        row["channel"]          = "wire"
        row["transaction_type"] = "transfer"
        row["amount"]           = round(float(rng.uniform(3000, 20000)), 2)
        row["amount_zscore"]    = round(float(rng.uniform(8, 25)), 4)
        row["is_night"]         = 1
        row["hour_of_day"]      = int(rng.integers(1, 5))
        row["tx_count_1h"]      = int(rng.integers(3, 10))

    elif fraud_type == "synthetic_id":
        row["unique_merchants_7d"]    = int(rng.integers(15, 40))
        row["tx_count_7d"]            = int(rng.integers(60, 200))
        row["amount_sum_7d"]          = round(float(rng.uniform(avg_spend * 5, avg_spend * 20)), 2)
        row["merchant_fraud_rate_30d"]= round(float(rng.uniform(0.03, 0.15)), 4)

    # re-clip amount
    row["amount"] = round(max(row["amount"], 0.01), 2)
    row["amount_sum_24h"] = round(row.get("amount_sum_24h", 0) + row["amount"], 2)
    return row


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def generate(n_rows: int, fraud_rate: float, out_path: str):
    print(f"Generating {n_rows:,} rows  (fraud rate: {fraud_rate:.1%}) …")
    n_fraud  = int(n_rows * fraud_rate)
    n_normal = n_rows - n_fraud

    # 500 synthetic accounts
    accounts = [
        (str(uuid.uuid4()), *random_home(), float(rng.uniform(500, 8000)))
        for _ in range(500)
    ]
    base_time = datetime.utcnow()

    rows = []
    for _ in range(n_normal):
        acc_id, hlat, hlon, avg = random.choice(accounts)
        rows.append(make_normal_row(acc_id, hlat, hlon, avg, base_time))

    # distribute fraud types roughly evenly
    for i in range(n_fraud):
        acc_id, hlat, hlon, avg = random.choice(accounts)
        ftype = FRAUD_TYPES[i % len(FRAUD_TYPES)]
        rows.append(make_fraud_row(acc_id, hlat, hlon, avg, base_time, ftype))

    random.shuffle(rows)
    df = pd.DataFrame(rows)

    # encode categoricals
    df["channel"]           = df["channel"].astype("category").cat.codes
    df["transaction_type"]  = df["transaction_type"].astype("category").cat.codes
    df["merchant_category"] = df["merchant_category"].astype("category").cat.codes

    df.to_csv(out_path, index=False)
    print(f"✅ Saved {len(df):,} rows → {out_path}")
    print(f"   Fraud: {df['is_fraud'].sum():,}  ({df['is_fraud'].mean():.2%})")
    print(f"   Fraud types:\n{df[df.is_fraud==1]['fraud_type'].value_counts().to_string()}")


if __name__ == "__main__":
    import os
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows",       type=int,   default=100_000)
    parser.add_argument("--fraud-rate", type=float, default=0.025)
    parser.add_argument("--out",        type=str,   default=os.path.join(os.path.dirname(__file__), "transactions.csv"))
    args = parser.parse_args()
    generate(args.rows, args.fraud_rate, args.out)
