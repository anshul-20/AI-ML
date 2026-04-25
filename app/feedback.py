"""
Feature 6: Feedback Loop System
Stores AI review outputs + human feedback for future prompt tuning and analytics.
Uses a simple JSON file store (drop-in replacement for a DB in production).
"""

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logger import log_event
from app.schemas import FeedbackRequest, FeedbackResponse

logger = logging.getLogger(__name__)

FEEDBACK_STORE_PATH = Path(os.getenv("FEEDBACK_STORE", "feedback_store.json"))


# ── Storage helpers ──────────────────────────────────────────────────────────

def _load_store() -> List[Dict[str, Any]]:
    if FEEDBACK_STORE_PATH.exists():
        try:
            with open(FEEDBACK_STORE_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read feedback store: %s", exc)
    return []


def _save_store(records: List[Dict[str, Any]]) -> None:
    try:
        with open(FEEDBACK_STORE_PATH, "w") as f:
            json.dump(records, f, indent=2)
    except OSError as exc:
        logger.error("Could not write feedback store: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────

def save_feedback(req: FeedbackRequest, ai_output: Optional[Dict] = None) -> str:
    """
    Persist feedback + AI output to the feedback store.
    Returns the feedback_id.
    """
    feedback_id = str(uuid.uuid4())[:8]
    record = {
        "feedback_id": feedback_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pr_id": req.pr_id,
        "accepted": req.accepted,
        "false_positive": req.false_positive,
        "comments": req.comments,
        "ai_output": ai_output or {},
    }

    records = _load_store()
    records.append(record)
    _save_store(records)

    log_event(logger, "feedback_saved",
              feedback_id=feedback_id, pr_id=req.pr_id,
              accepted=req.accepted, false_positive=req.false_positive)
    return feedback_id


def get_all_feedback() -> List[Dict[str, Any]]:
    """Return all stored feedback entries."""
    return _load_store()


def get_feedback_stats() -> Dict[str, Any]:
    """Compute simple analytics over stored feedback."""
    records = _load_store()
    if not records:
        return {"total": 0, "accepted": 0, "rejected": 0,
                "false_positive_rate": 0.0, "acceptance_rate": 0.0}

    total = len(records)
    accepted = sum(1 for r in records if r.get("accepted"))
    false_positives = sum(1 for r in records if r.get("false_positive"))

    return {
        "total": total,
        "accepted": accepted,
        "rejected": total - accepted,
        "false_positives": false_positives,
        "acceptance_rate": round(accepted / total, 2),
        "false_positive_rate": round(false_positives / total, 2),
    }


async def handle_feedback(req: FeedbackRequest) -> FeedbackResponse:
    """Handle incoming feedback from the API endpoint."""
    feedback_id = save_feedback(req)
    msg = (
        "Thank you — feedback recorded and will be used for model improvement."
        if req.accepted
        else "Feedback recorded. We'll use this to reduce false positives."
    )
    return FeedbackResponse(
        status="ok",
        feedback_id=feedback_id,
        message=msg,
    )
