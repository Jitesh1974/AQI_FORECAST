"""Collect recent location-specific hourly pollution/weather history from Open-Meteo."""
from __future__ import annotations
import argparse
from pathlib import Path
import requests
import pandas as pd

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


def get_json(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=90)
    response.raise_for_status()
    data = response.json()
    if "hourly" not in data or "time" not in data["hourly"]:
        raise RuntimeError(f"The upstream API returned no hourly data: {data}")
    return data


def collect(latitude: float, longitude: float, days: int, output: Path) -> Path:
    if not 1 <= days <= 92:
        raise ValueError("days must be between 1 and 92")
    common = {"latitude": latitude, "longitude": longitude, "past_days": days,
              "forecast_days": 0, "timezone": "auto"}
    air = get_json(AIR_URL, {**common, "hourly": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone"})
    weather = get_json(WEATHER_URL, {**common,
        "hourly": "temperature_2m,surface_pressure,dew_point_2m,precipitation,wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "ms"})
    a = pd.DataFrame(air["hourly"]).rename(columns={
        "pm2_5": "pm25", "carbon_monoxide": "co", "nitrogen_dioxide": "no2",
        "sulphur_dioxide": "so2", "ozone": "o3"})
    w = pd.DataFrame(weather["hourly"]).rename(columns={
        "temperature_2m": "temp", "surface_pressure": "pres", "dew_point_2m": "dewp",
        "precipitation": "rain", "wind_speed_10m": "wspm", "wind_direction_10m": "wd"})
    if "time" not in a or "time" not in w:
        raise RuntimeError("Upstream API schemas changed; expected hourly time fields.")
    merged = a.merge(w, on="time", how="inner").drop_duplicates(subset=["time"]).sort_values("time")
    merged["station"] = f"openmeteo_{latitude:.4f}_{longitude:.4f}"
    output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output, index=False)
    print(f"Saved {len(merged):,} merged hourly records to {output}")
    print("Source note: Open-Meteo/CAMS values are model/reanalysis data, not direct ground-monitor observations.")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, required=True, help="Latitude, e.g. 19.0760 for Mumbai")
    parser.add_argument("--lon", type=float, required=True, help="Longitude, e.g. 72.8777 for Mumbai")
    parser.add_argument("--days", type=int, default=90, help="History window, 1 to 92 days")
    parser.add_argument("--output", type=Path, default=Path("data/local_history.csv"))
    args = parser.parse_args()
    collect(args.lat, args.lon, args.days, args.output)
