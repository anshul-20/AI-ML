"""
Utility helpers: JSON parsing and fallback review.
Logging setup lives in app.logger.
"""
import json
import logging
import re

# Re-export so main.py can still do: from app.utils import setup_logging
from app.logger import setup_logging  # noqa: F401


def parse_llm_json(raw: str) -> dict:
    """
    Robustly parse JSON from LLM output.
    Handles markdown fences, surrounding text, and minor formatting quirks.
    """
    logger = logging.getLogger(__name__)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.error("Failed to parse LLM JSON. Raw snippet:\n%s", raw[:500])
    raise ValueError("LLM returned unparseable JSON.")


def fallback_review() -> dict:
    """Safe fallback when LLM call or parsing fails completely."""
    return {
        "summary": "Review could not be completed due to an internal error.",
        "score": 0.0,
        "issues": [],
        "strengths": [],
    }
