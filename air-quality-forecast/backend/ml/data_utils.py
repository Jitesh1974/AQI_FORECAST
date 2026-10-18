"""Data loading and feature construction for next-hour PM2.5 prediction."""
from __future__ import annotations

from pathlib import Path
import math
import re
import zipfile

import numpy as np
import pandas as pd
import requests

UCI_URL = "https://archive.ics.uci.edu/static/public/501/beijing+multi+site+air+quality+data.zip"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "uci"
FEATURE_COLUMNS = [
    "pm25", "pm10", "so2", "no2", "co", "o3", "temp", "pres", "dewp",
    "rain", "wspm", "hour", "month", "wind_sin", "wind_cos",
]
COLUMN_ALIASES = {
    "pm2.5": "pm25", "pm2_5": "pm25", "pm25": "pm25",
    "pm10": "pm10", "so2": "so2", "no2": "no2", "co": "co", "o3": "o3",
    "temp": "temp", "temperature_2m": "temp",
    "pres": "pres", "surface_pressure": "pres",
    "dewp": "dewp", "dew_point_2m": "dewp",
    "rain": "rain", "precipitation": "rain",
    "wspm": "wspm", "wind_speed_10m": "wspm",
    "wd": "wd", "wind_direction_10m": "wd",
    "timestamp": "time", "datetime": "time",
}
WIND_DEGREES = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90,
    "ESE": 112.5, "SE": 135, "SSE": 157.5, "S": 180,
    "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270,
    "WNW": 292.5, "NW": 315, "NNW": 337.5,
}


def download_uci_dataset(force: bool = False) -> Path:
    """Download and extract the UCI archive, including nested ZIP files."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    def station_csvs() -> list[Path]:
        return [path for path in RAW_DIR.rglob("*.csv")
                if path.name.lower().startswith("prsa_data_")]

    csvs = station_csvs()
    if csvs and not force:
        return RAW_DIR

    archive = RAW_DIR / "beijing_air_quality.zip"
    response = requests.get(UCI_URL, timeout=120,
                            headers={"User-Agent": "AirCast-ML/1.0"})
    response.raise_for_status()
    if not response.content.startswith(b"PK\x03\x04"):
        preview = response.text[:200].replace("\n", " ")
        raise RuntimeError(
            "The UCI download URL did not return a ZIP archive. "
            f"Response preview: {preview!r}. Check UCI_URL in data_utils.py."
        )
    archive.write_bytes(response.content)

    # Extract nested ZIP archives too; some mirrors wrap the dataset ZIP.
    pending = [archive]
    seen: set[Path] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            with zipfile.ZipFile(current) as zf:
                bad_member = zf.testzip()
                if bad_member:
                    raise RuntimeError(f"Corrupt ZIP member: {bad_member}")
                zf.extractall(current.parent)
        except zipfile.BadZipFile as exc:
            raise RuntimeError(f"Not a valid ZIP archive: {current}") from exc
        pending.extend(candidate for candidate in current.parent.rglob("*.zip")
                       if candidate not in seen)

    csvs = station_csvs()
    if not csvs:
        inventory = [str(path.relative_to(RAW_DIR)) for path in RAW_DIR.rglob("*")
                     if path.is_file()][:30]
        raise RuntimeError(
            "The UCI archive was extracted, but no PRSA_Data_*.csv station files "
            f"were found under {RAW_DIR}. Extracted files (first 30): {inventory}. "
            "Check the archive contents or update UCI_URL."
        )
    return RAW_DIR


def load_uci_dataset() -> pd.DataFrame:
    """Load and combine the 12 station CSVs from the official UCI dataset."""
    root = download_uci_dataset()
    files = sorted(root.rglob("PRSA_Data_*.csv"))
    if not files:
        raise FileNotFoundError("UCI station CSV files are missing; run the dataset downloader first.")
    frames = []
    for path in files:
        frame = pd.read_csv(path)
        # Station name is also embedded in each official filename.
        match = re.search(r"PRSA_Data_(.+?)_20130301", path.name)
        if "station" not in frame.columns and match:
            frame["station"] = match.group(1)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize UCI CSVs and Open-Meteo collector CSVs to one schema."""
    out = df.copy()
    renamed = {}
    for col in out.columns:
        key = str(col).strip().lower().replace(" ", "")
        if key in COLUMN_ALIASES:
            renamed[col] = COLUMN_ALIASES[key]
    out = out.rename(columns=renamed)

    if "time" not in out.columns:
        if not {"year", "month", "day", "hour"}.issubset(out.columns):
            raise ValueError("Input data needs a 'time' column or year/month/day/hour columns.")
        out["time"] = pd.to_datetime(
            out[["year", "month", "day", "hour"]], errors="coerce"
        )
    else:
        out["time"] = pd.to_datetime(out["time"], errors="coerce")

    if "station" not in out.columns:
        out["station"] = "single_location"

    if "wd" in out.columns:
        wind_text = out["wd"].astype("string").str.upper().str.strip()
        wind_as_degrees = wind_text.map(WIND_DEGREES)
        numeric_wind = pd.to_numeric(out["wd"], errors="coerce")
        out["wd_degrees"] = numeric_wind.fillna(wind_as_degrees)
    else:
        out["wd_degrees"] = np.nan

    required = ["pm25", "pm10", "so2", "no2", "co", "o3", "temp", "pres", "dewp", "rain", "wspm"]
    for col in required:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["hour"] = out["time"].dt.hour
    out["month"] = out["time"].dt.month
    radians = np.deg2rad(out["wd_degrees"])
    out["wind_sin"] = np.sin(radians)
    out["wind_cos"] = np.cos(radians)
    out = out.dropna(subset=["time", "pm25"])
    return out.sort_values(["station", "time"]).reset_index(drop=True)


def make_training_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Build one-step-ahead samples and discard gaps larger than one hour."""
    clean = standardize_columns(df)
    clean["target_pm25"] = clean.groupby("station", sort=False)["pm25"].shift(-1)
    clean["target_time"] = clean.groupby("station", sort=False)["time"].shift(-1)
    gap = clean["target_time"] - clean["time"]
    clean = clean.loc[(gap == pd.Timedelta(hours=1)) & clean["target_pm25"].notna()].copy()
    if len(clean) < 100:
        raise ValueError(
            f"Only {len(clean)} valid one-hour samples were created. At least 100 are required; "
            "collect more history or check the input CSV."
        )
    X = clean[FEATURE_COLUMNS].astype(float)
    y = clean["target_pm25"].astype(float)
    target_time = clean["target_time"]
    return X, y, target_time


def latest_feature_row(values: dict, timestamp: pd.Timestamp | None = None) -> pd.DataFrame:
    """Convert current pollutant/weather measurements into the training feature schema."""
    ts = timestamp if timestamp is not None else pd.Timestamp.now()
    wd = values.get("wd")
    if wd is None or pd.isna(wd):
        wind_sin = wind_cos = np.nan
    else:
        radians = math.radians(float(wd))
        wind_sin, wind_cos = math.sin(radians), math.cos(radians)
    row = {
        "pm25": values.get("pm25"), "pm10": values.get("pm10"),
        "so2": values.get("so2"), "no2": values.get("no2"),
        "co": values.get("co"), "o3": values.get("o3"),
        "temp": values.get("temp"), "pres": values.get("pres"),
        "dewp": values.get("dewp"), "rain": values.get("rain"),
        "wspm": values.get("wspm"), "hour": ts.hour, "month": ts.month,
        "wind_sin": wind_sin, "wind_cos": wind_cos,
    }
    return pd.DataFrame([row], columns=FEATURE_COLUMNS).astype(float)
