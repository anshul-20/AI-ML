"""
AI-Augmented CI/CD System — FastAPI Application
Features: Code Review, Quality Gate, Multi-Agent Review, Docs Generator, Feedback
"""

import logging
import time
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.logger import setup_logging, set_request_id, log_event
from app.schemas import (
    ReviewRequest, ReviewResponse,
    GateRequest, GateResponse,
    MultiAgentRequest, MultiAgentResponse,
    DocsRequest, DocsResponse,
    FeedbackRequest, FeedbackResponse,
)
from app.reviewer import perform_review
from app.gate import evaluate_gate
from app.multi_agent import run_multi_agent_review
from app.docs_generator import generate_docs
from app.feedback import handle_feedback, get_feedback_stats

setup_logging()
logger = logging.getLogger(__name__)

AI_REVIEW_SCERET = os.getenv("AI_REVIEW_SCERET")

app = FastAPI(
    title="AI-Augmented CI/CD System",
    description="End-to-end AI code review pipeline powered entirely by OpenAI GPT: review → gate → docs → feedback",
    version="2.0.0",
)
#this is a test comment to trigger the webhook and see if it works
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
#-----------------Middleware--------------------------------------
# @app.middleware("http")
# async def token_auth_middleware(request: Request, call_next):
#     # Skip auth for health check
#     if request.url.path == "/health":
#         return await call_next(request)
    
#     token = request.headers.get("X-API-Token")
#     expected = os.getenv("AI_REVIEW_SCERET")
    
#     if expected and token != expected:
#         return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
#     return await call_next(request)
@app.middleware("http")
async def token_auth_middleware(request: Request, call_next):
    # Always allow health checks (GitHub Actions checks this first)
    if request.url.path == "/health":
        return await call_next(request)

    # If token is configured on server, enforce it
    if AI_REVIEW_SCERET:
        incoming = request.headers.get("X-API-Token", "")
        if incoming != AI_REVIEW_SCERET:
            logger.warning("Unauthorized request | path=%s", request.url.path)
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

    return await call_next(request)


# ── Request correlation middleware ───────────────────────────────────────────

@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    set_request_id(rid)
    t0 = time.perf_counter()
    response = await call_next(request)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    log_event(logger, "http_request",
              method=request.method, path=request.url.path,
              status=response.status_code, latency_ms=latency_ms)
    response.headers["X-Request-ID"] = rid
    return response


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok", "version": "2.0.0"}


# ── GitHub Integrations ──────────────────────────────────────────────────────

async def post_github_pr_comment(repo_name: str, pr_number: int, comment_body: str):
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        logger.warning("No GITHUB_TOKEN set. Skipping PR comment.")
        return
        
    url = f"https://api.github.com/repos/{repo_name}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json={"body": comment_body})
        if resp.status_code != 201:
            logger.error(f"Failed to post comment: {resp.text}")

async def set_github_commit_status(repo_name: str, commit_sha: str, state: str, description: str):
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        logger.warning("No GITHUB_TOKEN set. Skipping commit status.")
        return
        
    url = f"https://api.github.com/repos/{repo_name}/statuses/{commit_sha}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "state": state,
        "description": description[:140],
        "context": "ai-code-review-agent"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 201:
            logger.error(f"Failed to set status: {resp.text}")


# ── Webhooks ─────────────────────────────────────────────────────────────────

# @app.post("/webhook/github", tags=["Webhooks"])
# async def github_webhook(request: Request, background_tasks: BackgroundTasks):
#     """Handle GitHub Pull Request webhooks."""
#     event = request.headers.get("x-github-event")
#     if event != "pull_request":
#         # Ignore other events or ping
#         return {"detail": f"Ignoring event: {event}"}
        
#     payload = await request.json()
#     action = payload.get("action")
#     if action not in ["opened", "synchronize", "reopened"]:
#         return {"detail": f"Ignoring PR action: {action}"}
        
#     repo_name = payload.get("repository", {}).get("full_name", "unknown/repo")
#     pr_number = payload.get("pull_request", {}).get("number", 0)
#     diff_url = payload.get("pull_request", {}).get("diff_url")
#     commit_sha = payload.get("pull_request", {}).get("head", {}).get("sha")
    
#     if not diff_url:
#         raise HTTPException(status_code=400, detail="No diff_url found in payload")
        
#     logger.info(f"GitHub Webhook received: repo={repo_name} pr={pr_number}")
    
#     async with httpx.AsyncClient() as client:
#         resp = await client.get(diff_url)
#         diff_text = resp.text
        
#     if not diff_text.strip():
#         logger.warning(f"Empty diff for PR {pr_number}")
#         return {"detail": "Empty diff"}

#     # Step 1: Code review
#     review = await perform_review(diff_text)
    
#     # Step 2: Multi-agent
#     multi = await run_multi_agent_review(diff_text)
    
#     # Step 3: Quality gate
#     gate_req = GateRequest(
#         ai_score=review.score,
#         issues=[i.model_dump() for i in review.issues],
#         test_coverage=80.0,
#         lint_errors=0,
#     )
#     gate = await evaluate_gate(gate_req)
    
#     # Step 4: Docs
#     docs = await generate_docs(DocsRequest(diff=diff_text))

#     logger.info(f"GitHub PR {pr_number} full pipeline completed. Score: {review.score}")
    
#     # Format Comment
#     comment_body = f"## 🤖 AI Code Review\n\n"
#     comment_body += f"**Score:** {review.score}/10.0\n"
#     comment_body += f"**Quality Gate:** {gate.status}\n\n"
#     comment_body += f"### 📊 Summary\n{review.summary}\n\n"
    
#     if review.issues:
#         comment_body += "### 🚨 Issues\n"
#         for issue in review.issues:
#             comment_body += f"- **{issue.title}** ({issue.severity}): {issue.description}\n"
            
#     if review.strengths:
#         comment_body += "### ✨ Strengths\n"
#         for strength in review.strengths:
#             comment_body += f"- {strength}\n"
            
#     comment_body += "\n---\n*Generated by AI-Augmented CI/CD System*"
    
#     # Post comment and status using background tasks
#     background_tasks.add_task(post_github_pr_comment, repo_name, pr_number, comment_body)
    
#     if commit_sha:
#         state = "success" if gate.status == "PASS" else "failure"
#         desc = "AI Code Review Passed" if state == "success" else f"AI Code Review Failed: Score {review.score}"
#         background_tasks.add_task(set_github_commit_status, repo_name, commit_sha, state, desc)
    
#     return {
#         "status": "success",
#         "repo": repo_name,
#         "pr_number": pr_number,
#         "review": review.model_dump(),
#         "multi_agent_review": multi.model_dump(),
#         "quality_gate": gate.model_dump(),
#         "documentation": docs.model_dump()
#     }


# @app.post("/webhook/gitlab", tags=["Webhooks"])
# async def gitlab_webhook(request: Request):
#     """Handle GitLab Merge Request webhooks."""
#     event = request.headers.get("x-gitlab-event")
#     if event != "Merge Request Hook":
#         return {"detail": f"Ignoring event: {event}"}
        
#     payload = await request.json()
#     action = payload.get("object_attributes", {}).get("action")
#     if action not in ["open", "update", "reopen"]:
#         return {"detail": f"Ignoring MR action: {action}"}
        
#     repo_name = payload.get("project", {}).get("path_with_namespace", "unknown/repo")
#     mr_iid = payload.get("object_attributes", {}).get("iid", 0)
    
#     web_url = payload.get("project", {}).get("web_url")
#     if not web_url:
#         raise HTTPException(status_code=400, detail="No web_url found in payload")
        
#     # GitLab diff URL: project_url/-/merge_requests/iid.diff
#     diff_url = f"{web_url}/-/merge_requests/{mr_iid}.diff"
    
#     logger.info(f"GitLab Webhook received: repo={repo_name} mr={mr_iid}")
    
#     async with httpx.AsyncClient() as client:
#         resp = await client.get(diff_url)
#         diff_text = resp.text
        
#     if not diff_text.strip():
#         logger.warning(f"Empty diff for MR {mr_iid}")
#         return {"detail": "Empty diff"}

#     # Step 1: Code review
#     review = await perform_review(diff_text)
    
#     # Step 2: Multi-agent
#     multi = await run_multi_agent_review(diff_text)
    
#     # Step 3: Quality gate
#     gate_req = GateRequest(
#         ai_score=review.score,
#         issues=[i.model_dump() for i in review.issues],
#         test_coverage=80.0,
#         lint_errors=0,
#     )
#     gate = await evaluate_gate(gate_req)
    
#     # Step 4: Docs
#     docs = await generate_docs(DocsRequest(diff=diff_text))

#     logger.info(f"GitLab MR {mr_iid} full pipeline completed. Score: {review.score}")
    
#     return {
#         "status": "success",
#         "repo": repo_name,
#         "mr_iid": mr_iid,
#         "review": review.model_dump(),
#         "multi_agent_review": multi.model_dump(),
#         "quality_gate": gate.model_dump(),
#         "documentation": docs.model_dump()
#     }



# ── Feature 1: Code Review ───────────────────────────────────────────────────

@app.post("/review", response_model=ReviewResponse, tags=["Feature 1: Code Review"])
async def review_pr(request: ReviewRequest):
    """Analyze a Git diff and return a structured AI code review."""
    logger.info("review | repo=%s pr_id=%s diff_len=%d",
                request.repo, request.pr_id, len(request.diff))

    if not request.diff.strip():
        raise HTTPException(status_code=400, detail="Diff cannot be empty.")

    result = await perform_review(request.diff)
    logger.info("review done | score=%.1f issues=%d", result.score, len(result.issues))
    return result


# ── Feature 2: Quality Gate ───────────────────────────────────────────────────

@app.post("/evaluate", response_model=GateResponse, tags=["Feature 2: Quality Gate"])
async def evaluate(request: GateRequest):
    """Evaluate PR against quality thresholds and return PASS/FAIL/REVIEW decision."""
    logger.info("evaluate | score=%.1f coverage=%.1f lint=%d issues=%d",
                request.ai_score, request.test_coverage,
                request.lint_errors, len(request.issues))

    result = await evaluate_gate(request)
    logger.info("gate result | status=%s confidence=%.2f", result.status, result.confidence)
    return result


# ── Feature 3: Multi-Agent Review ────────────────────────────────────────────

@app.post("/multi-review", response_model=MultiAgentResponse,
          tags=["Feature 3: Multi-Agent Review"])
async def multi_agent_review(request: MultiAgentRequest):
    """Run three specialized agents (quality, security, performance) concurrently."""
    if not request.diff.strip():
        raise HTTPException(status_code=400, detail="Diff cannot be empty.")

    logger.info("multi-review | diff_len=%d", len(request.diff))
    result = await run_multi_agent_review(request.diff)
    logger.info("multi-review done | final_score=%.2f", result.final_score)
    return result


# ── Feature 4: Documentation Generator ───────────────────────────────────────

@app.post("/generate-docs", response_model=DocsResponse,
          tags=["Feature 4: Docs Generator"])
async def generate_documentation(request: DocsRequest):
    """Generate changelog, API changes, and developer notes from a Git diff."""
    if not request.diff.strip():
        raise HTTPException(status_code=400, detail="Diff cannot be empty.")

    logger.info("generate-docs | diff_len=%d", len(request.diff))
    result = await generate_docs(request)
    logger.info("docs done | changelog=%d api=%d notes=%d",
                len(result.changelog), len(result.api_changes), len(result.developer_notes))
    return result


# ── Feature 6: Feedback Loop ──────────────────────────────────────────────────

@app.post("/feedback", response_model=FeedbackResponse, tags=["Feature 6: Feedback"])
async def submit_feedback(request: FeedbackRequest):
    """Record developer feedback on AI review quality."""
    logger.info("feedback | pr_id=%d accepted=%s fp=%s",
                request.pr_id, request.accepted, request.false_positive)
    return await handle_feedback(request)


@app.get("/feedback/stats", tags=["Feature 6: Feedback"])
def feedback_stats():
    """Return aggregate statistics over all stored feedback."""
    return get_feedback_stats()


# ── Pipeline endpoint (integrate all features) ───────────────────────────────

@app.post("/pipeline", tags=["Pipeline"])
async def full_pipeline(request: ReviewRequest):
    """
    Run the full AI-powered CI/CD pipeline (all OpenAI):
    /review → /multi-review → /evaluate → /generate-docs
    Returns all outputs in a single response.
    """
    if not request.diff.strip():
        raise HTTPException(status_code=400, detail="Diff cannot be empty.")

    logger.info("pipeline start | repo=%s pr_id=%s", request.repo, request.pr_id)

    # Step 1: Code review
    review = await perform_review(request.diff)

    # Step 2: Multi-agent (concurrent with gate prep)
    multi = await run_multi_agent_review(request.diff)

    # Step 3: Quality gate (uses review output)
    gate_req = GateRequest(
        ai_score=review.score,
        issues=[i.model_dump() for i in review.issues],
        test_coverage=80.0,   # Default — caller should provide real value
        lint_errors=0,
    )
    gate = await evaluate_gate(gate_req)

    # Step 4: Docs
    docs = await generate_docs(DocsRequest(diff=request.diff))

    log_event(logger, "pipeline_done",
              repo=request.repo, pr_id=request.pr_id,
              score=review.score, gate=gate.status)

    return {
        "repo": request.repo,
        "pr_id": request.pr_id,
        "review": review.model_dump(),
        "multi_agent_review": multi.model_dump(),
        "quality_gate": gate.model_dump(),
        "documentation": docs.model_dump(),
    }
