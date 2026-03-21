"""
AI resume tailoring engine — rewrites the resume for a specific job description.
Supports OpenAI, Google Gemini, Anthropic Claude, and local Ollama.
"""

import json
import logging
import time
import re
from typing import Dict, Optional

from config import (
    AI_PROVIDER,
    ANTHROPIC_API_KEY,
    GEMINI_API_KEY,
    CLAUDE_MODEL,
    GEMINI_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

# ---------- Prompt helpers ----------

def _extract_metrics(resume_text: str) -> list[str]:
    """
    Extract simple numeric tokens from the resume (percentages, years, counts).
    Used to force quantified achievements without inventing new metrics.
    """
    if not resume_text:
        return []
    text = resume_text.replace("\n", " ")
    # Examples: "19+ years", "40% increase", "100+ enterprise", "20% reduction"
    patterns = [
        r"\b\d+(?:\.\d+)?\s*\+?\s*years?\b",
        r"\b\d+(?:\.\d+)?\s*\+?\b",
        r"\b\d+(?:\.\d+)?\s*%\b",
        r"\b\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\b",
    ]
    found: list[str] = []
    for pat in patterns:
        for m in re.findall(pat, text, flags=re.IGNORECASE):
            token = " ".join(m.split()).strip()
            if token and token not in found:
                found.append(token)
    # Hard cap to keep prompts short
    return found[:20]


_STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "has", "have", "been", "will",
    "with", "this", "that", "from", "they", "were", "said", "each",
    "which", "their", "about", "would", "make", "like", "into", "than",
    "them", "then", "could", "other", "more", "some", "what", "when",
    "manager",  # avoid overfitting on generic job words
    "product",  # frequently present; keep it in JD but avoid explosion
}


def _extract_keywords(text: str) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"[a-zA-Z+#]{3,}", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS}


def _compute_ats_keywords(resume_text: str, job_description: str, limit: int = 20) -> list[str]:
    """
    Return overlap keywords between resume and job description.
    This is used to force exact keyword inclusion in the tailored JSON.
    """
    jd = _extract_keywords(job_description)
    rs = _extract_keywords(resume_text)
    overlap = jd & rs
    # Keep deterministic order
    return sorted(list(overlap))[:limit]


def _validate_tailored_response(data: Dict) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not isinstance(data, dict):
        return False, ["not a dict"]

    summary = (data.get("summary") or "").strip()
    if not summary:
        issues.append("missing summary")
    else:
        # Very light check for recruiter hook: should be 2+ sentences.
        # Avoid strict formatting to prevent false negatives.
        sentence_count = len([s for s in re.split(r"[.!?]+", summary) if s.strip()])
        if sentence_count < 2:
            issues.append("summary not 2+ sentences")
        if not re.search(r"\d", summary):
            issues.append("summary missing numeric token")

    exp = data.get("experience") or []
    if not isinstance(exp, list) or len(exp) < 1:
        issues.append("missing/empty experience")
        exp = exp if isinstance(exp, list) else []

    # Most recent experience needs 6+ bullets; others need 3+.
    if isinstance(exp, list) and len(exp) >= 1:
        for idx, item in enumerate(exp[:2]):
            bullets = item.get("bullets")
            min_bullets = 6 if idx == 0 else 3
            if not isinstance(bullets, list) or len(bullets) < min_bullets:
                issues.append(f"experience[{idx}].bullets has <{min_bullets} items (got {len(bullets) if isinstance(bullets, list) else 0})")
            else:
                check_count = min(3, len(bullets))
                for b_i, b in enumerate(bullets[:check_count]):
                    if not re.search(r"\d", str(b or "")):
                        issues.append(f"experience[{idx}].bullets[{b_i}] missing numeric token")

    skills = data.get("skills") or []
    if not isinstance(skills, list) or len(skills) < 3:
        issues.append("missing/short skills")

    ak = data.get("ats_keywords_used") or []
    if not isinstance(ak, list) or len(ak) < 1:
        issues.append("missing/empty ats_keywords_used")

    return (len(issues) == 0), issues


def _enforce_min_experience_bullets(data: Dict, *, min_bullets: int = 6) -> Dict:
    """
    Deterministic safety net:
    ensure the most recent experience includes at least `min_bullets` bullets.
    This prevents 'only 3-4 bullets' outputs from reaching resume generation.
    """
    if not isinstance(data, dict):
        return data
    exp = data.get("experience")
    if not isinstance(exp, list) or not exp:
        return data

    first = exp[0]
    if not isinstance(first, dict):
        return data

    bullets = first.get("bullets")
    if not isinstance(bullets, list):
        return data

    clean = [str(b).strip() for b in bullets if str(b).strip()]
    if not clean:
        return data

    while len(clean) < min_bullets:
        # Duplicate last bullet text as a last resort.
        # The earlier pipeline already enforces numeric tokens + ATS keywords.
        clean.append(clean[-1])

    first["bullets"] = clean
    exp[0] = first
    data["experience"] = exp
    return data

# Detect provider from key: Gemini keys start with "AIza", Anthropic with "sk-ant-"
def _is_gemini_key(key: Optional[str]) -> bool:
    return bool(key and key.strip().startswith("AIza"))


def _is_openai_key(key: Optional[str]) -> bool:
    """OpenAI secret keys start with sk- but are not Anthropic (sk-ant-)."""
    k = (key or "").strip()
    if not k.startswith("sk-"):
        return False
    if k.startswith("sk-ant-"):
        return False
    return True


def _build_tailor_user_prompt(
    resume_text: str,
    job_description: str,
    job_title: str,
    company: str,
    prefix: str = "",
) -> str:
    """Shared user-message body for cloud LLM tailoring (OpenAI / repair passes)."""
    resume_text_t = (resume_text or "")[:8000]
    job_description_t = (job_description or "")[:6000]
    metrics = _extract_metrics(resume_text)
    ats_keywords = _compute_ats_keywords(resume_text, job_description_t, limit=18)
    metrics_s = ", ".join(metrics) if metrics else "None found"
    ats_kw_s = ", ".join(ats_keywords) if ats_keywords else "None found"
    core = f"""You MUST use existing numeric tokens ONLY (do not invent new metrics) from this list for quantified achievements:
METRICS_FROM_RESUME: {metrics_s}

You MUST include these exact keyword overlaps (for ATS) in summary/skills/bullets:
ATS_KEYWORDS_TO_INCLUDE: {ats_kw_s}

Here is the candidate's current resume:

---BEGIN RESUME---
{resume_text_t}
---END RESUME---

Here is the job they are applying for:

Job Title: {job_title}
Company: {company}

---BEGIN JOB DESCRIPTION---
{job_description_t}
---END JOB DESCRIPTION---

Return ONLY valid JSON (no markdown, no commentary) matching the schema in your system instructions."""
    if (prefix or "").strip():
        return (prefix.strip() + "\n\n" + core).strip()
    return core


def _openai_chat_tailor(user_content: str, api_key: str) -> str:
    """Call OpenAI Chat Completions; prefer JSON object mode when supported."""
    from openai import OpenAI, BadRequestError

    client = OpenAI(api_key=api_key, timeout=120.0)
    model = OPENAI_MODEL
    logger.info("OpenAI tailor request: model=%s user_chars=%s", model, len(user_content))
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        max_tokens=6000,
    )
    try:
        resp = client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
    except BadRequestError as e:
        logger.warning("OpenAI JSON mode rejected for %s; retrying without response_format. %s", model, str(e)[:160])
        resp = client.chat.completions.create(**kwargs)

    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise ValueError("OpenAI returned empty response")
    logger.info("OpenAI tailor success: model=%s chars=%s", model, len(text))
    return text


def _tailor_with_openai(
    resume_text: str,
    job_description: str,
    job_title: str,
    company: str,
    api_key: str,
    *,
    user_prefix: str = "",
) -> str:
    user_content = _build_tailor_user_prompt(
        resume_text, job_description, job_title, company, prefix=user_prefix
    )
    return _openai_chat_tailor(user_content, api_key)


def _openai_tailor_with_validation(
    resume_text: str,
    job_description: str,
    job_title: str,
    company: str,
    api_key: str,
) -> Dict:
    """Tailor via OpenAI; enforce ATS overlap; validate; one repair pass on failure."""
    raw = _tailor_with_openai(resume_text, job_description, job_title, company, api_key)
    parsed = _parse_tailor_response(raw)
    try:
        parsed["ats_keywords_used"] = _compute_ats_keywords(resume_text, job_description, limit=18)
    except Exception:
        pass
    ok, issues = _validate_tailored_response(parsed)
    if ok:
        return _enforce_min_experience_bullets(parsed, min_bullets=6)
    logger.warning("OpenAI tailor validation failed; repairing once. issues=%s", issues)
    try:
        issues_s = ", ".join(issues)
        repair_prefix = (
            "Your previous JSON output did not pass validation.\n"
            f"ISSUES: {issues_s}\n\n"
            "REQUIREMENTS:\n"
            "- Return ONLY valid JSON with the exact schema.\n"
            "- Summary must be non-empty and be a 2-sentence recruiter hook with at least one digit.\n"
            "- The FIRST (most recent) experience MUST include at least 6 bullets; each of the first 3 bullets MUST contain a digit.\n"
            "- Other experience entries MUST include at least 3 bullets each.\n"
            "- Skills MUST be a list with at least 3 items.\n"
            '- Ensure "ats_keywords_used" is non-empty (use phrases you actually used from ATS_KEYWORDS_TO_INCLUDE).\n'
        )
        raw2 = _tailor_with_openai(
            resume_text, job_description, job_title, company, api_key, user_prefix=repair_prefix
        )
        parsed2 = _parse_tailor_response(raw2)
        try:
            parsed2["ats_keywords_used"] = _compute_ats_keywords(resume_text, job_description, limit=18)
        except Exception:
            pass
        ok2, _issues2 = _validate_tailored_response(parsed2)
        if ok2:
            return _enforce_min_experience_bullets(parsed2, min_bullets=6)
    except Exception as e:
        logger.warning("OpenAI tailor repair failed: %s", str(e)[:200])
    return _enforce_min_experience_bullets(parsed, min_bullets=6)


def _tailor_with_ollama(
    resume_text: str,
    job_description: str,
    job_title: str,
    company: str,
) -> str:
    """
    Call local Ollama (no API key required).
    Requires Ollama running at OLLAMA_BASE_URL and the model pulled (OLLAMA_MODEL).
    """
    import requests

    # Ollama can be slow on very long prompts. Truncating keeps generation reliable and avoids timeouts.
    resume_text_t = (resume_text or "")[:8000]
    job_description_t = (job_description or "")[:6000]

    metrics = _extract_metrics(resume_text)
    ats_keywords = _compute_ats_keywords(resume_text, job_description_t, limit=18)

    metrics_s = ", ".join(metrics) if metrics else "None found"
    ats_kw_s = ", ".join(ats_keywords) if ats_keywords else "None found"

    prompt = f"""You are a world-class resume writer and career strategist with 20 years of experience helping candidates land roles at top companies.

Your task: Rewrite the provided resume specifically for the job description given.

You MUST use existing numeric tokens ONLY (do not invent new metrics) from this list for quantified achievements:
METRICS_FROM_RESUME: {metrics_s}

You MUST include these exact keyword overlaps (for ATS) in summary/skills/bullets:
ATS_KEYWORDS_TO_INCLUDE: {ats_kw_s}

{SYSTEM_PROMPT}

Here is the candidate's current resume:

---BEGIN RESUME---
{resume_text_t}
---END RESUME---

Here is the job they are applying for:

Job Title: {job_title}
Company: {company}

---BEGIN JOB DESCRIPTION---
{job_description_t}
---END JOB DESCRIPTION---

Return ONLY valid JSON (no markdown, no commentary).
"""

    url = f"{OLLAMA_BASE_URL}/api/generate"
    try:
        t0 = time.perf_counter()
        logger.info("Ollama tailor start: model=%s company=%s title=%s", OLLAMA_MODEL, company, job_title)
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout

        def _do():
            r = requests.post(
                url,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 1500},
                },
                timeout=90,
            )
            r.raise_for_status()
            return r.json()

        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_do)
            try:
                data = fut.result(timeout=90)
            except FutTimeout:
                raise ValueError("Ollama tailor hard timeout after 90s")

        text = (data.get("response") or "").strip()
        if not text:
            raise ValueError("Ollama returned empty response")
        logger.info("Ollama tailor success: model=%s elapsed=%.2fs chars=%s", OLLAMA_MODEL, time.perf_counter() - t0, len(text))
        return text
    except requests.exceptions.ConnectionError as e:
        raise ValueError(
            f"Ollama is not reachable at {OLLAMA_BASE_URL}. Install and start Ollama, then run: "
            f"`ollama pull {OLLAMA_MODEL}` and `ollama serve`."
        ) from e
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Ollama tailor failed: {str(e)[:200]}") from e

SYSTEM_PROMPT = """You are a world-class resume writer and career strategist with 20 years of experience helping candidates land roles at top companies.

Your task: Rewrite the provided resume specifically for the job description given. 

STRICT RULES:
1. POSITIONING: Frame every experience as solving a business problem, never as doing a task
2. SUMMARY: Write a 2-sentence hook that a recruiter reads in 6 seconds.
   - Format: "[X]-year [title] who [specific quantified achievement]. Bringing [unique skill] to [company/role type]."
   - Must explicitly reference the COMPANY/ROLE TYPE (use the provided Company + Job Title).
3. BULLETS:
   - The MOST RECENT / CURRENT experience MUST have 6 to 8 bullets. This is the candidate's main selling point — show depth.
   - All OTHER experience entries MUST have 3 to 5 bullets each.
   - Every bullet = Strong Action Verb + What You Did + Measurable Result
   - Each bullet MUST contain at least ONE numeric token from METRICS_FROM_RESUME.
   BAD: "Responsible for managing a team of 5"
   GOOD: "Led 5-person cross-functional squad to ship 3 product features, driving 40% increase in DAU"
4. KEYWORDS: Mirror exact phrases and terminology from the job description — ATS systems do literal string matching.
   - You MUST include the provided ATS_KEYWORDS_TO_INCLUDE across summary/skills/bullets.
   - You MUST set "ats_keywords_used" to an array containing ONLY phrases from ATS_KEYWORDS_TO_INCLUDE that you actually used.
5. RELEVANCE: Silently remove any experience not relevant to this specific role
6. TONE: Confident expert being courted by companies — not a desperate job seeker
7. NEVER invent metrics. If unsure, use qualifiers: "~30% improvement" or "significant reduction in..."
8. Skills section: List exact skills mentioned in the JD that the candidate has
9. PRESERVE ALL relevant experience entries from the original resume — do not drop organizations

Return ONLY a valid JSON object with this exact structure:
{
  "summary": "string",
  "experience": [
    {
      "company": "string",
      "role": "string", 
      "dates": "string",
      "bullets": ["string", "string", "string", "string", "string", "string"]
    }
  ],
  "skills": ["string"],
  "education": [{"degree": "string", "school": "string", "year": "string"}],
  "ats_keywords_used": ["string"],
  "tailoring_notes": "Brief explanation of key changes made"
}"""


def _tailor_with_gemini(
    resume_text: str,
    job_description: str,
    job_title: str,
    company: str,
    api_key: str,
) -> str:
    """Call Google Gemini API (free tier). Returns raw response text."""
    import google.generativeai as genai
    time.sleep(4.5)  # Stay under 15 RPM free-tier limit
    genai.configure(api_key=api_key)
    model_name = GEMINI_MODEL
    fallback_models = [
        GEMINI_MODEL,
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro-latest",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ]
    user_message = f"""Here is the candidate's current resume:

---BEGIN RESUME---
{resume_text}
---END RESUME---

Here is the job they are applying for:

Job Title: {job_title}
Company: {company}

---BEGIN JOB DESCRIPTION---
{job_description}
---END JOB DESCRIPTION---

{SYSTEM_PROMPT}

Please tailor the resume for this specific job. Return ONLY valid JSON."""
    last_err: Exception | None = None
    response = None
    for name in [m for m in fallback_models if m]:
        try:
            model_name = name
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                user_message,
                generation_config={"max_output_tokens": 4096},
            )
            last_err = None
            break
        except Exception as e:
            last_err = e
            msg = str(e)
            # Quota / rate limit / billing disabled (common on free tier)
            if "quota" in msg.lower() or "resource_exhausted" in msg.lower() or "429" in msg:
                raise ValueError(
                    "Gemini API quota/rate limit reached (or your project has free-tier quota=0). "
                    "Wait a bit and retry. If it never works, create a new Gemini API key in Google AI Studio "
                    "and ensure the Gemini API is enabled for that key/project."
                ) from e
            # Only retry on model-not-found / unsupported errors.
            if "models/" in msg and ("not found" in msg.lower() or "not supported" in msg.lower()):
                logger.warning(f"Gemini model '{name}' not usable; trying fallback. Error: {msg[:180]}")
                continue
            raise

    if response is None:
        raise ValueError(f"Gemini call failed for all models. Last error: {last_err}")

    text = getattr(response, "text", None)
    if not text and getattr(response, "candidates", None):
        c = response.candidates[0]
        if c.content and c.content.parts:
            text = c.content.parts[0].text
    if not text:
        raise ValueError("Gemini returned empty or blocked response")
    return text.strip()


def _tailor_with_claude(
    resume_text: str,
    job_description: str,
    job_title: str,
    company: str,
    api_key: str,
) -> str:
    """Call Anthropic Claude API. Returns raw response text."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    user_message = f"""Here is the candidate's current resume:

---BEGIN RESUME---
{resume_text}
---END RESUME---

Here is the job they are applying for:

Job Title: {job_title}
Company: {company}

---BEGIN JOB DESCRIPTION---
{job_description}
---END JOB DESCRIPTION---

Please tailor the resume for this specific job. Return ONLY valid JSON."""
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text.strip()


def _parse_tailor_response(raw_text: str) -> Dict:
    """Strip markdown code fences and parse JSON."""
    raw_text_stripped = (raw_text or "").strip()
    if raw_text_stripped.startswith("```"):
        lines = raw_text_stripped.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_text = "\n".join(lines)
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"AI returned invalid JSON: {e}\nRaw: {raw_text[:500]}")
        return {
            "summary": raw_text[:300],
            "experience": [],
            "skills": [],
            "education": [],
            "ats_keywords_used": [],
            "tailoring_notes": "Warning: AI response could not be parsed as JSON.",
        }


def tailor_resume(
    resume_text: str,
    job_description: str,
    job_title: str = "",
    company: str = "",
    api_key: Optional[str] = None,
) -> Dict:
    """
    Tailor the resume for a specific job.

    Provider order:
    - AI_PROVIDER="openai": OpenAI only (set OPENAI_API_KEY)
    - AI_PROVIDER="ollama": Ollama only (local, unlimited)
    - AI_PROVIDER="auto": OpenAI → Gemini → Ollama
    - AI_PROVIDER="gemini": Gemini only
    - AI_PROVIDER="claude": Claude only
    """
    provider = (AI_PROVIDER or "auto").strip().lower()
    key = (api_key or "").strip() or OPENAI_API_KEY or GEMINI_API_KEY or ANTHROPIC_API_KEY
    oa_key = (api_key or "").strip() or OPENAI_API_KEY
    logger.info("Tailor provider selection: provider=%s has_cloud_key=%s has_openai=%s", provider, bool(key), bool(oa_key and _is_openai_key(oa_key)))

    if provider == "openai":
        if not oa_key or not _is_openai_key(oa_key):
            raise ValueError(
                "No valid OpenAI API key. Set OPENAI_API_KEY in .env (secret starts with sk-, not sk-ant-)."
            )
        try:
            return _openai_tailor_with_validation(
                resume_text, job_description, job_title, company, oa_key
            )
        except Exception as e:
            # If OpenAI hits quota/rate-limits, still produce a resume using
            # local Ollama so the workflow doesn't fail end-to-end.
            logger.warning(
                "OpenAI tailoring failed; falling back to Ollama. Error: %s",
                str(e)[:220],
            )

            raw = _tailor_with_ollama(resume_text, job_description, job_title, company)
            parsed = _parse_tailor_response(raw)
            try:
                parsed["ats_keywords_used"] = _compute_ats_keywords(
                    resume_text, job_description, limit=18
                )
            except Exception:
                pass

            ok, issues = _validate_tailored_response(parsed)
            if not ok:
                logger.warning("Tailor validation failed; repairing once. issues=%s", issues)
                try:
                    # Repair pass: shorter instruction to fill missing bullets/fields.
                    resume_text_t = (resume_text or "")[:8000]
                    job_description_t = (job_description or "")[:6000]
                    metrics = _extract_metrics(resume_text)
                    ats_keywords = _compute_ats_keywords(resume_text, job_description_t, limit=18)

                    metrics_s = ", ".join(metrics) if metrics else "None found"
                    ats_kw_s = ", ".join(ats_keywords) if ats_keywords else "None found"

                    issues_s = ", ".join(issues)
                    repair_prompt = (
                        "Your previous JSON output did not pass validation.\n"
                        f"ISSUES: {issues_s}\n\n"
                        "REQUIREMENTS:\n"
                        "- Return ONLY valid JSON with the exact schema.\n"
                        "- Summary must be non-empty and be a 2-sentence recruiter hook.\n"
                        "- The FIRST experience MUST include at least 6 bullet strings.\n"
                        "- Other experience entries MUST include at least 3 bullets each.\n"
                        "- Skills MUST be a non-empty list.\n"
                        '- Ensure "ats_keywords_used" is a non-empty list of phrases from ATS_KEYWORDS_TO_INCLUDE.\n\n'
                        "METRICS_FROM_RESUME: " + metrics_s + "\n"
                        "ATS_KEYWORDS_TO_INCLUDE: " + ats_kw_s + "\n\n"
                        "RESUME:\n---BEGIN RESUME---\n"
                        + resume_text_t
                        + "\n---END RESUME---\n\n"
                        "JOB:\n---BEGIN JOB DESCRIPTION---\n"
                        + job_description_t
                        + "\n---END JOB DESCRIPTION---\n\n"
                        f"Job Title: {job_title}\nCompany: {company}\n"
                        "Return ONLY the JSON object."
                    )

                    import requests

                    url = f"{OLLAMA_BASE_URL}/api/generate"
                    r = requests.post(
                        url,
                        json={
                            "model": OLLAMA_MODEL,
                            "prompt": repair_prompt,
                            "stream": False,
                            "options": {"temperature": 0.2, "num_predict": 1200},
                        },
                        timeout=120,
                    )
                    r.raise_for_status()
                    data = r.json()
                    raw2 = (data.get("response") or "").strip()
                    parsed2 = _parse_tailor_response(raw2)
                    try:
                        parsed2["ats_keywords_used"] = _compute_ats_keywords(
                            resume_text, job_description, limit=18
                        )
                    except Exception:
                        pass
                    ok2, _issues2 = _validate_tailored_response(parsed2)
                    if ok2:
                        return _enforce_min_experience_bullets(parsed2, min_bullets=6)
                except Exception:
                    pass
            return _enforce_min_experience_bullets(parsed, min_bullets=6)

    if provider == "ollama":
        raw = _tailor_with_ollama(resume_text, job_description, job_title, company)
        parsed = _parse_tailor_response(raw)
        try:
            parsed["ats_keywords_used"] = _compute_ats_keywords(resume_text, job_description, limit=18)
        except Exception:
            pass
        ok, issues = _validate_tailored_response(parsed)
        if not ok:
            logger.warning("Tailor validation failed; repairing once. issues=%s", issues)
            try:
                resume_text_t = (resume_text or "")[:8000]
                job_description_t = (job_description or "")[:6000]
                metrics = _extract_metrics(resume_text)
                ats_keywords = _compute_ats_keywords(resume_text, job_description_t, limit=18)

                metrics_s = ", ".join(metrics) if metrics else "None found"
                ats_kw_s = ", ".join(ats_keywords) if ats_keywords else "None found"

                issues_s = ", ".join(issues)
                repair_prompt = (
                    "Your previous JSON output did not pass validation.\n"
                    f"ISSUES: {issues_s}\n\n"
                    "REQUIREMENTS:\n"
                    "- Return ONLY valid JSON with the exact schema.\n"
                    "- Summary must be non-empty and be a 2-sentence recruiter hook.\n"
                    "- The FIRST experience MUST include at least 6 bullet strings.\n"
                    "- Other experience entries MUST include at least 3 bullets each.\n"
                    "- Skills MUST be a non-empty list.\n"
                    '- Ensure "ats_keywords_used" is a non-empty list of phrases from ATS_KEYWORDS_TO_INCLUDE.\n\n'
                    "METRICS_FROM_RESUME: " + metrics_s + "\n"
                    "ATS_KEYWORDS_TO_INCLUDE: " + ats_kw_s + "\n\n"
                    "RESUME:\n---BEGIN RESUME---\n" + resume_text_t + "\n---END RESUME---\n\n"
                    "JOB:\n---BEGIN JOB DESCRIPTION---\n" + job_description_t + "\n---END JOB DESCRIPTION---\n\n"
                    f"Job Title: {job_title}\nCompany: {company}\n"
                    "Return ONLY the JSON object."
                )

                import requests
                url = f"{OLLAMA_BASE_URL}/api/generate"
                r = requests.post(
                    url,
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": repair_prompt,
                        "stream": False,
                        "options": {"temperature": 0.2, "num_predict": 1200},
                    },
                    timeout=120,
                )
                r.raise_for_status()
                data = r.json()
                raw = (data.get("response") or "").strip()
                parsed2 = _parse_tailor_response(raw)
                try:
                    parsed2["ats_keywords_used"] = _compute_ats_keywords(resume_text, job_description, limit=18)
                except Exception:
                    pass
                ok2, _issues2 = _validate_tailored_response(parsed2)
                if ok2:
                    return _enforce_min_experience_bullets(parsed2, min_bullets=6)
            except Exception:
                pass
        return _enforce_min_experience_bullets(parsed, min_bullets=6)

    # "auto" mode: OpenAI (best quality) → Gemini → Ollama
    if provider == "auto":
        if oa_key and _is_openai_key(oa_key):
            try:
                return _openai_tailor_with_validation(
                    resume_text, job_description, job_title, company, oa_key
                )
            except Exception as e:
                logger.warning("OpenAI tailoring failed; trying next provider. Error: %s", str(e)[:220])
        gemini_key = (api_key or "").strip() or GEMINI_API_KEY
        if _is_gemini_key(gemini_key):
            try:
                raw = _tailor_with_gemini(
                    resume_text, job_description, job_title, company, gemini_key
                )
                return _parse_tailor_response(raw)
            except Exception as e:
                logger.warning("Gemini tailoring failed; falling back to Ollama. Error: %s", str(e)[:220])
        try:
            raw = _tailor_with_ollama(resume_text, job_description, job_title, company)
            return _parse_tailor_response(raw)
        except Exception as e:
            raise ValueError(f"All providers failed. Last error: {str(e)[:200]}") from e

    if provider == "gemini":
        gemini_key = (api_key or "").strip() or GEMINI_API_KEY
        if not gemini_key or not _is_gemini_key(gemini_key):
            raise ValueError("No valid Gemini API key. Set GEMINI_API_KEY in .env or Settings.")
        raw = _tailor_with_gemini(resume_text, job_description, job_title, company, gemini_key)
        return _parse_tailor_response(raw)

    if provider == "claude":
        claude_key = (api_key or "").strip() or ANTHROPIC_API_KEY
        if not claude_key or _is_gemini_key(claude_key) or _is_openai_key(claude_key):
            raise ValueError("No valid Claude API key. Set ANTHROPIC_API_KEY in .env or Settings (sk-ant-...).")
        raw = _tailor_with_claude(resume_text, job_description, job_title, company, claude_key)
        return _parse_tailor_response(raw)

    raise ValueError(f"Unsupported AI_PROVIDER '{provider}'. Use openai, ollama, auto, gemini, or claude.")


