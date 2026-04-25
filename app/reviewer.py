"""
Feature 1: AI Code Review Agent — powered by OpenAI GPT.
Accepts a Git diff, sends it to OpenAI, returns a structured JSON review.
No Anthropic/Claude dependency.
"""

import logging
from typing import Optional

from app.logger import log_event
from app.openai_client import call_openai, parse_json_response
from app.prompt import build_prompt
from app.schemas import ReviewResponse
from app.utils import fallback_review

logger = logging.getLogger(__name__)

# System prompt keeps the LLM strictly in "code reviewer" mode
_REVIEW_SYSTEM = (
    "You are a senior staff-level software engineer performing a professional code review. "
    "Return ONLY valid JSON. No markdown, no commentary outside JSON."
)


def _extract_file_from_diff(diff: str) -> str:
    """Extract the first modified filename from a git diff header."""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            return line[6:]
        if line.startswith("diff --git"):
            parts = line.split(" b/")
            if len(parts) > 1:
                return parts[-1]
    return "unknown"


def _mock_review(diff: str) -> dict:
    """
    Heuristic mock review used when OPENAI_API_KEY is not set.
    Detects SQL injection, hardcoded secrets, and missing type hints.
    """
    issues = []
    score = 8.5
    diff_lower = diff.lower()
    fname = _extract_file_from_diff(diff)

    # SQL injection
    if ("select" in diff_lower and '"+' in diff) or "' +" in diff or "query(" in diff_lower:
        issues.append({
            "type": "security",
            "severity": "critical",
            "file": fname,
            "line": None,
            "title": "SQL Injection Vulnerability",
            "description": (
                "String concatenation is used to build a SQL query. "
                "Attackers can manipulate the query structure via user-controlled input."
            ),
            "suggestion": (
                "Use parameterized queries or an ORM. "
                "Example: db.query('SELECT * FROM users WHERE id = %s', (id,))"
            ),
        })
        score = 2.0

    # Hardcoded secrets
    if any(kw in diff_lower for kw in ("password =", "secret =", "api_key =", "token =")):
        issues.append({
            "type": "security",
            "severity": "critical",
            "file": fname,
            "line": None,
            "title": "Hardcoded Secret",
            "description": "A credential or secret appears to be hardcoded in the source.",
            "suggestion": "Move secrets to environment variables or a secrets manager (e.g. AWS Secrets Manager).",
        })
        score = min(score, 2.0)

    # Missing type hints
    if "def " in diff and "->" not in diff:
        issues.append({
            "type": "style",
            "severity": "low",
            "file": fname,
            "line": None,
            "title": "Missing Type Hints",
            "description": "Function definitions lack return type and/or parameter annotations.",
            "suggestion": "Add type annotations: def get_user(id: int) -> User:",
        })
        score = min(score, 7.5)

    strengths = [] if issues else [
        "No obvious issues detected.",
        "Code appears clean and readable.",
    ]
    if not issues:
        score = 9.0

    return {
        "summary": (
            f"Mock review — {len(issues)} issue(s) detected via pattern analysis. "
            "Set OPENAI_API_KEY for a full GPT-powered review."
        ),
        "score": score,
        "issues": issues,
        "strengths": strengths,
    }


async def call_llm(diff: str) -> dict:
    """
    Build the review prompt and call OpenAI.
    Falls back to heuristic mock when no API key is configured.
    Retry logic is handled inside openai_client.call_openai.
    """
    prompt = build_prompt(diff)
    log_event(logger, "review_prompt_built", length=len(prompt))

    raw = await call_openai(prompt, system=_REVIEW_SYSTEM, max_tokens=2048)

    if not raw:
        logger.warning("No OpenAI response — using mock review (OPENAI_API_KEY not set?)")
        return _mock_review(diff)

    try:
        result = parse_json_response(raw)
        log_event(logger, "review_parsed",
                  score=result.get("score"), issues=len(result.get("issues", [])))
        return result
    except Exception as exc:
        logger.error("Failed to parse OpenAI review response: %s", exc)
        return fallback_review()


async def perform_review(diff: str) -> ReviewResponse:
    """
    Full review pipeline:
      1. Build prompt
      2. Call OpenAI (with retry + mock fallback)
      3. Validate and clamp score
      4. Return typed ReviewResponse
    """
    raw_result = await call_llm(diff)

    # Clamp score to valid [0, 10] range
    raw_result["score"] = max(0.0, min(10.0, float(raw_result.get("score", 0))))

    logger.info("review_complete | score=%.1f issues=%d strengths=%d",
                raw_result["score"],
                len(raw_result.get("issues", [])),
                len(raw_result.get("strengths", [])))

    return ReviewResponse(**raw_result)
