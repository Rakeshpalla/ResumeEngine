"""
Job scraper — Windows-safe.

Important: Playwright can fail silently when launched from a thread inside a FastAPI
worker/reloader environment on Windows. That caused "0 jobs" despite jobs existing.

This implementation uses plain HTTP (`requests`) + HTML parsing (`BeautifulSoup`)
so it can't hang/crash in that way.
"""

import asyncio
import json
import random
import datetime
import time
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional, Callable
import subprocess
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import (
    MAX_JOBS_PER_PORTAL, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX, JOBS_DIR
)

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_executor = ThreadPoolExecutor(max_workers=2)

_COMMON_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

def _sleep_jitter():
    time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))


def _http_get(url: str, *, timeout_s: int = 25) -> requests.Response:
    t0 = time.time()
    resp = requests.get(url, headers=_COMMON_HEADERS, timeout=timeout_s, allow_redirects=True)
    dt = time.time() - t0

    final_url = resp.url
    logger.info(f"[HTTP] GET {url} -> {resp.status_code} in {dt:.2f}s (final={final_url})")

    # Minimal diagnostics to detect blocks/login walls
    body = resp.text or ""
    body_l = body.lower()
    if "captcha" in body_l or "verify" in body_l and "human" in body_l:
        logger.warning(f"[HTTP] Possible bot protection/captcha on {final_url}")
    if "sign in" in body_l and ("linkedin" in final_url.lower() or "login" in final_url.lower()):
        logger.warning(f"[HTTP] Possible login wall on {final_url}")
    return resp


def _txt(s: str) -> str:
    return " ".join((s or "").split())


def _abs_url(base: str, href: str) -> str:
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return base.rstrip("/") + href
    return base.rstrip("/") + "/" + href.lstrip("/")


def fetch_linkedin_job_description(job_url: str) -> str:
    """
    Best-effort extraction of LinkedIn job description text.
    Returns "" if blocked/throttled or if the HTML does not expose the description.
    """
    if not job_url:
        return ""
    try:
        resp = _http_get(job_url, timeout_s=35)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "lxml")

        selectors = [
            "div.show-more-less-html__markup",
            "div.jobs-unified-show-more-less-content__markup",
            "div.description__text",
            "[class*='job-description']",
            "section#job-details",
        ]

        text = ""
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                if text and len(text) > 120:
                    break

        if not text:
            el = soup.select_one("div#job-details")
            if el:
                text = el.get_text(" ", strip=True)

        text = _txt(text)
        return text if len(text) > 120 else ""
    except Exception:
        return ""


def fetch_linkedin_job_description_via_worker(job_url: str, timeout_s: int = 150) -> str:
    """
    Use Playwright worker to fetch LinkedIn job page and extract description.
    This is more reliable than requests on LinkedIn, but slower.
    """
    worker_path = Path(__file__).resolve().parent / "scraper_worker.py"
    cmd = [
        sys.executable,
        str(worker_path),
        "--portal",
        "linkedin",
        "--role",
        "noop",
        "--location",
        "noop",
        "--max_jobs",
        "0",
        "--job_url",
        job_url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        logger.error("LinkedIn worker timeout for url=%s", job_url)
        return ""

    if proc.returncode != 0:
        logger.error(
            "LinkedIn worker failed rc=%s stderr=%s",
            proc.returncode,
            (proc.stderr or "").strip()[:300],
        )
        return ""

    try:
        data = json.loads(proc.stdout)
    except Exception:
        logger.error("LinkedIn worker returned non-JSON stdout: %s", (proc.stdout or "")[:300])
        return ""

    if isinstance(data, dict):
        return data.get("description") or ""
    return ""


def _scrape_linkedin_sync(role: str, location: str) -> List[Dict]:
    """
    Scrape LinkedIn public job search page.
    Uses HTML returned by LinkedIn's public jobs search (SEO). No browser required.

    Note: LinkedIn changes HTML often. If blocked, logs will show redirects/captcha.
    """
    jobs = []
    logger.info(f"[LinkedIn] Starting (requests): role='{role}', location='{location}'")

    url = (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={requests.utils.quote(role)}"
        f"&location={requests.utils.quote(location)}"
    )

    def _scrape_linkedin_job_description_sync(job_url: str) -> str:
        """
        Best-effort extraction of LinkedIn job description text.
        LinkedIn may throttle/block; on failure we return "" so the pipeline
        can fall back to the listing snippet.
        """
        if not job_url:
            return ""

        try:
            resp = _http_get(job_url, timeout_s=35)
            if resp.status_code != 200:
                return ""

            soup = BeautifulSoup(resp.text, "lxml")

            # LinkedIn commonly wraps job description in one of these containers.
            selectors = [
                "div.show-more-less-html__markup",
                "div.jobs-unified-show-more-less-content__markup",
                "div.description__text",
                "[class*='job-description']",
                "section#job-details",
            ]

            text = ""
            for sel in selectors:
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(" ", strip=True)
                    if text and len(text) > 120:
                        break

            if not text:
                # Fallback: attempt to pull text from job details section.
                el = soup.select_one("div#job-details")
                if el:
                    text = el.get_text(" ", strip=True)

            text = _txt(text)
            return text if len(text) > 120 else ""
        except Exception:
            return ""

    try:
        resp = _http_get(url)
        if resp.status_code != 200:
            logger.error(f"[LinkedIn] Non-200 response: {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select(".base-card")
        logger.info(f"[LinkedIn] Parsed {len(cards)} cards from HTML")

        for card in cards[:MAX_JOBS_PER_PORTAL]:
            title = _txt((card.select_one(".base-search-card__title") or {}).get_text() if card.select_one(".base-search-card__title") else "")
            company = _txt((card.select_one(".base-search-card__subtitle") or {}).get_text() if card.select_one(".base-search-card__subtitle") else "")
            loc_el = card.select_one(".job-search-card__location") or card.select_one(".base-search-card__metadata span")
            loc = _txt(loc_el.get_text() if loc_el else "") or location
            link_el = card.select_one("a.base-card__full-link") or card.select_one("a")
            href = link_el.get("href", "") if link_el else ""
            apply_url = _abs_url("https://www.linkedin.com", href.split("?")[0])
            time_el = card.select_one("time")
            date_posted = _txt(time_el.get("datetime", "") if time_el else "") or _txt(time_el.get_text() if time_el else "") or "Recent"

            if not title:
                continue

            # Try to fetch the actual job description from the job page.
            # If blocked, keep a small placeholder so tailoring still works.
            detailed_desc = fetch_linkedin_job_description(apply_url)
            if not detailed_desc:
                detailed_desc = f"{title} at {company} in {loc}. Apply link has full description."

            jobs.append(
                {
                    "title": title,
                    "company": company,
                    "location": loc,
                    "date_posted": date_posted,
                    "description": detailed_desc,
                    "apply_url": apply_url,
                    "portal": "linkedin",
                }
            )

            _sleep_jitter()

        logger.info(f"[LinkedIn] Done — {len(jobs)} jobs scraped")
    except Exception as e:
        logger.error(f"[LinkedIn] Failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    return jobs


def _scrape_indeed_sync(role: str, location: str) -> List[Dict]:
    """Scrape Indeed search results via HTML (best-effort)."""
    jobs = []
    logger.info(f"[Indeed] Starting (requests): role='{role}', location='{location}'")
    url = (
        "https://www.indeed.com/jobs"
        f"?q={requests.utils.quote(role)}"
        f"&l={requests.utils.quote(location)}"
    )
    try:
        resp = _http_get(url)
        if resp.status_code != 200:
            logger.error(f"[Indeed] Non-200 response: {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select(".job_seen_beacon")
        logger.info(f"[Indeed] Parsed {len(cards)} cards from HTML")
        for card in cards[:MAX_JOBS_PER_PORTAL]:
            title_el = card.select_one("h2.jobTitle a") or card.select_one("h2.jobTitle span")
            title = _txt(title_el.get_text() if title_el else "")
            company_el = card.select_one("[data-testid='company-name']") or card.select_one(".companyName")
            company = _txt(company_el.get_text() if company_el else "")
            loc_el = card.select_one("[data-testid='text-location']") or card.select_one(".companyLocation")
            loc = _txt(loc_el.get_text() if loc_el else "") or location
            snippet_el = card.select_one(".job-snippet") or card.select_one(".metadata")
            snippet = _txt(snippet_el.get_text() if snippet_el else "")
            href = (title_el.get("href", "") if title_el else "") or ""
            apply_url = _abs_url("https://www.indeed.com", href)

            if not title:
                continue

            jobs.append(
                {
                    "title": title,
                    "company": company,
                    "location": loc,
                    "date_posted": "Recent",
                    "description": snippet or f"{title} at {company} in {loc}. Apply link has full description.",
                    "apply_url": apply_url,
                    "portal": "indeed",
                }
            )

        logger.info(f"[Indeed] Done — {len(jobs)} jobs scraped")
    except Exception as e:
        logger.error(f"[Indeed] Failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    return jobs


def _naukri_strip_html_desc(raw: str) -> str:
    """Light cleanup of HTML snippets from Naukri jobDesc."""
    if not raw:
        return ""
    s = raw.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    s = BeautifulSoup(s, "lxml").get_text(" ", strip=True)
    return _txt(s)


def _scrape_naukri_via_api(role: str, location: str) -> List[Dict]:
    """
    Naukri search results via public JSON API (same data as the website SRP).
    Headless Playwright often gets 'Access Denied'; the listing page is also a
    Next.js shell with no SSR job cards for requests-based HTML parsing.
    """
    jobs: List[Dict] = []
    loc_param = (location or "").split(",")[0].strip()
    if not loc_param:
        loc_param = (location or "").strip() or "India"
    logger.info(f"[Naukri] Starting (jobapi/v2/search): role='{role}', location='{loc_param}'")
    headers = {
        **_COMMON_HEADERS,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.naukri.com/",
    }
    params = {
        "keyword": (role or "").strip(),
        "location": loc_param,
        "pageNo": "1",
        "noOfResults": str(MAX_JOBS_PER_PORTAL),
    }
    try:
        resp = requests.get(
            "https://www.naukri.com/jobapi/v2/search",
            params=params,
            headers=headers,
            timeout=35,
        )
        if resp.status_code != 200:
            logger.error(f"[Naukri] API non-200: {resp.status_code}")
            return []
        data = resp.json()
        items = data.get("list") or []
        total = data.get("totaljobs")
        logger.info(f"[Naukri] API totaljobs={total} list_len={len(items)}")
        for it in items[:MAX_JOBS_PER_PORTAL]:
            title = _txt(it.get("post") or "")
            if not title:
                continue
            company = _txt(it.get("companyName") or "") or "Unknown"
            city = _txt(it.get("city") or "") or loc_param
            jd_raw = it.get("jobDesc") or it.get("tupleDesc") or ""
            desc = _naukri_strip_html_desc(str(jd_raw)) if jd_raw else ""
            if not desc:
                desc = f"{title} at {company} in {city}. Apply link has full description."
            apply_url = (it.get("urlStr") or "").strip()
            if apply_url and not apply_url.startswith("http"):
                apply_url = _abs_url("https://www.naukri.com", apply_url)
            jobs.append(
                {
                    "title": title,
                    "company": company,
                    "location": city,
                    "date_posted": "Recent",
                    "description": desc,
                    "apply_url": apply_url,
                    "portal": "naukri",
                }
            )
        logger.info(f"[Naukri] Done — {len(jobs)} jobs from API")
    except Exception as e:
        logger.error(f"[Naukri] API failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    return jobs


def _scrape_naukri(role: str, location: str) -> List[Dict]:
    """Prefer JSON API; Playwright worker often blocked by Naukri."""
    jobs = _scrape_naukri_via_api(role, location)
    if jobs:
        return jobs
    logger.warning("[Naukri] API returned 0 jobs; trying Playwright worker (may still be blocked)")
    return _scrape_via_worker("naukri", role, location, MAX_JOBS_PER_PORTAL)


def _scrape_via_worker(portal: str, role: str, location: str, max_jobs: int) -> List[Dict]:
    """
    Use `scraper_worker.py` to run Playwright in an isolated process.
    This avoids Windows/async/subprocess instability in the main FastAPI process.
    """
    worker_path = Path(__file__).resolve().parent / "scraper_worker.py"
    cmd = [
        sys.executable,
        str(worker_path),
        "--portal",
        portal,
        "--role",
        role,
        "--location",
        location,
        "--max_jobs",
        str(max_jobs),
    ]

    logger.info(f"[{portal.title()}] Starting (worker): role='{role}', location='{location}'")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        logger.error(f"[{portal.title()}] Worker timeout for role='{role}', location='{location}'")
        return []

    if proc.returncode != 0:
        logger.error(
            f"[{portal.title()}] Worker failed rc={proc.returncode} stderr={proc.stderr.strip()[:300]} stdout={proc.stdout.strip()[:200]}"
        )
        return []

    try:
        data = json.loads(proc.stdout)
        if isinstance(data, list):
            return data
    except Exception:
        logger.error(f"[{portal.title()}] Worker returned non-JSON stdout: {proc.stdout.strip()[:300]}")

    return []


PORTAL_SCRAPERS = {
    "linkedin": _scrape_linkedin_sync,
    # Browser worker for portals that require client-side rendering.
    "indeed": lambda role, location: _scrape_via_worker("indeed", role, location, MAX_JOBS_PER_PORTAL),
    # Naukri: use public jobapi JSON first (Playwright often gets Access Denied).
    "naukri": _scrape_naukri,
}


async def run_scraper(
    portals: List[str],
    roles: List[str],
    locations: List[str],
    status_callback: Optional[Callable] = None,
) -> List[Dict]:
    """Run sync scrapers in a thread pool so FastAPI's async loop stays free."""
    loop = asyncio.get_event_loop()
    all_jobs: List[Dict] = []

    for portal in portals:
        scraper_fn = PORTAL_SCRAPERS.get(portal.lower())
        if not scraper_fn:
            logger.warning(f"Unknown portal: {portal}")
            continue

        for role in roles:
            for location in locations:
                if status_callback:
                    await status_callback(f"🔍 Searching {portal.title()} for {role} in {location}...")
                try:
                    jobs = await loop.run_in_executor(_executor, scraper_fn, role, location)
                    all_jobs.extend(jobs)
                    if status_callback:
                        await status_callback(f"✓ Found {len(jobs)} jobs on {portal.title()}")
                except Exception as e:
                    logger.error(f"Scraper error ({portal}/{role}/{location}): {type(e).__name__}: {e}\n{traceback.format_exc()}")
                    if status_callback:
                        await status_callback(f"⚠ {portal.title()} scraping failed: {str(e)[:80]}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = JOBS_DIR / f"raw_{timestamp}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)

    if status_callback:
        await status_callback(f"✓ Total: {len(all_jobs)} jobs found across {len(portals)} portal(s)")

    return all_jobs
