from typing import List, Optional, Literal
from pydantic import BaseModel, Field


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
