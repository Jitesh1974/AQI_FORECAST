# Deploy the existing AirCast frontend to Vercel

This is the existing React + Vite frontend. It is configured to call the deployed FastAPI backend at:

`https://aqi-forecast-kappa.vercel.app`

## Deploy from the existing GitHub repository

1. Open Vercel and choose **Add New → Project**.
2. Import the GitHub repository that contains this project.
3. Set **Root Directory** to the folder containing this frontend's `package.json` (for the existing monorepo, this should be `air-quality-forecast/frontend`). If you uploaded this folder as the repository root, choose `./` instead.
4. Use these settings if Vercel does not detect them automatically:
   - Framework Preset: **Vite**
   - Build Command: `npm run build`
   - Output Directory: `dist`
   - Install Command: `npm install`
5. The tracked `.env.production` already points to the deployed backend. Alternatively, set the same value under **Project Settings → Environment Variables** as `VITE_API_BASE_URL`, scoped to Production (and Preview if desired).
6. Click **Deploy**.

## Test locally against the deployed backend (optional)

From this frontend directory, create a `.env.local` file with:

`VITE_API_BASE_URL=https://aqi-forecast-kappa.vercel.app`

Then run:

```bash
npm install
npm run dev
```

Open the local URL printed by Vite, usually `http://localhost:5173`.

## CORS note

The FastAPI backend must permit the final frontend origin. If the browser Console/Network tab reports a CORS error, add the deployed frontend domain (for example, `https://your-project.vercel.app`) to the `allow_origins` list in the FastAPI app's `CORSMiddleware`, commit that backend change, and redeploy the backend. Do not add a trailing slash to the origin. Keep `allow_credentials=False` unless the API genuinely uses browser cookies or credentials.

## Verification

After deployment, open the frontend URL, check the browser DevTools **Network** tab, and test **Predict next hour**. The frontend calls `/api/health`, `/api/metrics`, and `/api/live-forecast` on the configured backend. A successful `/api/health` response in Swagger alone does not prove that browser CORS is configured correctly.
