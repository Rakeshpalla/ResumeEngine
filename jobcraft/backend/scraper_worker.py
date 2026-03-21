"""
Scraper worker (browser-based, runs as separate process).

Playwright runs in its own process to avoid Windows/async issues with FastAPI.
Called by scraper.py via subprocess for portals that need client-side rendering.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any, Dict, List
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _txt(v: Any) -> str:
    if not v:
        return ""
    return " ".join(str(v).split()).strip()


def _get_text(el) -> str:
    if not el:
        return ""
    try:
        return _txt(el.inner_text())
    except Exception:
        try:
            return _txt(el.text_content())
        except Exception:
            return ""


def scrape_indeed(page, context, role: str, location: str, max_jobs: int) -> List[Dict]:
    url = (
        "https://www.indeed.com/jobs"
        f"?q={role.replace(' ', '%20')}"
        f"&l={location.replace(' ', '%20')}"
    )
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(3000)

    card_selector = ".job_seen_beacon, div[data-jk]"
    try:
        page.wait_for_selector(card_selector, timeout=10_000)
    except Exception:
        pass

    cards = page.locator(card_selector)
    count = cards.count()
    print(f"[worker] portal=indeed url={url} cards={count} title={page.title()}", file=sys.stderr)

    jobs: List[Dict] = []
    for i in range(min(count, max_jobs)):
        try:
            card = cards.nth(i)
            title_el = card.locator("h2.jobTitle a, h2.jobTitle span, a[data-testid='job-title']").first
            company_el = card.locator("[data-testid='company-name'], .companyName, span.css-1h7lukg").first
            loc_el = card.locator("[data-testid='text-location'], .companyLocation, div.css-1restlb").first
            snippet_el = card.locator(".job-snippet, td.resultContent .heading6").first

            title = _get_text(title_el)
            company = _get_text(company_el)
            loc = _get_text(loc_el) or location
            snippet = _get_text(snippet_el)

            href = ""
            try:
                href = title_el.get_attribute("href") or ""
            except Exception:
                pass

            if not title:
                continue

            apply_url = href
            if apply_url and not apply_url.startswith("http"):
                apply_url = "https://www.indeed.com" + apply_url

            jobs.append({
                "title": _txt(title),
                "company": _txt(company) or "Unknown",
                "location": _txt(loc) or location,
                "date_posted": "Recent",
                "description": _txt(snippet) or f"{title} at {company} in {loc}. Apply link has full description.",
                "apply_url": apply_url,
                "portal": "indeed",
            })
        except Exception:
            continue

    return jobs


def _naukri_location_slug_for_path(location: str) -> str:
    """
    Naukri SEO URLs often use city-specific slugs (e.g. Hyderabad -> hyderabad-secunderabad),
    not just 'hyderabad'. Building ...-jobs-in-hyderabad alone often returns 0 parseable cards.
    """
    loc = (location or "").strip().lower()
    if "," in loc:
        loc = loc.split(",")[0].strip()
    loc = loc.replace(".", "").strip()
    if "hyderabad" in loc:
        return "hyderabad-secunderabad"
    if "bengaluru" in loc or "bangalore" in loc:
        return "bangalore"
    if "new delhi" in loc or loc in ("delhi", "ncr", "gurgaon", "gurugram", "noida", "faridabad"):
        return "delhi-ncr"
    if "chennai" in loc:
        return "chennai"
    if "pune" in loc:
        return "pune"
    if "mumbai" in loc:
        return "mumbai"
    if "kolkata" in loc:
        return "kolkata"
    return loc.replace(" ", "-")


def _naukri_search_urls(role: str, location: str) -> List[str]:
    """Build candidate listing URLs (Naukri changes layout; try multiple patterns)."""
    role_slug = role.lower().strip().replace(" ", "-")
    loc_slug = _naukri_location_slug_for_path(location)
    k = quote_plus(role.strip())
    lparam = quote_plus((location or "").split(",")[0].strip())
    base = f"https://www.naukri.com/{role_slug}-jobs-in-{loc_slug}"
    urls = [
        f"{base}?k={k}&l={lparam}",
        base,
    ]
    # If we mapped Hyderabad, also try the plain slug (some Naukri redirects still land on SRP)
    if loc_slug == "hyderabad-secunderabad":
        plain = f"https://www.naukri.com/{role_slug}-jobs-in-hyderabad?k={k}&l={lparam}"
        urls.insert(1, plain)
    # Dedupe while preserving order
    seen = set()
    out: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def scrape_naukri(page, context, role: str, location: str, max_jobs: int) -> List[Dict]:
    urls = _naukri_search_urls(role, location)
    cards = None
    count = 0
    used_url = ""

    for url in urls:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(4000)
            try:
                page.evaluate("window.scrollTo(0, Math.min(document.body.scrollHeight, 1200))")
            except Exception:
                pass
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f"[worker] portal=naukri goto failed url={url} err={e}", file=sys.stderr)
            continue

        card_selectors = [
            "article.cust-job-tuple",
            "div.cust-job-tuple",
            "div.srp-jobtuple-wrapper",
            "article.jobTuple",
            ".srp-jobtuple-wrapper",
            "[class*='jobTuple']",
            "[data-job-id]",
        ]
        best = 0
        best_loc = None
        for sel in card_selectors:
            loc = page.locator(sel)
            c = loc.count()
            if c > best:
                best = c
                best_loc = loc

        if best > 0 and best_loc is not None:
            cards = best_loc
            count = best
            used_url = url
            break

    print(
        f"[worker] portal=naukri url={used_url or urls[0]} cards={count} title={page.title()}",
        file=sys.stderr,
    )

    if cards is None or count == 0:
        return []

    jobs: List[Dict] = []
    for i in range(min(count, max_jobs)):
        try:
            card = cards.nth(i)
            title_el = card.locator(
                "a.title, a.srpJobTuple-link, a[class*='title'], .title a, h2 a, h3 a, a[href*='/job-listings']"
            ).first
            company_el = card.locator(".comp-name, a.subTitle, .companyInfo a, [class*='comp']").first
            loc_el = card.locator(".locWdth, .location, .loc, [class*='loc']").first
            snippet_el = card.locator(".job-desc, .ellipsis, .row3, [class*='desc']").first

            title = _get_text(title_el)
            company = _get_text(company_el)
            loc = _get_text(loc_el) or location
            snippet = _get_text(snippet_el)

            href = ""
            try:
                href = title_el.get_attribute("href") or ""
            except Exception:
                pass

            if not title:
                continue

            apply_url = href
            if apply_url and not apply_url.startswith("http"):
                apply_url = "https://www.naukri.com" + apply_url.split("?")[0]

            jobs.append({
                "title": _txt(title),
                "company": _txt(company) or "Unknown",
                "location": _txt(loc) or location,
                "date_posted": "Recent",
                "description": _txt(snippet) or f"{title} at {company} in {loc}. Apply link has full description.",
                "apply_url": apply_url,
                "portal": "naukri",
            })
        except Exception:
            continue

    return jobs


PORTAL_FNS = {
    "indeed": scrape_indeed,
    "naukri": scrape_naukri,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portal", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--max_jobs", type=int, default=20)
    parser.add_argument("--job_url", required=False, default="")
    args = parser.parse_args()

    # Dedicated mode: fetch + extract a single LinkedIn job description.
    # This is used by the backend when listing HTML is missing real JD text.
    if args.job_url:
        url = args.job_url
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()

                page.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
                    window.chrome = { runtime: {} };
                    """
                )

                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(3000)

                # Try common LinkedIn job description containers.
                selectors = [
                    "div.show-more-less-html__markup",
                    "div.jobs-unified-show-more-less-content__markup",
                    "div.description__text",
                    "section#job-details",
                    "[class*='job-description']",
                ]

                text = ""
                for sel in selectors:
                    try:
                        el = page.locator(sel).first
                        if el.count() > 0:
                            t = el.inner_text()
                            t = _txt(t)
                            if t and len(t) > 200:
                                text = t
                                break
                    except Exception:
                        continue

                if not text:
                    try:
                        el = page.locator("div#job-details").first
                        if el.count() > 0:
                            text = _txt(el.inner_text())
                    except Exception:
                        pass

                browser.close()

            print(json.dumps({"description": text}, ensure_ascii=False))
            return
        except Exception:
            print(json.dumps({"description": ""}, ensure_ascii=False))
            traceback.print_exc(file=sys.stderr)
            return

    fn = PORTAL_FNS.get(args.portal.lower())
    if not fn:
        print(json.dumps([]))
        print(f"[worker] unsupported portal: {args.portal}", file=sys.stderr)
        sys.exit(1)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()

            try:
                page.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
                    window.chrome = { runtime: {} };
                    """
                )
            except Exception:
                pass

            jobs = fn(page, context, args.role, args.location, args.max_jobs)
            browser.close()

        print(json.dumps(jobs, ensure_ascii=False))
    except Exception:
        print(json.dumps([]))
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
