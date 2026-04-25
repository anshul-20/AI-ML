from typing import List, Optional, Literal, Any, Dict
from pydantic import BaseModel, Field


# ── Existing (Feature 1) ────────────────────────────────────────────────────

class ReviewRequest(BaseModel):
    repo: str = Field(..., description="Repository name")
    pr_id: int = Field(..., description="Pull request ID")
    diff: str = Field(..., description="Git diff string")


class Issue(BaseModel):
    type: Literal["bug", "security", "performance", "style", "best_practice"]
    severity: Literal["low", "medium", "high", "critical"]
    file: str
    line: Optional[int] = None
    title: str
    description: str
    suggestion: str


class ReviewResponse(BaseModel):
    summary: str
    score: float = Field(..., ge=0, le=10)
    issues: List[Issue] = []
    strengths: List[str] = []


# ── Feature 2: Quality Gate ─────────────────────────────────────────────────

class GateRequest(BaseModel):
    ai_score: float = Field(..., ge=0, le=10)
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    test_coverage: float = Field(..., ge=0, le=100)
    lint_errors: int = Field(..., ge=0)


class GateResponse(BaseModel):
    status: Literal["PASS", "FAIL", "REVIEW"]
    reasons: List[str]
    confidence: float = Field(..., ge=0, le=1)


# ── Feature 3: Multi-Agent Review ───────────────────────────────────────────

class MultiAgentRequest(BaseModel):
    diff: str = Field(..., description="Git diff string")


class AgentResult(BaseModel):
    score: float = Field(..., ge=0, le=10)
    issues: List[Dict[str, Any]] = []
    summary: str = ""


class MultiAgentResponse(BaseModel):
    code_quality: AgentResult
    security: AgentResult
    performance: AgentResult
    final_score: float = Field(..., ge=0, le=10)


# ── Feature 4: Documentation Generator ──────────────────────────────────────

class DocsRequest(BaseModel):
    diff: str = Field(..., description="Git diff string")


class DocsResponse(BaseModel):
    summary: str
    changelog: List[str] = []
    api_changes: List[str] = []
    developer_notes: List[str] = []


# ── Feature 6: Feedback Loop ─────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    pr_id: int
    accepted: bool
    false_positive: bool = False
    comments: Optional[str] = None


class FeedbackResponse(BaseModel):
    status: str
    feedback_id: str
    message: str
