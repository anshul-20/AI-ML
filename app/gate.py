"""
Feature 2: AI Quality Gate Engine
Rule-based + AI-assisted evaluation to decide PASS / FAIL / REVIEW.
"""

import logging
from typing import List, Dict, Any, Tuple

from app.logger import log_event
from app.openai_client import call_openai, parse_json_response
from app.schemas import GateRequest, GateResponse

logger = logging.getLogger(__name__)

# ── Rule-based evaluation ────────────────────────────────────────────────────

def _has_severity(issues: List[Dict[str, Any]], *levels: str) -> bool:
    return any(i.get("severity") in levels for i in issues)


def rule_based_evaluate(req: GateRequest) -> Tuple[str, List[str], float]:
    """
    Pure rule-based gate logic.
    Returns (status, reasons, confidence).
    """
    reasons: List[str] = []
    fail_flags: List[str] = []
    review_flags: List[str] = []

    # FAIL conditions
    if _has_severity(req.issues, "critical"):
        fail_flags.append("Critical severity issue(s) detected")

    if req.ai_score < 5:
        fail_flags.append(f"AI score {req.ai_score:.1f} is below minimum threshold of 5.0")

    if req.lint_errors > 0:
        fail_flags.append(f"{req.lint_errors} lint error(s) must be resolved before merge")

    if fail_flags:
        return "FAIL", fail_flags, 0.95

    # REVIEW conditions
    if 5.0 <= req.ai_score <= 7.0:
        review_flags.append(f"AI score {req.ai_score:.1f} is in the review range (5–7)")

    if req.test_coverage < 80:
        review_flags.append(f"Test coverage {req.test_coverage:.1f}% is below 80% minimum")

    if _has_severity(req.issues, "high"):
        review_flags.append("High severity issue(s) require human review")

    if review_flags:
        return "REVIEW", review_flags, 0.80

    # PASS
    reasons.append(f"AI score {req.ai_score:.1f} exceeds threshold")
    reasons.append(f"Test coverage {req.test_coverage:.1f}% meets minimum")
    reasons.append("No high or critical severity issues")
    return "PASS", reasons, 0.90


# ── AI-assisted reasoning prompt ─────────────────────────────────────────────

_GATE_SYSTEM = (
    "You are a software quality gate evaluator. "
    "Analyze the provided metrics and return ONLY valid JSON with no markdown."
)

_GATE_PROMPT = """You are a software quality gate evaluator.

Input metrics:
- AI review score: {score}/10
- Test coverage: {coverage}%
- Lint errors: {lint}
- Issues summary: {issues_summary}

Based on these metrics, decide the gate status.

Rules:
- FAIL if: critical issues exist, score < 5, or lint_errors > 0
- REVIEW if: score between 5-7, or coverage < 80%
- PASS if: score > 7, no high/critical issues, coverage >= 80%

Return ONLY this JSON:
{{
  "status": "PASS" | "FAIL" | "REVIEW",
  "reasons": ["reason1", "reason2"],
  "confidence": 0.0-1.0
}}"""


def _build_issues_summary(issues: List[Dict[str, Any]]) -> str:
    if not issues:
        return "No issues found"
    counts: Dict[str, int] = {}
    for i in issues:
        sev = i.get("severity", "unknown")
        counts[sev] = counts.get(sev, 0) + 1
    return ", ".join(f"{v} {k}" for k, v in counts.items())


async def evaluate_gate(req: GateRequest) -> GateResponse:
    """
    Evaluate PR gate status using rule-based logic + optional AI reasoning.
    """
    log_event(logger, "gate_evaluate",
              score=req.ai_score, coverage=req.test_coverage,
              lint=req.lint_errors, issue_count=len(req.issues))

    # Always compute rule-based result (authoritative)
    rule_status, rule_reasons, rule_conf = rule_based_evaluate(req)

    # Try AI reasoning for richer explanation
    prompt = _GATE_PROMPT.format(
        score=req.ai_score,
        coverage=req.test_coverage,
        lint=req.lint_errors,
        issues_summary=_build_issues_summary(req.issues),
    )

    raw = await call_openai(prompt, system=_GATE_SYSTEM, max_tokens=512)

    if raw:
        try:
            ai_result = parse_json_response(raw)
            # Trust AI status only if it agrees with rules on FAIL
            ai_status = ai_result.get("status", rule_status)
            ai_reasons = ai_result.get("reasons", rule_reasons)
            ai_conf = float(ai_result.get("confidence", rule_conf))

            # Rule-based FAIL is always authoritative
            final_status = rule_status if rule_status == "FAIL" else ai_status
            log_event(logger, "gate_ai_result", status=ai_status, confidence=ai_conf)

            return GateResponse(
                status=final_status,
                reasons=ai_reasons,
                confidence=round(ai_conf, 2),
            )
        except Exception as exc:
            logger.warning("AI gate parsing failed, using rule-based: %s", exc)

    # Fallback: pure rule-based
    return GateResponse(
        status=rule_status,
        reasons=rule_reasons,
        confidence=rule_conf,
    )
