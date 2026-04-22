import asyncio
import logging
import os
from typing import Optional

import httpx

from app.prompt import build_prompt
from app.schemas import ReviewResponse
from app.utils import parse_llm_json, fallback_review

logger = logging.getLogger(__name__)

OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds


async def call_llm(diff: str) -> dict:
    """
    Call the LLM (OpenAI) with the review prompt.
    Falls back to a mock response if no API key is configured.
    Retries up to MAX_RETRIES times on transient failures.
    """
    prompt = build_prompt(diff)
    logger.info("Prompt built | length=%d chars", len(prompt))

    if not OPENAI_API_KEY:
        logger.warning("No OPENAI_API_KEY set \u2014 using mock LLM response.")
        return _mock_llm_response(diff)

    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await _call_openai(prompt)
            return result
        except Exception as exc:
            last_error = exc
            logger.warning("LLM call attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)

    logger.error("All LLM retries exhausted. Last error: %s", last_error)
    return fallback_review()


async def _call_openai(prompt: str) -> dict:
    """Make the HTTP call to the OpenAI chat completions API."""
    payload = {
        "model": OPENAI_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": "You must output valid STRICT JSON matching the required schema. Do not output markdown, just the JSON."},
            {"role": "user", "content": prompt}
        ],
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers=headers,
        )

    if response.status_code != 200:
        raise RuntimeError(f"OpenAI API error {response.status_code}: {response.text[:300]}")

    data = response.json()
    raw_text = data["choices"][0]["message"]["content"]
    logger.debug("Raw LLM response:\n%s", raw_text[:1000])

    return parse_llm_json(raw_text)


def _mock_llm_response(diff: str) -> dict:
    """
    Deterministic mock response for testing without an API key.
    Detects obvious patterns (SQL injection, hardcoded secrets) for realistic output.
    """
    issues = []
    strengths = []
    score = 8.5

    diff_lower = diff.lower()

    # SQL injection detection
    if "select" in diff_lower and '"+' in diff or "' +" in diff or "query(" in diff_lower:
        issues.append({
            "type": "security",
            "severity": "critical",
            "file": _extract_file_from_diff(diff),
            "line": None,
            "title": "SQL Injection Vulnerability",
            "description": (
                "String concatenation is used to build a SQL query, which allows "
                "attackers to manipulate the query structure via user-controlled input."
            ),
            "suggestion": (
                "Use parameterized queries or an ORM. "
                "E.g., db.query('SELECT * FROM users WHERE id = %s', (id,))"
            ),
        })
        score = 2.0

    # Hardcoded secret detection
    if any(kw in diff_lower for kw in ("password =", "secret =", "api_key =", "token =")):
        issues.append({
            "type": "security",
            "severity": "critical",
            "file": _extract_file_from_diff(diff),
            "line": None,
            "title": "Hardcoded Secret",
            "description": "A secret or credential appears to be hardcoded in the source.",
            "suggestion": "Move secrets to environment variables or a secrets manager.",
        })
        score = min(score, 2.0)

    # Missing type hints
    if "def " in diff and "->" not in diff:
        issues.append({
            "type": "style",
            "severity": "low",
            "file": _extract_file_from_diff(diff),
            "line": None,
            "title": "Missing Type Hints",
            "description": "Function definitions lack return type annotations.",
            "suggestion": "Add type hints for all function parameters and return values.",
        })
        score = min(score, 7.5)

    if not issues:
        strengths = ["No obvious issues detected.", "Code appears clean and readable."]
        score = 9.0

    return {
        "summary": (
            "Mock review: detected patterns analyzed. "
            f"{len(issues)} issue(s) found. "
            "Enable OPENAI_API_KEY for a full AI-powered review."
        ),
        "score": score,
        "issues": issues,
        "strengths": strengths,
    }


def _extract_file_from_diff(diff: str) -> str:
    """Try to extract the first modified filename from a git diff."""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            return line[6:]
        if line.startswith("diff --git"):
            parts = line.split(" b/")
            if len(parts) > 1:
                return parts[-1]
    return "unknown"


async def perform_review(diff: str) -> ReviewResponse:
    """Orchestrate the full review: call LLM \u2192 validate \u2192 return response."""
    raw_result = await call_llm(diff)
    logger.info("Parsed review | score=%.1f issues=%d strengths=%d",
                raw_result.get("score", 0),
                len(raw_result.get("issues", [])),
                len(raw_result.get("strengths", [])))

    # Clamp score to valid range
    raw_result["score"] = max(0.0, min(10.0, float(raw_result.get("score", 0))))

    return ReviewResponse(**raw_result)
