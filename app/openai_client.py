"""
Shared OpenAI API client used by ALL features (1, 2, 3, 4).
Single source of truth for model, retries, auth, and JSON parsing.
Supports real OpenAI calls with retry + graceful empty-string fallback
(callers handle mock logic themselves when this returns "").
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

from app.logger import log_event

logger = logging.getLogger(__name__)

OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
MAX_RETRIES = 3
RETRY_DELAY = 2.0


async def call_openai(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    """
    Call OpenAI chat completions API asynchronously.
    Returns raw text content. Retries on transient errors.
    Falls back to None if no API key set.
    """
    if not OPENAI_API_KEY:
        return ""  # Caller handles mock

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            t0 = time.perf_counter()
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(OPENAI_API_URL, json=payload, headers=headers)

            latency_ms = int((time.perf_counter() - t0) * 1000)

            if resp.status_code != 200:
                raise RuntimeError(f"OpenAI HTTP {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            log_event(logger, "openai_call", status="ok", latency_ms=latency_ms,
                      tokens=data.get("usage", {}).get("total_tokens", "?"))
            logger.debug("OpenAI raw response:\n%s", raw[:600])
            return raw

        except Exception as exc:
            last_error = exc
            logger.warning("OpenAI attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)

    logger.error("All OpenAI retries exhausted: %s", last_error)
    return ""


def parse_json_response(raw: str) -> dict:
    """Robustly parse JSON from LLM output, stripping markdown fences."""
    if not raw:
        raise ValueError("Empty response from LLM")

    # Strip ```json fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Extract first {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.error("Failed to parse JSON. Raw:\n%s", raw[:400])
    raise ValueError("Unparseable JSON from LLM")
