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
