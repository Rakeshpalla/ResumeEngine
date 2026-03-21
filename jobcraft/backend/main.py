"""
FastAPI application entry point — all REST API routes.
Handles auth, resume upload, job search orchestration, and settings.
"""

import asyncio
import datetime
import uuid
import logging
import time
import functools
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from logging.handlers import RotatingFileHandler

from fastapi import (
    FastAPI, Depends, HTTPException, UploadFile, File,
    Query, status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import engine, get_db, Base
from models import User, UserSettings, SearchRun, Job
from auth import (
    LoginRequest, TokenResponse,
    hash_password, authenticate_user, create_access_token, get_current_user,
)
from config import (
    CORS_ORIGINS, RESUMES_BASE_DIR, MAX_UPLOAD_SIZE_MB,
    ALLOWED_EXTENSIONS, DEFAULT_USERNAME, DEFAULT_PASSWORD,
    SCRAPE_COOLDOWN_SECONDS, GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, AI_PROVIDER, DATA_DIR,
    TOP_JOBS_PER_PORTAL_FOR_TAILORING, PERFECT_ALIGNMENT_MIN_ATS_SCORE,
    AGENT_RUN_STALE_SECONDS,
)
from resume_parser import parse_resume
from scraper import run_scraper
from tailor import tailor_resume
from scorer import score_job, compute_ats_score
from resume_generator import generate_pdf, generate_docx

# Console + file logging for easier debugging and post-mortem analysis.
log_dir = DATA_DIR / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "backend.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"),
    ],
    force=True,
)
logger = logging.getLogger(__name__)

# --- Create tables on startup ---
Base.metadata.create_all(bind=engine)

app = FastAPI(title="JobCraft API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory status store for the currently running search agent
_agent_status = {
    "running": False,
    "run_id": None,
    "progress": 0,
    "messages": [],
}


# ─────────────────────────── Startup Event ───────────────────────────

@app.on_event("startup")
def create_default_user():
    """Ensure a default admin account exists on first launch."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == DEFAULT_USERNAME).first()
        if not existing:
            user = User(
                username=DEFAULT_USERNAME,
                hashed_password=hash_password(DEFAULT_PASSWORD),
            )
            db.add(user)
            db.flush()
            settings = UserSettings(user_id=user.id, portals=["linkedin", "indeed"])
            db.add(settings)
            db.commit()
            logger.info(f"Default user '{DEFAULT_USERNAME}' created.")
    finally:
        db.close()


# ─────────────────────────── Pydantic Schemas ───────────────────────────

class SearchStartRequest(BaseModel):
    titles: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    portals: List[str] = Field(default_factory=list)

class SettingsUpdate(BaseModel):
    target_titles: Optional[List[str]] = None
    preferred_locations: Optional[List[str]] = None
    portals: Optional[List[str]] = None
    years_of_experience: Optional[str] = None
    anthropic_api_key: Optional[str] = None


class ProcessSelectionRequest(BaseModel):
    job_ids: List[int] = Field(default_factory=list)

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ─────────────────────────── Auth Routes ───────────────────────────

@app.post("/api/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token({"sub": user.username})
    return TokenResponse(access_token=token)


@app.post("/api/auth/logout")
def logout():
    return {"message": "Logged out (client should discard the token)"}


@app.post("/api/auth/change-password")
def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from auth import verify_password
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


# ─────────────────────────── Resume Upload ───────────────────────────

@app.post("/api/resume/upload")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Only PDF and DOCX files are allowed. Got: {ext}")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File too large. Max {MAX_UPLOAD_SIZE_MB}MB.")

    safe_name = f"{uuid.uuid4().hex}{ext}"
    RESUMES_BASE_DIR.mkdir(parents=True, exist_ok=True)
    save_path = RESUMES_BASE_DIR / safe_name
    save_path.write_bytes(contents)

    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
    settings.base_resume_filename = safe_name
    db.commit()

    return {"filename": safe_name, "size": len(contents), "message": "Resume uploaded successfully"}


@app.get("/api/resume/current")
def get_current_resume(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings or not settings.base_resume_filename:
        return {"has_resume": False}
    file_path = RESUMES_BASE_DIR / settings.base_resume_filename
    return {
        "has_resume": file_path.exists(),
        "filename": settings.base_resume_filename,
    }


# ─────────────────────────── Search / Agent ───────────────────────────

async def _run_agent(run_id: int, user_id: int, titles, locations, portals, api_key: str):
    """
    Background task: scrape jobs → tailor resumes → score → save to DB.
    Updates _agent_status in real-time for the polling endpoint.
    """
    from database import SessionLocal
    db = SessionLocal()
    loop = asyncio.get_running_loop()
    ai_executor = ThreadPoolExecutor(max_workers=2)

    async def update_status(msg: str):
        _agent_status["messages"].append(msg)
        logger.info(msg)
        # Avoid the UI looking "stuck at 10%" while scraping.
        # During scraping, we only jump to 40% once scraping completes.
        # These heuristics move the progress bar while portal searches run.
        try:
            msg_l = (msg or "").lower()
            cur = _agent_status.get("progress", 0)

            # Keep progress moving as soon as we start portal searches.
            if "searching" in msg_l and cur <= 10:
                _agent_status["progress"] = max(cur, 15)

            # Portal-specific nudges (helps the user trust the UI).
            if "searching" in msg_l and "linkedin" in msg_l:
                _agent_status["progress"] = max(_agent_status.get("progress", 0), 25)
            if "found" in msg_l and "linkedin" in msg_l:
                _agent_status["progress"] = max(_agent_status.get("progress", 0), 28)

            if "searching" in msg_l and "indeed" in msg_l:
                _agent_status["progress"] = max(_agent_status.get("progress", 0), 32)
            if "found" in msg_l and "indeed" in msg_l:
                _agent_status["progress"] = max(_agent_status.get("progress", 0), 38)
        except Exception:
            pass

        # Persist latest progress + message to DB so UI never depends solely on
        # in-memory state (prevents "stuck at 10%" / "already running" desync).
        try:
            run.status_message = msg
            run.progress = int(_agent_status.get("progress", 0))
            db.commit()
        except Exception:
            # Never crash the agent because DB status update failed.
            pass

    try:
        run_started = time.perf_counter()
        logger.info(
            "Agent run started: run_id=%s user_id=%s titles=%s locations=%s portals=%s",
            run_id, user_id, titles, locations, portals
        )
        _agent_status["running"] = True
        _agent_status["progress"] = 5

        run = db.query(SearchRun).get(run_id)
        run.status = "running"
        run.progress = int(_agent_status["progress"])
        run.status_message = "🚀 Starting JobCraft agent..."
        db.commit()

        # 1. Read the user's base resume
        settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not settings or not settings.base_resume_filename:
            raise ValueError("No resume uploaded")
        resume_path = RESUMES_BASE_DIR / settings.base_resume_filename
        resume_text = parse_resume(resume_path)
        await update_status("✓ Resume parsed successfully")
        _agent_status["progress"] = 10
        run.progress = 10
        db.commit()

        # 2. Scrape jobs
        scrape_started = time.perf_counter()
        raw_jobs = await run_scraper(portals, titles, locations, update_status)
        logger.info(
            "Scrape complete: run_id=%s jobs=%s elapsed=%.2fs",
            run_id,
            len(raw_jobs),
            time.perf_counter() - scrape_started,
        )
        _agent_status["progress"] = 40
        run.progress = 40
        db.commit()

        if not raw_jobs:
            await update_status("⚠ No jobs found. Try different search terms or portals.")
            run.status = "completed"
            run.completed_at = datetime.datetime.utcnow()
            run.total_jobs_found = 0
            db.commit()
            _agent_status["progress"] = 100
            run.progress = 100
            run.status_message = "⚠ No jobs found. Try different search terms or portals."
            _agent_status["running"] = False
            return

        await update_status("🎯 Selecting top aligned jobs (top 5 per portal)...")

        # ── Location filter ──────────────────────────────────────────
        # Remove jobs whose location does not match the user's preferred
        # locations.  This prevents Indeed/Naukri US results from leaking
        # through when the user specified "Hyderabad" etc.
        if locations:
            loc_lower = [l.strip().lower() for l in locations if l.strip()]
            if loc_lower:
                before = len(raw_jobs)
                raw_jobs = [
                    j for j in raw_jobs
                    if any(tok in (j.get("location") or "").lower() for tok in loc_lower)
                ]
                filtered_out = before - len(raw_jobs)
                if filtered_out:
                    logger.info("Location filter removed %s/%s jobs (kept %s)", filtered_out, before, len(raw_jobs))
                    await update_status(f"📍 Filtered to {len(raw_jobs)} jobs matching preferred locations")

        if not raw_jobs:
            await update_status("⚠ No jobs matched your preferred locations. Try broader locations.")
            run.status = "completed"
            run.completed_at = datetime.datetime.utcnow()
            run.total_jobs_found = 0
            _agent_status["progress"] = 100
            run.progress = 100
            run.status_message = "⚠ No jobs matched your preferred locations."
            db.commit()
            _agent_status["running"] = False
            return

        # Fast alignment selection using ATS keyword overlap (no AI calls).
        by_portal = {}
        for job in raw_jobs:
            portal = (job.get("portal") or "unknown").lower()
            jd = job.get("description", "") or ""
            ats = compute_ats_score(resume_text, jd)
            # Keep the pre-AI ATS score alongside the candidate job so we can
            # display it in the selection UI before tailoring.
            job_copy = dict(job)
            job_copy["_pre_ats_score"] = float(ats)
            by_portal.setdefault(portal, []).append((job_copy, ats))

        selected_jobs = []
        for portal, items in by_portal.items():
            items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
            top_items = items_sorted[:TOP_JOBS_PER_PORTAL_FOR_TAILORING]

            # If any of the top candidates are above the "perfect alignment" threshold,
            # keep only those; otherwise we still take the best N by ATS score.
            perfect = [it for it in top_items if it[1] >= PERFECT_ALIGNMENT_MIN_ATS_SCORE]
            if perfect:
                top_items = perfect

            selected_jobs.extend([j for j, _ats in top_items])

        # Deduplicate by apply_url if present (helps avoid repeats).
        seen_apply_urls = set()
        deduped_jobs = []
        for job in selected_jobs:
            au = (job.get("apply_url") or "").strip()
            if au:
                if au in seen_apply_urls:
                    continue
                seen_apply_urls.add(au)
            deduped_jobs.append(job)

        raw_jobs = deduped_jobs

        run.total_jobs_found = len(raw_jobs)
        db.commit()

        # 3. Stop here: store the shortlisted jobs as "candidates" in DB.
        # The user will select which ones to tailor, and we'll process only
        # those selected job_ids in a separate endpoint.
        _agent_status["progress"] = 60
        run.status = "selection_pending"
        run.progress = 60
        run.status_message = "✅ Jobs found. Select which resumes to create."
        db.commit()

        await update_status(f"✅ Selected {len(raw_jobs)} top-aligned jobs. Please choose them for tailoring.")

        for raw in raw_jobs:
            company = raw.get("company", "Unknown")
            title = raw.get("title", "Unknown")
            job = Job(
                search_run_id=run_id,
                user_id=user_id,
                title=title,
                company=company,
                location=raw.get("location", ""),
                date_posted=raw.get("date_posted", ""),
                description=raw.get("description", ""),
                apply_url=raw.get("apply_url", ""),
                portal=raw.get("portal", ""),
                tailored_resume=None,
                tailored_pdf_path="",
                ats_score=float(raw.get("_pre_ats_score", 0.0)),
                keyword_score=0.0,
                experience_fit_score=0.0,
                recruiter_hook_score=0.0,
                composite_score=0.0,
                grade="D",
                experience_fit_reasoning="",
                recruiter_hook_reasoning="",
                tailoring_notes="",
            )
            db.add(job)
        db.commit()
        logger.info("Shortlisted %s candidate jobs for run_id=%s", len(raw_jobs), run_id)
        _agent_status["running"] = False
        return

    except Exception as e:
        logger.exception("Agent run failed: run_id=%s error=%s", run_id, e)
        await update_status(f"❌ Agent error: {str(e)[:120]}")
        run = db.query(SearchRun).get(run_id)
        if run:
            run.status = "failed"
            db.commit()
    finally:
        _agent_status["running"] = False
        db.close()
        try:
            ai_executor.shutdown(wait=False, cancel_futures=True)  # type: ignore[arg-type]
        except Exception:
            pass


async def _process_selected_jobs(
    run_id: int,
    user_id: int,
    job_ids: List[int],
    api_key: str,
):
    """
    Tailor + score + generate PDF ONLY for the user-selected job_ids.
    Used after the agent has shortlisted candidate jobs and set run.status="selection_pending".
    """
    from database import SessionLocal

    db = SessionLocal()
    loop = asyncio.get_running_loop()
    ai_executor = ThreadPoolExecutor(max_workers=2)

    async def update_status(msg: str):
        _agent_status["messages"].append(msg)
        logger.info(msg)
        try:
            run_obj = db.query(SearchRun).get(run_id)
            if run_obj:
                run_obj.status_message = msg
                run_obj.progress = int(_agent_status.get("progress", 0))
                db.commit()
        except Exception:
            pass

    try:
        run_started = time.perf_counter()
        _agent_status["running"] = True
        _agent_status["run_id"] = run_id
        _agent_status["progress"] = 40
        _agent_status["messages"] = ["🚀 Creating tailored resumes..."]

        run_obj = db.query(SearchRun).get(run_id)
        if not run_obj:
            raise ValueError("Search run not found")

        run_obj.status = "running"
        run_obj.progress = 40
        run_obj.status_message = "🤖 Creating tailored resumes..."
        db.commit()

        settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not settings or not settings.base_resume_filename:
            raise ValueError("No resume uploaded")

        resume_path = RESUMES_BASE_DIR / settings.base_resume_filename
        resume_text = parse_resume(resume_path)

        # Process jobs in the order provided by the client.
        selected_jobs = (
            db.query(Job)
            .filter(Job.user_id == user_id, Job.search_run_id == run_id, Job.id.in_(job_ids))
            .all()
        )
        job_by_id = {j.id: j for j in selected_jobs}
        ordered = [job_by_id[jid] for jid in job_ids if jid in job_by_id]

        total = max(len(ordered), 1)
        await update_status(f"🎯 Tailoring {len(ordered)} selected resumes...")

        for i, job in enumerate(ordered):
            job_started = time.perf_counter()
            # Progress is persisted to DB inside `update_status()`.
            # For a single selected job, the previous math kept progress at 40%
            # for the whole duration. We now advance progress across tailoring,
            # scoring, and PDF generation sub-steps.
            base_pct = 40 + int((i / total) * 55)
            base_pct = min(95, max(40, base_pct))
            try:
                _agent_status["progress"] = min(95, base_pct + 5)

                # If we have a placeholder LinkedIn JD (listing snippet only),
                # refresh the real job description before tailoring.
                try:
                    job_desc_l = (job.description or "").lower()
                    needs_refresh = (job.portal or "").lower() == "linkedin" and (
                        len(job.description or "") < 250
                        or "apply link has full description" in job_desc_l
                    )
                    if needs_refresh and job.apply_url:
                        from scraper import (
                            fetch_linkedin_job_description,
                            fetch_linkedin_job_description_via_worker,
                        )

                        refreshed = await loop.run_in_executor(
                            ai_executor,
                            functools.partial(fetch_linkedin_job_description, job.apply_url),
                        )
                        if not refreshed:
                            refreshed = await loop.run_in_executor(
                                ai_executor,
                                functools.partial(fetch_linkedin_job_description_via_worker, job.apply_url),
                            )
                        if refreshed:
                            job.description = refreshed
                            db.commit()
                            logger.info("Refreshed LinkedIn job description for job_id=%s", job.id)
                except Exception:
                    logger.exception("JD refresh failed for job_id=%s", job.id)

                await update_status(f"🤖 Tailoring resume for {job.company} — {job.title}...")
                tailor_call = functools.partial(
                    tailor_resume,
                    resume_text=resume_text,
                    job_description=job.description,
                    job_title=job.title,
                    company=job.company,
                    api_key=api_key,
                )
                tailored = await loop.run_in_executor(ai_executor, tailor_call)
            except Exception as e:
                logger.exception("Tailoring failed: run_id=%s job_id=%s error=%s", run_id, job.id, e)
                _agent_status["progress"] = min(95, base_pct + 25)
                tailored = {
                    "summary": "",
                    "experience": [],
                    "skills": [],
                    "education": [],
                    "ats_keywords_used": [],
                    "tailoring_notes": f"Error: {e}",
                }

            try:
                _agent_status["progress"] = min(95, base_pct + 25)
                await update_status(f"📊 Scoring {job.company} — {job.title}...")
                score_call = functools.partial(
                    score_job,
                    resume_text=resume_text,
                    job_description=job.description,
                    tailored_resume=tailored,
                    job_title=job.title,
                    api_key=api_key,
                )
                scores = await loop.run_in_executor(ai_executor, score_call)
            except Exception as e:
                logger.exception("Scoring failed: run_id=%s job_id=%s error=%s", run_id, job.id, e)
                _agent_status["progress"] = min(95, base_pct + 45)
                scores = {
                    "ats_score": 0.0,
                    "keyword_score": 0.0,
                    "experience_fit_score": 0.0,
                    "recruiter_hook_score": 0.0,
                    "composite_score": 0.0,
                    "grade": "D",
                    "experience_fit_reasoning": "",
                    "recruiter_hook_reasoning": "",
                }

            try:
                _agent_status["progress"] = min(95, base_pct + 45)
                pdf_call = functools.partial(generate_pdf, tailored, job.title, job.company)
                pdf_path = await loop.run_in_executor(ai_executor, pdf_call)
                pdf_name = pdf_path.name
            except Exception as e:
                logger.exception("PDF generation failed: run_id=%s job_id=%s error=%s", run_id, job.id, e)
                _agent_status["progress"] = min(95, base_pct + 65)
                pdf_name = ""

            job.tailored_resume = tailored
            job.tailored_pdf_path = pdf_name
            job.ats_score = float(scores.get("ats_score", 0.0))
            job.keyword_score = float(scores.get("keyword_score", 0.0))
            job.experience_fit_score = float(scores.get("experience_fit_score", 0.0))
            job.recruiter_hook_score = float(scores.get("recruiter_hook_score", 0.0))
            job.composite_score = float(scores.get("composite_score", 0.0))
            job.grade = scores.get("grade", "D")
            job.experience_fit_reasoning = scores.get("experience_fit_reasoning", "")
            job.recruiter_hook_reasoning = scores.get("recruiter_hook_reasoning", "")
            job.tailoring_notes = tailored.get("tailoring_notes", "")
            db.commit()

            logger.info(
                "Job processed (selection): run_id=%s job_id=%s company=%s title=%s elapsed=%.2fs",
                run_id,
                job.id,
                job.company,
                job.title,
                time.perf_counter() - job_started,
            )
            _agent_status["progress"] = min(95, base_pct + 70)
            try:
                run_obj = db.query(SearchRun).get(run_id)
                if run_obj:
                    run_obj.progress = int(_agent_status.get("progress", 0))
                    run_obj.status_message = f"✅ Finished {job.company} — {job.title}"
                    db.commit()
            except Exception:
                pass

        run_obj.status = "completed"
        run_obj.completed_at = datetime.datetime.utcnow()
        _agent_status["progress"] = 100
        run_obj.progress = 100
        db.commit()
        await update_status(f"✅ Done! {len(ordered)} resumes created and ready for download.")
        logger.info(
            "Selection processing completed: run_id=%s total_selected=%s elapsed=%.2fs",
            run_id,
            len(ordered),
            time.perf_counter() - run_started,
        )
    except Exception as e:
        logger.exception("Selection processing failed: run_id=%s error=%s", run_id, e)
        run_obj = db.query(SearchRun).get(run_id)
        if run_obj:
            run_obj.status = "failed"
            run_obj.status_message = f"❌ Agent error: {str(e)[:120]}"
            db.commit()
        await update_status(f"❌ Agent error: {str(e)[:120]}")
    finally:
        _agent_status["running"] = False
        db.close()
        try:
            ai_executor.shutdown(wait=False, cancel_futures=True)  # type: ignore[arg-type]
        except Exception:
            pass


@app.get("/api/search/{run_id}/candidates")
def get_candidate_jobs(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.query(SearchRun).filter(SearchRun.id == run_id, SearchRun.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found")

    # Candidates are jobs shortlisted by the agent but not yet tailored.
    candidates = (
        db.query(Job)
        .filter(
            Job.search_run_id == run_id,
            Job.user_id == current_user.id,
            # SQLite JSON serializes null as the string "null", so don't rely on
            # JSON NULL comparisons. Candidate jobs are those without a generated PDF yet.
            Job.tailored_pdf_path == "",
        )
        .order_by(Job.portal.asc(), Job.ats_score.desc())
        .all()
    )

    return {
        "run_id": run.id,
        "run_status": run.status,
        "progress": int(run.progress or 0),
        "status_message": run.status_message,
        "candidates": [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "date_posted": j.date_posted,
                "portal": j.portal,
                "apply_url": j.apply_url,
                "ats_score": float(j.ats_score or 0.0),
            }
            for j in candidates
        ],
    }


@app.post("/api/search/{run_id}/process-selected")
async def process_selected_jobs(
    run_id: int,
    body: ProcessSelectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.query(SearchRun).filter(SearchRun.id == run_id, SearchRun.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found")

    if run.status not in {"selection_pending", "running"}:
        raise HTTPException(status_code=409, detail=f"Cannot process selection when run status='{run.status}'")

    job_ids = body.job_ids or []
    if not job_ids:
        raise HTTPException(status_code=400, detail="Provide at least one job_id to process")

    # Only process jobs that are still candidates (tailored_resume is NULL).
    candidates = (
        db.query(Job)
        .filter(
            Job.search_run_id == run_id,
            Job.user_id == current_user.id,
            Job.id.in_(job_ids),
            Job.tailored_pdf_path == "",
        )
        .all()
    )
    if not candidates:
        raise HTTPException(status_code=400, detail="None of the provided jobs are ready to process")
    candidate_id_set = {j.id for j in candidates}
    selected_job_ids = [jid for jid in job_ids if jid in candidate_id_set]
    if not selected_job_ids:
        raise HTTPException(status_code=400, detail="None of the provided jobs are ready to process")

    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    api_key = ""
    if settings and settings.anthropic_api_key:
        api_key = (settings.anthropic_api_key or "").strip()
    if not api_key:
        api_key = (OPENAI_API_KEY or GEMINI_API_KEY or ANTHROPIC_API_KEY or "").strip()

    provider = (AI_PROVIDER or "").strip().lower()
    if not api_key and provider not in {"ollama", "auto"}:
        raise HTTPException(
            status_code=400,
            detail="No API key. Add OPENAI_API_KEY in .env or use AI_PROVIDER=ollama.",
        )

    # Update in-memory status immediately so the UI can show progress.
    _agent_status["run_id"] = run_id
    _agent_status["progress"] = 40
    _agent_status["messages"] = ["🚀 Starting tailored resume creation..."]

    asyncio.create_task(
        _process_selected_jobs(
            run_id=run_id,
            user_id=current_user.id,
            job_ids=selected_job_ids,
            api_key=api_key,
        )
    )
    return {"message": "Selection processing started", "run_id": run_id}


@app.post("/api/search/start")
async def start_search(
    body: SearchStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Permanent safety: lock by DB state (not only in-memory), and clear stale runs.
    active_run = (
        db.query(SearchRun)
        .filter(SearchRun.user_id == current_user.id)
        .filter(SearchRun.status.in_(["running", "pending", "selection_pending"]))
        .order_by(SearchRun.started_at.desc())
        .first()
    )

    if active_run and active_run.started_at:
        elapsed = (datetime.datetime.utcnow() - active_run.started_at).total_seconds()
        if elapsed < AGENT_RUN_STALE_SECONDS:
            raise HTTPException(status_code=429, detail="A search is already running. Please wait.")
        # Stale run (crash/hang) - mark as failed and allow a new run.
        active_run.status = "failed"
        active_run.completed_at = datetime.datetime.utcnow()
        active_run.status_message = "Stale run auto-closed."
        active_run.progress = int(active_run.progress or 0)
        db.commit()

    # If DB shows no active run, clear in-memory gate too.
    if not db.query(SearchRun).filter(SearchRun.user_id == current_user.id).filter(SearchRun.status.in_(["running", "pending", "selection_pending"])).first():
        _agent_status["running"] = False
        _agent_status["run_id"] = None
        _agent_status["progress"] = 0
        _agent_status["messages"] = []

    # Rate limit: check last run time
    last_run = (
        db.query(SearchRun)
        .filter(SearchRun.user_id == current_user.id)
        .order_by(SearchRun.started_at.desc())
        .first()
    )
    if last_run and last_run.started_at:
        elapsed = (datetime.datetime.utcnow() - last_run.started_at).total_seconds()
        if elapsed < SCRAPE_COOLDOWN_SECONDS:
            remaining = int(SCRAPE_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limited. Wait {remaining} seconds before next search."
            )

    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    titles = body.titles or (settings.target_titles if settings else [])
    locations = body.locations or (settings.preferred_locations if settings else [])
    portals = body.portals or (settings.portals if settings else ["linkedin", "indeed"])

    if not titles:
        raise HTTPException(status_code=400, detail="Provide at least one job title to search.")
    if not locations:
        raise HTTPException(status_code=400, detail="Provide at least one location.")

    # Prefer Gemini (free) then Anthropic; key can be stored in Settings or .env
    api_key = ""
    if settings and settings.anthropic_api_key:
        api_key = (settings.anthropic_api_key or "").strip()
    if not api_key:
        api_key = (OPENAI_API_KEY or GEMINI_API_KEY or ANTHROPIC_API_KEY or "").strip()
    provider = (AI_PROVIDER or "").strip().lower()
    if not api_key and provider not in {"ollama", "auto"}:
        raise HTTPException(
            status_code=400,
            detail="No API key. Add OPENAI_API_KEY in .env, or a FREE Gemini key from https://aistudio.google.com as GEMINI_API_KEY, or use AI_PROVIDER=ollama.",
        )

    run = SearchRun(
        user_id=current_user.id,
        status="pending",
        progress=0,
        status_message="🚀 Starting JobCraft agent...",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    _agent_status["run_id"] = run.id
    _agent_status["progress"] = 0
    _agent_status["messages"] = ["🚀 Starting JobCraft agent..."]

    asyncio.create_task(
        _run_agent(run.id, current_user.id, titles, locations, portals, api_key)
    )

    return {"run_id": run.id, "message": "Search started"}


@app.get("/api/search/status")
def get_search_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    active_run = (
        db.query(SearchRun)
        .filter(SearchRun.user_id == current_user.id)
        .filter(SearchRun.status.in_(["running", "pending", "selection_pending"]))
        .order_by(SearchRun.started_at.desc())
        .first()
    )

    if not active_run:
        # No active run: return the latest run's progress/message so the
        # frontend can redirect on completion even if in-memory state was reset
        # (e.g., backend restart during a user session).
        last_run = (
            db.query(SearchRun)
            .filter(SearchRun.user_id == current_user.id)
            .order_by(SearchRun.started_at.desc())
            .first()
        )
        if last_run:
            return {
                "running": False,
                "run_id": last_run.id,
                "progress": int(last_run.progress or 0),
                "messages": [last_run.status_message] if last_run.status_message else [],
            }
        return {"running": False, "run_id": None, "progress": 0, "messages": []}

    # Prefer the full in-memory message list if it matches the active run.
    messages = []
    if _agent_status.get("run_id") == active_run.id and _agent_status.get("messages"):
        messages = _agent_status["messages"]
    elif active_run.status_message:
        messages = [active_run.status_message]

    return {
        "running": True,
        "run_id": active_run.id,
        "progress": int(active_run.progress or 0),
        "messages": messages,
    }


@app.get("/api/search/history")
def get_search_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    runs = (
        db.query(SearchRun)
        .filter(SearchRun.user_id == current_user.id)
        .order_by(SearchRun.started_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": r.id,
            "status": r.status,
            "total_jobs_found": r.total_jobs_found,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


# ─────────────────────────── Jobs ───────────────────────────

@app.get("/api/jobs")
def list_jobs(
    sort_by: str = Query("composite_score", regex="^(composite_score|ats_score|keyword_score|created_at)$"),
    grade: Optional[str] = Query(None, regex="^[A-D]$"),
    search: Optional[str] = None,
    run_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Job).filter(Job.user_id == current_user.id)
    # Only show jobs that have already been processed (SQLite JSON null becomes string "null").
    q = q.filter(Job.tailored_resume != "null")
    q = q.filter(Job.tailored_pdf_path != "")

    # Scope to a specific run, or the latest completed run by default.
    if run_id:
        q = q.filter(Job.search_run_id == run_id)
    else:
        latest_run = (
            db.query(SearchRun)
            .filter(SearchRun.user_id == current_user.id, SearchRun.status == "completed")
            .order_by(SearchRun.started_at.desc())
            .first()
        )
        if latest_run:
            q = q.filter(Job.search_run_id == latest_run.id)

    if grade:
        q = q.filter(Job.grade == grade)
    if search:
        q = q.filter(
            (Job.company.ilike(f"%{search}%")) | (Job.title.ilike(f"%{search}%"))
        )

    sort_col = getattr(Job, sort_by, Job.composite_score)
    q = q.order_by(sort_col.desc())

    jobs = q.all()
    return [
        {
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "date_posted": j.date_posted,
            "portal": j.portal,
            "apply_url": j.apply_url,
            "ats_score": j.ats_score,
            "keyword_score": j.keyword_score,
            "experience_fit_score": j.experience_fit_score,
            "recruiter_hook_score": j.recruiter_hook_score,
            "composite_score": j.composite_score,
            "grade": j.grade,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@app.get("/api/jobs/{job_id}")
def get_job_detail(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "date_posted": job.date_posted,
        "description": job.description,
        "portal": job.portal,
        "apply_url": job.apply_url,
        "tailored_resume": job.tailored_resume,
        "ats_score": job.ats_score,
        "keyword_score": job.keyword_score,
        "experience_fit_score": job.experience_fit_score,
        "recruiter_hook_score": job.recruiter_hook_score,
        "composite_score": job.composite_score,
        "grade": job.grade,
        "experience_fit_reasoning": job.experience_fit_reasoning,
        "recruiter_hook_reasoning": job.recruiter_hook_reasoning,
        "tailoring_notes": job.tailoring_notes,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


@app.get("/api/jobs/{job_id}/resume")
def get_tailored_resume(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"tailored_resume": job.tailored_resume}


@app.get("/api/jobs/{job_id}/download")
def download_resume(
    job_id: int,
    format: str = Query("pdf", regex="^(pdf|docx)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    safe_name = f"Resume_{job.company}_{job.title}".replace(" ", "_")

    if format == "docx":
        if not job.tailored_resume or job.tailored_resume == "null":
            raise HTTPException(status_code=404, detail="No tailored resume data available for DOCX export")
        try:
            docx_path = generate_docx(job.tailored_resume, job.title, job.company)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"DOCX generation failed: {str(e)[:200]}")
        return FileResponse(
            str(docx_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{safe_name}.docx",
        )

    if not job.tailored_pdf_path:
        raise HTTPException(status_code=404, detail="No PDF available for this job")

    from config import RESUMES_TAILORED_DIR
    pdf_path = RESUMES_TAILORED_DIR / job.tailored_pdf_path
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"{safe_name}.pdf",
    )


@app.post("/api/jobs/{job_id}/regenerate")
async def regenerate_resume(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings or not settings.base_resume_filename:
        raise HTTPException(status_code=400, detail="No base resume uploaded")

    resume_path = RESUMES_BASE_DIR / settings.base_resume_filename
    resume_text = parse_resume(resume_path)

    # If the stored job description is a placeholder (especially for LinkedIn),
    # refresh it from the job URL before tailoring so the AI uses real
    # qualifications/responsibilities.
    try:
        job_desc_l = (job.description or "").lower()
        if (job.portal or "").lower() == "linkedin" and (
            len(job.description or "") < 250 or "apply link has full description" in job_desc_l
        ):
            from scraper import fetch_linkedin_job_description, fetch_linkedin_job_description_via_worker
            if job.apply_url:
                refreshed = fetch_linkedin_job_description(job.apply_url)
                if not refreshed:
                    refreshed = fetch_linkedin_job_description_via_worker(job.apply_url)
                if refreshed:
                    job.description = refreshed
                    db.commit()
                    logger.info("Refreshed LinkedIn job description for job_id=%s", job_id)
    except Exception:
        logger.exception("Failed to refresh job description for job_id=%s", job_id)

    provider = (AI_PROVIDER or "").strip().lower()
    api_key = (
        (settings.anthropic_api_key if settings and settings.anthropic_api_key else "").strip()
        or OPENAI_API_KEY
        or GEMINI_API_KEY
        or ANTHROPIC_API_KEY
    )
    # Ollama/local mode should work without any cloud keys.
    if not api_key and provider not in {"ollama", "auto"}:
        raise HTTPException(
            status_code=400,
            detail="No API key. Set OPENAI_API_KEY in .env or add a Gemini key in Settings / GEMINI_API_KEY.",
        )

    try:
        tailored = tailor_resume(
            resume_text=resume_text,
            job_description=job.description,
            job_title=job.title,
            company=job.company,
            api_key=api_key,
        )
        scores = score_job(
            resume_text=resume_text,
            job_description=job.description,
            tailored_resume=tailored,
            job_title=job.title,
            api_key=api_key,
        )
        pdf_path = generate_pdf(tailored, job.title, job.company)
    except Exception as e:
        # Do not crash the UI with 500s; surface a clear actionable error.
        logger.error(f"Regenerate failed for job_id={job_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e)[:400])

    job.tailored_resume = tailored
    job.tailored_pdf_path = pdf_path.name
    job.ats_score = scores["ats_score"]
    job.keyword_score = scores["keyword_score"]
    job.experience_fit_score = scores["experience_fit_score"]
    job.recruiter_hook_score = scores["recruiter_hook_score"]
    job.composite_score = scores["composite_score"]
    job.grade = scores["grade"]
    job.experience_fit_reasoning = scores.get("experience_fit_reasoning", "")
    job.recruiter_hook_reasoning = scores.get("recruiter_hook_reasoning", "")
    job.tailoring_notes = tailored.get("tailoring_notes", "")
    db.commit()

    return {"message": "Resume regenerated", "composite_score": job.composite_score, "grade": job.grade}


# ─────────────────────────── Settings ───────────────────────────

@app.get("/api/settings")
def get_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings:
        return {
            "target_titles": [],
            "preferred_locations": [],
            "portals": ["linkedin", "indeed"],
            "years_of_experience": "",
            "base_resume_filename": "",
            "has_api_key": False,
        }
    return {
        "target_titles": settings.target_titles or [],
        "preferred_locations": settings.preferred_locations or [],
        "portals": settings.portals or [],
        "years_of_experience": settings.years_of_experience or "",
        "base_resume_filename": settings.base_resume_filename or "",
        "has_api_key": bool(settings.anthropic_api_key),
    }


@app.put("/api/settings")
def update_settings(
    body: SettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    if body.target_titles is not None:
        settings.target_titles = body.target_titles
    if body.preferred_locations is not None:
        settings.preferred_locations = body.preferred_locations
    if body.portals is not None:
        settings.portals = body.portals
    if body.years_of_experience is not None:
        settings.years_of_experience = body.years_of_experience
    if body.anthropic_api_key is not None:
        settings.anthropic_api_key = body.anthropic_api_key

    db.commit()
    return {"message": "Settings updated successfully"}


@app.delete("/api/settings/clear-data")
def clear_all_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(Job).filter(Job.user_id == current_user.id).delete()
    db.query(SearchRun).filter(SearchRun.user_id == current_user.id).delete()
    db.commit()
    return {"message": "All job data cleared"}
