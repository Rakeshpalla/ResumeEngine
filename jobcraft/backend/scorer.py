"""
Job scoring and ranking engine.
Scores each job on 4 dimensions; subjective scores use OpenAI, Gemini, Claude, or Ollama.
"""

import json
import re
import logging
import time
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


def _is_gemini_key(key: Optional[str]) -> bool:
    return bool(key and key.strip().startswith("AIza"))


def _is_openai_key(key: Optional[str]) -> bool:
    k = (key or "").strip()
    if not k.startswith("sk-"):
        return False
    if k.startswith("sk-ant-"):
        return False
    return True


def _ollama_post(url: str, payload: dict, hard_timeout: float = 45) -> dict:
    """POST to Ollama with a hard wall-clock timeout using a thread."""
    import requests
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout

    def _do():
        r = requests.post(url, json=payload, timeout=hard_timeout)
        r.raise_for_status()
        return r.json()

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_do)
        try:
            return fut.result(timeout=hard_timeout)
        except FutTimeout:
            raise TimeoutError(f"Ollama hard timeout after {hard_timeout}s")


def _ask_ollama_for_score(prompt: str) -> Dict:
    """
    Use local Ollama (no API key required) to rate 0–100 with reasoning.
    Returns {score, reasoning}. Falls back to a neutral score on JSON parse issues.
    """
    system = (
        "You are an expert recruiter. "
        "Rate the following on a scale of 0 to 100 and explain briefly. "
        "Return ONLY a JSON object: {\"score\": <number>, \"reasoning\": \"<string>\"}"
    )
    prompt_trimmed = prompt[:1500]
    full_prompt = f"{system}\n\n{prompt_trimmed}"
    url = f"{OLLAMA_BASE_URL}/api/generate"
    try:
        t0 = time.perf_counter()
        logger.info("Ollama score start: model=%s prompt_len=%s", OLLAMA_MODEL, len(prompt_trimmed))
        data = _ollama_post(url, {
            "model": OLLAMA_MODEL,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 200},
        }, hard_timeout=45)
        raw = (data.get("response") or "").strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)
        try:
            out = json.loads(raw)
            if "score" not in out:
                raise ValueError("Missing score field")
            logger.info("Ollama score success: model=%s elapsed=%.2fs score=%s", OLLAMA_MODEL, time.perf_counter() - t0, out.get("score"))
            return {"score": float(out["score"]), "reasoning": str(out.get("reasoning", ""))[:500]}
        except Exception:
            logger.warning("Ollama score parse fallback: model=%s elapsed=%.2fs", OLLAMA_MODEL, time.perf_counter() - t0)
            return {"score": 50.0, "reasoning": raw[:200]}
    except Exception as e:
        logger.warning("Ollama score error: %s", str(e)[:200])
        raise ValueError(f"Ollama scoring failed: {str(e)[:200]}") from e


def _extract_keywords(text: str) -> set:
    """Extract meaningful keywords (3+ chars) from text, lowercased."""
    words = re.findall(r"[a-zA-Z+#]{3,}", text.lower())
    stop = {
        "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
        "her", "was", "one", "our", "out", "has", "have", "been", "will",
        "with", "this", "that", "from", "they", "were", "said", "each",
        "which", "their", "about", "would", "make", "like", "into", "than",
        "them", "then", "could", "other", "more", "some", "what", "when",
    }
    return {w for w in words if w not in stop}


def compute_ats_score(resume_text: str, job_description: str) -> float:
    jd_keywords = _extract_keywords(job_description)
    resume_keywords = _extract_keywords(resume_text)
    if not jd_keywords:
        return 0.0
    overlap = jd_keywords & resume_keywords
    return round((len(overlap) / len(jd_keywords)) * 100, 1)


def compute_keyword_match(tailored_resume: Dict, job_description: str) -> float:
    resume_parts = []
    resume_parts.append(tailored_resume.get("summary", ""))
    for exp in tailored_resume.get("experience", []):
        resume_parts.append(exp.get("role", ""))
        resume_parts.extend(exp.get("bullets", []))
    resume_parts.extend(tailored_resume.get("skills", []))
    resume_text = " ".join(resume_parts).lower()
    jd_keywords = _extract_keywords(job_description)
    resume_keywords = _extract_keywords(resume_text)
    if not jd_keywords:
        return 0.0
    overlap = jd_keywords & resume_keywords
    return round((len(overlap) / len(jd_keywords)) * 100, 1)


def _ask_gemini_for_score(prompt: str, api_key: str) -> Dict:
    """Use Google Gemini (free) to rate 0–100 with reasoning."""
    import google.generativeai as genai
    time.sleep(4.5)  # Stay under 15 RPM free-tier limit
    genai.configure(api_key=api_key)
    fallback_models = [
        GEMINI_MODEL,
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro-latest",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ]
    system = (
        "You are an expert recruiter. "
        "Rate the following on a scale of 0 to 100 and explain briefly. "
        "Return ONLY a JSON object: {\"score\": <number>, \"reasoning\": \"<string>\"}"
    )
    full_prompt = f"{system}\n\n{prompt}"
    last_err: Exception | None = None
    response = None
    for name in [m for m in fallback_models if m]:
        try:
            model = genai.GenerativeModel(name)
            response = model.generate_content(full_prompt, generation_config={"max_output_tokens": 500})
            last_err = None
            break
        except Exception as e:
            last_err = e
            msg = str(e)
            # Quota / rate limit / billing disabled (common on free tier)
            if "quota" in msg.lower() or "resource_exhausted" in msg.lower() or "429" in msg:
                logger.warning(f"Gemini quota/rate limit hit. Error: {msg[:220]}")
                return {"score": 50.0, "reasoning": f"Gemini quota/rate limit reached. Try again later. Details: {msg[:160]}"}
            if "models/" in msg and ("not found" in msg.lower() or "not supported" in msg.lower()):
                logger.warning(f"Gemini model '{name}' not usable; trying fallback. Error: {msg[:180]}")
                continue
            raise

    if response is None:
        return {"score": 50.0, "reasoning": f"Gemini call failed for all models: {str(last_err)[:200]}"}

    text = getattr(response, "text", None)
    if not text and getattr(response, "candidates", None) and response.candidates and response.candidates[0].content.parts:
        text = response.candidates[0].content.parts[0].text
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"score": 50.0, "reasoning": raw[:200]}


def _ask_openai_for_score(prompt: str, api_key: str) -> Dict:
    """Use OpenAI Chat Completions for 0–100 score + reasoning JSON."""
    from openai import OpenAI, BadRequestError

    system = (
        "You are an expert recruiter. "
        "Rate the following on a scale of 0 to 100 and explain briefly. "
        "Return ONLY a JSON object: {\"score\": <number>, \"reasoning\": \"<string>\"}"
    )
    client = OpenAI(api_key=api_key, timeout=60.0)
    user = (prompt or "")[:1500]
    kwargs = dict(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=350,
    )
    try:
        resp = client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
    except BadRequestError:
        resp = client.chat.completions.create(**kwargs)
    raw = (resp.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines)
    try:
        out = json.loads(raw)
        return {"score": float(out["score"]), "reasoning": str(out.get("reasoning", ""))[:500]}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {"score": 50.0, "reasoning": raw[:200]}


def _ask_claude_for_score(prompt: str, api_key: str) -> Dict:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        system=(
            "You are an expert recruiter. "
            "Rate the following on a scale of 0 to 100 and explain briefly. "
            "Return ONLY a JSON object: {\"score\": <number>, \"reasoning\": \"<string>\"}"
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"score": 50.0, "reasoning": raw[:200]}


def _ask_ai_for_score(prompt: str, api_key: Optional[str] = None) -> Dict:
    """
    Use Ollama (local) / Gemini / Claude to rate 0–100. Returns {score, reasoning}.

    Provider order:
    - AI_PROVIDER="openai": OpenAI only
    - AI_PROVIDER="ollama": Ollama only
    - AI_PROVIDER="auto": OpenAI → Gemini → Ollama
    - AI_PROVIDER="gemini": Gemini only
    - AI_PROVIDER="claude": Claude only
    """
    provider = (AI_PROVIDER or "auto").strip().lower()
    key = (api_key or "").strip() or OPENAI_API_KEY or GEMINI_API_KEY or ANTHROPIC_API_KEY
    oa_key = (api_key or "").strip() or OPENAI_API_KEY
    logger.info("Score provider selection: provider=%s has_cloud_key=%s", provider, bool(key))

    if provider == "openai":
        if not oa_key or not _is_openai_key(oa_key):
            return {"score": 50.0, "reasoning": "No valid OpenAI API key. Set OPENAI_API_KEY in .env."}
        try:
            return _ask_openai_for_score(prompt, oa_key)
        except Exception as e:
            logger.warning("OpenAI scoring failed; falling back to Ollama. Error: %s", str(e)[:220])
            try:
                return _ask_ollama_for_score(prompt)
            except Exception:
                return {"score": 50.0, "reasoning": f"OpenAI error: {str(e)[:180]}"}

    if provider == "ollama":
        try:
            return _ask_ollama_for_score(prompt)
        except Exception as e:
            return {"score": 50.0, "reasoning": f"Ollama error: {str(e)[:180]}"}

    # "auto" mode: OpenAI → Gemini → Ollama
    if provider == "auto":
        if oa_key and _is_openai_key(oa_key):
            try:
                return _ask_openai_for_score(prompt, oa_key)
            except Exception as e:
                logger.warning("OpenAI scoring failed; trying Gemini/Ollama. Error: %s", str(e)[:220])
        gemini_key = (api_key or "").strip() or GEMINI_API_KEY
        if _is_gemini_key(gemini_key):
            try:
                return _ask_gemini_for_score(prompt, gemini_key)
            except Exception as e:
                logger.warning("Gemini scoring failed; falling back to Ollama. Error: %s", str(e)[:220])
        try:
            return _ask_ollama_for_score(prompt)
        except Exception as e:
            return {"score": 50.0, "reasoning": f"All providers failed: {str(e)[:180]}"}

    if provider == "gemini":
        gemini_key = (api_key or "").strip() or GEMINI_API_KEY
        if not gemini_key or not _is_gemini_key(gemini_key):
            return {"score": 50.0, "reasoning": "No valid Gemini API key."}
        return _ask_gemini_for_score(prompt, gemini_key)

    if provider == "claude":
        claude_key = (api_key or "").strip() or ANTHROPIC_API_KEY
        if not claude_key or _is_gemini_key(claude_key) or _is_openai_key(claude_key):
            return {"score": 50.0, "reasoning": "No valid Claude API key."}
        return _ask_claude_for_score(prompt, claude_key)

    return {"score": 50.0, "reasoning": f"Unsupported AI_PROVIDER '{provider}'."}


def compute_experience_fit(
    resume_text: str,
    job_description: str,
    api_key: Optional[str] = None,
) -> Dict:
    prompt = (
        f"Rate how well this candidate's resume matches the job requirements (0–100).\n\n"
        f"RESUME:\n{resume_text[:1000]}\n\n"
        f"JOB DESCRIPTION:\n{job_description[:1000]}"
    )
    return _ask_ai_for_score(prompt, api_key)


def compute_recruiter_hook(
    summary: str,
    job_title: str,
    api_key: Optional[str] = None,
) -> Dict:
    prompt = (
        f"Rate this resume summary on how well it hooks a recruiter in 6 seconds "
        f"for a '{job_title}' role (0–100).\n\nSUMMARY:\n{summary}"
    )
    return _ask_ai_for_score(prompt, api_key)


def compute_composite_score(
    ats: float,
    keyword: float,
    experience_fit: float,
    recruiter_hook: float,
) -> float:
    return round(
        (ats * 0.30) + (keyword * 0.30) + (experience_fit * 0.25) + (recruiter_hook * 0.15),
        1,
    )


def assign_grade(composite: float) -> str:
    if composite >= 85:
        return "A"
    elif composite >= 70:
        return "B"
    elif composite >= 55:
        return "C"
    return "D"


def _ollama_dual_fit_hook_scores(
    resume_text: str,
    job_description: str,
    summary: str,
    job_title: str,
) -> tuple[Dict, Dict]:
    """
    One Ollama generation for both subjective scores (replaces two sequential LLM calls).
    Cuts typical scoring time roughly in half vs separate fit + hook calls.
    """
    import requests
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout

    resume_t = (resume_text or "")[:1200]
    jd_t = (job_description or "")[:1200]
    summary_t = (summary or "")[:900]
    jt = (job_title or "")[:120]

    system = (
        "You are an expert recruiter. Return ONLY valid JSON (no markdown, no commentary) with this exact shape:\n"
        '{"experience_fit":{"score":<number 0-100>,"reasoning":"<string>"},'
        '"recruiter_hook":{"score":<number 0-100>,"reasoning":"<string>"}}\n\n'
        "experience_fit: how well the RESUME matches the JOB DESCRIPTION (0-100).\n"
        f"recruiter_hook: how well the SUMMARY hooks a recruiter in 6 seconds for role '{jt}' (0-100).\n"
    )
    user = f"RESUME:\n{resume_t}\n\nJOB DESCRIPTION:\n{jd_t}\n\nSUMMARY:\n{summary_t}"
    full_prompt = f"{system}\n{user}"

    url = f"{OLLAMA_BASE_URL}/api/generate"

    def _do():
        r = requests.post(
            url,
            json={
                "model": OLLAMA_MODEL,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 420},
            },
            timeout=90,
        )
        r.raise_for_status()
        return r.json()

    t0 = time.perf_counter()
    logger.info("Ollama dual-score start: model=%s job_title=%s", OLLAMA_MODEL, jt)
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_do)
        try:
            data = fut.result(timeout=95)
        except FutTimeout:
            raise TimeoutError("Ollama dual-score hard timeout after 95s") from None

    raw = (data.get("response") or "").strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        raw = "\n".join(lines)
    try:
        out = json.loads(raw)
        ef = out.get("experience_fit") or {}
        rh = out.get("recruiter_hook") or {}
        fit_result = {
            "score": float(ef.get("score", 50)),
            "reasoning": str(ef.get("reasoning", ""))[:500],
        }
        hook_result = {
            "score": float(rh.get("score", 50)),
            "reasoning": str(rh.get("reasoning", ""))[:500],
        }
        logger.info(
            "Ollama dual-score success: elapsed=%.2fs fit=%s hook=%s",
            time.perf_counter() - t0,
            fit_result["score"],
            hook_result["score"],
        )
        return fit_result, hook_result
    except Exception as e:
        logger.warning("Ollama dual-score JSON parse failed: %s raw=%s", str(e)[:120], raw[:200])
        raise


def score_job(
    resume_text: str,
    job_description: str,
    tailored_resume: Dict,
    job_title: str = "",
    api_key: Optional[str] = None,
) -> Dict:
    tailored_text_parts = [tailored_resume.get("summary", "")]
    for exp in tailored_resume.get("experience", []):
        tailored_text_parts.append(exp.get("role", ""))
        tailored_text_parts.extend(exp.get("bullets", []))
    tailored_text_parts.extend(tailored_resume.get("skills", []))
    tailored_flat = " ".join(tailored_text_parts)

    ats = compute_ats_score(tailored_flat, job_description)
    keyword = compute_keyword_match(tailored_resume, job_description)

    provider = (AI_PROVIDER or "auto").strip().lower()
    summary = tailored_resume.get("summary", "") or ""

    # Ollama: one combined call beats two slow sequential generations.
    if provider == "ollama":
        try:
            fit_result, hook_result = _ollama_dual_fit_hook_scores(
                resume_text, job_description, summary, job_title
            )
        except Exception as e:
            logger.warning("Ollama dual-score failed; falling back to 2 calls. %s", str(e)[:200])
            fit_result = compute_experience_fit(resume_text, job_description, api_key)
            hook_result = compute_recruiter_hook(summary, job_title, api_key)
    else:
        # Cloud APIs: run fit + hook in parallel (was fully sequential before).
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_fit = pool.submit(compute_experience_fit, resume_text, job_description, api_key)
            fut_hook = pool.submit(compute_recruiter_hook, summary, job_title, api_key)
            fit_result = fut_fit.result()
            hook_result = fut_hook.result()

    composite = compute_composite_score(
        ats, keyword, fit_result["score"], hook_result["score"]
    )

    return {
        "ats_score": ats,
        "keyword_score": keyword,
        "experience_fit_score": fit_result["score"],
        "recruiter_hook_score": hook_result["score"],
        "composite_score": composite,
        "grade": assign_grade(composite),
        "experience_fit_reasoning": fit_result.get("reasoning", ""),
        "recruiter_hook_reasoning": hook_result.get("reasoning", ""),
    }
