"""
Application configuration — loads all settings from .env file.
Never hardcode secrets; they all come from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# --- Paths ---
DATA_DIR = BASE_DIR / "data"
RESUMES_BASE_DIR = DATA_DIR / "resumes" / "base"
RESUMES_TAILORED_DIR = DATA_DIR / "resumes" / "tailored"
JOBS_DIR = DATA_DIR / "jobs"
DATABASE_PATH = DATA_DIR / "jobcraft.db"

# --- Security ---
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-before-production-use")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

# --- AI: Google Gemini (FREE — no credit card) or Anthropic Claude ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# NOTE: Google periodically deprecates model IDs. Use a "latest" alias by default.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# --- AI: OpenAI (paid API, strong resume quality) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
# Cost-friendly default; override with gpt-4o, gpt-4-turbo, etc. in .env
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

# --- AI: Ollama (local, unlimited) ---
# Provider selection:
# - "openai": OpenAI only (set OPENAI_API_KEY)
# - "ollama": use local Ollama only (no cloud keys needed)
# - "auto": try OpenAI (if OPENAI_API_KEY), else Gemini (if GEMINI_API_KEY), else Ollama
# - "gemini": force Gemini
# - "claude": force Claude
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1").strip()
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

# --- Default Admin Account (created on first run) ---
DEFAULT_USERNAME = os.getenv("DEFAULT_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD", "jobcraft2024")

# --- Scraper Limits ---
MAX_JOBS_PER_PORTAL = 10
SCRAPE_COOLDOWN_SECONDS = 60  # 1 minute between scraping runs (dev-friendly)
REQUEST_DELAY_MIN = 2  # seconds
REQUEST_DELAY_MAX = 5

# --- Resume Generation Limits ---
# To keep runtime reasonable, we scrape more jobs but only tailor/score the
# best-aligned subset per portal.
TOP_JOBS_PER_PORTAL_FOR_TAILORING = 5
# "Perfect alignment" is approximated using a fast ATS keyword overlap score
# (based on the raw JD + the user's base resume). If fewer than N match this
# threshold, we still take the top N by ATS score.
PERFECT_ALIGNMENT_MIN_ATS_SCORE = 60.0

# --- Agent Run Lock Safety ---
# If an agent run stays in "running/pending" for too long (crash, stuck model call, etc),
# allow a new run after this timeout.
AGENT_RUN_STALE_SECONDS = 600  # 10 minutes (prevents "already running" lock forever)

# --- File Upload Limits ---
MAX_UPLOAD_SIZE_MB = 5
ALLOWED_EXTENSIONS = {".pdf", ".docx"}

# --- CORS ---
# Comma-separated extra origins (e.g. your Vercel preview/production URLs)
_cors_extra = os.getenv("CORS_ORIGINS", "").strip()
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
if _cors_extra:
    CORS_ORIGINS.extend(
        [o.strip() for o in _cors_extra.split(",") if o.strip() and o.strip() not in CORS_ORIGINS]
    )
