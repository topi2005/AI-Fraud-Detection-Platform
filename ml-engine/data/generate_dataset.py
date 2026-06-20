"""
ml-engine/data/generate_dataset.py
 
Generates a synthetic, labelled fraud dataset and saves it as
ml-engine/data/transactions.csv  (used for model training).
 
v2 — REALISM PASS
------------------
The original generator made fraud trivially separable (extreme z-scores,
huge distances, no overlap with legitimate transactions), which let the
model hit ~100% on every metric — a sign of an unrealistically easy
dataset rather than a good model.
 
This version intentionally:
  - Adds gaussian noise to every feature
  - Shrinks the gap between fraud and normal value ranges so they overlap
  - Generates "hard negatives": legitimate transactions that look risky
    (big spenders, frequent travelers, occasional high-value purchases)
  - Generates "hard positives": fraud that looks mostly normal (low-value
    card testing, slow-building account takeover, fraud from a nearby city)
  - Adds label noise (~1.5% of labels are flipped) to simulate real-world
    mislabeling / analyst error
 


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
 
LABEL_NOISE_RATE = 0.015   # ~1.5% of labels get flipped — simulates real mislabeling
 
 
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
 
 
def noisy(value, rel_noise=0.15, min_val=None):
    """Add proportional gaussian noise to a value."""
    noised = value * (1 + rng.normal(0, rel_noise))
    if min_val is not None:
        noised = max(noised, min_val)
    return noised
 
 
def customer_archetype():
    """
    Assign each synthetic customer a behavioural archetype so legitimate
    spending patterns vary realistically — some customers are naturally
    "high velocity" or "high spend" without being fraudulent, which is
    exactly what creates realistic overlap with fraud signals.
    """
    return random.choices(
        ["typical", "big_spender", "frequent_traveler", "high_velocity", "low_activity"],
        weights=[0.55, 0.15, 0.12, 0.10, 0.08],
    )[0]
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Row generators
# ──────────────────────────────────────────────────────────────────────────────
 
def make_normal_row(account_id, home_lat, home_lon, avg_spend, archetype, base_time):
    category = random.choice([c for c in MERCHANT_CATEGORIES if c not in HIGH_RISK_CATEGORIES])
    hour = int(rng.integers(6, 23))
    dow  = int(rng.integers(0, 7))
 
    # Archetype-driven baselines create legitimate overlap with "risky-looking" stats
    if archetype == "big_spender":
        avg_spend *= rng.uniform(2.5, 5.0)
        amount = float(np.clip(rng.lognormal(math.log(max(avg_spend / 28, 8)), 0.7), 1, avg_spend * 4))
    elif archetype == "frequent_traveler":
        amount = float(np.clip(rng.lognormal(math.log(max(avg_spend / 30, 5)), 0.65), 1, avg_spend * 3))
    elif archetype == "high_velocity":
        amount = float(np.clip(rng.lognormal(math.log(max(avg_spend / 45, 4)), 0.6), 1, avg_spend * 2))
    elif archetype == "low_activity":
        amount = float(np.clip(rng.lognormal(math.log(max(avg_spend / 20, 6)), 0.5), 1, avg_spend * 2.5))
    else:
        amount = float(np.clip(rng.lognormal(math.log(max(avg_spend / 30, 5)), 0.55), 1, avg_spend * 3))
 
    # Location: frequent travelers legitimately roam further from home
    if archetype == "frequent_traveler" and rng.random() < 0.35:
        tx_lat = home_lat + rng.uniform(-8, 8)
        tx_lon = home_lon + rng.uniform(-8, 8)
    else:
        tx_lat = home_lat + rng.uniform(-0.3, 0.3)
        tx_lon = home_lon + rng.uniform(-0.3, 0.3)
    geo_dist = noisy(haversine_km(home_lat, home_lon, tx_lat, tx_lon), 0.2)
 
    last_amount = float(np.clip(rng.lognormal(math.log(max(avg_spend / 30, 5)), 0.5), 1, avg_spend * 2))
    time_since  = float(max(rng.exponential(300), 2))
 
    # Velocity baselines vary by archetype — high_velocity customers legitimately
    # transact often, which overlaps with what velocity_abuse fraud looks like
    if archetype == "high_velocity":
        tx_1h, tx_24h, tx_7d = int(rng.poisson(4)), int(rng.poisson(14)), int(rng.poisson(55))
    elif archetype == "low_activity":
        tx_1h, tx_24h, tx_7d = int(rng.poisson(0.3)), int(rng.poisson(1)), int(rng.poisson(4))
    else:
        tx_1h, tx_24h, tx_7d = int(rng.poisson(1.2)), int(rng.poisson(4)), int(rng.poisson(18))
 
    std_30d = noisy(avg_spend / 30 * 0.4, 0.25, min_val=1)
    zscore  = (amount - avg_spend / 30) / max(std_30d, 1)
 
    return {
        "tx_id":                  str(uuid.uuid4()),
        "account_id":             account_id,
        "amount":                 round(max(amount, 0.5), 2),
        "hour_of_day":            hour,
        "day_of_week":            dow,
        "is_weekend":             int(dow >= 5),
        "is_night":               int(hour < 6 or hour >= 22),
        "channel":                random.choices(CHANNELS, weights=[0.5, 0.25, 0.15, 0.08, 0.02])[0],
        "transaction_type":       random.choice(["purchase", "online_purchase", "purchase"]),
        "merchant_category":      category,
        "is_high_risk_merchant":  0,
        "tx_count_1h":            tx_1h,
        "tx_count_24h":           tx_24h,
        "tx_count_7d":            tx_7d,
        "amount_sum_1h":          round(noisy(rng.uniform(0, avg_spend * 0.2), 0.3), 2),
        "amount_sum_24h":         round(noisy(rng.uniform(0, avg_spend * 0.8), 0.3), 2),
        "amount_sum_7d":          round(noisy(rng.uniform(avg_spend * 0.5, avg_spend * 3), 0.3), 2),
        "avg_amount_30d":         round(avg_spend / 30, 2),
        "std_amount_30d":         round(std_30d, 2),
        "amount_zscore":          round(zscore, 4),
        "unique_merchants_7d":    int(rng.integers(2, 12)),
        "unique_countries_7d":    1 if archetype != "frequent_traveler" else int(rng.integers(1, 4)),
        "geo_distance_km":        round(geo_dist, 2),
        "time_since_last_tx_min": round(time_since, 2),
        "impossible_travel":      0,
        "last_tx_amount":         round(last_amount, 2),
        "merchant_fraud_rate_30d":round(float(np.clip(rng.normal(0.004, 0.006), 0, 0.05)), 4),
        "is_fraud":               0,
        "fraud_type":             None,
    }
 
 
def make_fraud_row(account_id, home_lat, home_lon, avg_spend, archetype, base_time, fraud_type=None):
    if fraud_type is None:
        fraud_type = random.choice(FRAUD_TYPES)
 
    row = make_normal_row(account_id, home_lat, home_lon, avg_spend, archetype, base_time)
    row["is_fraud"]    = 1
    row["fraud_type"]  = fraud_type
 
    # "Hard" vs "easy" fraud — roughly a third of fraud cases are subtle,
    # mimicking real-world fraud that doesn't trip every signal at once
    subtlety = rng.random()
    is_hard  = subtlety < 0.32
 
    if fraud_type == "card_not_present":
        row["channel"]               = "online"
        row["transaction_type"]      = "online_purchase"
        if is_hard:
            # fraud from a plausible nearby country, moderate amount
            row["geo_distance_km"]   = round(noisy(rng.uniform(300, 1500), 0.25), 2)
            row["amount"]            = round(noisy(rng.uniform(40, 250), 0.3), 2)
        else:
            row["geo_distance_km"]   = round(noisy(rng.uniform(1800, 11000), 0.2), 2)
            row["amount"]            = round(noisy(rng.uniform(150, 2500), 0.3), 2)
        row["unique_countries_7d"]   = int(rng.integers(1, 5))
        row["is_high_risk_merchant"] = int(rng.random() > 0.5)
        row["merchant_fraud_rate_30d"] = round(float(np.clip(rng.normal(0.06, 0.05), 0, 0.35)), 4)
 
    elif fraud_type == "velocity_abuse":
        if is_hard:
            row["tx_count_1h"]   = int(rng.integers(5, 14))     # overlaps with high_velocity legit customers
            row["tx_count_24h"]  = int(rng.integers(15, 45))
        else:
            row["tx_count_1h"]   = int(rng.integers(15, 55))
            row["tx_count_24h"]  = int(rng.integers(40, 180))
        row["amount"]         = round(noisy(rng.uniform(1, 90), 0.4), 2)
        row["amount_sum_1h"]  = round(row["tx_count_1h"] * row["amount"] * rng.uniform(0.5, 0.9), 2)
        row["amount_zscore"]  = round(noisy(rng.uniform(-1, 1.2), 0.3), 4)
 
    elif fraud_type == "amount_spike":
        spike = noisy(rng.uniform(6, 45) if is_hard else rng.uniform(15, 55), 0.25)
        row["amount"]         = round(max(avg_spend / 30 * spike, 50), 2)
        row["amount_zscore"]  = round(noisy(spike * 0.75, 0.3), 4)
        row["channel"]        = random.choice(["wire", "online"])
        row["transaction_type"] = "transfer"
 
    elif fraud_type == "geo_anomaly":
        if is_hard:
            row["geo_distance_km"]        = round(noisy(rng.uniform(800, 3000), 0.25), 2)
            row["time_since_last_tx_min"] = round(noisy(rng.uniform(90, 400), 0.3), 2)
            row["impossible_travel"]      = int(rng.random() > 0.4)
        else:
            row["geo_distance_km"]        = round(noisy(rng.uniform(4000, 14000), 0.2), 2)
            row["time_since_last_tx_min"] = round(noisy(rng.uniform(5, 150), 0.3), 2)
            row["impossible_travel"]      = 1
        row["unique_countries_7d"]   = int(rng.integers(2, 7))
 
    elif fraud_type == "account_takeover":
        row["channel"]          = "wire"
        row["transaction_type"] = "transfer"
        if is_hard:
            row["amount"]        = round(noisy(rng.uniform(800, 3500), 0.3), 2)
            row["amount_zscore"] = round(noisy(rng.uniform(3, 9), 0.3), 4)
        else:
            row["amount"]        = round(noisy(rng.uniform(3000, 18000), 0.25), 2)
            row["amount_zscore"] = round(noisy(rng.uniform(8, 22), 0.25), 4)
        row["is_night"]         = int(rng.random() > 0.3)
        row["hour_of_day"]      = int(rng.integers(0, 6)) if row["is_night"] else int(rng.integers(6, 23))
        row["tx_count_1h"]      = int(rng.integers(1, 8))
 
    elif fraud_type == "synthetic_id":
        if is_hard:
            row["unique_merchants_7d"]     = int(rng.integers(8, 20))
            row["tx_count_7d"]             = int(rng.integers(25, 70))
            row["amount_sum_7d"]           = round(noisy(rng.uniform(avg_spend * 1.5, avg_spend * 6), 0.3), 2)
        else:
            row["unique_merchants_7d"]     = int(rng.integers(15, 40))
            row["tx_count_7d"]             = int(rng.integers(55, 200))
            row["amount_sum_7d"]           = round(noisy(rng.uniform(avg_spend * 5, avg_spend * 20), 0.3), 2)
        row["merchant_fraud_rate_30d"] = round(float(np.clip(rng.normal(0.05, 0.04), 0, 0.25)), 4)
 
    row["amount"] = round(max(row["amount"], 0.01), 2)
    row["amount_sum_24h"] = round(max(row.get("amount_sum_24h", 0), 0) + row["amount"], 2)
    return row
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
 
def generate(n_rows: int, fraud_rate: float, out_path: str):
    print(f"Generating {n_rows:,} rows  (fraud rate: {fraud_rate:.1%}) …")
    n_fraud  = int(n_rows * fraud_rate)
    n_normal = n_rows - n_fraud
 
    # 500 synthetic accounts, each with a behavioural archetype
    accounts = [
        (str(uuid.uuid4()), *random_home(), float(rng.uniform(500, 8000)), customer_archetype())
        for _ in range(500)
    ]
    base_time = datetime.utcnow()
 
    rows = []
    for _ in range(n_normal):
        acc_id, hlat, hlon, avg, archetype = random.choice(accounts)
        rows.append(make_normal_row(acc_id, hlat, hlon, avg, archetype, base_time))
 
    for i in range(n_fraud):
        acc_id, hlat, hlon, avg, archetype = random.choice(accounts)
        ftype = FRAUD_TYPES[i % len(FRAUD_TYPES)]
        rows.append(make_fraud_row(acc_id, hlat, hlon, avg, archetype, base_time, ftype))
 
    random.shuffle(rows)
    df = pd.DataFrame(rows)
 
    # ── Label noise — flip a small % of labels to simulate real-world
    # mislabeling / analyst error. This alone prevents a model from ever
    # legitimately reaching 100%, which is realistic and expected.
    n_flip = int(len(df) * LABEL_NOISE_RATE)
    flip_idx = rng.choice(df.index, size=n_flip, replace=False)
    df.loc[flip_idx, "is_fraud"] = 1 - df.loc[flip_idx, "is_fraud"]
 
    # encode categoricals
    df["channel"]           = df["channel"].astype("category").cat.codes
    df["transaction_type"]  = df["transaction_type"].astype("category").cat.codes
    df["merchant_category"] = df["merchant_category"].astype("category").cat.codes
 
    df.to_csv(out_path, index=False)
    print(f"✅ Saved {len(df):,} rows → {out_path}")
    print(f"   Fraud: {df['is_fraud'].sum():,}  ({df['is_fraud'].mean():.2%})")
    print(f"   Label noise applied to: {n_flip:,} rows")
    print(f"   Fraud types:\n{df[df.is_fraud==1]['fraud_type'].value_counts(dropna=False).to_string()}")
 
 
if __name__ == "__main__":
    import os
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows",       type=int,   default=100_000)
    parser.add_argument("--fraud-rate", type=float, default=0.025)
    parser.add_argument("--out",        type=str,   default=os.path.join(os.path.dirname(__file__), "transactions.csv"))
    args = parser.parse_args()
    generate(args.rows, args.fraud_rate, args.out)
 