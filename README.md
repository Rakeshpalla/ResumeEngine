# ResumeEngine (JobCraft)

AI-assisted job search and tailored resume generation.

## Project layout

- **`jobcraft/backend`** — FastAPI API, scrapers, resume logic  
- **`jobcraft/frontend`** — React + Vite UI  

## Quick start

1. Copy `jobcraft/.env.example` to `jobcraft/.env` and set your keys.  
2. Backend: from `jobcraft/backend`, create a venv, install `requirements.txt`, run `uvicorn main:app --reload --host 127.0.0.1 --port 8080`.  
3. Frontend: from `jobcraft/frontend`, `npm install` and `npm run dev` (proxies `/api` to port 8080).  

See `jobcraft/.gitignore` for paths excluded from version control (data, `.env`, venv).

## Production (Vercel + API)

- **Frontend:** deploy `jobcraft/frontend` to [Vercel](https://vercel.com); set `VITE_API_BASE_URL` to your hosted API (e.g. `https://your-api.example.com/api`).  
- **Backend:** host FastAPI separately (Railway, Render, Fly, VPS)—see **[DEPLOY.md](./DEPLOY.md)** for steps and CORS.
