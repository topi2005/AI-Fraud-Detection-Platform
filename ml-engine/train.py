"""
ml-engine/train.py

Trains a fraud detection ensemble:
  • Random Forest   (good recall, interpretable)
  • XGBoost         (high precision, handles imbalance)
  • Soft-vote ensemble of both

Handles class imbalance with SMOTE oversampling.
Tracks every experiment in MLflow.
Saves the best model to ml-engine/models/fraud_model.pkl

Run:
    python train.py
    python train.py --data data/transactions.csv --threshold 0.35
"""

import os
import sys
import argparse
import warnings
import joblib
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # non-interactive backend for servers
import matplotlib.pyplot as plt
import seaborn as sns
import mlflow
import mlflow.sklearn

from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import (
    classification_report, confusion_matrix,
    roc_auc_score, average_precision_score,
    precision_recall_curve, roc_curve,
    f1_score,
)
from sklearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
import xgboost as xgb

sys.path.insert(0, os.path.dirname(__file__))
from features import (
    build_preprocessor, ALL_FEATURES, TARGET,
    NUMERIC_FEATURES, BINARY_FEATURES, CATEGORICAL_FEATURES,
)

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("train")

MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{MODELS_DIR}/mlflow.db")
EXPERIMENT_NAME     = "fraud-detection"


# ──────────────────────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────────────────────

def load_data(csv_path: str) -> tuple[pd.DataFrame, pd.Series]:
    log.info("Loading dataset from %s", csv_path)
    df = pd.read_csv(csv_path)

    missing = [c for c in ALL_FEATURES if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in dataset: {missing}")

    X = df[ALL_FEATURES]
    y = df[TARGET]

    log.info("Dataset: %d rows | Fraud: %d (%.2f%%)", len(df), y.sum(), y.mean() * 100)
    return X, y


# ──────────────────────────────────────────────────────────────────────────────
# Model definitions
# ──────────────────────────────────────────────────────────────────────────────

def build_rf() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=300,
        max_depth=20,
        min_samples_split=5,
        min_samples_leaf=2,
        max_features="sqrt",
        class_weight="balanced",
        n_jobs=-1,
        random_state=42,
    )


def build_xgb() -> xgb.XGBClassifier:
    return xgb.XGBClassifier(
        n_estimators=400,
        max_depth=8,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        scale_pos_weight=40,       # ~fraud_rate reciprocal
        eval_metric="aucpr",
        use_label_encoder=False,
        n_jobs=-1,
        random_state=42,
        verbosity=0,
    )


def build_ensemble(rf, xgb_clf) -> VotingClassifier:
    return VotingClassifier(
        estimators=[("rf", rf), ("xgb", xgb_clf)],
        voting="soft",
        weights=[1, 1.5],       # slight XGB preference (higher precision)
    )


# ──────────────────────────────────────────────────────────────────────────────
# Evaluation helpers
# ──────────────────────────────────────────────────────────────────────────────

def evaluate(model, X_test: pd.DataFrame, y_test: pd.Series, threshold: float, label: str):
    proba = model.predict_proba(X_test)[:, 1]
    preds = (proba >= threshold).astype(int)

    report   = classification_report(y_test, preds, digits=4, output_dict=True)
    roc_auc  = roc_auc_score(y_test, proba)
    avg_prec = average_precision_score(y_test, proba)
    f1       = f1_score(y_test, preds)

    log.info("─── %s ──────────────────────────────", label)
    log.info("  ROC-AUC  : %.4f", roc_auc)
    log.info("  Avg Prec : %.4f", avg_prec)
    log.info("  F1       : %.4f", f1)
    log.info("  Precision: %.4f  Recall: %.4f",
             report["1"]["precision"], report["1"]["recall"])
    log.info("  FP rate  : %.4f",
             report["0"]["recall"])   # 1 - specificity

    return {
        "roc_auc":          roc_auc,
        "avg_precision":    avg_prec,
        "f1":               f1,
        "precision":        report["1"]["precision"],
        "recall":           report["1"]["recall"],
        "proba":            proba,
        "preds":            preds,
    }


def plot_confusion(y_test, preds, path: Path, title: str):
    cm = confusion_matrix(y_test, preds)
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=ax,
                xticklabels=["Legit", "Fraud"],
                yticklabels=["Legit", "Fraud"])
    ax.set_title(title)
    ax.set_ylabel("Actual")
    ax.set_xlabel("Predicted")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_pr_roc(y_test, proba, out_dir: Path, label: str):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # Precision-Recall
    precision, recall, _ = precision_recall_curve(y_test, proba)
    ap = average_precision_score(y_test, proba)
    axes[0].plot(recall, precision, lw=2, label=f"AP={ap:.3f}")
    axes[0].set_xlabel("Recall"); axes[0].set_ylabel("Precision")
    axes[0].set_title(f"{label} — Precision-Recall Curve")
    axes[0].legend(); axes[0].grid(True)

    # ROC
    fpr, tpr, _ = roc_curve(y_test, proba)
    auc = roc_auc_score(y_test, proba)
    axes[1].plot(fpr, tpr, lw=2, label=f"AUC={auc:.3f}")
    axes[1].plot([0, 1], [0, 1], "k--", lw=1)
    axes[1].set_xlabel("FPR"); axes[1].set_ylabel("TPR")
    axes[1].set_title(f"{label} — ROC Curve")
    axes[1].legend(); axes[1].grid(True)

    fig.tight_layout()
    path = out_dir / f"{label.lower().replace(' ', '_')}_curves.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_feature_importance(model, feature_names: list[str], out_dir: Path):
    """Extract RF feature importances."""
    rf_step = None
    # model is Pipeline → VotingClassifier → RF
    try:
        vc = model.named_steps["model"]
        rf_step = dict(vc.named_estimators_)["rf"]
    except Exception:
        return

    importances = rf_step.feature_importances_
    if len(importances) != len(feature_names):
        return

    idx  = np.argsort(importances)[::-1][:20]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh([feature_names[i] for i in idx[::-1]], importances[idx[::-1]])
    ax.set_title("Top 20 Feature Importances (Random Forest)")
    ax.set_xlabel("Importance")
    fig.tight_layout()
    path = out_dir / "feature_importance.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Main training loop
# ──────────────────────────────────────────────────────────────────────────────

def train(data_path: str, threshold: float, test_size: float):
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    X, y = load_data(data_path)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=42
    )
    log.info("Train: %d  |  Test: %d", len(X_train), len(X_test))

    preprocessor = build_preprocessor()
    rf_clf  = build_rf()
    xgb_clf = build_xgb()
    ensemble = build_ensemble(rf_clf, xgb_clf)

    # Full pipeline: preprocess → SMOTE → ensemble
    pipeline = ImbPipeline([
        ("preprocess", preprocessor),
        ("smote",      SMOTE(sampling_strategy=0.15, random_state=42, n_jobs=-1)),
        ("model",      ensemble),
    ])

    with mlflow.start_run(run_name="ensemble-rf-xgb") as run:
        log.info("Training ensemble pipeline… (this takes ~2-3 min)")
        pipeline.fit(X_train, y_train)
        log.info("Training complete ✅")

        # ── Evaluate ─────────────────────────────────────────────────────────
        metrics = evaluate(pipeline, X_test, y_test, threshold, "Ensemble")

        # ── MLflow logging ───────────────────────────────────────────────────
        mlflow.log_params({
            "threshold":     threshold,
            "test_size":     test_size,
            "smote_ratio":   0.15,
            "rf_estimators": 300,
            "xgb_estimators":400,
            "xgb_lr":        0.05,
        })
        mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, float)})

        # ── Plots ─────────────────────────────────────────────────────────────
        plots_dir = MODELS_DIR / "plots"
        plots_dir.mkdir(exist_ok=True)

        cm_path  = plot_confusion(y_test, metrics["preds"], plots_dir / "confusion.png", "Ensemble")
        prc_path = plot_pr_roc(y_test, metrics["proba"], plots_dir, "Ensemble")
        fi_path  = plot_feature_importance(pipeline, ALL_FEATURES, plots_dir)

        for p in [cm_path, prc_path, fi_path]:
            if p and Path(p).exists():
                mlflow.log_artifact(str(p))

        # ── Save model artifact ───────────────────────────────────────────────
        model_path = MODELS_DIR / "fraud_model.pkl"
        joblib.dump(pipeline, model_path)
        log.info("Model saved → %s", model_path)

        # Save metadata sidecar consumed by the inference API
        meta = {
            "model_version":   run.info.run_id[:8],
            "threshold":       threshold,
            "roc_auc":         round(metrics["roc_auc"], 4),
            "avg_precision":   round(metrics["avg_precision"], 4),
            "f1":              round(metrics["f1"], 4),
            "precision":       round(metrics["precision"], 4),
            "recall":          round(metrics["recall"], 4),
            "feature_names":   ALL_FEATURES,
        }
        meta_path = MODELS_DIR / "model_meta.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        mlflow.log_artifact(str(meta_path))

        mlflow.sklearn.log_model(pipeline, "fraud_model")

        log.info("━" * 60)
        log.info("  ROC-AUC  : %.4f", metrics["roc_auc"])
        log.info("  Avg Prec : %.4f", metrics["avg_precision"])
        log.info("  F1       : %.4f", metrics["f1"])
        log.info("  Run ID   : %s", run.info.run_id)
        log.info("  Model    : %s", model_path)
        log.info("━" * 60)

    return pipeline, meta


# ──────────────────────────────────────────────────────────────────────────────
# Risk tier mapper  (used by inference API)
# ──────────────────────────────────────────────────────────────────────────────

def score_to_risk_tier(score: float) -> str:
    if score >= 0.80:
        return "critical"
    elif score >= 0.55:
        return "high"
    elif score >= 0.30:
        return "medium"
    return "low"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",      default=str(Path(__file__).parent / "data/transactions.csv"))
    parser.add_argument("--threshold", type=float, default=0.35)
    parser.add_argument("--test-size", type=float, default=0.20)
    args = parser.parse_args()

    # Auto-generate dataset if missing
    if not Path(args.data).exists():
        log.info("Dataset not found — generating synthetic data…")
        import subprocess
        subprocess.run(
            [sys.executable, str(Path(__file__).parent / "data/generate_dataset.py"),
             "--rows", "100000", "--out", args.data],
            check=True,
        )

    train(args.data, args.threshold, args.test_size)
