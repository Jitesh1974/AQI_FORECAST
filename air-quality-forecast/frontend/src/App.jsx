import { useEffect, useMemo, useState } from 'react';
import { Activity, ArrowDownRight, ArrowUpRight, CalendarClock, CheckCircle2, Cloud, Database, Gauge, MapPin, RefreshCw, ShieldAlert, Wind } from 'lucide-react';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const DEFAULT_LAT = '39.9042';
const DEFAULT_LON = '116.4074';

function fmt(value, digits = 2) {
  return value === null || value === undefined || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);
}
function formatTime(value) {
  if (!value) return 'Next hour';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || `Request failed (${response.status})`);
  return body;
}

export default function App() {
  const [latitude, setLatitude] = useState(DEFAULT_LAT);
  const [longitude, setLongitude] = useState(DEFAULT_LON);
  const [forecast, setForecast] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);

  const ready = health?.model_loaded === true;
  const change = useMemo(() => {
    if (forecast?.current_pm25_ug_m3 == null || forecast?.predicted_pm25_ug_m3 == null) return null;
    return forecast.predicted_pm25_ug_m3 - forecast.current_pm25_ug_m3;
  }, [forecast]);

  async function loadStatus() {
    try {
      const h = await apiGet('/api/health');
      setHealth(h);
      if (h.model_loaded) {
        const m = await apiGet('/api/metrics');
        setMetrics(m);
      }
    } catch (e) {
      setHealth({ model_loaded: false, status: 'api_unavailable', error: e.message });
    }
  }

  async function runForecast(event) {
    event?.preventDefault();
    setError('');
    setLoading(true);
    try {
      const lat = Number(latitude);
      const lon = Number(longitude);
      if (!Number.isFinite(lat) || lat < -90 || lat > 90) throw new Error('Latitude must be between -90 and 90.');
      if (!Number.isFinite(lon) || lon < -180 || lon > 180) throw new Error('Longitude must be between -180 and 180.');
      const data = await apiGet(`/api/live-forecast?latitude=${encodeURIComponent(lat)}&longitude=${encodeURIComponent(lon)}`);
      setForecast(data);
      setLastUpdated(new Date());
      setHealth((prev) => ({ ...(prev || {}), model_loaded: true, status: 'ok' }));
      setMetrics({ metrics: data.metrics, dataset_name: data.model_dataset, training_region: data.model_training_region });
    } catch (e) {
      setError(e.message || 'Unable to load the forecast. Check the backend and internet connection.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadStatus(); }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="AirCast home">
          <span className="brand-mark"><Wind size={21} strokeWidth={2.2} /></span>
          <span>AIR<span className="brand-light">CAST</span><small>ENVIRONMENTAL INTELLIGENCE</small></span>
        </a>
        <div className="top-meta"><span className={`status-dot ${ready ? 'online' : ''}`} />{ready ? 'ML service ready' : 'Connecting to ML service'}</div>
      </header>

      <main id="top" className="main-content">
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow"><Activity size={14} /> MACHINE LEARNING · REGRESSION</div>
            <h1>See the air<br /><span>one hour ahead.</span></h1>
            <p className="hero-subtitle">A next-hour PM2.5 estimate powered by a trained machine learning model and live weather / air-quality inputs.</p>
            <div className="hero-tags"><span><Database size={14} /> Reproducible pipeline</span><span><Gauge size={14} /> Regression model</span></div>
          </div>
          <div className="hero-art" aria-hidden="true">
            <div className="orb orb-one" /><div className="orb orb-two" /><div className="orb orb-three" />
            <div className="air-lines"><i /><i /><i /><i /><i /><i /><i /></div>
            <div className="hero-readout"><span>PM2.5 · μg/m³</span><strong>{forecast ? fmt(forecast.predicted_pm25_ug_m3, 1) : '—'}</strong><small>PROJECTED NEXT HOUR</small></div>
          </div>
        </section>

        <section className="control-card">
          <div className="section-heading">
            <div><span className="step-number">01</span><h2>Choose a location</h2></div>
            <p>Pull current conditions and generate a prediction.</p>
          </div>
          <form className="location-form" onSubmit={runForecast}>
            <label><span><MapPin size={15} /> Latitude</span><input value={latitude} onChange={(e) => setLatitude(e.target.value)} inputMode="decimal" required aria-label="Latitude" /></label>
            <label><span><MapPin size={15} /> Longitude</span><input value={longitude} onChange={(e) => setLongitude(e.target.value)} inputMode="decimal" required aria-label="Longitude" /></label>
            <button className="primary-button" type="submit" disabled={loading || !ready}>
              {loading ? <><RefreshCw className="spin" size={17} /> Working…</> : <><Activity size={17} /> Predict next hour</>}
            </button>
          </form>
          <div className="coordinate-hint">Default coordinates: Beijing, China — the region represented in the included training dataset.</div>
          {!ready && <div className="inline-warning"><ShieldAlert size={16} /><span>{health?.error || 'Model is not ready. Train the model using the README instructions, then start the backend.'}</span></div>}
          {error && <div className="error-banner"><ShieldAlert size={17} /><span>{error}</span></div>}
        </section>

        <section className="results-section">
          <div className="section-heading results-heading">
            <div><span className="step-number">02</span><h2>Forecast overview</h2></div>
            <span className="updated-label">{lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'Waiting for first prediction'}</span>
          </div>
          <div className="result-grid">
            <article className="metric-card forecast-card">
              <div className="metric-top"><span>Predicted PM2.5</span><span className="metric-icon"><Activity size={17} /></span></div>
              <div className="metric-value">{fmt(forecast?.predicted_pm25_ug_m3, 1)} <small>μg/m³</small></div>
              <div className="metric-footer"><CalendarClock size={14} /><span>{forecast ? formatTime(forecast.forecast_for) : 'Next-hour estimate appears here'}</span></div>
            </article>
            <article className="metric-card">
              <div className="metric-top"><span>Current PM2.5</span><span className="metric-icon muted"><Cloud size={17} /></span></div>
              <div className="metric-value">{fmt(forecast?.current_pm25_ug_m3, 1)} <small>μg/m³</small></div>
              <div className="metric-footer"><Wind size={14} /><span>Open-Meteo current condition</span></div>
            </article>
            <article className="metric-card">
              <div className="metric-top"><span>Expected change</span><span className={`metric-icon ${change !== null && change > 0 ? 'rise' : 'fall'}`}>{change !== null && change > 0 ? <ArrowUpRight size={17} /> : <ArrowDownRight size={17} />}</span></div>
              <div className="metric-value">{change === null ? '—' : `${change > 0 ? '+' : ''}${fmt(change, 1)}`} <small>μg/m³</small></div>
              <div className="metric-footer"><Activity size={14} /><span>Forecast minus current value</span></div>
            </article>
          </div>
        </section>

        <section className="details-grid">
          <article className="detail-card">
            <div className="detail-title"><Database size={17} /><h3>Model & evaluation</h3></div>
            <div className="detail-row"><span>Training dataset</span><strong>{metrics?.dataset_name || 'Not loaded'}</strong></div>
            <div className="detail-row"><span>Training region</span><strong>{metrics?.training_region || health?.training_region || '—'}</strong></div>
            <div className="metric-trio">
              <div><span>MAE</span><strong>{fmt(metrics?.metrics?.mae, 2)}</strong><small>μg/m³</small></div>
              <div><span>RMSE</span><strong>{fmt(metrics?.metrics?.rmse, 2)}</strong><small>μg/m³</small></div>
              <div><span>R²</span><strong>{fmt(metrics?.metrics?.r2, 3)}</strong><small>test split</small></div>
            </div>
            <p className="mini-note">Metrics are calculated on a chronological hold-out set during training. They are not a guarantee of accuracy for a different region or data provider.</p>
          </article>
          <article className="detail-card pipeline-card">
            <div className="detail-title"><CheckCircle2 size={17} /><h3>Pipeline status</h3></div>
            <div className="pipeline-step done"><span>01</span><div><strong>Data collection</strong><small>UCI station data / Open-Meteo input</small></div><CheckCircle2 size={16} /></div>
            <div className="pipeline-step done"><span>02</span><div><strong>Preprocessing & features</strong><small>Missing-value imputation, wind encoding, time features</small></div><CheckCircle2 size={16} /></div>
            <div className={`pipeline-step ${ready ? 'done' : ''}`}><span>03</span><div><strong>Model serving</strong><small>FastAPI prediction endpoint</small></div>{ready ? <CheckCircle2 size={16} /> : <span className="pending-dot" />}</div>
            <div className="pipeline-step"><span>04</span><div><strong>Monitoring & retraining</strong><small>Recollect data and retrain when appropriate</small></div><span className="pending-dot" /></div>
          </article>
        </section>

        <section className="notice"><ShieldAlert size={18} /><div><strong>Important limitation</strong><p>The included model is trained on historical observations from Beijing (2013–2017). Live inputs for another city can have a substantial data-distribution shift. For a local deployment, collect location-specific history with the included collector and retrain the model. This project is educational; it is not an official AQI service or a substitute for government pollution alerts.</p></div></section>
      </main>

      <footer className="footer"><span> AIRCAST / END-TO-END ML PIPELINE</span><span>Python 3.10 · FastAPI · Scikit-learn · React</span></footer>
    </div>
  );
}
