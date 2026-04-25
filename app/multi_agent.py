"""
Feature 3: Multi-Agent AI Review System
Three specialized agents: Code Quality, Security, Performance.
Each runs independently with a focused prompt, then results are aggregated.
"""

import asyncio
import logging
from typing import Dict, Any, List

from app.logger import log_event
from app.openai_client import call_openai, parse_json_response
from app.prompt import MAX_DIFF_CHARS
from app.schemas import AgentResult, MultiAgentResponse

logger = logging.getLogger(__name__)


# ── Agent prompts ─────────────────────────────────────────────────────────────

_AGENT_SYSTEM = (
    "You are a specialist code review agent. "
    "Return ONLY valid JSON. No markdown, no explanation outside JSON."
)

_QUALITY_PROMPT = """You are a CODE QUALITY specialist agent.

Focus ONLY on:
- Readability and naming conventions
- Code structure and modularity
- Maintainability and technical debt
- DRY principle violations
- Dead code or unnecessary complexity

DO NOT evaluate security or performance.

Git diff:
{diff}

Return ONLY this JSON:
{{
  "score": <float 0-10>,
  "summary": "2 sentence quality assessment",
  "issues": [
    {{
      "type": "style" | "best_practice",
      "severity": "low" | "medium" | "high",
      "file": "filename",
      "line": null,
      "title": "issue title",
      "description": "explanation",
      "suggestion": "fix"
    }}
  ]
}}"""

_SECURITY_PROMPT = """You are a SECURITY specialist agent.

Focus ONLY on:
- SQL/command injection vulnerabilities
- Hardcoded secrets, tokens, passwords
- Insecure deserialization
- OWASP Top 10 violations
- Missing authentication/authorization checks
- Unsafe use of user input

DO NOT evaluate code quality or performance.

Git diff:
{diff}

Return ONLY this JSON:
{{
  "score": <float 0-10>,
  "summary": "2 sentence security assessment",
  "issues": [
    {{
      "type": "security",
      "severity": "low" | "medium" | "high" | "critical",
      "file": "filename",
      "line": null,
      "title": "issue title",
      "description": "explanation",
      "suggestion": "fix"
    }}
  ]
}}"""

_PERFORMANCE_PROMPT = """You are a PERFORMANCE specialist agent.

Focus ONLY on:
- Inefficient algorithms (O(n²) where O(n) is possible)
- N+1 query patterns
- Unnecessary loops or re-computation
- Memory leaks or unbounded data structures
- Missing caching opportunities
- Blocking I/O in async context

DO NOT evaluate security or code style.

Git diff:
{diff}

Return ONLY this JSON:
{{
  "score": <float 0-10>,
  "summary": "2 sentence performance assessment",
  "issues": [
    {{
      "type": "performance",
      "severity": "low" | "medium" | "high",
      "file": "filename",
      "line": null,
      "title": "issue title",
      "description": "explanation",
      "suggestion": "fix"
    }}
  ]
}}"""


# ── Mock responses (no API key) ──────────────────────────────────────────────

def _mock_quality(diff: str) -> dict:
    has_type_hints = "->" in diff
    score = 8.5 if has_type_hints else 6.5
    issues = [] if has_type_hints else [{
        "type": "style", "severity": "low", "file": _first_file(diff),
        "line": None, "title": "Missing type hints",
        "description": "Functions lack type annotations.",
        "suggestion": "Add parameter and return type annotations.",
    }]
    return {"score": score, "summary": "Mock quality review.", "issues": issues}


def _mock_security(diff: str) -> dict:
    diff_lower = diff.lower()
    issues = []
    score = 9.0

    if 'query("select' in diff_lower or "query('select" in diff_lower or \
            ('select' in diff_lower and ('" +' in diff or "' +" in diff)):
        issues.append({
            "type": "security", "severity": "critical", "file": _first_file(diff),
            "line": None, "title": "SQL Injection",
            "description": "String concatenation in SQL query allows injection.",
            "suggestion": "Use parameterized queries.",
        })
        score = 1.0

    if any(k in diff_lower for k in ("password =", "secret =", "api_key =", "token =")):
        issues.append({
            "type": "security", "severity": "critical", "file": _first_file(diff),
            "line": None, "title": "Hardcoded Secret",
            "description": "Credential appears hardcoded in source.",
            "suggestion": "Use environment variables or secrets manager.",
        })
        score = min(score, 1.0)

    return {"score": score, "summary": "Mock security review.", "issues": issues}


def _mock_performance(diff: str) -> dict:
    issues = []
    score = 8.0
    if "for " in diff and "for " in diff[diff.find("for ") + 4:]:
        issues.append({
            "type": "performance", "severity": "medium", "file": _first_file(diff),
            "line": None, "title": "Possible nested loop",
            "description": "Nested iterations detected — may be O(n²).",
            "suggestion": "Consider using set/dict lookups or vectorized operations.",
        })
        score = 6.5
    return {"score": score, "summary": "Mock performance review.", "issues": issues}


def _first_file(diff: str) -> str:
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            return line[6:]
        if line.startswith("diff --git"):
            parts = line.split(" b/")
            if len(parts) > 1:
                return parts[-1]
    return "unknown"


# ── Agent runner ─────────────────────────────────────────────────────────────

async def _run_agent(name: str, prompt_template: str, diff: str,
                     mock_fn) -> AgentResult:
    """Run a single agent: call OpenAI or use mock, parse result."""
    diff_truncated = diff[:MAX_DIFF_CHARS]
    prompt = prompt_template.format(diff=diff_truncated)

    logger.info("Running agent: %s", name)
    raw = await call_openai(prompt, system=_AGENT_SYSTEM, max_tokens=800)

    if raw:
        try:
            data = parse_json_response(raw)
            log_event(logger, f"agent_{name}", score=data.get("score"),
                      issues=len(data.get("issues", [])))
            return AgentResult(
                score=max(0.0, min(10.0, float(data.get("score", 5.0)))),
                issues=data.get("issues", []),
                summary=data.get("summary", ""),
            )
        except Exception as exc:
            logger.warning("Agent %s parse error: %s — using mock", name, exc)

    # Fallback to mock
    data = mock_fn(diff)
    log_event(logger, f"agent_{name}_mock", score=data.get("score"))
    return AgentResult(
        score=max(0.0, min(10.0, float(data.get("score", 5.0)))),
        issues=data.get("issues", []),
        summary=data.get("summary", ""),
    )


async def run_multi_agent_review(diff: str) -> MultiAgentResponse:
    """
    Run all three agents concurrently, aggregate results.
    """
    log_event(logger, "multi_agent_start", diff_length=len(diff))

    quality_task = _run_agent("quality", _QUALITY_PROMPT, diff, _mock_quality)
    security_task = _run_agent("security", _SECURITY_PROMPT, diff, _mock_security)
    performance_task = _run_agent("performance", _PERFORMANCE_PROMPT, diff, _mock_performance)

    quality, security, performance = await asyncio.gather(
        quality_task, security_task, performance_task
    )

    final_score = round((quality.score + security.score + performance.score) / 3, 2)

    log_event(logger, "multi_agent_done",
              quality=quality.score, security=security.score,
              performance=performance.score, final=final_score)

    return MultiAgentResponse(
        code_quality=quality,
        security=security,
        performance=performance,
        final_score=final_score,
    )
