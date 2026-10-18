from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.ml.data_utils import latest_feature_row

APP_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = APP_DIR.parent / "artifacts" / "model.joblib"
MODEL_PATH = Path(os.getenv("MODEL_PATH", str(DEFAULT_MODEL_PATH)))
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

app = FastAPI(
    title="AirCast ML API",
    description=(
        "A machine-learning demonstration that predicts next-hour PM2.5 concentration. "
        "Predictions are estimates, not official AQI values or health advice."
    ),
    version="1.0.0",
)
origins = [x.strip() for x in os.getenv(
    "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

bundle: dict[str, Any] | None = None
load_error: str | None = None


def load_model() -> None:
    global bundle, load_error
    try:
        if not MODEL_PATH.exists():
            bundle = None
            load_error = f"Model file not found at {MODEL_PATH}. Run the training instructions in README.md first."
            return
        loaded = joblib.load(MODEL_PATH)
        if not isinstance(loaded, dict) or "model" not in loaded:
            raise ValueError("Invalid model bundle format")
        bundle = loaded
        load_error = None
    except Exception as exc:  # startup should still allow /api/health to explain the problem
        bundle = None
        load_error = str(exc)


@app.on_event("startup")
def startup_event() -> None:
    load_model()


class ManualPrediction(BaseModel):
    pm25: float = Field(..., ge=0, le=2000, description="Current PM2.5, micrograms/m³")
    pm10: float = Field(..., ge=0, le=5000)
    so2: float = Field(..., ge=0, le=10000)
    no2: float = Field(..., ge=0, le=10000)
    co: float = Field(..., ge=0, le=1000000, description="CO in micrograms/m³")
    o3: float = Field(..., ge=0, le=10000)
    temp: float = Field(..., ge=-80, le=70, description="Temperature in °C")
    pres: float = Field(..., ge=500, le=1200, description="Surface pressure in hPa")
    dewp: float = Field(..., ge=-100, le=70, description="Dew point in °C")
    rain: float = Field(..., ge=0, le=1000, description="Precipitation in mm")
    wspm: float = Field(..., ge=0, le=150, description="Wind speed in m/s")
    wind_direction_deg: float = Field(..., ge=0, le=360)
    hour: int = Field(..., ge=0, le=23)
    month: int = Field(..., ge=1, le=12)


def require_model() -> dict[str, Any]:
    if bundle is None:
        raise HTTPException(status_code=503, detail=load_error or "Model is not loaded")
    return bundle


def make_result(features: pd.DataFrame, timestamp: str | None, source: str,
                location: dict[str, float] | None = None,
                current_pm25: float | None = None) -> dict[str, Any]:
    active_bundle = require_model()
    prediction = float(active_bundle["model"].predict(features)[0])
    prediction = max(0.0, prediction)
    result: dict[str, Any] = {
        "predicted_pm25_ug_m3": round(prediction, 2),
        "forecast_for": (pd.Timestamp(timestamp) + pd.Timedelta(hours=1)).isoformat() if timestamp else None,
        "input_time": timestamp,
        "current_pm25_ug_m3": round(float(current_pm25), 2) if current_pm25 is not None else None,
        "source": source,
        "model_dataset": active_bundle.get("dataset_name", "Unknown"),
        "model_training_region": active_bundle.get("training_region", "Unknown"),
        "metrics": active_bundle.get("metrics", {}),
        "location": location,
        "disclaimer": (
            "Educational estimate of next-hour PM2.5 concentration, not an official AQI or health warning. "
            "Accuracy depends on the training region and input data source."
        ),
    }
    return result


def openmeteo_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not retrieve live data from Open-Meteo: {exc}") from exc


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "AirCast ML API", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if bundle is not None else "model_not_ready",
        "model_loaded": bundle is not None,
        "model_path": str(MODEL_PATH),
        "error": load_error,
        "model_dataset": bundle.get("dataset_name") if bundle else None,
        "training_region": bundle.get("training_region") if bundle else None,
    }


@app.get("/api/metrics")
def metrics() -> dict[str, Any]:
    active_bundle = require_model()
    return {
        "metrics": active_bundle.get("metrics", {}),
        "dataset_name": active_bundle.get("dataset_name"),
        "training_region": active_bundle.get("training_region"),
        "trained_at_utc": active_bundle.get("trained_at_utc"),
        "target": active_bundle.get("target"),
    }


@app.post("/api/predict")
def predict_manual(payload: ManualPrediction) -> dict[str, Any]:
    values = payload.model_dump()
    values["wd"] = values.pop("wind_direction_deg")
    timestamp = pd.Timestamp(year=2024, month=values.pop("month"), day=1, hour=values.pop("hour"))
    features = latest_feature_row(values, timestamp)
    return make_result(features, timestamp.isoformat(), "manual_observation", current_pm25=payload.pm25)


@app.get("/api/live-forecast")
def live_forecast(
    latitude: float = Query(39.9042, ge=-90, le=90),
    longitude: float = Query(116.4074, ge=-180, le=180),
) -> dict[str, Any]:
    """Fetch current Open-Meteo pollution/weather conditions and predict next-hour PM2.5."""
    common = {"latitude": latitude, "longitude": longitude, "timezone": "auto"}
    air = openmeteo_json(AIR_URL, {
        **common,
        "current": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone",
    })
    weather = openmeteo_json(WEATHER_URL, {
        **common,
        "current": "temperature_2m,surface_pressure,dew_point_2m,precipitation,wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "ms",
    })
    air_current = air.get("current") or {}
    weather_current = weather.get("current") or {}
    timestamp_text = weather_current.get("time") or air_current.get("time")
    if not timestamp_text:
        raise HTTPException(status_code=502, detail="Open-Meteo returned no current timestamp")
    ts = pd.to_datetime(timestamp_text, errors="coerce")
    if pd.isna(ts):
        raise HTTPException(status_code=502, detail="Open-Meteo returned an invalid timestamp")

    values = {
        "pm25": air_current.get("pm2_5"),
        "pm10": air_current.get("pm10"),
        "co": air_current.get("carbon_monoxide"),
        "no2": air_current.get("nitrogen_dioxide"),
        "so2": air_current.get("sulphur_dioxide"),
        "o3": air_current.get("ozone"),
        "temp": weather_current.get("temperature_2m"),
        "pres": weather_current.get("surface_pressure"),
        "dewp": weather_current.get("dew_point_2m"),
        "rain": weather_current.get("precipitation"),
        "wspm": weather_current.get("wind_speed_10m"),
        "wd": weather_current.get("wind_direction_10m"),
    }
    features = latest_feature_row(values, ts)
    current_pm25 = values.get("pm25")
    return make_result(
        features, str(timestamp_text), "Open-Meteo current conditions",
        location={"latitude": latitude, "longitude": longitude},
        current_pm25=float(current_pm25) if current_pm25 is not None else None,
    )

