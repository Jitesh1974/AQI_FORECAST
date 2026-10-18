# AirCast — End-to-End PM2.5 Forecasting ML Pipeline

A full-stack educational project that predicts **PM2.5 concentration one hour ahead**. It includes data download, preprocessing, chronological model evaluation, model artifact versioning, a FastAPI inference service, a React dashboard, optional location-specific data collection, Docker deployment, and basic API health/metrics endpoints.

> **Important limitation:** the default model is trained on the UCI Beijing Multi-Site Air Quality dataset (12 Beijing stations, March 2013–February 2017). Its validation metrics do not establish accuracy in India or any other city. For a city-specific demonstration, use the Open-Meteo history collector and retrain with the location you want to explore. Open-Meteo historical/reanalysis values are model-derived estimates, not ground-monitor observations. This app is not an official AQI service or a health-warning system.

## 1. Dataset

**Primary training dataset — UCI Beijing Multi-Site Air Quality**

- Dataset page and official download: https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality
- DOI: https://doi.org/10.24432/C5RK5G
- License: Creative Commons Attribution 4.0 International (CC BY 4.0).
- Content: 420,768 hourly records from 12 monitoring sites, with PM2.5, PM10, SO2, NO2, CO, O3, temperature, pressure, dew point, precipitation, wind direction and wind speed; missing values are present.
- Attribution: Chen, S. (2017). *Beijing Multi-Site Air Quality*. UCI Machine Learning Repository. https://doi.org/10.24432/C5RK5G.

The downloader fetches the archive from UCI on the first run; you do not need to manually download/unzip it. The dataset is not bundled in this source ZIP.

**Optional recent-location data collector**

The included collector fetches up to 92 days of hourly pollutant and weather fields from Open-Meteo:

- Air Quality API: https://open-meteo.com/en/docs/air-quality-api
- Weather Forecast API: https://open-meteo.com/en/docs

It merges the time series and saves a CSV for local retraining. Check the API's terms and attribution requirements for your intended use.

## 2. Project structure

```text
air-quality-forecast/
├── backend/
│   ├── app/main.py             # FastAPI health, metrics, live and manual prediction endpoints
│   ├── ml/data_utils.py        # UCI downloader, standardization and feature engineering
│   ├── ml/download_data.py     # data acquisition command
│   ├── ml/collect_openmeteo.py # optional location-specific collection
│   ├── ml/train.py             # chronological training/evaluation and joblib artifact
│   ├── requirements.txt        # Python 3.10 dependencies
│   └── artifacts/              # trained model is generated here
├── frontend/                   # React + Vite UI (Nginx in Docker)
├── data/                       # downloaded and collected data
├── docker-compose.yml
└── README.md
```

## 3. Local setup (Python 3.10)

Run commands from the extracted project root. On Windows PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
python -m backend.ml.download_data
python -m backend.ml.train
```

The first training run downloads the official UCI archive, combines the station CSV files, builds one-hour-ahead examples, performs a chronological 80/20 hold-out split, fits a `HistGradientBoostingRegressor`, calculates MAE/RMSE/R², and writes:

- `backend/artifacts/model.joblib`
- `backend/artifacts/metrics.json`

Do not use a random train/test split for this time-series task; it can leak temporal patterns between train and test sets.

### Start the backend

In one terminal, from the project root with the virtual environment activated:

```powershell
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify:

- API health: http://127.0.0.1:8000/api/health
- Training metrics: http://127.0.0.1:8000/api/metrics
- Interactive API docs: http://127.0.0.1:8000/docs

### Start the frontend

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` requests to `http://127.0.0.1:8000` by default. To use another local backend URL, set `VITE_DEV_API_TARGET` before starting Vite.

The dashboard defaults to Beijing coordinates to match the training region. Enter another latitude/longitude to fetch current Open-Meteo conditions. A geographically different region can cause major data-distribution shift; see the next section before interpreting those results.

## 4. Optional: collect data for a location and retrain

Example for Mumbai, India (latitude 19.0760, longitude 72.8777):

```powershell
python -m backend.ml.collect_openmeteo --lat 19.0760 --lon 72.8777 --days 90 --output data/mumbai_history.csv
python -m backend.ml.train --csv data/mumbai_history.csv --region "Mumbai, India (Open-Meteo/CAMS model-derived history)"
```

Restart the API process after training so the new artifact is loaded:

```powershell
# Stop the running uvicorn process with Ctrl+C, then run again
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

This supports a reproducible *location-specific demonstration*, but the data are model-derived and not independent ground truth. If you can obtain official/local monitor data, train and evaluate against those observations before claiming local accuracy. Aim for a longer history and validate on a later untouched time window for serious use.

## 5. Permanent backend deployment without Docker (Render)

This repository includes a Render Blueprint (`render.yaml`) configured for Render's native Python runtime, not Docker. The paid Starter web service is intended to stay running instead of sleeping on idle. Render currently lists the Starter service at $7/month; confirm the current price before deploying. Free web services spin down after 15 minutes without incoming traffic and have an ephemeral filesystem, so they are not suitable if you require an always-on API.

1. Push the entire project folder to a GitHub repository. Keep the repository root as the deploy root; do not set the service root directory to `backend`, because imports use the `backend.ml` package path.
2. In Render, choose **New → Blueprint** and connect the GitHub repository containing `render.yaml`, or choose **New → Web Service** and use the settings below.
3. For a manual Web Service, set **Runtime/Language** to **Python 3** (not Docker), **Root Directory** to blank/repository root, **Build Command** to `pip install -r backend/requirements.txt && python -m backend.ml.download_data && python -m backend.ml.train`, and **Start Command** to `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`. Set the plan to a paid always-on plan, such as Starter. The `.python-version` file pins Python 3.10.14.
4. The build command downloads the UCI data and creates `backend/artifacts/model.joblib` and `metrics.json` during deployment. Wait for the build and service to finish, then open `https://YOUR-SERVICE.onrender.com/api/health`; `model_loaded` should be `true`. Check `https://YOUR-SERVICE.onrender.com/docs` for the API schema.
5. If the React frontend is deployed separately, set the backend environment variable `FRONTEND_ORIGINS` to the exact frontend origin, for example `https://your-frontend-name.onrender.com` (no trailing slash). Multiple origins can be separated by commas. Redeploy after changing the variable. Then set the frontend's `VITE_API_BASE_URL` to `https://YOUR-SERVICE.onrender.com` when building the frontend.
6. After the first successful deploy, enable/verify automatic deploys from your chosen Git branch. Render builds the service from the repository when you push code changes. The API is publicly available as long as the paid service remains active and in good standing; no hosting provider can guarantee literal permanence.

**Deployment notes:** The model file is deliberately generated in the build step because generated artifacts are excluded from Git. Each new deploy retrains the model from the default Beijing dataset. For a Mumbai-specific model, change the build workflow to use a checked-in/externally stored local dataset and run the collector/training commands; do not assume the Beijing model is accurate for India.

## 6. Docker deployment (optional)

First train a model as above so `backend/artifacts/model.joblib` exists. Then, from the project root:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f backend
```

Open the frontend at http://localhost:5173 and the API docs at http://localhost:8000/docs. The frontend Nginx container proxies API requests to the backend service within the Compose network. To stop:

```powershell
docker compose down
```

For a public deployment, use HTTPS, configure a restricted `FRONTEND_ORIGINS`, avoid exposing development/debug endpoints, and store generated model/data artifacts using your deployment platform's persistent artifact storage. Do not publish private datasets or credentials in the image.

## 7. API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | API/model readiness and model metadata |
| `GET` | `/api/metrics` | Held-out MAE, RMSE, R², training region and target |
| `GET` | `/api/live-forecast?latitude=39.9042&longitude=116.4074` | Fetch current Open-Meteo air and weather conditions; predict PM2.5 for roughly one hour later |
| `POST` | `/api/predict` | Predict from manually supplied current measurements |
| `GET` | `/docs` | Swagger UI |

Example manual prediction body:

```json
{
  "pm25": 35.0,
  "pm10": 60.0,
  "so2": 4.0,
  "no2": 22.0,
  "co": 450.0,
  "o3": 30.0,
  "temp": 28.0,
  "pres": 1008.0,
  "dewp": 20.0,
  "rain": 0.0,
  "wspm": 1.5,
  "wind_direction_deg": 180.0,
  "hour": 14,
  "month": 10
}
```

Units: PM2.5/PM10/SO2/NO2/CO/O3 are µg/m³; temperature/dew point are °C; pressure is hPa; rain is mm; wind speed is m/s; wind direction is degrees.

## 8. What the pipeline does

1. **Ingest:** download the UCI archive or collect location-specific history through Open-Meteo.
2. **Validate/clean:** normalize schema, parse timestamps, and remove rows that cannot form a one-hour target.
3. **Engineer features:** use current pollutant/weather readings, hour/month, and sine/cosine wind-direction features.
4. **Prevent temporal leakage:** pair each row with the next hourly PM2.5 value at the same station; only retain consecutive-hour pairs.
5. **Train/evaluate:** chronological hold-out set with MAE, RMSE and R². The imputer and regressor are persisted together.
6. **Serve:** FastAPI loads the saved pipeline and provides prediction, health and model-metrics endpoints.
7. **Display/deploy:** React dashboard; Docker Compose starts the API and Nginx-served frontend.

## 9. Responsible interpretation

- A next-hour **PM2.5 concentration estimate is not the same as AQI**.
- API model estimates and Beijing monitor observations come from different data sources; performance may be poor under distribution shift.
- MAE/RMSE/R² measure a historical hold-out set only, not guaranteed future performance.
- For stronger MLOps, add scheduled collection, data drift checks, alerts, model registry, model-quality gates and repeatable automated deployment.
