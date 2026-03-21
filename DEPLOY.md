# Deploy JobCraft to production

The **React app** fits [Vercel](https://vercel.com) well. The **Python API** (FastAPI, SQLite, Playwright scrapers, file uploads) is **not** a good fit for Vercel serverless—host it on a **container / VM** service instead.

## 1. Deploy the frontend on Vercel

1. Push this repo to GitHub (already done for [ResumeEngine](https://github.com/Rakeshpalla/ResumeEngine)).
2. In Vercel: **Add New Project** → import **ResumeEngine**.
3. **Root Directory:** `jobcraft/frontend`
4. **Framework Preset:** Vite (auto-detected).
5. **Environment Variables** (Production + Preview):
   - `VITE_API_BASE_URL` = your public API base, **must include `/api`**  
     Example: `https://your-backend.example.com/api`
6. Deploy.

`jobcraft/frontend/vercel.json` adds SPA rewrites so React Router works on refresh.

## 2. Deploy the backend (choose one)

Run the FastAPI app with **persistent disk** (for `data/`, SQLite, uploads) and **enough RAM** for Playwright if you use browser scrapers.

| Platform | Notes |
|----------|--------|
| [Railway](https://railway.app) | Dockerfile or `nixpacks`, attach volume for `/app/data` |
| [Render](https://render.com) | Web Service + disk |
| [Fly.io](https://fly.io) | `fly.toml` + volume |
| VPS (DigitalOcean, etc.) | Docker + reverse proxy (Caddy/nginx) |

Minimum backend settings:

- Start command (example):  
  `uvicorn main:app --host 0.0.0.0 --port $PORT`  
  (use the port your host injects, e.g. Railway’s `PORT`).
- Set all secrets from `jobcraft/.env.example` on the host (not in Git).
- **`CORS_ORIGINS`**: comma-separated list including your Vercel URL(s), e.g.  
  `https://your-app.vercel.app,https://your-domain.com`

Example:

```env
CORS_ORIGINS=https://resume-engine.vercel.app,https://jobcraft.example.com
SECRET_KEY=your-long-random-secret
```

## 3. Smoke test

1. Open the Vercel URL → login should call `https://your-api/.../api/...` (check browser Network tab).
2. If you see CORS errors, fix `CORS_ORIGINS` on the backend and redeploy the API.

## Why not put the API on Vercel?

- Long-running job scrapes exceed typical serverless timeouts.
- SQLite and local `data/` need a **persistent filesystem** (one container/process), not ephemeral serverless disks.
- Playwright is heavy and often blocked on serverless runtimes.

If you later move the DB to Postgres and drop Playwright for API-only scrapers, you could explore splitting the API—but the current architecture is **frontend on Vercel + API elsewhere**.
