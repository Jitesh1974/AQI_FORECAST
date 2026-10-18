"""Train and evaluate a one-hour-ahead PM2.5 regressor.

Default: train on the official UCI Beijing station dataset.
Local option: pass a CSV produced by collect_openmeteo.py.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from backend.ml.data_utils import load_uci_dataset, make_training_rows, FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "backend" / "artifacts"


def train(csv_path: Path | None = None, region: str | None = None) -> dict:
    if csv_path:
        if not csv_path.exists():
            raise FileNotFoundError(f"Input CSV not found: {csv_path}")
        raw = pd.read_csv(csv_path)
        dataset_name = f"Open-Meteo location history: {region or csv_path.stem}"
        training_region = region or "User-selected coordinates (model-derived history)"
    else:
        raw = load_uci_dataset()
        dataset_name = "UCI Beijing Multi-Site Air Quality"
        training_region = "Beijing, China (12 monitoring stations, 2013-2017)"

    X, y, target_time = make_training_rows(raw)
    # Strict chronological split: no shuffling of observations over time.
    cutoff = target_time.sort_values().iloc[int(len(target_time) * 0.8)]
    train_mask = target_time < cutoff
    test_mask = ~train_mask
    if train_mask.sum() < 50 or test_mask.sum() < 20:
        raise ValueError("Not enough samples after chronological split; collect more data.")

    model = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("regressor", HistGradientBoostingRegressor(
            max_iter=180, learning_rate=0.08, max_leaf_nodes=31,
            l2_regularization=1.0, random_state=42,
        )),
    ])
    model.fit(X.loc[train_mask], y.loc[train_mask])
    predictions = model.predict(X.loc[test_mask])
    metrics = {
        "mae": round(float(mean_absolute_error(y.loc[test_mask], predictions)), 4),
        "rmse": round(float(mean_squared_error(y.loc[test_mask], predictions) ** 0.5), 4),
        "r2": round(float(r2_score(y.loc[test_mask], predictions)), 4),
        "train_rows": int(train_mask.sum()), "test_rows": int(test_mask.sum()),
        "cutoff_target_time": str(pd.Timestamp(cutoff)),
        "total_rows": int(len(X)),
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "metrics": metrics,
        "dataset_name": dataset_name,
        "training_region": training_region,
        "target": "PM2.5 concentration one hour after the input observation (ug/m^3)",
        "trained_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "training_rows": int(train_mask.sum()),
    }
    joblib.dump(bundle, ARTIFACT_DIR / "model.joblib", compress=3)
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"saved_model": str(ARTIFACT_DIR / "model.joblib"), **metrics,
                      "dataset": dataset_name, "region": training_region}, indent=2))
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=None,
                        help="Optional normalized CSV, e.g. output of collect_openmeteo.py")
    parser.add_argument("--region", type=str, default=None,
                        help="Region label to store in model metadata when --csv is used")
    args = parser.parse_args()
    train(args.csv, args.region)
