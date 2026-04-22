import json
import logging
import re
import sys


def setup_logging() -> None:
    """Configure structured logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_llm_json(raw: str) -> dict:
    """
    Robustly parse JSON from LLM output.
    Handles markdown fences, leading/trailing text, and minor formatting issues.
    """
    logger = logging.getLogger(__name__)

    # Step 1: try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Step 2: strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Step 3: extract first {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.error("Failed to parse LLM output as JSON. Raw response:\n%s", raw[:500])
    raise ValueError("LLM returned unparseable JSON.")


def fallback_review() -> dict:
    """Return a safe fallback response when LLM parsing fails completely."""
    return {
        "summary": "Review could not be completed due to a parsing error.",
        "score": 0.0,
        "issues": [],
        "strengths": [],
    }
