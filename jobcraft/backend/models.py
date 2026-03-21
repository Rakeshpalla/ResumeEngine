"""
SQLAlchemy ORM models for the JobCraft database.
Tables: users, jobs, search_runs, settings
"""

import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    settings = relationship("UserSettings", back_populates="user", uselist=False)
    search_runs = relationship("SearchRun", back_populates="user")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    target_titles = Column(JSON, default=list)       # ["Product Manager", "PM"]
    preferred_locations = Column(JSON, default=list)  # ["Hyderabad", "Remote"]
    portals = Column(JSON, default=list)              # ["linkedin", "indeed"]
    years_of_experience = Column(String(20), default="")
    base_resume_filename = Column(String(255), default="")
    anthropic_api_key = Column(String(255), default="")

    user = relationship("User", back_populates="settings")


class SearchRun(Base):
    """One complete agent run — scrape + tailor + score."""
    __tablename__ = "search_runs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(50), default="pending")  # pending | running | completed | failed
    progress = Column(Integer, default=0)            # 0-100
    status_message = Column(Text, default="")
    total_jobs_found = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="search_runs")
    jobs = relationship("Job", back_populates="search_run")


class Job(Base):
    """A single scraped job posting with its tailored resume + scores."""
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    search_run_id = Column(Integer, ForeignKey("search_runs.id"), nullable=False)
    user_id = Column(Integer, nullable=False)

    # Job listing info
    title = Column(String(255), default="")
    company = Column(String(255), default="")
    location = Column(String(255), default="")
    date_posted = Column(String(100), default="")
    description = Column(Text, default="")
    apply_url = Column(String(1000), default="")
    portal = Column(String(50), default="")  # linkedin | indeed | naukri | glassdoor

    # AI-generated tailored resume (JSON)
    tailored_resume = Column(JSON, nullable=True)
    tailored_pdf_path = Column(String(500), default="")

    # Scores
    ats_score = Column(Float, default=0.0)
    keyword_score = Column(Float, default=0.0)
    experience_fit_score = Column(Float, default=0.0)
    recruiter_hook_score = Column(Float, default=0.0)
    composite_score = Column(Float, default=0.0)
    grade = Column(String(1), default="D")

    # AI reasoning
    experience_fit_reasoning = Column(Text, default="")
    recruiter_hook_reasoning = Column(Text, default="")
    tailoring_notes = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    search_run = relationship("SearchRun", back_populates="jobs")
